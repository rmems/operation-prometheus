#!/usr/bin/env python3
"""Export accepted trajectory v1.1 records as Agoge observable-action rows.

The row shape is the already-merged consumer contract: ``messages`` objects
with string ``role`` and ``content``. ``_prometheus`` carries the source
trajectory id and ordered event timestamps. Hidden-reasoning fields are not
copied.
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

from lib.hermes_sanitize import strip_hidden_reasoning  # noqa: E402

_ROLE_BY_ACTOR = {
    "human": "user",
    "agent": "assistant",
    "application": "system",
}


def export_record(record: dict[str, Any]) -> dict[str, Any] | None:
    messages = _messages(record.get("events"))
    if not messages:
        return None
    row: dict[str, Any] = {"messages": messages}
    meta = _prometheus_meta(record)
    if meta:
        row["_prometheus"] = meta
    return row


def export_jsonl(path: Path) -> str:
    lines: list[str] = []
    for record in _load_records(path):
        row = export_record(record)
        if row is None:
            continue
        lines.append(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def _load_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.is_file() or path.stat().st_size == 0:
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parsed = json.loads(line)
        if isinstance(parsed, dict):
            records.append(parsed)
    return records


def _messages(events: Any) -> list[dict[str, str]]:
    if not isinstance(events, list):
        return []
    messages: list[dict[str, str]] = []
    for event in events:
        message = _message(event)
        if message is not None:
            messages.append(message)
    return messages


def _message(event: Any) -> dict[str, str] | None:
    if not isinstance(event, dict):
        return None
    role = _role(event)
    content = event.get("content")
    if role is None or not isinstance(content, str):
        return None
    cleaned = strip_hidden_reasoning(content)
    if not isinstance(cleaned, str) or not cleaned.strip():
        return None
    return {"role": role, "content": cleaned}


def _role(event: dict[str, Any]) -> str | None:
    event_type = event.get("event_type") or event.get("type")
    if event_type == "tool_call":
        return "tool"
    actor = event.get("actor")
    if not isinstance(actor, dict):
        return None
    return _ROLE_BY_ACTOR.get(str(actor.get("type") or ""))


def _prometheus_meta(record: dict[str, Any]) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    trajectory_id = record.get("trajectory_id")
    if isinstance(trajectory_id, str) and trajectory_id.strip():
        meta["source_trajectory_id"] = trajectory_id
    stamps = _event_timestamps(record.get("events"))
    if stamps:
        meta["event_timestamps"] = stamps
    return meta


def _event_timestamps(events: Any) -> list[str]:
    if not isinstance(events, list):
        return []
    stamps: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        stamp = event.get("timestamp")
        if isinstance(stamp, str) and stamp:
            stamps.append(stamp)
    return stamps


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    chunks = [export_jsonl(path) for path in args.inputs]
    text = "".join(chunks)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
