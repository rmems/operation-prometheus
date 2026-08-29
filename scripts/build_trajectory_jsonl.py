#!/usr/bin/env python3
"""Normalize raw PR records into schema-compliant trajectory JSONL.

Examples:
    python scripts/build_trajectory_jsonl.py \\
      --raw-dir datasets/raw/corinth-canal \\
      --card datasets/cards/corinth-canal-v0.json \\
      --out datasets/jsonl/corinth-canal-v0.jsonl

    python scripts/validate_jsonl.py datasets/jsonl/corinth-canal-v0.jsonl
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

# Safe dataset id for deriving datasets/jsonl/<name>.jsonl (no path separators).
_SAFE_CARD_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.normalize import load_card, load_raw_record, normalize_record  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("build_trajectory_jsonl")

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schemas" / "pr_trajectory.schema.json"


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


def _validate(record: dict, validator) -> list[str]:
    if validator is None:
        return ["jsonschema not installed"]
    return [e.message for e in sorted(validator.iter_errors(record), key=lambda e: list(e.path))]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    raw_dir: Path = args.raw_dir
    if not raw_dir.is_dir():
        logger.error("raw-dir not found: %s", raw_dir)
        return 2

    # Load schema once; missing jsonschema is a hard startup failure (avoid silent skips).
    try:
        import jsonschema
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        validator = jsonschema.Draft7Validator(schema)
    except ImportError:
        logger.error("jsonschema is required. Install with: pip install jsonschema")
        return 2

    try:
        card = load_card(args.card)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 2
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to load card %s: %s", args.card, exc)
        return 2
    out_path: Path | None = args.out
    if out_path is None:
        # Derive from card name when possible; never silently default to corinth-canal.
        card_name = card.get("name") if isinstance(card, dict) else None
        name = str(card_name).strip() if card_name is not None else ""
        if name and _SAFE_CARD_NAME.fullmatch(name) and ".." not in name:
            out_path = ROOT / "datasets" / "jsonl" / f"{name}.jsonl"
        else:
            if name:
                logger.error(
                    "Card name %r is not a safe dataset id (must match %s). "
                    "Pass --out explicitly.",
                    name,
                    _SAFE_CARD_NAME.pattern,
                )
            else:
                logger.error(
                    "Refusing to write without --out (or a --card with a safe name field). "
                    "This prevents overwriting curated JSONL by accident."
                )
            return 2
    try:
        pr_filter = _parse_prs(args.pr)
    except ValueError as exc:
        logger.error("Invalid --pr value: %s", exc)
        return 2
    paths = sorted(raw_dir.glob("pr-*.json"))
    if not paths:
        logger.error("No pr-*.json files in %s", raw_dir)
        return 1

    lines: list[str] = []
    errors = 0
    for path in paths:
        try:
            raw = load_raw_record(path)
            pr = int((raw.get("source") or {}).get("pr_number") or 0)
            if pr_filter is not None and pr not in pr_filter:
                continue
            source_license = str(
                (raw.get("source") or {}).get("license")
                or card.get("source_license")
                or card.get("license")
                or "NOASSERTION"
            ).strip()
            traj = normalize_record(
                raw,
                card,
                raw_path=path,
                max_patch_bytes=args.max_patch_bytes,
                source_license=source_license or "NOASSERTION",
            )
            schema_errors = _validate(traj, validator)
            if schema_errors:
                errors += 1
                logger.error("%s schema errors:", path.name)
                for err in schema_errors:
                    logger.error("  - %s", err)
                if args.strict:
                    return 1
                continue
            lines.append(json.dumps(traj, ensure_ascii=False, separators=(",", ":")))
            logger.info(
                "OK %s (quality=%.2f training_use=%s)",
                path.name,
                traj.get("quality_score", 0),
                traj.get("training_use"),
            )
        except Exception as exc:
            errors += 1
            logger.error("Failed %s: %s", path.name, exc)
            if args.strict:
                return 1

    if not lines:
        logger.error("No trajectories produced")
        return 1

    # Never overwrite a curated JSONL with a partial batch after errors.
    if errors:
        logger.error(
            "Aborting write: %s record error(s); leaving %s unchanged",
            errors,
            out_path,
        )
        return 1

    assert out_path is not None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp_path.replace(out_path)
    logger.info("Wrote %s trajectories → %s", len(lines), out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
