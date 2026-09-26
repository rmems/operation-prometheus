#!/usr/bin/env python3
"""Weekly read-only source-inventory audit.

Reports new, renamed, and deleted repositories plus changed terminal candidates.
Never mutates source repositories and never creates GitHub issues.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.ci_audit_prs import diff_terminal_candidates  # noqa: E402
from lib.ci_audit_repos import diff_repositories  # noqa: E402
from lib.ci_contracts import (  # noqa: E402
    INVENTORY_DIR,
    load_inventory_candidates,
    load_inventory_repositories,
)
from lib.github_client import GitHubClient, GitHubError  # noqa: E402
from lib.source_inventory import collect_source_inventory  # noqa: E402

DEFAULT_OWNERS = ("user:rmems", "org:Limen-Neural")
REPORT_SCHEMA = "source_inventory_audit_v1"


def _as_rows(snapshot: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = snapshot.get(key)
    if not isinstance(value, list):
        return []
    return list(value)


def _live_repos(live_snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return _as_rows(live_snapshot, "repositories")


def _terminal_changes(
    frozen_candidates: list[dict[str, Any]],
    live_snapshot: dict[str, Any],
    *,
    skip_terminal_diff: bool,
) -> list[dict[str, Any]]:
    if skip_terminal_diff:
        return []
    return diff_terminal_candidates(
        frozen_candidates, _as_rows(live_snapshot, "pull_requests")
    )


def _counts(
    frozen_repos: list[dict[str, Any]],
    live_repos: list[dict[str, Any]],
    repo_diff: dict[str, list[dict[str, str]]],
    changed: list[dict[str, Any]],
) -> dict[str, int]:
    return {
        "frozen_repositories": len(frozen_repos),
        "live_repositories": len(live_repos),
        "new_repositories": len(repo_diff["new"]),
        "deleted_repositories": len(repo_diff["deleted"]),
        "renamed_repositories": len(repo_diff["renamed"]),
        "changed_terminal_candidates": len(changed),
    }


def build_report(
    frozen_repos: list[dict[str, Any]],
    frozen_candidates: list[dict[str, Any]],
    live_snapshot: dict[str, Any],
    *,
    skip_terminal_diff: bool = False,
) -> dict[str, Any]:
    live_repos = _live_repos(live_snapshot)
    repo_diff = diff_repositories(frozen_repos, live_repos)
    changed = _terminal_changes(
        frozen_candidates,
        live_snapshot,
        skip_terminal_diff=skip_terminal_diff,
    )
    return {
        "schema_version": REPORT_SCHEMA,
        "read_only": True,
        "creates_source_issues": False,
        "mutates_source_repositories": False,
        "repositories": repo_diff,
        "changed_terminal_candidates": changed,
        "counts": _counts(frozen_repos, live_repos, repo_diff, changed),
    }


def _dry_run_snapshot(frozen_repos: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "repositories": frozen_repos,
        "pull_requests": [],
    }


def _file_snapshot(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _owners(args: argparse.Namespace) -> list[str]:
    owners = args.owners
    if owners:
        return list(owners)
    return list(DEFAULT_OWNERS)


def _github_snapshot(owners: list[str]) -> dict[str, Any]:
    client = GitHubClient.from_env()
    return collect_source_inventory(client, owners)


def _choose_snapshot(
    args: argparse.Namespace, frozen_repos: list[dict[str, Any]]
) -> dict[str, Any]:
    if args.dry_run:
        return _dry_run_snapshot(frozen_repos)
    if args.snapshot:
        return _file_snapshot(args.snapshot)
    return _github_snapshot(_owners(args))


def _has_list(snapshot: dict[str, Any], key: str) -> bool:
    return isinstance(snapshot.get(key), list)


def _snapshot_has_lists(snapshot: dict[str, Any]) -> bool:
    if not _has_list(snapshot, "repositories"):
        return False
    return _has_list(snapshot, "pull_requests")


def _snapshot_is_auditable(snapshot: dict[str, Any], *, dry_run: bool) -> bool:
    if not _snapshot_has_lists(snapshot):
        return False
    if dry_run:
        return True
    collection = snapshot.get("collection")
    return isinstance(collection, dict) and collection.get("complete") is True


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["counts"], indent=2))
    print(f"Wrote {path} (read-only; no source mutations, no source issues).")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory-dir", type=Path, default=INVENTORY_DIR)
    parser.add_argument(
        "--out", type=Path, default=Path("reports/source-inventory-audit.json")
    )
    parser.add_argument("--owner", action="append", dest="owners")
    parser.add_argument(
        "--snapshot",
        type=Path,
        help="Use a previously collected snapshot instead of calling GitHub",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load frozen ledger only and write an empty live diff (no GitHub calls)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    frozen_repos = load_inventory_repositories(args.inventory_dir)
    frozen_candidates = load_inventory_candidates(args.inventory_dir)
    try:
        live_snapshot = _choose_snapshot(args, frozen_repos)
    except (GitHubError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"source-inventory-audit FAILED: {exc}", file=sys.stderr)
        return 1
    if not _snapshot_is_auditable(live_snapshot, dry_run=args.dry_run):
        print(
            "source-inventory-audit FAILED: snapshot must include repository and "
            "pull_request lists and collection.complete=true",
            file=sys.stderr,
        )
        return 1
    report = build_report(
        frozen_repos,
        frozen_candidates,
        live_snapshot,
        skip_terminal_diff=args.dry_run,
    )
    _write_report(args.out, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
