"""Shared v1 event spec used by review, check, timeline, and terminal builders."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .normalize_v1_append import _append_event, _event_id
from .normalize_v1_common import EventContext, EventDraft


@dataclass(frozen=True)
class EventSpec:
    kind: str
    stamp_parts: tuple[Any, ...]
    timestamp: Any
    actor: dict[str, str]
    event_type: str | None = None
    code_state: dict[str, str] | None = None
    content: str | None = None
    disposition: str | None = None
    evidence: list[str] | None = None


def _url_evidence(url: Any) -> list[str] | None:
    if not url:
        return None
    return [str(url)]


def _append_spec(ctx: EventContext, spec: EventSpec) -> None:
    event_type = spec.event_type or spec.kind
    _append_event(
        ctx.events,
        EventDraft(
            event_id=_event_id(spec.kind, ctx.source_id, *spec.stamp_parts),
            timestamp=spec.timestamp,
            actor=spec.actor,
            event_type=event_type,
            code_state=spec.code_state,
            content=spec.content,
            disposition=spec.disposition,
            evidence=spec.evidence,
        ),
    )
