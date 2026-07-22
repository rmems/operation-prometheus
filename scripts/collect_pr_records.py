#!/usr/bin/env python3
"""Read-only GitHub PR collector for Operation Prometheus.

Collects public PR trajectory signals into local JSON under datasets/raw/.
Performs no write operations against GitHub.

Examples:
    export GITHUB_TOKEN=...
    python scripts/collect_pr_records.py \\
      --repo rmems/corinth-canal --pr 89 \\
      --out-dir datasets/raw/corinth-canal

    python scripts/collect_pr_records.py \\
      --repo rmems/corinth-canal --pr 82,89,91,94,95,96 \\
      --out-dir datasets/raw/corinth-canal
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Allow running as `python scripts/collect_pr_records.py`
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.github_client import GitHubClient, GitHubError, parse_repo, repo_slug  # noqa: E402
from lib.raw_record import collect_pr, write_raw_record  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("collect_pr_records")


def parse_pr_list(values: list[str]) -> list[int]:
    prs: list[int] = []
    for value in values:
        for part in value.split(","):
            part = part.strip()
            if not part:
                continue
            prs.append(int(part))
    if not prs:
        raise argparse.ArgumentTypeError("at least one PR number required")
    return prs


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", required=True, help="GitHub repository owner/name")
    p.add_argument(
        "--pr",
        action="append",
        required=True,
        help="PR number or comma-separated list (repeatable)",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory (default: datasets/raw/<repo-slug>)",
    )
    p.add_argument(
        "--token-env",
        default="GITHUB_TOKEN",
        help="Environment variable holding the GitHub token (default: GITHUB_TOKEN)",
    )
    p.add_argument(
        "--max-inline-diff-bytes",
        type=int,
        default=256 * 1024,
        help="Sidecar threshold for unified diffs (default: 256KiB)",
    )
    p.add_argument("--skip-checks", action="store_true", help="Skip check-runs API")
    p.add_argument("--skip-diff", action="store_true", help="Skip full unified diff fetch")
    p.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue batch if one PR fails",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned work without calling GitHub",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        owner, name = parse_repo(args.repo)
        full = f"{owner}/{name}"
        prs = parse_pr_list(args.pr)
    except (ValueError, argparse.ArgumentTypeError) as exc:
        logger.error("%s", exc)
        return 2

    out_dir = args.out_dir
    if out_dir is None:
        root = Path(__file__).resolve().parent.parent
        out_dir = root / "datasets" / "raw" / repo_slug(full)

    if args.dry_run:
        print(f"Would collect {full} PRs {prs} → {out_dir}")
        return 0

    client = GitHubClient.from_env(args.token_env)
    failures = 0
    for pr in prs:
        logger.info("Collecting %s#%s …", full, pr)
        try:
            record = collect_pr(
                client,
                full,
                pr,
                include_checks=not args.skip_checks,
                include_diff=not args.skip_diff,
            )
            path = write_raw_record(
                record,
                out_dir,
                max_inline_diff_bytes=args.max_inline_diff_bytes,
            )
            logger.info("Wrote %s", path)
        except (GitHubError, OSError, ValueError) as exc:
            failures += 1
            logger.error("Failed %s#%s: %s", full, pr, exc)
            if not args.continue_on_error:
                return 1

    if failures:
        logger.error("%s PR(s) failed", failures)
        return 1
    logger.info("Collected %s PR(s) into %s", len(prs), out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
