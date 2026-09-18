"""Terminal-candidate diffs for the weekly source-inventory audit."""

from __future__ import annotations

from typing import Any

from .ci_audit_repos import keep

TERMINAL_SOURCE_STATES = frozenset({"merged", "closed"})


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def live_candidate_id(pr: dict[str, Any]) -> str:
    repo_id = _text(pr.get("repository_id"))
    pr_id = _text(pr.get("id"))
    if not repo_id:
        return ""
    if not pr_id:
        return ""
    return f"github:repository:{repo_id}:pull:{pr_id}"


def _is_merged(pr: dict[str, Any]) -> bool:
    if pr.get("merged"):
        return True
    return bool(pr.get("merged_at"))


def _raw_state(pr: dict[str, Any]) -> str:
    state = pr.get("state")
    if state:
        return str(state).casefold()
    source = pr.get("source_state")
    if source:
        return str(source).casefold()
    return ""


def live_source_state(pr: dict[str, Any]) -> str:
    if _is_merged(pr):
        return "merged"
    return _raw_state(pr)


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
    live_state = live_source_state(live)
    frozen_state = _text(frozen_row.get("source_state"))
    if frozen_state == live_state:
        return None
    return {
        "candidate_id": candidate_id,
        "kind": "source_state_changed",
        "from": frozen_state,
        "to": live_state,
    }


def _pr_repo_name(live: dict[str, Any]) -> str:
    name = live.get("repository_name_with_owner")
    if name:
        return str(name)
    fallback = live.get("name_with_owner")
    if fallback:
        return str(fallback)
    return ""


def _pr_number(live: dict[str, Any]) -> Any:
    number = live.get("number")
    if number is not None:
        return number
    return live.get("pull_request_number")


def _new_terminal(candidate_id: str, live: dict[str, Any]) -> dict[str, Any] | None:
    live_state = live_source_state(live)
    if live_state not in TERMINAL_SOURCE_STATES:
        return None
    return {
        "candidate_id": candidate_id,
        "kind": "new_terminal_candidate",
        "source_state": live_state,
        "repository": _pr_repo_name(live),
        "number": _pr_number(live),
    }


def _one_frozen_change(
    candidate_id: str, frozen_row: dict[str, Any], live: dict[str, Any] | None
) -> dict[str, Any] | None:
    if live is None:
        return _missing_terminal(candidate_id, frozen_row)
    return _state_change(candidate_id, frozen_row, live)


def _frozen_changes(
    frozen_by_id: dict[str, dict[str, Any]], live_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    return keep(
        [
            _one_frozen_change(candidate_id, frozen_row, live_by_id.get(candidate_id))
            for candidate_id, frozen_row in frozen_by_id.items()
        ]
    )


def _maybe_new_terminal(
    candidate_id: str,
    frozen_by_id: dict[str, dict[str, Any]],
    live: dict[str, Any],
) -> dict[str, Any] | None:
    if candidate_id in frozen_by_id:
        return None
    return _new_terminal(candidate_id, live)


def _new_live_terminals(
    frozen_by_id: dict[str, dict[str, Any]], live_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    return keep(
        [
            _maybe_new_terminal(candidate_id, frozen_by_id, live)
            for candidate_id, live in live_by_id.items()
        ]
    )


def _live_index(live_prs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for pr in live_prs:
        candidate_id = live_candidate_id(pr)
        if candidate_id:
            indexed[candidate_id] = pr
    return indexed


def diff_terminal_candidates(
    frozen: list[dict[str, Any]],
    live_prs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    frozen_by_id = {str(row.get("candidate_id")): row for row in frozen}
    live_by_id = _live_index(live_prs)
    changed = _frozen_changes(frozen_by_id, live_by_id)
    changed.extend(_new_live_terminals(frozen_by_id, live_by_id))
    changed.sort(key=lambda row: str(row.get("candidate_id")))
    return changed
