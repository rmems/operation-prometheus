#!/usr/bin/env python3
"""Migrate pr_trajectory_v0 JSONL into trajectory-v1 envelopes.

Lossless: preserves raw source values, records source bytes/digest and the
migration tool version, and refuses or quarantines anything that would require
invented evidence (timestamps, commit OIDs, unknown events, already-v1 input).

The source file is never overwritten. Re-running the same command is
byte-identical for both the admitted JSONL and the refusal report.

Examples:
    python scripts/migrate_v0_to_v1.py \\
      --out /tmp/corinth-canal-v1.jsonl \\
      --report /tmp/corinth-canal-v1.report.json \\
      datasets/jsonl/corinth-canal-v0.jsonl

    python scripts/validate_jsonl.py --strict-policy /tmp/corinth-canal-v1.jsonl
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.migrate_v0_to_v1 import (  # noqa: E402
    MIGRATION_TOOL_VERSION,
    migrate_files,
    resolved_same,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("migrate_v0_to_v1")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="Source JSONL files (never overwritten)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Admitted trajectory-v1 JSONL path (must not be a source file)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Refusal/quarantine report JSON (default: <out>.migration-report.json)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    inputs: list[Path] = args.inputs
    out_path: Path = args.out
    report_path: Path = args.report if args.report is not None else Path(
        str(out_path) + ".migration-report.json"
    )

    for source in inputs:
        if not source.is_file():
            logger.error("source not found: %s", source)
            return 2
        if resolved_same(source, out_path):
            logger.error("refusing to overwrite source file: %s", source)
            return 2
        if resolved_same(source, report_path):
            logger.error("refusing to overwrite source file with the report: %s", source)
            return 2

    try:
        report = migrate_files(inputs, out_path=out_path, report_path=report_path)
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 2

    logger.info(
        "migrated with %s: admitted=%s refused=%s → %s (report %s)",
        MIGRATION_TOOL_VERSION,
        report["admitted_count"],
        report["refused_count"],
        out_path,
        report_path,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
