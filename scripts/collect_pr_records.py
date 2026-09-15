#!/usr/bin/env python3
"""Read-only GitHub PR collector for Operation Prometheus.

Collects public PR trajectory signals into local JSON under datasets/raw/
(or $PROMETHEUS_DATA_ROOT/raw/ when set). Performs no write operations against GitHub.

Per-PR (v0-compatible):

    export GITHUB_TOKEN="$(gh auth token)"
    python scripts/collect_pr_records.py \\
      --repo rmems/corinth-canal --pr 89 \\
      --out-dir datasets/raw/corinth-canal

Inventory-driven batch with durable resume and content-addressed snapshots:

    python scripts/collect_pr_records.py \\
      --inventory datasets/inventory/v0.7/candidates.jsonl \\
      --artifact-store "$PROMETHEUS_DATA_ROOT/artifacts" \\
      --resume-state "$PROMETHEUS_DATA_ROOT/collector-state.json" \\
      --snapshots
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
from pathlib import Path

# Allow running as `python scripts/collect_pr_records.py`
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.cas import ContentAddressedStore  # noqa: E402
from lib.github_client import GitHubClient, GitHubError, parse_repo, repo_slug  # noqa: E402
from lib.inventory_targets import DEFAULT_STATES, load_inventory_targets  # noqa: E402
from lib.paths import (  # noqa: E402
    DATA_ROOT_ENV,
    data_root_from_env,
    repo_root,
    resolve_artifact_store_dir,
    resolve_raw_out_dir,
    resolve_resume_state_path,
)
from lib.raw_record import collect_pr, write_raw_record  # noqa: E402
from lib.resume_state import ResumeState  # noqa: E402

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


def _parse_states(value: str | None) -> tuple[str, ...]:
    if not value:
        return DEFAULT_STATES
    parts = tuple(p.strip() for p in value.split(",") if p.strip())
    return parts or DEFAULT_STATES


def _parse_owners(values: list[str] | None) -> tuple[str, ...]:
    owners: list[str] = []
    for value in values or []:
        for part in value.split(","):
            part = part.strip()
            if part:
                owners.append(part)
    return tuple(owners)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", help="GitHub repository owner/name (per-PR mode)")
    p.add_argument(
        "--pr",
        action="append",
        help="PR number or comma-separated list (repeatable; per-PR mode)",
    )
    p.add_argument(
        "--inventory",
        type=Path,
        help="Eligibility candidates JSONL or ledger directory (inventory mode)",
    )
    p.add_argument(
        "--states",
        default=",".join(DEFAULT_STATES),
        help="Comma-separated ledger states to collect (inventory mode)",
    )
    p.add_argument(
        "--owner",
        action="append",
        dest="owners",
        help="Restrict inventory collection to this owner login (repeatable)",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of inventory items to collect",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help=(
            "Output directory. Per-PR default: $"
            + DATA_ROOT_ENV
            + "/raw/<owner_repo> if set, else datasets/raw/<owner_repo>. "
            "Inventory mode: parent of per-repo slug directories."
        ),
    )
    p.add_argument(
        "--artifact-store",
        type=Path,
        default=None,
        help="Content-addressed artifact store root (default: $PROMETHEUS_DATA_ROOT/artifacts)",
    )
    p.add_argument(
        "--resume-state",
        type=Path,
        default=None,
        help="Durable resume-state JSON (inventory mode)",
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
    p.add_argument("--skip-timeline", action="store_true", help="Skip issue timeline events")
    p.add_argument(
        "--snapshots",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Fetch git commit/blob objects into the artifact store "
            "(default: on for --inventory, off for --repo/--pr)"
        ),
    )
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


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _raw_parent_for_inventory(out_dir: Path | None) -> Path:
    if out_dir is not None:
        return Path(out_dir)
    root = data_root_from_env()
    if root is not None:
        return root / "raw"
    return repo_root() / "datasets" / "raw"


def _collect_one(
    client: GitHubClient,
    repo: str,
    pr: int,
    out_dir: Path,
    args: argparse.Namespace,
    store: ContentAddressedStore | None,
    *,
    include_snapshots: bool,
) -> tuple[Path, dict]:
    record = collect_pr(
        client,
        repo,
        pr,
        include_checks=not args.skip_checks,
        include_diff=not args.skip_diff,
        include_timeline=not args.skip_timeline,
        include_snapshots=include_snapshots,
        artifact_store=store,
        cross_repo_allowlist=tuple(args.allow_cross_repo or ()),
    )
    path = write_raw_record(
        record,
        out_dir,
        max_inline_diff_bytes=args.max_inline_diff_bytes,
        artifact_store=store,
    )
    return path, record


def _run_per_pr(args: argparse.Namespace) -> int:
    try:
        owner, name = parse_repo(args.repo)
        full = f"{owner}/{name}"
        prs = parse_pr_list(args.pr)
    except (ValueError, argparse.ArgumentTypeError) as exc:
        logger.error("%s", exc)
        return 2

    out_dir = resolve_raw_out_dir(full, args.out_dir)
    include_snapshots = bool(args.snapshots)
    store = None
    if include_snapshots or args.artifact_store:
        store = ContentAddressedStore(resolve_artifact_store_dir(args.artifact_store))

    if args.dry_run:
        print(f"Would collect {full} PRs {prs} → {out_dir}")
        if args.skip_existing:
            print("(with --skip-existing)")
        if include_snapshots:
            print("(with --snapshots)")
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
            path, _record = _collect_one(
                client, full, pr, out_dir, args, store, include_snapshots=include_snapshots
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


def _run_inventory(args: argparse.Namespace) -> int:
    try:
        states = _parse_states(args.states)
        owners = _parse_owners(args.owners)
        items, inventory_sha = load_inventory_targets(
            args.inventory,
            states=states,
            owners=owners or None,
            limit=args.limit,
        )
    except (OSError, ValueError) as exc:
        logger.error("%s", exc)
        return 2

    raw_parent = _raw_parent_for_inventory(args.out_dir)
    store_dir = resolve_artifact_store_dir(args.artifact_store)
    store = ContentAddressedStore(store_dir)
    resume_path = resolve_resume_state_path(args.resume_state)
    include_snapshots = True if args.snapshots is None else bool(args.snapshots)

    if args.dry_run:
        print(f"Would collect {len(items)} inventory items → {raw_parent}")
        print(f"inventory_sha256={inventory_sha}")
        print(f"resume_state={resume_path}")
        print(f"artifact_store={store_dir}")
        owners_seen = sorted({it["owner"] for it in items})
        print(f"owners={owners_seen}")
        for item in items[:20]:
            print(f"  {item['repo']}#{item['pr_number']} ({item.get('state')})")
        if len(items) > 20:
            print(f"  … {len(items) - 20} more")
        return 0

    resume = ResumeState(resume_path, inventory_sha256=inventory_sha)
    client = GitHubClient.from_env(args.token_env)
    failures = 0
    collected = 0
    skipped = 0
    quarantined = 0

    for item in items:
        item_id = item["item_id"]
        repo = item["repo"]
        pr = int(item["pr_number"])
        out_dir = raw_parent / repo_slug(repo)
        target = out_dir / f"pr-{pr}.json"

        if resume.is_complete(item_id):
            if target.exists() and resume.get(item_id):
                stored = (resume.get(item_id) or {}).get("record_sha256")
                try:
                    actual = _file_sha256(target)
                except OSError:
                    actual = None
                if stored and actual == stored:
                    logger.info("Skipping %s#%s (resume complete)", repo, pr)
                    skipped += 1
                    continue
                logger.warning(
                    "Resume marked complete but shard hash mismatch for %s#%s; re-collecting",
                    repo,
                    pr,
                )
            elif args.skip_existing and target.exists():
                logger.info("Skipping %s#%s (exists: %s)", repo, pr, target)
                skipped += 1
                continue
        elif args.skip_existing and target.exists():
            logger.info("Skipping %s#%s (exists: %s)", repo, pr, target)
            skipped += 1
            continue

        resume.mark(
            item_id,
            "in_progress",
            extra={"repo": repo, "pr_number": pr, "shard": str(target)},
        )
        logger.info("Collecting %s#%s (%s) …", repo, pr, item.get("state"))
        try:
            path, record = _collect_one(
                client, repo, pr, out_dir, args, store, include_snapshots=include_snapshots
            )
            record_sha = _file_sha256(path)
            pack = record.get("snapshots") or {}
            q_reason = None
            status = "complete"
            if include_snapshots and isinstance(pack, dict) and pack.get("quarantine"):
                status = "quarantined"
                q_reason = "git_object_inaccessible"
                quarantined += 1
            extra = {
                "repo": repo,
                "pr_number": pr,
                "shard": str(path),
                "record_sha256": record_sha,
                "pack_sha256": pack.get("pack_sha256") if isinstance(pack, dict) else None,
                "evidence_complete": (record.get("collection_meta") or {}).get(
                    "evidence_complete"
                ),
            }
            if q_reason:
                extra["reason"] = q_reason
            resume.mark(item_id, status, extra=extra)
            logger.info("Wrote %s (%s)", path, status)
            collected += 1
        except (GitHubError, OSError, ValueError) as exc:
            failures += 1
            resume.mark(
                item_id,
                "failed",
                extra={"repo": repo, "pr_number": pr, "reason": str(exc)[:500]},
            )
            logger.error("Failed %s#%s: %s", repo, pr, exc)
            if not args.continue_on_error:
                return 1

    logger.info(
        "Done: %s collected, %s skipped, %s quarantined, %s failed → %s",
        collected,
        skipped,
        quarantined,
        failures,
        raw_parent,
    )
    logger.info("Resume state %s counts=%s", resume_path, resume.counts())
    if failures:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.inventory:
        if args.repo or args.pr:
            logger.error("Use either --inventory or --repo/--pr, not both")
            return 2
        return _run_inventory(args)
    if not args.repo or not args.pr:
        logger.error("Provide --repo and --pr, or --inventory")
        return 2
    return _run_per_pr(args)


if __name__ == "__main__":
    sys.exit(main())
