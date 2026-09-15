"""v1 artifact, payload, and evidence helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .bots import extract_section, strip_bot_boilerplate
from .cas import ContentAddressedStore, sha256_bytes
from .normalize import extract_patch, extract_validation


def _sha256_is_digest(sha256: Any) -> bool:
    if not isinstance(sha256, str):
        return False
    return len(sha256) == 64


def _reproduction_role(obj: dict[str, Any]) -> str:
    return str(obj.get("role") or obj.get("kind") or "git_object")


def _present_art_record(obj: dict[str, Any], index: int) -> dict[str, Any]:
    uri = obj.get("uri")
    art = {
        "id": f"obj-{index}",
        "sha256": obj.get("sha256"),
        "media_type": obj.get("media_type") or "application/octet-stream",
        "byte_size": int(obj.get("byte_size") or 0),
        "availability": "inline",
        "reproduction_role": _reproduction_role(obj),
    }
    if uri:
        art["availability"] = "remote"
        art["uri"] = uri
    return art


def _present_git_artifact(obj: dict[str, Any], index: int) -> dict[str, Any] | None:
    availability = obj.get("availability") or "missing"
    if availability != "present":
        return None
    if not _sha256_is_digest(obj.get("sha256")):
        return None
    return _present_art_record(obj, index)


def _placeholder_git_artifact(obj: dict[str, Any], index: int) -> dict[str, Any]:
    placeholder = {
        "reason": obj.get("reason") or "missing",
        "git_oid": obj.get("git_oid"),
        "kind": obj.get("kind"),
        "availability": obj.get("availability") or "missing",
    }
    encoded = repr(placeholder).encode("utf-8")
    return {
        "id": f"obj-{index}",
        "sha256": sha256_bytes(encoded),
        "media_type": "application/json",
        "byte_size": len(encoded),
        "availability": "missing",
        "reproduction_role": _reproduction_role(obj),
    }


def _artifact_from_object(obj: dict[str, Any], index: int) -> dict[str, Any]:
    present = _present_git_artifact(obj, index)
    if present:
        return present
    return _placeholder_git_artifact(obj, index)


def _cas_patch_artifact(artifact_meta: dict[str, Any], patch: str) -> tuple[str, dict[str, Any]]:
    art = {
        "id": "unified-diff",
        "sha256": artifact_meta["sha256"],
        "media_type": "text/x-diff",
        "byte_size": int(artifact_meta.get("byte_size") or len(patch.encode("utf-8"))),
        "availability": "remote",
        "reproduction_role": "implementation_patch",
        "uri": artifact_meta.get("uri") or f"cas://sha256/{artifact_meta['sha256']}",
    }
    summary = patch if patch else f"cas://sha256/{artifact_meta['sha256']}"
    return summary, art


def _inline_patch_artifact(patch: str) -> tuple[str, dict[str, Any] | None]:
    if not patch:
        return "patch not collected", None
    data = patch.encode("utf-8")
    return patch, {
        "id": "inline-patch",
        "sha256": sha256_bytes(data),
        "media_type": "text/x-diff",
        "byte_size": len(data),
        "availability": "inline",
        "reproduction_role": "implementation_patch",
        "content": patch,
    }


def _patch_artifact(
    raw: dict[str, Any],
    max_patch_bytes: int,
    raw_path: Path | None = None,
) -> tuple[str, dict[str, Any] | None]:
    patch = extract_patch(raw, raw_path=raw_path, max_bytes=max_patch_bytes)
    diff = raw.get("diff") or {}
    artifact_meta = diff.get("artifact") if isinstance(diff, dict) else None
    if isinstance(artifact_meta, dict) and artifact_meta.get("sha256"):
        return _cas_patch_artifact(artifact_meta, patch)
    return _inline_patch_artifact(patch)


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


def _validation_outcome(raw: dict[str, Any]) -> str:
    events = extract_validation(raw)
    if not events:
        merge = raw.get("merge_state") or {}
        if merge.get("merged"):
            return "merged without recorded checks"
        return "validation not collected"
    bits = [f"{e.get('type')}={e.get('result')}: {e.get('detail')}" for e in events]
    return "; ".join(bits)


def _software_payload(raw: dict[str, Any], patch_text: str) -> dict[str, str]:
    pull = raw.get("pull") or {}
    body = strip_bot_boilerplate(pull.get("body") or "")
    criteria = extract_section(body, ("acceptance", "criteria", "requirements")) or ""
    payload = {
        "issue_statement": _issue_statement(raw),
        "pre_change_state": str(pull.get("base_sha") or "unknown"),
        "implementation_patch": patch_text or "patch not collected",
        "validation_outcome": _validation_outcome(raw),
    }
    if criteria.strip():
        payload["acceptance_criteria"] = criteria.strip()
    return payload

def _completeness_score(n_events: int, pack: dict[str, Any], warnings: list[Any]) -> float:
    completeness = 0.4
    if n_events >= 3:
        completeness = 0.7
    if pack.get("complete"):
        completeness = 1.0
    elif pack.get("quarantine"):
        completeness = min(completeness, 0.5)
    if warnings:
        completeness = min(completeness, 0.8)
    return completeness


def _evidence_quality(raw: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, float]:
    pack = raw.get("snapshots") or {}
    if not isinstance(pack, dict):
        pack = {}
    warnings = (raw.get("collection_meta") or {}).get("warnings") or []
    has_review = any(e.get("event_type") in {"review", "review_comment"} for e in events)
    has_check = any(e.get("event_type") in {"check_run", "check_suite"} for e in events)
    snr = 0.5 + (0.2 if has_review else 0.0) + (0.2 if has_check else 0.0)
    repro = 1.0 if pack.get("complete") else (0.4 if pack else 0.2)
    return {
        "signal_to_noise": round(min(1.0, snr), 3),
        "reproducibility": round(repro, 3),
        "completeness": round(_completeness_score(len(events), pack, warnings), 3),
    }


def _pack_store_artifact(pack: dict[str, Any], store: ContentAddressedStore | None) -> dict[str, Any] | None:
    if store is None:
        return None
    digest = pack.get("store_sha256") or pack.get("pack_sha256")
    if not digest:
        return None
    if not store.exists(digest):
        return None
    return {
        "id": "object-pack",
        "sha256": digest,
        "media_type": "application/json",
        "byte_size": len(store.get_bytes(digest)),
        "availability": "remote",
        "reproduction_role": "object_pack",
        "uri": store.uri(digest),
    }


def _assemble_artifacts(
    raw: dict[str, Any],
    patch_art: dict[str, Any] | None,
    store: ContentAddressedStore | None,
) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    if patch_art:
        artifacts.append(patch_art)
    pack = raw.get("snapshots") or {}
    objects = pack.get("objects") or [] if isinstance(pack, dict) else []
    for index, obj in enumerate(objects):
        artifacts.append(_artifact_from_object(obj, index))
    pack_art = _pack_store_artifact(pack if isinstance(pack, dict) else {}, store)
    if pack_art:
        artifacts.append(pack_art)
    return artifacts


def _task_family(card: dict[str, Any]) -> str:
    task_family = str(card.get("trajectory_type") or "software")
    if task_family not in {"software", "research"}:
        return "software"
    return task_family


def _typed_payloads(raw: dict[str, Any], patch_text: str, task_family: str) -> dict[str, Any]:
    if task_family == "research":
        pull = raw.get("pull") or {}
        return {
            "research_payload": {
                "hypothesis": _issue_statement(raw),
                "initial_state": str(pull.get("base_sha") or "unknown"),
                "plan": strip_bot_boilerplate(pull.get("body") or "") or pull.get("title") or "unspecified",
                "measurements": _validation_outcome(raw),
            }
        }
    return {"software_payload": _software_payload(raw, patch_text)}


def _lineage(_raw: dict[str, Any], _source_id: str) -> dict[str, list[str]]:
    return {
        "supersedes": [],
        "reverts": [],
        "multi_pr_links": [],
    }

