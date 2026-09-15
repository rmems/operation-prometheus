#!/usr/bin/env python3
"""Corpus integrity: frozen inventory, hashes, duplicates, and mutable-release rules."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from build_manifest import build_manifest, render  # noqa: E402
from lib.ci_contracts import (  # noqa: E402
    INVENTORY_DIR,
    JSONL_DIR,
    MANIFEST_DIR,
    MUTABLE_SOURCE_STATES,
    MUTABLE_STATES,
    PARQUET_DIR,
    POSITIVE_RELEASE_STATES,
    RELEASE_MANIFEST,
    ROOT,
    candidate_index,
    candidate_reason_errors,
    inventory_file_hash_errors,
    load_inventory_candidates,
    load_jsonl,
    parquet_hash_errors,
    sha256_file,
    silent_truncation_errors,
    validation_evidence_errors,
)
from lib.eligibility_common import LEDGER_STATES  # noqa: E402
from lib.eligibility_existing import _load_existing_rows  # noqa: E402

REPORT_SCHEMA = "corpus_integrity_report_v1"


def _manifest_errors() -> list[str]:
    errors: list[str] = []
    jsonl_stems = {path.stem for path in JSONL_DIR.glob("*.jsonl")}
    card_stems = {path.stem for path in (ROOT / "datasets" / "cards").glob("*.json")}
    manifest_stems = {
        path.name.removesuffix(".manifest.json")
        for path in MANIFEST_DIR.glob("*.manifest.json")
    }
    for stem in sorted(jsonl_stems | card_stems):
        if stem not in manifest_stems:
            errors.append(f"dataset {stem} is missing its manifest")
    for path in sorted(MANIFEST_DIR.glob("*.manifest.json")):
        errors.extend(_one_manifest_error(path))
    return errors


def _one_manifest_error(path: Path) -> list[str]:
    committed = json.loads(path.read_text(encoding="utf-8"))
    name = path.name.removesuffix(".manifest.json")
    card_path = ROOT / "datasets" / "cards" / f"{name}.json"
    jsonl_path = JSONL_DIR / f"{name}.jsonl"
    if not card_path.is_file() or not jsonl_path.is_file():
        return [f"manifest {path.name} is missing its JSONL or card"]
    card = json.loads(card_path.read_text(encoding="utf-8"))
    generated = build_manifest(
        jsonl_path,
        card,
        created_at=str(committed.get("created_at") or ""),
        created_by=str(committed.get("created_by") or ""),
        name=name,
    )
    errors: list[str] = []
    if render(generated) != path.read_text(encoding="utf-8"):
        errors.append(f"{path.name} is stale versus {jsonl_path.name}")
    declared = str(committed.get("sha256") or "")
    if declared and declared != sha256_file(jsonl_path):
        errors.append(f"{path.name} sha256 does not match {jsonl_path.name}")
    return errors


def _duplicate_report(inventory_dir: Path) -> dict[str, Any]:
    path = inventory_dir / "duplicates.jsonl"
    rows = [row for _, row in load_jsonl(path)] if path.is_file() else []
    return {
        "path": path.relative_to(ROOT).as_posix() if path.is_file() else None,
        "group_count": len(rows),
        "exact_count": sum(1 for row in rows if row.get("exact") is True),
        "near_count": sum(1 for row in rows if row.get("exact") is False),
        "kinds": sorted({str(row.get("kind")) for row in rows}),
        "groups": rows,
    }


def _unresolved_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "file": row["file"],
        "line": row["line"],
        "record_id": row["record_id"],
        "repo": row["repo"],
        "pr_number": row["pr_number"],
        "reason": "not_in_frozen_inventory",
    }


def _resolved_row(
    row: dict[str, Any], candidate: dict[str, Any], state: str
) -> dict[str, Any]:
    return {
        "file": row["file"],
        "line": row["line"],
        "record_id": row["record_id"],
        "candidate_id": candidate.get("candidate_id"),
        "state": state,
    }


def _mutable_state_errors(
    row: dict[str, Any], candidate: dict[str, Any]
) -> tuple[list[str], str]:
    state = candidate.get("state")
    source_state = candidate.get("source_state")
    errors: list[str] = []
    if state is None:
        errors.append(
            f"{row['file']}:{row['line']} maps to candidate "
            f"{candidate.get('candidate_id')} with no ledger state"
        )
        state = "unknown"
    if state in MUTABLE_STATES or source_state in MUTABLE_SOURCE_STATES:
        errors.append(
            f"{row['file']}:{row['line']} maps to mutable candidate "
            f"{candidate.get('candidate_id')} ({state}/{source_state}) and cannot enter a positive release"
        )
    if state in POSITIVE_RELEASE_STATES and source_state in MUTABLE_SOURCE_STATES:
        errors.append(
            f"{row['file']}:{row['line']} is included_positive but source_state is {source_state}"
        )
    return errors, str(state)


def _resolve_records(
    candidates: list[dict[str, Any]],
) -> tuple[list[str], dict[str, int], list[dict[str, Any]], list[dict[str, Any]]]:
    index = candidate_index(candidates)
    errors: list[str] = []
    resolved: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for row in _load_existing_rows(ROOT):
        key = (str(row["repo"]).casefold(), int(row["pr_number"]))
        candidate = index.get(key)
        if candidate is None:
            unresolved.append(_unresolved_row(row))
            continue
        mutable_errors, state = _mutable_state_errors(row, candidate)
        errors.extend(mutable_errors)
        resolved.append(_resolved_row(row, candidate, state))
    return errors, Counter(item["state"] for item in resolved), resolved, unresolved


def _record_hygiene_errors() -> list[str]:
    errors: list[str] = []
    for path in sorted(JSONL_DIR.glob("*.jsonl")):
        for line_number, record in load_jsonl(path):
            for message in silent_truncation_errors(record):
                errors.append(f"{path.name}:{line_number} {message}")
            for message in validation_evidence_errors(record):
                errors.append(f"{path.name}:{line_number} {message}")
    return errors


def _candidate_reason_errors(candidates: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for candidate in candidates:
        errors.extend(candidate_reason_errors(candidate))
    return errors


def _report_counts(payload: dict[str, Any]) -> dict[str, Any]:
    state_counts: Counter = payload["state_counts"]
    duplicates: dict[str, Any] = payload["duplicates"]
    return {
        "candidates": len(payload["candidates"]),
        "jsonl_records": len(_load_existing_rows(ROOT)),
        "resolved_jsonl_records": len(payload["resolved"]),
        "unresolved_jsonl_records": len(payload["unresolved"]),
        "ledger_state_counts": dict(sorted(state_counts.items())),
        "resolved_state_counts": dict(sorted(payload["resolved_states"].items())),
        "duplicate_groups": duplicates["group_count"],
    }


def _inventory_label(inventory_dir: Path) -> str:
    if inventory_dir.is_relative_to(ROOT):
        return inventory_dir.relative_to(ROOT).as_posix()
    return str(inventory_dir)


def _write_corpus_outputs(
    out_dir: Path, report: dict[str, Any], duplicates: dict[str, Any]
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "corpus-integrity-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (out_dir / "duplicates.jsonl").write_text(
        "".join(
            json.dumps(row, ensure_ascii=False) + "\n" for row in duplicates["groups"]
        ),
        encoding="utf-8",
    )
    (out_dir / "unresolved.jsonl").write_text(
        "".join(
            json.dumps(row, ensure_ascii=False) + "\n"
            for row in report["unresolved_jsonl"]
        ),
        encoding="utf-8",
    )


def build_report(
    inventory_dir: Path, out_dir: Path | None, *, strict_resolve: bool = False
) -> dict[str, Any]:
    candidates = load_inventory_candidates(inventory_dir)
    state_counts = Counter(str(row.get("state")) for row in candidates)
    resolve_errors, resolved_states, resolved, unresolved = _resolve_records(candidates)
    errors = [
        *inventory_file_hash_errors(inventory_dir),
        *_manifest_errors(),
        *parquet_hash_errors(RELEASE_MANIFEST, PARQUET_DIR),
        *resolve_errors,
        *_candidate_reason_errors(candidates),
        *_record_hygiene_errors(),
    ]
    if strict_resolve:
        for row in unresolved:
            errors.append(
                f"{row['file']}:{row['line']} does not resolve to the frozen inventory "
                f"({row['repo']}#{row['pr_number']})"
            )
    duplicates = _duplicate_report(inventory_dir)
    report = {
        "schema_version": REPORT_SCHEMA,
        "inventory_dir": _inventory_label(inventory_dir),
        "counts": _report_counts(
            {
                "candidates": candidates,
                "resolved": resolved,
                "unresolved": unresolved,
                "state_counts": state_counts,
                "resolved_states": resolved_states,
                "duplicates": duplicates,
            }
        ),
        "quality": {
            "included_positive": state_counts.get("included_positive", 0),
            "included_negative": state_counts.get("included_negative", 0),
            "quarantined": state_counts.get("quarantined", 0),
            "excluded": state_counts.get("excluded", 0),
            "watchlist_open": state_counts.get("watchlist_open", 0),
        },
        "exclusion_report": {
            state: state_counts.get(state, 0) for state in sorted(LEDGER_STATES)
        },
        "duplicates": {
            "path": duplicates["path"],
            "group_count": duplicates["group_count"],
            "exact_count": duplicates["exact_count"],
            "near_count": duplicates["near_count"],
            "kinds": duplicates["kinds"],
        },
        "unresolved_jsonl": unresolved,
        "errors": errors,
        "ok": not errors,
    }
    if out_dir is not None:
        _write_corpus_outputs(out_dir, report, duplicates)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory-dir", type=Path, default=INVENTORY_DIR)
    parser.add_argument(
        "--out-dir", type=Path, default=Path("reports/corpus-integrity")
    )
    parser.add_argument(
        "--strict-resolve",
        action="store_true",
        help="Fail when a JSONL trajectory is absent from the frozen inventory",
    )
    args = parser.parse_args(argv)
    report = build_report(
        args.inventory_dir.resolve(), args.out_dir, strict_resolve=args.strict_resolve
    )
    print(
        json.dumps(
            {k: report[k] for k in ("schema_version", "counts", "quality", "ok")},
            indent=2,
        )
    )
    if report["errors"]:
        print("\ncorpus-integrity FAILED:")
        for error in report["errors"]:
            print(f"  {error}")
        return 1
    print("\ncorpus-integrity passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
