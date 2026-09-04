"""Lineage edges between candidates: reverts, supersedes, and shared issues."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from .eligibility_common import _source_ref

_PR_REF_PATTERN = (
    r"(?:(?:https://github\.com/)?(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)"
    r"(?:/pull/|#)|(?:pull/|pr\s*#?|#))(?P<number>\d+)\b"
)
_REVERT_REF = re.compile(
    r"\brevert(?:s|ed|ing)?\b[^\n]{0,160}?" + _PR_REF_PATTERN,
    re.IGNORECASE,
)
_SUPERSEDE_REF = re.compile(
    r"\bsupersed(?:e|es|ed|ing)\b[^\n]{0,160}?" + _PR_REF_PATTERN,
    re.IGNORECASE,
)
_ISSUE_SCOPED_BARE_REF = re.compile(
    r"(?i)\b(?:issues?|bugs?|tickets?|close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?[ \t]*#\d+\b"
)


def _lineage(
    pr: dict[str, Any],
    by_repo_number: dict[tuple[str, int], str],
) -> dict[str, list[dict[str, str]]]:
    text = f"{pr.get('title') or ''}\n{pr.get('body') or ''}"
    repo_name = str(pr.get("repository_name_with_owner") or "").casefold()

    def edges(pattern: re.Pattern[str], relation: str) -> list[dict[str, str]]:
        found: list[dict[str, str]] = []
        seen: set[str] = set()
        for match in pattern.finditer(text):
            if match.group("repo") is None and _ISSUE_SCOPED_BARE_REF.search(match.group(0)):
                continue
            number = int(match.group("number"))
            referenced_repo = str(match.group("repo") or repo_name).casefold()
            target = by_repo_number.get((referenced_repo, number))
            if not target or target in seen:
                continue
            seen.add(target)
            found.append(
                {
                    "relation": relation,
                    "target_candidate_id": target,
                    "evidence_ref": _source_ref(pr),
                }
            )
        return found

    return {
        "reverts": edges(_REVERT_REF, "reverts"),
        "supersedes": edges(_SUPERSEDE_REF, "supersedes"),
        "multi_pr_links": [],
    }


def _issue_candidate_map(candidates: list[dict[str, Any]]) -> dict[str, list[str]]:
    by_issue: dict[str, list[str]] = defaultdict(list)
    for candidate in candidates:
        for issue in candidate.get("linked_issues") or []:
            issue_id = str(issue.get("id") or "")
            if issue_id:
                by_issue[issue_id].append(candidate["candidate_id"])
    return by_issue


def _shared_issue_edges(
    issue_id: str,
    source_id: str,
    unique: list[str],
) -> list[dict[str, str]]:
    return [
        {
            "relation": "shares_formal_issue",
            "target_candidate_id": target_id,
            "evidence_ref": f"github:issue:{issue_id}",
        }
        for target_id in unique
        if target_id != source_id
    ]


def _multi_pr_lineage(candidates: list[dict[str, Any]]) -> None:
    by_issue = _issue_candidate_map(candidates)
    by_id = {row["candidate_id"]: row for row in candidates}
    for issue_id, candidate_ids in by_issue.items():
        unique = sorted(set(candidate_ids))
        if len(unique) < 2:
            continue
        for source_id in unique:
            edges = by_id[source_id]["lineage"]["multi_pr_links"]
            edges.extend(_shared_issue_edges(issue_id, source_id, unique))
