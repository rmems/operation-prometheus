#!/usr/bin/env python3
"""Read-only GitHub PR collector for Operation Prometheus.

Collects public PR trajectory signals into local JSON under datasets/raw/
(or $PROMETHEUS_DATA_ROOT/raw/ when set). Performs no write operations against GitHub.

Examples:
    export GITHUB_TOKEN="$(gh auth token)"
    python scripts/collect_pr_records.py \\
      --repo rmems/corinth-canal --pr 89 \\
      --out-dir datasets/raw/corinth-canal

    export PROMETHEUS_DATA_ROOT=~/rmems/prometheus-data
    python scripts/collect_pr_records.py \\
      --repo Limen-Neural/neuromod --pr 5,8,9 --skip-existing
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

from lib.github_client import GitHubClient, GitHubError, parse_repo  # noqa: E402
from lib.paths import DATA_ROOT_ENV, resolve_raw_out_dir  # noqa: E402
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
        help=(
            "Output directory. Default: $"
            + DATA_ROOT_ENV
            + "/raw/<owner_repo> if set, else datasets/raw/<owner_repo>"
        ),
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
        "--skip-existing",
        action="store_true",
        help="Skip PRs that already have pr-N.json in out-dir (resume-friendly)",
    )
    p.add_argument(
        "--allow-cross-repo",
        action="append",
        default=[],
        metavar="OWNER/REPO",
        help=(
            "Allow fetching linked issues from this owner/repo (repeatable). "
            "Cross-repo Closes/Fixes references are skipped unless allowlisted."
        ),
    )
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

    out_dir = resolve_raw_out_dir(full, args.out_dir)

    if args.dry_run:
        print(f"Would collect {full} PRs {prs} → {out_dir}")
        if args.skip_existing:
            print("(with --skip-existing)")
        return 0

    client = GitHubClient.from_env(args.token_env)
    failures = 0
    collected = 0
    skipped = 0
    for pr in prs:
        target = out_dir / f"pr-{pr}.json"
        if args.skip_existing and target.exists():
            logger.info("Skipping %s#%s (exists: %s)", full, pr, target)
            skipped += 1
            continue
        logger.info("Collecting %s#%s …", full, pr)
        try:
            record = collect_pr(
                client,
                full,
                pr,
                include_checks=not args.skip_checks,
                include_diff=not args.skip_diff,
                cross_repo_allowlist=tuple(args.allow_cross_repo or ()),
            )
            path = write_raw_record(
                record,
                out_dir,
                max_inline_diff_bytes=args.max_inline_diff_bytes,
            )
            logger.info("Wrote %s", path)
            collected += 1
        except (GitHubError, OSError, ValueError) as exc:
            failures += 1
            logger.error("Failed %s#%s: %s", full, pr, exc)
            if not args.continue_on_error:
                return 1

    if failures:
        logger.error(
            "%s PR(s) failed (%s collected, %s skipped)",
            failures,
            collected,
            skipped,
        )
        return 1
    logger.info(
        "Done: %s collected, %s skipped → %s",
        collected,
        skipped,
        out_dir,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
