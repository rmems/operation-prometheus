"""Emit schema-validated trajectory JSONL records."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cas import ContentAddressedStore
from .normalize import load_raw_record, normalize_record, resolve_source_license
from .normalize_v1 import V1NormalizeOptions, normalize_record_v1

logger = logging.getLogger("build_trajectory_jsonl")


@dataclass
class EmitJob:
    raw_dir: Path
    card: dict[str, Any]
    out_path: Path
    emit_v1: bool
    store: ContentAddressedStore | None
    max_patch_bytes: int
    pr_filter: set[int] | None
    validator: Any
    strict: bool


def _validate(record: dict, validator: Any) -> list[str]:
    if validator is None:
        return ["jsonschema not installed"]
    return [e.message for e in sorted(validator.iter_errors(record), key=lambda e: list(e.path))]


def _normalize_one(raw: dict[str, Any], path: Path, job: EmitJob) -> dict[str, Any]:
    source_license = resolve_source_license(raw.get("source") or {}, job.card)
    if not job.emit_v1:
        return normalize_record(
            raw,
            job.card,
            raw_path=path,
            max_patch_bytes=job.max_patch_bytes,
            source_license=source_license,
        )
    options = V1NormalizeOptions(
        artifact_store=job.store,
        max_patch_bytes=job.max_patch_bytes,
        source_license=source_license,
        raw_path=path,
    )
    return normalize_record_v1(raw, job.card, options)


def _dump_trajectory(traj: dict[str, Any], emit_v1: bool) -> str:
    dump_kwargs: dict = {"ensure_ascii": False, "separators": (",", ":")}
    if emit_v1:
        dump_kwargs["sort_keys"] = True
    return json.dumps(traj, **dump_kwargs)


def _log_ok(path_name: str, traj: dict[str, Any], emit_v1: bool) -> None:
    if emit_v1:
        logger.info(
            "OK %s (v1 disposition=%s events=%s)",
            path_name,
            traj.get("terminal_disposition"),
            len(traj.get("events") or []),
        )
        return
    logger.info(
        "OK %s (quality=%.2f training_use=%s)",
        path_name,
        traj.get("quality_score", 0),
        traj.get("training_use"),
    )


def _is_schema_failure(exc: Exception) -> bool:
    if not isinstance(exc, ValueError):
        return False
    return str(exc) == "schema validation failed"


def _emit_one(path: Path, job: EmitJob) -> str | None:
    raw = load_raw_record(path)
    pr = int((raw.get("source") or {}).get("pr_number") or 0)
    if job.pr_filter is not None and pr not in job.pr_filter:
        return None
    traj = _normalize_one(raw, path, job)
    schema_errors = _validate(traj, job.validator)
    if schema_errors:
        logger.error("%s schema errors:", path.name)
        for err in schema_errors:
            logger.error("  - %s", err)
        raise ValueError("schema validation failed")
    _log_ok(path.name, traj, job.emit_v1)
    return _dump_trajectory(traj, job.emit_v1)


def emit_all(job: EmitJob) -> tuple[list[str], int]:
    paths = sorted(job.raw_dir.glob("pr-*.json"))
    if not paths:
        logger.error("No pr-*.json files in %s", job.raw_dir)
        return [], 1
    lines: list[str] = []
    errors = 0
    for path in paths:
        try:
            line = _emit_one(path, job)
        except Exception as exc:
            errors += 1
            if not _is_schema_failure(exc):
                logger.error("Failed %s: %s", path.name, exc)
            if job.strict:
                return [], 1
            continue
        if line is not None:
            lines.append(line)
    return lines, errors


def write_jsonl(out_path: Path, lines: list[str]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp_path.replace(out_path)
    logger.info("Wrote %s trajectories → %s", len(lines), out_path)
