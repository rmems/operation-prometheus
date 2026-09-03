"""Deterministic task-family inference and fail-closed state assignment."""

from __future__ import annotations

import re
from typing import Any

from .eligibility_common import LEDGER_STATES, _text

_TASK_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)^fix(?:\(|:|\b)"), "bugfix"),
    (re.compile(r"(?i)^feat(?:\(|:|\b)"), "feature"),
    (re.compile(r"(?i)^refactor(?:\(|:|\b)"), "refactor"),
    (re.compile(r"(?i)^test(?:s)?(?:\(|:|\b)"), "test"),
    (re.compile(r"(?i)^perf(?:\(|:|\b)"), "performance"),
    (re.compile(r"(?i)^sec(?:urity)?(?:\(|:|\b)"), "security"),
    (re.compile(r"(?i)^(?:ci|build)(?:\(|:|\b)"), "ci"),
    (re.compile(r"(?i)^data(?:\(|:|\b)"), "data"),
    (re.compile(r"(?i)^docs?(?:\(|:|\b)"), "documentation"),
    (re.compile(r"(?i)^(?:release|chore\(release\))(?:\(|:|\b)"), "release"),
    (re.compile(r"(?i)^(?:research|experiment|eval)(?:\(|:|\b)"), "research_experiment"),
)
_BOT_DEPENDENCY_MARKERS = ("dependabot", "renovate", "snyk-bot")
_LABEL_FAMILY_MAP = {
    "bug": "bugfix",
    "enhancement": "feature",
    "documentation": "documentation",
    "security": "security",
    "ci": "ci",
    "data": "data",
}


def _is_dependency_author(author: str, author_type: str, policy: dict[str, Any]) -> bool:
    dependency_authors = {
        str(item).casefold() for item in (policy.get("dependency_authors") or [])
    }
    if author in dependency_authors:
        return True
    return author_type == "bot" and any(
        marker in author for marker in _BOT_DEPENDENCY_MARKERS
    )


def _family_from_title(title: str) -> str | None:
    for pattern, family in _TASK_PATTERNS:
        if pattern.search(title):
            return family
    return None


def _family_from_labels(labels: set[str]) -> tuple[str, str] | None:
    for label, family in _LABEL_FAMILY_MAP.items():
        if label in labels:
            return label, family
    return None


def infer_task_family(pr: dict[str, Any], policy: dict[str, Any]) -> tuple[str, list[str]]:
    title = _text(pr.get("title")).strip()
    author_record = pr.get("author") or {}
    author = _text(author_record.get("login")).casefold()
    author_type = _text(author_record.get("type")).casefold()
    if _is_dependency_author(author, author_type, policy):
        return "dependency", ["dependency_automation_author"]
    title_family = _family_from_title(title)
    if title_family is not None:
        return title_family, [f"title_pattern:{title_family}"]
    labels = {_text(item).casefold() for item in (pr.get("labels") or [])}
    label_match = _family_from_labels(labels)
    if label_match is not None:
        label, family = label_match
        return family, [f"github_label:{label}"]
    return "other", ["no_deterministic_task_family_rule"]


_RELEASE_TITLE = re.compile(r"(?i)\b(?:release|version|changelog)\b")
_FORMAT_TITLE = re.compile(r"(?i)^(?:style|format)(?:\(|:|\b)")


def _open_state_reasons(pr: dict[str, Any]) -> list[str]:
    reasons = ["mutable_open_pull_request"]
    if pr.get("draft"):
        reasons.append("draft_pull_request")
    return reasons


def _exclusion_reason(task_family: str, title: str) -> str | None:
    if task_family == "dependency":
        return "dependency_only"
    if task_family == "release" and _RELEASE_TITLE.search(title):
        return "routine_release_only"
    if task_family == "documentation":
        return "non_executable_documentation"
    if _FORMAT_TITLE.search(title):
        return "formatting_only"
    return None


def _quarantine_reason(state: str) -> str:
    if state == "merged":
        return "full_trajectory_collection_pending"
    if state == "closed":
        return "negative_trajectory_evidence_incomplete"
    return "source_disposition_unresolved"


def _automatic_state(
    pr: dict[str, Any],
    task_family: str,
) -> tuple[str, list[str]]:
    state = _text(pr.get("state")).lower()
    title = _text(pr.get("title")).strip()
    if state == "open":
        return "watchlist_open", _open_state_reasons(pr)
    exclusion = _exclusion_reason(task_family, title)
    if exclusion is not None:
        return "excluded", [exclusion]
    return "quarantined", [_quarantine_reason(state)]


def _override_state_violation(state: str, source_state: str) -> str | None:
    rules = {
        "included_positive": (
            source_state != "merged",
            "Override cannot include non-merged candidate as positive",
        ),
        "included_negative": (
            source_state == "open",
            "Override cannot include open candidate as negative",
        ),
        "watchlist_open": (
            source_state != "open",
            "Override cannot watchlist a terminal candidate",
        ),
    }
    violated, message = rules.get(state, (False, ""))
    if violated:
        return message
    return None


def _override_decision(
    cid: str,
    source_state: str,
    override: dict[str, Any],
) -> tuple[str, list[str]]:
    state = str(override["state"])
    violation = _override_state_violation(state, source_state)
    if violation:
        raise ValueError(f"{violation}: {cid}")
    reason_codes = [str(item) for item in override["reason_codes"]]
    return state, reason_codes


def _override_target(raw: Any, seen: set[str]) -> str:
    if not isinstance(raw, dict):
        raise ValueError("Eligibility override must be an object")
    target = _text(raw.get("candidate_id"))
    if not target or target in seen:
        raise ValueError(f"Missing or duplicate override candidate_id {target!r}")
    return target


def _validate_override_content(target: str, raw: dict[str, Any]) -> None:
    state = _text(raw.get("state"))
    reasons = raw.get("reason_codes") or []
    evidence = raw.get("evidence_refs") or []
    if any((state not in LEDGER_STATES, not reasons, not evidence)):
        raise ValueError(f"Override {target} lacks a valid state, reasons, or evidence")


def _validated_override(raw: Any, seen: set[str]) -> tuple[str, dict[str, Any]]:
    target = _override_target(raw, seen)
    _validate_override_content(target, raw)
    return target, raw


def _override_map(policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    overrides: dict[str, dict[str, Any]] = {}
    for raw in policy.get("overrides") or []:
        target, override = _validated_override(raw, set(overrides))
        overrides[target] = override
    return overrides
