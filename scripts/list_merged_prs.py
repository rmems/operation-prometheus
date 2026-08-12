#!/usr/bin/env python3
"""List merged public PRs for a repository (discovery helper for scale waves).

Read-only. Default output is a human table plus a ``# numbers:`` line.
Use ``--json`` for a JSON array, or ``--numbers-only`` for a comma-separated list.

Examples:
    export GITHUB_TOKEN="$(gh auth token)"
    python scripts/list_merged_prs.py --repo Limen-Neural/neuromod --limit 30
    python scripts/list_merged_prs.py --repo rmems/corinth-canal --limit 10 --numbers-only
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.github_client import GitHubClient, GitHubError, parse_repo  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("list_merged_prs")


def list_merged_prs(
    client: GitHubClient,
    repo: str,
    *,
    limit: int = 50,
    per_page: int = 100,
) -> list[dict[str, Any]]:
    """Return up to ``limit`` merged PR summaries (newest first by update time)."""
    if limit < 1:
        raise ValueError("limit must be >= 1")
    owner, name = parse_repo(repo)
    full = f"{owner}/{name}"
    path = f"/repos/{full}/pulls?state=closed&sort=updated&direction=desc"
    found: list[dict[str, Any]] = []
    for page in client.paginate(path, per_page=per_page):
        for pr in page:
            if not isinstance(pr, dict):
                continue
            if not pr.get("merged_at"):
                continue
            num = pr.get("number")
            if num is None:
                continue
            found.append(
                {
                    "number": num,
                    "title": pr.get("title") or "",
                    "merged_at": pr.get("merged_at"),
                    "user": ((pr.get("user") or {}).get("login")),
                    "html_url": pr.get("html_url"),
                    "additions": pr.get("additions"),
                    "deletions": pr.get("deletions"),
                    "changed_files": pr.get("changed_files"),
                }
            )
            if len(found) >= limit:
                return found
        if not page:
            break
    return found


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", required=True, help="GitHub repository owner/name")
    p.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max merged PRs to return (default 50)",
    )
    p.add_argument(
        "--token-env",
        default="GITHUB_TOKEN",
        help="Env var for GitHub token (default GITHUB_TOKEN; also tries GH_TOKEN)",
    )
    p.add_argument(
        "--numbers-only",
        action="store_true",
        help="Print comma-separated PR numbers only (for piping into collect)",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON array (default is human table + # numbers: line)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        owner, name = parse_repo(args.repo)
        full = f"{owner}/{name}"
    except ValueError as exc:
        logger.error("%s", exc)
        return 2
    if args.limit < 1:
        logger.error("--limit must be >= 1")
        return 2

    client = GitHubClient.from_env(args.token_env)
    try:
        items = list_merged_prs(client, full, limit=args.limit)
    except GitHubError as exc:
        logger.error("%s", exc)
        return 1

    numbers = [
        int(i["number"]) for i in items if "number" in i and i["number"] is not None
    ]
    if args.numbers_only:
        print(",".join(str(n) for n in numbers))
        return 0
    if args.json:
        print(json.dumps(items, indent=2))
        return 0

    print(f"# {full}: {len(items)} merged PR(s) (limit={args.limit})")
    for i in items:
        print(
            f"  #{i['number']:>4}  {i.get('merged_at', '')[:10]}  "
            f"{(i.get('title') or '')[:72]}"
        )
    print(f"# numbers: {','.join(str(n) for n in numbers)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
