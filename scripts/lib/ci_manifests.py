"""Dataset manifest freshness and checksum checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from build_manifest import build_manifest, render

from .ci_io import JSONL_DIR, MANIFEST_DIR, ROOT, sha256_file


def _field(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if value is None:
        return ""
    return str(value)


def _missing_inputs(path: Path, card_path: Path, jsonl_path: Path) -> list[str]:
    if not card_path.is_file():
        return [f"manifest {path.name} is missing its JSONL or card"]
    if not jsonl_path.is_file():
        return [f"manifest {path.name} is missing its JSONL or card"]
    return []


def _stale_error(path: Path, generated: dict[str, Any], jsonl_path: Path) -> list[str]:
    if render(generated) == path.read_text(encoding="utf-8"):
        return []
    return [f"{path.name} is stale versus {jsonl_path.name}"]


def _sha_error(path: Path, committed: dict[str, Any], jsonl_path: Path) -> list[str]:
    declared = _field(committed, "sha256")
    if not declared:
        return []
    if declared == sha256_file(jsonl_path):
        return []
    return [f"{path.name} sha256 does not match {jsonl_path.name}"]


def _paths_for(path: Path) -> tuple[Path, Path]:
    name = path.name.removesuffix(".manifest.json")
    card_path = ROOT / "datasets" / "cards" / f"{name}.json"
    jsonl_path = JSONL_DIR / f"{name}.jsonl"
    return card_path, jsonl_path


def _generated_manifest(
    path: Path, committed: dict[str, Any], card_path: Path, jsonl_path: Path
) -> dict[str, Any]:
    name = path.name.removesuffix(".manifest.json")
    card = json.loads(card_path.read_text(encoding="utf-8"))
    return build_manifest(
        jsonl_path,
        card,
        created_at=_field(committed, "created_at"),
        created_by=_field(committed, "created_by"),
        name=name,
    )


def _one_manifest_error(path: Path) -> list[str]:
    committed = json.loads(path.read_text(encoding="utf-8"))
    card_path, jsonl_path = _paths_for(path)
    missing = _missing_inputs(path, card_path, jsonl_path)
    if missing:
        return missing
    generated = _generated_manifest(path, committed, card_path, jsonl_path)
    return [
        *_stale_error(path, generated, jsonl_path),
        *_sha_error(path, committed, jsonl_path),
    ]


def _missing_stem_errors(manifest_stems: set[str]) -> list[str]:
    jsonl_stems = {path.stem for path in JSONL_DIR.glob("*.jsonl")}
    card_stems = {path.stem for path in (ROOT / "datasets" / "cards").glob("*.json")}
    errors: list[str] = []
    for stem in sorted(jsonl_stems | card_stems):
        if stem not in manifest_stems:
            errors.append(f"dataset {stem} is missing its manifest")
    return errors


def manifest_errors() -> list[str]:
    manifest_stems = {
        path.name.removesuffix(".manifest.json")
        for path in MANIFEST_DIR.glob("*.manifest.json")
    }
    errors = _missing_stem_errors(manifest_stems)
    for path in sorted(MANIFEST_DIR.glob("*.manifest.json")):
        errors.extend(_one_manifest_error(path))
    return errors
