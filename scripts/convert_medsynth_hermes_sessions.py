#!/usr/bin/env python3
"""Convert medsynth Hermes teacher sessions into first-party artifacts.

Usage:
    python scripts/convert_medsynth_hermes_sessions.py \
      --batch-manifest <medsynth-batch-manifest-json> \
      --session-root <fulfillment-directory> \
      --output <canonical-jsonl> \
      --report <conversion-report-json>

The converter is offline and local-file only. It scans `<session-root>` for
`*.session.json`, binds each file to the manifest rights envelope by exact
filename and SHA-256, and records every refusal in the report.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.medsynth_hermes_common import CONVERTER_VERSION  # noqa: E402
from lib.medsynth_hermes_convert import convert_files  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("convert_medsynth_hermes_sessions")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--batch-manifest",
        type=Path,
        required=True,
        help="medsynth batch manifest JSON",
    )
    parser.add_argument(
        "--session-root",
        type=Path,
        required=True,
        help="directory containing <key>.session.json files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="canonical first-party trajectory artifact JSONL",
    )
    parser.add_argument(
        "--report",
        type=Path,
        required=True,
        help="accepted/refused conversion report JSON",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = convert_files(
            batch_manifest_path=args.batch_manifest,
            session_root=args.session_root,
            output_path=args.output,
            report_path=args.report,
        )
    except (FileNotFoundError, OSError, ValueError, RuntimeError) as exc:
        logger.error("%s", exc)
        return 2
    logger.info(
        "converted with %s: accepted=%s refused=%s â†’ %s (report %s)",
        CONVERTER_VERSION,
        report["accepted_count"],
        report["refused_count"],
        args.output,
        args.report,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
