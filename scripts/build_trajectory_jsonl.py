#!/usr/bin/env python3
"""Normalize raw PR records into schema-compliant trajectory JSONL.

Examples:
    python scripts/build_trajectory_jsonl.py \\
      --raw-dir datasets/raw/corinth-canal \\
      --card datasets/cards/corinth-canal-v0.json \\
      --out datasets/jsonl/corinth-canal-v0.jsonl

    python scripts/build_trajectory_jsonl.py \\
      --raw-dir datasets/raw/corinth-canal \\
      --card datasets/cards/corinth-canal-v0.json \\
      --schema-version v1 \\
      --out datasets/jsonl/corinth-canal-v1.jsonl

    python scripts/validate_jsonl.py datasets/jsonl/corinth-canal-v0.jsonl
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import jsonschema
except ImportError:  # pragma: no cover - exercised by missing-dep startup path
    jsonschema = None  # type: ignore[assignment]

# Safe dataset id for deriving datasets/jsonl/<name>.jsonl (no path separators).
_SAFE_CARD_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.cas import ContentAddressedStore  # noqa: E402
from lib.normalize import (  # noqa: E402
    load_card,
    load_raw_record,
    normalize_record,
    resolve_source_license,
)
from lib.normalize_v1 import V1NormalizeOptions, normalize_record_v1  # noqa: E402
from lib.paths import resolve_artifact_store_dir  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("build_trajectory_jsonl")

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_V0_PATH = ROOT / "schemas" / "pr_trajectory.schema.json"
SCHEMA_V1_PATH = ROOT / "schemas" / "trajectory_v1.schema.json"
V1_ALIASES = {"v1", "1", "1.0"}
V0_ALIASES = {"v0", "0", "0.1"}


@dataclass
class EmitJob:
    raw_dir: Path
    card: dict[str, Any]
    out_path: Path
    emit_v1: bool
    store: ContentAddressedStore | None
    max_patch_bytes: int
    pr_filter: set[int] | None
    validator: Any
    strict: bool


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--raw-dir",
        type=Path,
        required=True,
        help="Directory containing pr-*.json raw records",
    )
    p.add_argument(
        "--card",
        type=Path,
        default=None,
        help="Dataset card JSON for language/domain/bucket overlay",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output JSONL path (required unless --card provides a name, "
        "e.g. datasets/cards/foo-v0.json → datasets/jsonl/foo-v0.jsonl)",
    )
    p.add_argument(
        "--pr",
        action="append",
        default=None,
        help="Optional PR filter (repeatable or comma-separated)",
    )
    p.add_argument(
        "--max-patch-bytes",
        type=int,
        default=96 * 1024,
        help="Max bytes for trajectory patch field (default 96KiB)",
    )
    p.add_argument(
        "--schema-version",
        default="v0",
        help="Trajectory schema to emit: v0 (default) or v1",
    )
    p.add_argument(
        "--artifact-store",
        type=Path,
        default=None,
        help="Content-addressed store used to attach v1 remote artifact URIs",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Fail if any record fails schema validation",
    )
    return p


def _parse_prs(values: list[str] | None) -> set[int] | None:
    if not values:
        return None
    out: set[int] = set()
    for v in values:
        for part in v.split(","):
            part = part.strip()
            if part:
                out.add(int(part))
    return out


def _validate(record: dict, validator: Any) -> list[str]:
    if validator is None:
        return ["jsonschema not installed"]
    return [e.message for e in sorted(validator.iter_errors(record), key=lambda e: list(e.path))]


def _schema_choice(version: str) -> tuple[bool, Path] | None:
    schema_version = str(version or "v0").strip().lower()
    if schema_version in V1_ALIASES:
        return True, SCHEMA_V1_PATH
    if schema_version in V0_ALIASES:
        return False, SCHEMA_V0_PATH
    return None


def _load_validator(schema_path: Path) -> Any | None:
    if jsonschema is None:
        logger.error("jsonschema is required. Install with: pip install jsonschema")
        return None
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return jsonschema.Draft7Validator(schema)


def _derived_out_path(card: dict[str, Any]) -> Path | None:
    card_name = card.get("name") if isinstance(card, dict) else None
    name = str(card_name).strip() if card_name is not None else ""
    if name and _SAFE_CARD_NAME.fullmatch(name) and ".." not in name:
        return ROOT / "datasets" / "jsonl" / f"{name}.jsonl"
    if name:
        logger.error(
            "Card name %r is not a safe dataset id (must match %s). "
            "Pass --out explicitly.",
            name,
            _SAFE_CARD_NAME.pattern,
        )
        return None
    logger.error(
        "Refusing to write without --out (or a --card with a safe name field). "
        "This prevents overwriting curated JSONL by accident."
    )
    return None


def _load_card_or_fail(path: Path | None) -> dict[str, Any] | None:
    try:
        return load_card(path)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return None
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to load card %s: %s", path, exc)
        return None


def _normalize_one(raw: dict[str, Any], path: Path, job: EmitJob) -> dict[str, Any]:
    source_license = resolve_source_license(raw.get("source") or {}, job.card)
    if job.emit_v1:
        return normalize_record_v1(
            raw,
            job.card,
            V1NormalizeOptions(
                artifact_store=job.store,
                max_patch_bytes=job.max_patch_bytes,
                source_license=source_license,
            ),
        )
    return normalize_record(
        raw,
        job.card,
        raw_path=path,
        max_patch_bytes=job.max_patch_bytes,
        source_license=source_license,
    )


def _dump_trajectory(traj: dict[str, Any], emit_v1: bool) -> str:
    dump_kwargs: dict = {"ensure_ascii": False, "separators": (",", ":")}
    if emit_v1:
        dump_kwargs["sort_keys"] = True
    return json.dumps(traj, **dump_kwargs)


def _log_ok(path_name: str, traj: dict[str, Any], emit_v1: bool) -> None:
    if emit_v1:
        logger.info(
            "OK %s (v1 disposition=%s events=%s)",
            path_name,
            traj.get("terminal_disposition"),
            len(traj.get("events") or []),
        )
        return
    logger.info(
        "OK %s (quality=%.2f training_use=%s)",
        path_name,
        traj.get("quality_score", 0),
        traj.get("training_use"),
    )


def _emit_one(path: Path, job: EmitJob) -> str | None:
    raw = load_raw_record(path)
    pr = int((raw.get("source") or {}).get("pr_number") or 0)
    if job.pr_filter is not None and pr not in job.pr_filter:
        return None
    traj = _normalize_one(raw, path, job)
    schema_errors = _validate(traj, job.validator)
    if schema_errors:
        logger.error("%s schema errors:", path.name)
        for err in schema_errors:
            logger.error("  - %s", err)
        raise ValueError("schema validation failed")
    _log_ok(path.name, traj, job.emit_v1)
    return _dump_trajectory(traj, job.emit_v1)


def _emit_all(job: EmitJob) -> tuple[list[str], int]:
    paths = sorted(job.raw_dir.glob("pr-*.json"))
    if not paths:
        logger.error("No pr-*.json files in %s", job.raw_dir)
        return [], 1
    lines: list[str] = []
    errors = 0
    for path in paths:
        try:
            line = _emit_one(path, job)
        except Exception as exc:
            errors += 1
            if not isinstance(exc, ValueError) or str(exc) != "schema validation failed":
                logger.error("Failed %s: %s", path.name, exc)
            if job.strict:
                return [], 1
            continue
        if line is not None:
            lines.append(line)
    return lines, errors


def _write_jsonl(out_path: Path, lines: list[str]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp_path.replace(out_path)
    logger.info("Wrote %s trajectories → %s", len(lines), out_path)


def _build_job(args: argparse.Namespace) -> EmitJob | None:
    raw_dir: Path = args.raw_dir
    if not raw_dir.is_dir():
        logger.error("raw-dir not found: %s", raw_dir)
        return None
    choice = _schema_choice(args.schema_version)
    if choice is None:
        logger.error("Unknown --schema-version %s (expected v0 or v1)", args.schema_version)
        return None
    emit_v1, schema_path = choice
    validator = _load_validator(schema_path)
    if validator is None:
        return None
    card = _load_card_or_fail(args.card)
    if card is None:
        return None
    out_path: Path | None = args.out or _derived_out_path(card)
    if out_path is None:
        return None
    try:
        pr_filter = _parse_prs(args.pr)
    except ValueError as exc:
        logger.error("Invalid --pr value: %s", exc)
        return None
    store = ContentAddressedStore(resolve_artifact_store_dir(args.artifact_store)) if emit_v1 else None
    return EmitJob(
        raw_dir=raw_dir,
        card=card,
        out_path=out_path,
        emit_v1=emit_v1,
        store=store,
        max_patch_bytes=args.max_patch_bytes,
        pr_filter=pr_filter,
        validator=validator,
        strict=args.strict,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    job = _build_job(args)
    if job is None:
        return 2
    lines, errors = _emit_all(job)
    if errors and not lines:
        return 1
    if not lines:
        logger.error("No trajectories produced")
        return 1
    if errors:
        logger.error(
            "Aborting write: %s record error(s); leaving %s unchanged",
            errors,
            job.out_path,
        )
        return 1
    _write_jsonl(job.out_path, lines)
    return 0


if __name__ == "__main__":
    sys.exit(main())
