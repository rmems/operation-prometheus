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


def _refuse_gpu() -> None:
    visible = os.environ.get("CUDA_VISIBLE_DEVICES")
    if visible not in (None, "", "-1"):
        raise RuntimeError(
            "consumer-contract must run with no GPU (CUDA_VISIBLE_DEVICES)"
        )
    if "torch" in sys.modules:
        torch = sys.modules["torch"]
        cuda = getattr(torch, "cuda", None)
        if (
            cuda is not None
            and callable(getattr(cuda, "is_available", None))
            and cuda.is_available()
        ):
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


def _event_timestamps(record: dict[str, Any]) -> list[str]:
    timestamps: list[str] = []
    meta = record.get("_prometheus")
    if isinstance(meta, dict):
        raw = meta.get("event_timestamps") or []
        if isinstance(raw, list):
            timestamps.extend(item for item in raw if isinstance(item, str))
    events = record.get("events")
    if isinstance(events, list):
        for event in events:
            if isinstance(event, dict) and isinstance(event.get("timestamp"), str):
                timestamps.append(event["timestamp"])
    return timestamps


def future_event_errors(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
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


def load_derivative_rows(path: Path) -> list[tuple[int, dict[str, Any]]]:
    rows: list[tuple[int, dict[str, Any]]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            if isinstance(record, dict):
                rows.append((line_number, record))
    return rows


def consume(path: Path, normalize: Callable[..., dict[str, Any]]) -> dict[str, Any]:
    rows = load_derivative_rows(path)
    consumed: list[dict[str, Any]] = []
    errors: list[str] = []
    for line_number, record in rows:
        errors.extend(
            f"{path.name}:{line_number} {message}"
            for message in future_event_errors(record)
        )
        payload = {key: value for key, value in record.items() if key != "_prometheus"}
        try:
            normalized = normalize(payload, None, index=line_number)
        except ValueError as exc:
            errors.append(f"{path.name}:{line_number} {exc}")
            continue
        if not isinstance(normalized, dict) or not isinstance(normalized.get("text"), str):
            errors.append(f"{path.name}:{line_number} parser did not return a text row")
            continue
        consumed.append(
            {
                "line": line_number,
                "format": _format_name(payload),
                "text_sha256": hashlib.sha256(
                    normalized["text"].encode("utf-8")
                ).hexdigest(),
            }
        )
    sidecar = {
        "schema_version": SIDECAR_SCHEMA,
        "source_path": str(path.resolve()),
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
        digest = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:12]
        out_path = args.out_dir / f"{path.stem}-{digest}.sidecar.json"
        out_path.write_text(
            json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        if sidecar["ok"]:
            print(f"  ✓ {path.name} -> {out_path}")
        else:
            failed = True
            print(f"  ✗ {path.name}")
            for error in sidecar["errors"]:
                print(f"    {error}")
    if failed:
        print("\nconsumer-contract FAILED.")
        return 1
    print("\nconsumer-contract passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
