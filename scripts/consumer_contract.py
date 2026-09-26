#!/usr/bin/env python3
"""Agoge consumer contract: parse derivatives, sidecar provenance, no GPU."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_SCRIPTS = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.ci_contracts import ROOT, sha256_file  # noqa: E402

# This repository has a `datasets/` directory. Prefer the installed Hugging Face
# package when importing Agoge's parser.
sys.path = [entry for entry in sys.path if Path(entry or ".").resolve() != _REPO_ROOT]
try:
    from agoge_forger.datasets import normalize_row as agoge_normalize_row  # noqa: E402
except ImportError:
    agoge_normalize_row = None

CONSUMER_FIXTURES = ROOT / "tests" / "fixtures" / "consumer"
SIDECAR_SCHEMA = "agoge.consumer-sidecar.v1"


def _cuda_available() -> bool:
    if "torch" not in sys.modules:
        return False
    cuda = getattr(sys.modules["torch"], "cuda", None)
    if cuda is None:
        return False
    checker = getattr(cuda, "is_available", None)
    if not callable(checker):
        return False
    return bool(checker())


def _refuse_gpu() -> None:
    visible = os.environ.get("CUDA_VISIBLE_DEVICES")
    if visible not in (None, "", "-1"):
        raise RuntimeError(
            "consumer-contract must run with no GPU (CUDA_VISIBLE_DEVICES)"
        )
    if _cuda_available():
        raise RuntimeError("consumer-contract imported torch with CUDA available")


def _parser() -> Callable[..., dict[str, Any]]:
    if agoge_normalize_row is None:
        raise RuntimeError(
            "agoge_forger.datasets.normalize_row is required; checkout rmems/agoge-forger "
            "and set PYTHONPATH to its src/ directory"
        )
    return agoge_normalize_row


def _parse_timestamp(value: str) -> datetime:
    iso = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
    parsed = datetime.fromisoformat(iso)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _prometheus_meta(record: dict[str, Any]) -> dict[str, Any] | None:
    meta = record.get("_prometheus")
    if isinstance(meta, dict):
        return meta
    return None


def _prometheus_timestamp_errors(record: dict[str, Any]) -> list[str]:
    meta = _prometheus_meta(record)
    if meta is None or "event_timestamps" not in meta:
        return []
    raw = meta.get("event_timestamps")
    if not isinstance(raw, list):
        return ["_prometheus.event_timestamps is not a list"]
    errors: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            errors.append(f"malformed event timestamp {item!r}")
    return errors


def _prometheus_timestamps(record: dict[str, Any]) -> list[str]:
    meta = _prometheus_meta(record)
    if meta is None:
        return []
    raw = meta.get("event_timestamps") or []
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, str)]


def _payload_event_timestamps(record: dict[str, Any]) -> list[str]:
    events = record.get("events")
    if not isinstance(events, list):
        return []
    return [
        event["timestamp"]
        for event in events
        if isinstance(event, dict) and isinstance(event.get("timestamp"), str)
    ]


def _event_timestamps(record: dict[str, Any]) -> list[str]:
    # Payload events are the authoritative timeline. Metadata timestamps are
    # only used when the derivative has no events list, so the two copies of
    # the same ordered timeline are not concatenated.
    if isinstance(record.get("events"), list) and record.get("events"):
        return _payload_event_timestamps(record)
    return _prometheus_timestamps(record)


def future_event_errors(record: dict[str, Any]) -> list[str]:
    errors: list[str] = _prometheus_timestamp_errors(record)
    last: datetime | None = None
    for stamp in _event_timestamps(record):
        try:
            current = _parse_timestamp(stamp)
        except (ValueError, TypeError, OverflowError):
            errors.append(f"unparseable event timestamp {stamp}")
            continue
        if last is not None and current < last:
            errors.append(f"future-event leakage / events not ordered ({stamp})")
        last = current
    return errors


def load_derivative_rows(
    path: Path,
) -> tuple[list[tuple[int, dict[str, Any]]], list[str]]:
    rows: list[tuple[int, dict[str, Any]]] = []
    errors: list[str] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"{path.name}:{line_number} Invalid JSON: {exc}")
                continue
            if not isinstance(record, dict):
                errors.append(
                    f"{path.name}:{line_number} derivative row is not a JSON object"
                )
                continue
            rows.append((line_number, record))
    return rows, errors


def _source_identity(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(_REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _consumed_row(
    line_number: int,
    record: dict[str, Any],
    normalized: dict[str, Any],
) -> dict[str, Any]:
    payload = {key: value for key, value in record.items() if key != "_prometheus"}
    row = {
        "line": line_number,
        "format": _format_name(payload),
        "text_sha256": hashlib.sha256(normalized["text"].encode("utf-8")).hexdigest(),
    }
    meta = _prometheus_meta(record)
    source_trajectory_id = meta.get("source_trajectory_id") if meta is not None else None
    if isinstance(source_trajectory_id, str) and source_trajectory_id.strip():
        row["source_trajectory_id"] = source_trajectory_id
    return row


def _normalize_row(
    path: Path,
    line_number: int,
    record: dict[str, Any],
    normalize: Callable[..., dict[str, Any]],
) -> tuple[dict[str, Any] | None, str | None]:
    payload = {key: value for key, value in record.items() if key != "_prometheus"}
    try:
        normalized = normalize(payload, None, index=line_number)
    except ValueError as exc:
        return None, f"{path.name}:{line_number} {exc}"
    if not isinstance(normalized, dict) or not isinstance(normalized.get("text"), str):
        return None, f"{path.name}:{line_number} parser did not return a text row"
    return normalized, None


def consume(path: Path, normalize: Callable[..., dict[str, Any]]) -> dict[str, Any]:
    rows, errors = load_derivative_rows(path)
    consumed: list[dict[str, Any]] = []
    for line_number, record in rows:
        errors.extend(
            f"{path.name}:{line_number} {message}"
            for message in future_event_errors(record)
        )
        normalized, error = _normalize_row(path, line_number, record, normalize)
        if error is not None or normalized is None:
            if error is not None:
                errors.append(error)
            continue
        consumed.append(_consumed_row(line_number, record, normalized))
    sidecar = {
        "schema_version": SIDECAR_SCHEMA,
        "source_path": _source_identity(path),
        "source_sha256": sha256_file(path),
        "parser": "agoge_forger.datasets.normalize_row",
        "row_count": len(consumed),
        "rows": consumed,
        "errors": errors,
        "ok": not errors,
    }
    return sidecar


def _format_name(record: dict[str, Any]) -> str:
    if "messages" in record:
        return "messages"
    if "instruction" in record:
        return "instruction"
    if "text" in record:
        return "text"
    return "unknown"


def default_inputs() -> list[Path]:
    return sorted(CONSUMER_FIXTURES.glob("*.jsonl"))


def _sidecar_path(path: Path, out_dir: Path) -> Path:
    digest = hashlib.sha256(_source_identity(path).encode("utf-8")).hexdigest()[:12]
    return out_dir / f"{path.stem}-{digest}.sidecar.json"


def _write_sidecar(path: Path, sidecar: dict[str, Any], out_dir: Path) -> Path:
    out_path = _sidecar_path(path, out_dir)
    out_path.write_text(
        json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return out_path


def _print_sidecar(path: Path, sidecar: dict[str, Any], out_path: Path) -> bool:
    if sidecar["ok"]:
        print(f"  ✓ {path.name} -> {out_path}")
        return True
    print(f"  ✗ {path.name}")
    for error in sidecar["errors"]:
        print(f"    {error}")
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument(
        "--out-dir", type=Path, default=Path("reports/consumer-contract")
    )
    args = parser.parse_args(argv)
    _refuse_gpu()
    normalize = _parser()
    files = [path.resolve() for path in (args.files or default_inputs())]
    if not files:
        print("consumer-contract FAILED: no derivative JSONL files", file=sys.stderr)
        return 1
    args.out_dir.mkdir(parents=True, exist_ok=True)
    failed = False
    for path in files:
        sidecar = consume(path, normalize)
        out_path = _write_sidecar(path, sidecar, args.out_dir)
        if not _print_sidecar(path, sidecar, out_path):
            failed = True
    if failed:
        print("\nconsumer-contract FAILED.")
        return 1
    print("\nconsumer-contract passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
