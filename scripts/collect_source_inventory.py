#!/usr/bin/env python3
"""Collect a frozen, read-only GitHub repository and PR inventory.

The output is raw inventory metadata and belongs outside the Git repository,
normally under ``$PROMETHEUS_DATA_ROOT/inventory``.  Building the eligibility
ledger is a separate offline step.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.github_client import GitHubClient, GitHubError  # noqa: E402
from lib.source_inventory import collect_source_inventory  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("collect_source_inventory")

DEFAULT_OWNERS = ("user:rmems", "org:Limen-Neural")
DATA_ROOT_ENV = "PROMETHEUS_DATA_ROOT"


def _default_output() -> Path | None:
    value = os.environ.get(DATA_ROOT_ENV, "").strip()
    if not value:
        return None
    return Path(value).expanduser().resolve() / "inventory" / "github-source-snapshot.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--owner",
        action="append",
        dest="owners",
        help="Owner as user:LOGIN or org:LOGIN (repeatable; defaults to rmems + Limen-Neural)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Snapshot JSON path; defaults under $PROMETHEUS_DATA_ROOT/inventory",
    )
    parser.add_argument(
        "--token-env",
        default="GITHUB_TOKEN",
        help="Environment variable containing the GitHub token (default GITHUB_TOKEN)",
    )
    parser.add_argument(
        "--collected-at",
        help="Fixed RFC3339 query time for fixture generation; omit for current UTC time",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the collection target without calling GitHub",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    owners = list(args.owners or DEFAULT_OWNERS)
    out_path = args.out or _default_output()
    if out_path is None:
        logger.error("Pass --out or set %s; raw inventory must not default into the repo", DATA_ROOT_ENV)
        return 2
    out_path = out_path.expanduser().resolve()

    if args.dry_run:
        print(f"Would collect {', '.join(owners)} -> {out_path}")
        return 0

    client = GitHubClient.from_env(args.token_env)
    try:
        snapshot = collect_source_inventory(
            client,
            owners,
            collected_at=args.collected_at,
        )
    except (GitHubError, OSError, ValueError, json.JSONDecodeError) as exc:
        logger.error("Inventory collection failed: %s", exc)
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(out_path)
    logger.info(
        "Wrote complete snapshot: %s repositories, %s PRs, %s pages -> %s",
        snapshot["collection"]["repository_count"],
        snapshot["collection"]["pull_request_count"],
        snapshot["collection"]["page_count"],
        out_path,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
