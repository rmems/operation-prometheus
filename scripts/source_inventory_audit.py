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

from lib.ci_contracts import (  # noqa: E402
    INVENTORY_DIR,
    load_inventory_candidates,
    load_inventory_repositories,
)
from lib.github_client import GitHubClient, GitHubError  # noqa: E402
from lib.source_inventory import collect_source_inventory  # noqa: E402

DEFAULT_OWNERS = ("user:rmems", "org:Limen-Neural")
TERMINAL_SOURCE_STATES = frozenset({"merged", "closed"})
REPORT_SCHEMA = "source_inventory_audit_v1"


def _repo_key(row: dict[str, Any]) -> str:
    return str(row.get("repository_id") or row.get("id") or "")


def _repo_name(row: dict[str, Any]) -> str:
    return str(
        row.get("name_with_owner") or row.get("repository_name_with_owner") or ""
    )


def _id_only_in(
    primary_by_id: dict[str, dict[str, Any]],
    other_by_id: dict[str, dict[str, Any]],
    other_by_name: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for repo_id, row in primary_by_id.items():
        if repo_id in other_by_id:
            continue
        peer = other_by_name.get(_repo_name(row).casefold())
        if peer is not None and _repo_key(peer) == repo_id:
            continue
        rows.append({"repository_id": repo_id, "name_with_owner": _repo_name(row)})
    return rows


def _renamed_repositories(
    frozen_by_id: dict[str, dict[str, Any]],
    live_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    renamed: list[dict[str, str]] = []
    for repo_id, frozen_row in frozen_by_id.items():
        live_row = live_by_id.get(repo_id)
        if live_row is None:
            continue
        frozen_name = _repo_name(frozen_row)
        live_name = _repo_name(live_row)
        if frozen_name and live_name and frozen_name.casefold() != live_name.casefold():
            renamed.append(
                {"repository_id": repo_id, "from": frozen_name, "to": live_name}
            )
    return renamed


def diff_repositories(
    frozen: list[dict[str, Any]],
    live: list[dict[str, Any]],
) -> dict[str, list[dict[str, str]]]:
    frozen_by_id = {_repo_key(row): row for row in frozen if _repo_key(row)}
    live_by_id = {_repo_key(row): row for row in live if _repo_key(row)}
    frozen_by_name = {
        _repo_name(row).casefold(): row for row in frozen if _repo_name(row)
    }
    live_by_name = {_repo_name(row).casefold(): row for row in live if _repo_name(row)}
    return {
        "new": _id_only_in(live_by_id, frozen_by_id, frozen_by_name),
        "deleted": _id_only_in(frozen_by_id, live_by_id, live_by_name),
        "renamed": _renamed_repositories(frozen_by_id, live_by_id),
    }


def _live_candidate_id(pr: dict[str, Any]) -> str:
    repo_id = str(pr.get("repository_id") or "")
    pr_id = str(pr.get("id") or "")
    if repo_id and pr_id:
        return f"github:repository:{repo_id}:pull:{pr_id}"
    return ""


def _live_source_state(pr: dict[str, Any]) -> str:
    if pr.get("merged") or pr.get("merged_at"):
        return "merged"
    state = str(pr.get("state") or pr.get("source_state") or "").casefold()
    if state in {"open", "closed", "merged"}:
        return state
    return state


def _missing_terminal(
    candidate_id: str, frozen_row: dict[str, Any]
) -> dict[str, Any] | None:
    if frozen_row.get("source_state") not in TERMINAL_SOURCE_STATES:
        return None
    return {
        "candidate_id": candidate_id,
        "kind": "terminal_candidate_missing_from_live",
        "frozen_source_state": frozen_row.get("source_state"),
    }


def _state_change(
    candidate_id: str, frozen_row: dict[str, Any], live: dict[str, Any]
) -> dict[str, Any] | None:
    live_state = _live_source_state(live)
    frozen_state = str(frozen_row.get("source_state") or "")
    if frozen_state == live_state:
        return None
    return {
        "candidate_id": candidate_id,
        "kind": "source_state_changed",
        "from": frozen_state,
        "to": live_state,
    }


def _new_terminal(candidate_id: str, live: dict[str, Any]) -> dict[str, Any] | None:
    live_state = _live_source_state(live)
    if live_state not in TERMINAL_SOURCE_STATES:
        return None
    return {
        "candidate_id": candidate_id,
        "kind": "new_terminal_candidate",
        "source_state": live_state,
        "repository": str(
            live.get("repository_name_with_owner") or live.get("name_with_owner") or ""
        ),
        "number": live.get("number") or live.get("pull_request_number"),
    }


def diff_terminal_candidates(
    frozen: list[dict[str, Any]],
    live_prs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    frozen_by_id = {str(row.get("candidate_id")): row for row in frozen}
    live_by_id = {
        _live_candidate_id(pr): pr for pr in live_prs if _live_candidate_id(pr)
    }
    changed: list[dict[str, Any]] = []
    for candidate_id, frozen_row in frozen_by_id.items():
        live = live_by_id.get(candidate_id)
        if live is None:
            missing = _missing_terminal(candidate_id, frozen_row)
            if missing is not None:
                changed.append(missing)
            continue
        change = _state_change(candidate_id, frozen_row, live)
        if change is not None:
            changed.append(change)
    for candidate_id, live in live_by_id.items():
        if candidate_id in frozen_by_id:
            continue
        added = _new_terminal(candidate_id, live)
        if added is not None:
            changed.append(added)
    changed.sort(key=lambda row: str(row.get("candidate_id")))
    return changed


def build_report(
    frozen_repos: list[dict[str, Any]],
    frozen_candidates: list[dict[str, Any]],
    live_snapshot: dict[str, Any],
) -> dict[str, Any]:
    live_repos = list(live_snapshot.get("repositories") or [])
    repo_diff = diff_repositories(frozen_repos, live_repos)
    if live_snapshot.get("skip_terminal_diff"):
        changed: list[dict[str, Any]] = []
    else:
        live_prs = list(live_snapshot.get("pull_requests") or [])
        changed = diff_terminal_candidates(frozen_candidates, live_prs)
    return {
        "schema_version": REPORT_SCHEMA,
        "read_only": True,
        "creates_source_issues": False,
        "mutates_source_repositories": False,
        "repositories": repo_diff,
        "changed_terminal_candidates": changed,
        "counts": {
            "frozen_repositories": len(frozen_repos),
            "live_repositories": len(live_repos),
            "new_repositories": len(repo_diff["new"]),
            "deleted_repositories": len(repo_diff["deleted"]),
            "renamed_repositories": len(repo_diff["renamed"]),
            "changed_terminal_candidates": len(changed),
        },
    }


def main(argv: list[str] | None = None) -> int:
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
    args = parser.parse_args(argv)
    frozen_repos = load_inventory_repositories(args.inventory_dir)
    frozen_candidates = load_inventory_candidates(args.inventory_dir)
    if args.dry_run:
        live_snapshot = {
            "repositories": frozen_repos,
            "pull_requests": [],
            "skip_terminal_diff": True,
        }
    elif args.snapshot:
        live_snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        repos = live_snapshot.get("repositories")
        prs = live_snapshot.get("pull_requests")
        if not isinstance(repos, list) or not isinstance(prs, list):
            print(
                "source-inventory-audit FAILED: snapshot must include repositories and pull_requests lists",
                file=sys.stderr,
            )
            return 1
    else:
        client = GitHubClient.from_env()
        try:
            live_snapshot = collect_source_inventory(
                client, list(args.owners or DEFAULT_OWNERS)
            )
        except (GitHubError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"source-inventory-audit FAILED: {exc}", file=sys.stderr)
            return 1
    report = build_report(frozen_repos, frozen_candidates, live_snapshot)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["counts"], indent=2))
    print(f"Wrote {args.out} (read-only; no source mutations, no source issues).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
