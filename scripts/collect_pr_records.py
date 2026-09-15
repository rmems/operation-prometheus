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
from dataclasses import dataclass
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
from lib.raw_record import CollectOptions, collect_pr, write_raw_record  # noqa: E402
from lib.resume_state import ResumeState  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("collect_pr_records")


@dataclass
class CollectRequest:
    """One PR write: client, destination, and collect flags."""

    client: GitHubClient
    repo: str
    pr: int
    out_dir: Path
    options: CollectOptions
    max_inline_diff_bytes: int


@dataclass
class InventoryRun:
    items: list[dict]
    inventory_sha: str
    raw_parent: Path
    store: ContentAddressedStore
    resume_path: Path
    include_snapshots: bool
    args: argparse.Namespace


@dataclass
class ListedPrJob:
    client: GitHubClient
    full: str
    out_dir: Path
    args: argparse.Namespace
    options: CollectOptions


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


def _add_source_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", help="GitHub repository owner/name (per-PR mode)")
    parser.add_argument(
        "--pr",
        action="append",
        help="PR number or comma-separated list (repeatable; per-PR mode)",
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        help="Eligibility candidates JSONL or ledger directory (inventory mode)",
    )
    parser.add_argument(
        "--states",
        default=",".join(DEFAULT_STATES),
        help="Comma-separated ledger states to collect (inventory mode)",
    )
    parser.add_argument(
        "--owner",
        action="append",
        dest="owners",
        help="Restrict inventory collection to this owner login (repeatable)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of inventory items to collect",
    )


def _add_output_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
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
    parser.add_argument(
        "--artifact-store",
        type=Path,
        default=None,
        help="Content-addressed artifact store root (default: $PROMETHEUS_DATA_ROOT/artifacts)",
    )
    parser.add_argument(
        "--resume-state",
        type=Path,
        default=None,
        help="Durable resume-state JSON (inventory mode)",
    )
    parser.add_argument(
        "--token-env",
        default="GITHUB_TOKEN",
        help="Environment variable holding the GitHub token (default: GITHUB_TOKEN)",
    )


def _add_collect_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--max-inline-diff-bytes",
        type=int,
        default=256 * 1024,
        help="Sidecar threshold for unified diffs (default: 256KiB)",
    )
    parser.add_argument("--skip-checks", action="store_true", help="Skip check-runs API")
    parser.add_argument("--skip-diff", action="store_true", help="Skip full unified diff fetch")
    parser.add_argument("--skip-timeline", action="store_true", help="Skip issue timeline events")
    parser.add_argument(
        "--snapshots",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Fetch git commit/blob objects into the artifact store "
            "(default: on for --inventory, off for --repo/--pr)"
        ),
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip PRs that already have pr-N.json in out-dir (resume-friendly)",
    )
    parser.add_argument(
        "--allow-cross-repo",
        action="append",
        default=[],
        metavar="OWNER/REPO",
        help=(
            "Allow fetching linked issues from this owner/repo (repeatable). "
            "Cross-repo Closes/Fixes references are skipped unless allowlisted."
        ),
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue batch if one PR fails",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned work without calling GitHub",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    _add_source_args(parser)
    _add_output_args(parser)
    _add_collect_flags(parser)
    return parser


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _try_file_sha256(path: Path) -> str | None:
    try:
        return _file_sha256(path)
    except OSError:
        return None


def _raw_parent_for_inventory(out_dir: Path | None) -> Path:
    if out_dir is not None:
        return Path(out_dir)
    root = data_root_from_env()
    if root is not None:
        return root / "raw"
    return repo_root() / "datasets" / "raw"


def _options_from_args(args: argparse.Namespace, store: ContentAddressedStore | None, include_snapshots: bool) -> CollectOptions:
    return CollectOptions(
        include_checks=not args.skip_checks,
        include_diff=not args.skip_diff,
        include_timeline=not args.skip_timeline,
        include_snapshots=include_snapshots,
        artifact_store=store,
        cross_repo_allowlist=tuple(args.allow_cross_repo or ()),
    )


def _collect_one(request: CollectRequest) -> tuple[Path, dict]:
    record = collect_pr(request.client, request.repo, request.pr, options=request.options)
    path = write_raw_record(
        record,
        request.out_dir,
        max_inline_diff_bytes=request.max_inline_diff_bytes,
        artifact_store=request.options.artifact_store,
    )
    return path, record


def _per_pr_dry_run(full: str, prs: list[int], out_dir: Path, args: argparse.Namespace) -> int:
    print(f"Would collect {full} PRs {prs} → {out_dir}")
    if args.skip_existing:
        print("(with --skip-existing)")
    if args.snapshots:
        print("(with --snapshots)")
    return 0


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
        return _per_pr_dry_run(full, prs, out_dir, args)

    client = GitHubClient.from_env(args.token_env)
    options = _options_from_args(args, store, include_snapshots)
    job = ListedPrJob(client=client, full=full, out_dir=out_dir, args=args, options=options)
    failures = 0
    collected = 0
    skipped = 0
    for pr in prs:
        skipped_one, collected_one, failed = _collect_listed_pr(job, pr)
        skipped += skipped_one
        collected += collected_one
        failures += failed
        if failed and not args.continue_on_error:
            return 1
    if failures:
        logger.error(
            "%s PR(s) failed (%s collected, %s skipped)",
            failures,
            collected,
            skipped,
        )
        return 1
    logger.info("Done: %s collected, %s skipped → %s", collected, skipped, out_dir)
    return 0


def _collect_listed_pr(job: ListedPrJob, pr: int) -> tuple[int, int, int]:
    target = job.out_dir / f"pr-{pr}.json"
    if job.args.skip_existing and target.exists():
        logger.info("Skipping %s#%s (exists: %s)", job.full, pr, target)
        return 1, 0, 0
    logger.info("Collecting %s#%s …", job.full, pr)
    request = CollectRequest(
        client=job.client,
        repo=job.full,
        pr=pr,
        out_dir=job.out_dir,
        options=job.options,
        max_inline_diff_bytes=job.args.max_inline_diff_bytes,
    )
    try:
        path, _record = _collect_one(request)
        logger.info("Wrote %s", path)
        return 0, 1, 0
    except (GitHubError, OSError, ValueError) as exc:
        logger.error("Failed %s#%s: %s", job.full, pr, exc)
        return 0, 0, 1


def _inventory_dry_run(run: InventoryRun) -> int:
    items = run.items
    print(f"Would collect {len(items)} inventory items → {run.raw_parent}")
    print(f"inventory_sha256={run.inventory_sha}")
    print(f"resume_state={run.resume_path}")
    print(f"artifact_store={run.store.root}")
    owners_seen = sorted({it["owner"] for it in items})
    print(f"owners={owners_seen}")
    for item in items[:20]:
        print(f"  {item['repo']}#{item['pr_number']} ({item.get('state')})")
    if len(items) > 20:
        print(f"  … {len(items) - 20} more")
    return 0


def _complete_shard_matches(resume: ResumeState, item_id: str, target: Path) -> bool | None:
    """True if hashes match, False if complete-but-mismatch, None if not a complete shard."""
    if not resume.is_complete(item_id):
        return None
    if not target.exists():
        return None
    item = resume.get(item_id)
    if not item:
        return None
    stored = item.get("record_sha256")
    actual = _try_file_sha256(target)
    if stored and actual == stored:
        return True
    return False


def _skip_inventory_item(
    resume: ResumeState,
    item_id: str,
    target: Path,
    skip_existing: bool,
) -> str | None:
    """Return a skip reason, or None to collect."""
    match = _complete_shard_matches(resume, item_id, target)
    if match is True:
        return "complete"
    if match is False:
        logger.warning(
            "Resume marked complete but shard hash mismatch for %s; re-collecting",
            item_id,
        )
        return None
    if skip_existing and target.exists():
        return "exists"
    return None


def _finish_inventory_item(resume: ResumeState, item: dict, written: tuple[Path, dict], include_snapshots: bool) -> str:
    path, record = written
    pack = record.get("snapshots") or {}
    status = "complete"
    extra = {
        "repo": item["repo"],
        "pr_number": item["pr_number"],
        "shard": str(path),
        "record_sha256": _file_sha256(path),
        "pack_sha256": pack.get("pack_sha256") if isinstance(pack, dict) else None,
        "evidence_complete": (record.get("collection_meta") or {}).get("evidence_complete"),
    }
    if include_snapshots and isinstance(pack, dict) and pack.get("quarantine"):
        status = "quarantined"
        extra["reason"] = "git_object_inaccessible"
    resume.mark(item["item_id"], status, extra)
    return status


def _collect_inventory_item(
    run: InventoryRun,
    resume: ResumeState,
    client: GitHubClient,
    item: dict,
) -> str:
    """Collect one inventory item. Returns status or 'failed'."""
    item_id = item["item_id"]
    repo = item["repo"]
    pr = int(item["pr_number"])
    out_dir = run.raw_parent / repo_slug(repo)
    target = out_dir / f"pr-{pr}.json"
    skip = _skip_inventory_item(resume, item_id, target, run.args.skip_existing)
    if skip:
        logger.info("Skipping %s#%s (resume %s)", repo, pr, skip)
        return "skipped"
    resume.mark(item_id, "in_progress", {"repo": repo, "pr_number": pr, "shard": str(target)})
    logger.info("Collecting %s#%s (%s) …", repo, pr, item.get("state"))
    options = _options_from_args(run.args, run.store, run.include_snapshots)
    request = CollectRequest(
        client=client,
        repo=repo,
        pr=pr,
        out_dir=out_dir,
        options=options,
        max_inline_diff_bytes=run.args.max_inline_diff_bytes,
    )
    try:
        path, record = _collect_one(request)
        status = _finish_inventory_item(resume, item, (path, record), run.include_snapshots)
        logger.info("Wrote %s (%s)", path, status)
        return status
    except (GitHubError, OSError, ValueError) as exc:
        resume.mark(item_id, "failed", {"repo": repo, "pr_number": pr, "reason": str(exc)[:500]})
        logger.error("Failed %s#%s: %s", repo, pr, exc)
        return "failed"


def _load_inventory_run(args: argparse.Namespace) -> InventoryRun:
    states = _parse_states(args.states)
    owners = _parse_owners(args.owners)
    items, inventory_sha = load_inventory_targets(
        args.inventory,
        states=states,
        owners=owners or None,
        limit=args.limit,
    )
    store_dir = resolve_artifact_store_dir(args.artifact_store)
    include_snapshots = True if args.snapshots is None else bool(args.snapshots)
    return InventoryRun(
        items=items,
        inventory_sha=inventory_sha,
        raw_parent=_raw_parent_for_inventory(args.out_dir),
        store=ContentAddressedStore(store_dir),
        resume_path=resolve_resume_state_path(args.resume_state),
        include_snapshots=include_snapshots,
        args=args,
    )


def _run_inventory(args: argparse.Namespace) -> int:
    try:
        run = _load_inventory_run(args)
    except (OSError, ValueError) as exc:
        logger.error("%s", exc)
        return 2
    if args.dry_run:
        return _inventory_dry_run(run)

    resume = ResumeState(run.resume_path, inventory_sha256=run.inventory_sha)
    client = GitHubClient.from_env(args.token_env)
    tallies = {"collected": 0, "skipped": 0, "quarantined": 0, "failed": 0}
    for item in run.items:
        status = _collect_inventory_item(run, resume, client, item)
        if status == "skipped":
            tallies["skipped"] += 1
            continue
        if status == "failed":
            tallies["failed"] += 1
            if not args.continue_on_error:
                return 1
            continue
        tallies["collected"] += 1
        if status == "quarantined":
            tallies["quarantined"] += 1
    logger.info(
        "Done: %s collected, %s skipped, %s quarantined, %s failed → %s",
        tallies["collected"],
        tallies["skipped"],
        tallies["quarantined"],
        tallies["failed"],
        run.raw_parent,
    )
    logger.info("Resume state %s counts=%s", run.resume_path, resume.counts())
    return 1 if tallies["failed"] else 0


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
