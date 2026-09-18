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
from lib.normalize import load_card  # noqa: E402
from lib.paths import resolve_artifact_store_dir  # noqa: E402
from lib.trajectory_emit import EmitJob, emit_all, write_jsonl  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("build_trajectory_jsonl")

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_V0_PATH = ROOT / "schemas" / "pr_trajectory.schema.json"
SCHEMA_V1_PATH = ROOT / "schemas" / "trajectory_v1.schema.json"
V1_ALIASES = {"v1", "1", "1.0"}
V0_ALIASES = {"v0", "0", "0.1"}


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


def _safe_card_name(card: dict[str, Any]) -> str:
    card_name = card.get("name") if isinstance(card, dict) else None
    if card_name is None:
        return ""
    return str(card_name).strip()


def _is_safe_dataset_id(name: str) -> bool:
    if not name:
        return False
    if ".." in name:
        return False
    return bool(_SAFE_CARD_NAME.fullmatch(name))


def _derived_out_path(card: dict[str, Any]) -> Path | None:
    name = _safe_card_name(card)
    if _is_safe_dataset_id(name):
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
    store = None
    if emit_v1:
        store = ContentAddressedStore(resolve_artifact_store_dir(args.artifact_store))
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
    lines, errors = emit_all(job)
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
    write_jsonl(job.out_path, lines)
    return 0


if __name__ == "__main__":
    sys.exit(main())
