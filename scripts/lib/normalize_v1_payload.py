"""v1 typed payload, evidence quality, and lineage helpers."""

from __future__ import annotations

from typing import Any

from .bots import extract_section, strip_bot_boilerplate
from .normalize import extract_validation


def _text_parts(title: Any, body: Any) -> list[str]:
    parts: list[str] = []
    title_text = (title or "").strip()
    body_text = strip_bot_boilerplate(body or "")
    if title_text:
        parts.append(title_text)
    if body_text:
        parts.append(body_text)
    return parts


def _issue_statement(raw: dict[str, Any]) -> str:
    linked = raw.get("linked_issues") or []
    parts: list[str] = []
    for issue in linked:
        parts.extend(_text_parts(issue.get("title"), issue.get("body")))
    pull = raw.get("pull") or {}
    if not parts:
        parts = _text_parts(pull.get("title"), pull.get("body"))
    text = "\n\n".join(p for p in parts if p).strip()
    return text or (pull.get("title") or "untitled pull request")


def _missing_validation(raw: dict[str, Any]) -> str:
    merge = raw.get("merge_state") or {}
    if merge.get("merged"):
        return "merged without recorded checks"
    return "validation not collected"


def _validation_outcome(raw: dict[str, Any]) -> str:
    events = extract_validation(raw)
    if not events:
        return _missing_validation(raw)
    bits = [f"{e.get('type')}={e.get('result')}: {e.get('detail')}" for e in events]
    return "; ".join(bits)


def _software_payload(raw: dict[str, Any], patch_text: str) -> dict[str, str]:
    pull = raw.get("pull") or {}
    body = strip_bot_boilerplate(pull.get("body") or "")
    criteria = extract_section(body, ("acceptance", "criteria", "requirements")) or ""
    patch = patch_text or "patch not collected"
    payload = {
        "issue_statement": _issue_statement(raw),
        "pre_change_state": str(pull.get("base_sha") or "unknown"),
        "implementation_patch": patch,
        "validation_outcome": _validation_outcome(raw),
    }
    if criteria.strip():
        payload["acceptance_criteria"] = criteria.strip()
    return payload


def _research_payload(raw: dict[str, Any]) -> dict[str, str]:
    pull = raw.get("pull") or {}
    plan = strip_bot_boilerplate(pull.get("body") or "") or pull.get("title") or "unspecified"
    return {
        "hypothesis": _issue_statement(raw),
        "initial_state": str(pull.get("base_sha") or "unknown"),
        "plan": plan,
        "measurements": _validation_outcome(raw),
    }


def _snapshot_pack(raw: dict[str, Any]) -> dict[str, Any]:
    pack = raw.get("snapshots") or {}
    if isinstance(pack, dict):
        return pack
    return {}


def _has_event_types(events: list[dict[str, Any]], types: set[str]) -> bool:
    return any(e.get("event_type") in types for e in events)


def _signal_to_noise(events: list[dict[str, Any]]) -> float:
    score = 0.5
    if _has_event_types(events, {"review", "review_comment"}):
        score += 0.2
    if _has_event_types(events, {"check_run", "check_suite"}):
        score += 0.2
    return round(min(1.0, score), 3)


def _reproducibility(pack: dict[str, Any]) -> float:
    if pack.get("complete"):
        return 1.0
    if pack:
        return 0.4
    return 0.2


def _pack_completeness(pack: dict[str, Any], completeness: float) -> float:
    if pack.get("complete"):
        return 1.0
    if pack.get("quarantine"):
        return min(completeness, 0.5)
    return completeness


def _completeness_score(n_events: int, pack: dict[str, Any], warnings: list[Any]) -> float:
    completeness = 0.4
    if n_events >= 3:
        completeness = 0.7
    completeness = _pack_completeness(pack, completeness)
    if warnings:
        completeness = min(completeness, 0.8)
    return completeness


def _evidence_quality(raw: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, float]:
    pack = _snapshot_pack(raw)
    warnings = (raw.get("collection_meta") or {}).get("warnings") or []
    return {
        "signal_to_noise": _signal_to_noise(events),
        "reproducibility": round(_reproducibility(pack), 3),
        "completeness": round(_completeness_score(len(events), pack, warnings), 3),
    }


def _task_family(card: dict[str, Any]) -> str:
    task_family = str(card.get("trajectory_type") or "software")
    if task_family not in {"software", "research"}:
        return "software"
    return task_family


def _typed_payloads(raw: dict[str, Any], patch_text: str, task_family: str) -> dict[str, Any]:
    if task_family == "research":
        return {"research_payload": _research_payload(raw)}
    return {"software_payload": _software_payload(raw, patch_text)}


def _lineage(_raw: dict[str, Any], _source_id: str) -> dict[str, list[str]]:
    return {
        "supersedes": [],
        "reverts": [],
        "multi_pr_links": [],
    }
