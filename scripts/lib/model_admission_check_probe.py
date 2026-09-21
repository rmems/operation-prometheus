"""Ollama probe binding checks for local-model admission."""

from __future__ import annotations

from typing import Any

from .model_admission_evidence import (
    canonical_loopback_endpoint,
    ollama_digest_or_none,
    parse_rfc3339_tz,
)
from .model_admission_rights import normalize_license_id

PROBE_SCHEMA_VERSION = "ollama_probe_v1"


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _models_entries(probe: dict[str, Any]) -> list[dict[str, Any]]:
    models = probe.get("models")
    if not isinstance(models, list):
        return []
    return [entry for entry in models if isinstance(entry, dict)]


def _show_entry(probe: dict[str, Any], model: str) -> dict[str, Any] | None:
    show = probe.get("show")
    if not isinstance(show, dict):
        return None
    entry = show.get(model)
    return entry if isinstance(entry, dict) else None


def _schema_reasons(probe: dict[str, Any]) -> list[str]:
    version = probe.get("schema_version")
    if _text(version) is None:
        return ["probe_schema_missing"]
    if version != PROBE_SCHEMA_VERSION:
        return ["probe_schema_invalid"]
    return []


def _meta_reasons(
    probe: dict[str, Any], candidate: dict[str, Any]
) -> tuple[list[str], list[str]]:
    """Loopback endpoint / runtime / runtime-version / probe timestamp."""
    rejected, quarantined = [], []
    probe_endpoint = canonical_loopback_endpoint(probe.get("endpoint"))
    if probe_endpoint is None:
        quarantined.append("probe_endpoint_missing")
    elif canonical_loopback_endpoint(candidate.get("endpoint")) != probe_endpoint:
        quarantined.append("probe_endpoint_mismatch")
    if _text(probe.get("runtime")) is None or not _text(probe.get("version")):
        quarantined.append("probe_runtime_missing")
    probed_at = probe.get("probed_at")
    if not parse_rfc3339_tz(probed_at):
        quarantined.append("probe_timestamp_missing")
    else:
        declared_at = candidate.get("probed_at")
        if not isinstance(declared_at, str) or not declared_at.strip():
            quarantined.append("probe_timestamp_missing")
        elif not parse_rfc3339_tz(declared_at):
            quarantined.append("probe_timestamp_invalid")
        elif declared_at.strip() != probed_at.strip():
            quarantined.append("probe_timestamp_mismatch")
    return rejected, quarantined


def _identity_reasons(
    model: str, probe: dict[str, Any], candidate: dict[str, Any]
) -> tuple[list[str], list[str]]:
    """Exactly one matching model row with a valid, matching digest."""
    matches = [
        entry
        for entry in _models_entries(probe)
        if _text(entry.get("name")) == model
    ]
    if not matches:
        return [], ["probe_evidence_missing"]
    digests = {_text(entry.get("digest")) for entry in matches}
    if len(matches) > 1:
        if len(digests) > 1:
            return ["probe_digest_conflict"], []
        return [], ["probe_duplicate"]
    declared = ollama_digest_or_none(candidate.get("ollama_digest"))
    if declared is None:
        if _text(candidate.get("ollama_digest")) is None:
            return [], ["digest_missing"]
        return [], ["digest_invalid"]
    observed = _text(matches[0].get("digest"))
    if observed != declared:
        return ["probe_digest_mismatch"], []
    return [], []


def _show_reasons(
    model: str,
    candidate: dict[str, Any],
    probe: dict[str, Any],
    rights_license: str | None,
) -> tuple[list[str], list[str]]:
    show = _show_entry(probe, model)
    if show is None:
        return [], ["probe_evidence_missing"]
    details = show.get("details")
    observed_level = _text(show.get("quantization_level"))
    if observed_level is None and isinstance(details, dict):
        observed_level = _text(details.get("quantization_level"))
    declared_level = _text(candidate.get("quantization"))
    if observed_level is None:
        return [], ["probe_quantization_missing"]
    if declared_level is None or observed_level != declared_level:
        return ["probe_quantization_mismatch"], []
    probe_license = show.get("license")
    if _text(probe_license) is not None:
        if rights_license is None or normalize_license_id(
            probe_license
        ) != rights_license:
            return ["probe_license_conflict"], []
    return [], []


def probe_reasons(
    model: str,
    candidate: dict[str, Any],
    probe: dict[str, Any] | None,
    rights_license: str | None,
) -> tuple[list[str], list[str]]:
    if not isinstance(probe, dict):
        return [], ["probe_evidence_missing"]
    rejected, quarantined = [], []

    rejected += _schema_reasons(probe)
    rej, quar = _meta_reasons(probe, candidate)
    rejected += rej
    quarantined += quar
    rej, quar = _identity_reasons(model, probe, candidate)
    rejected += rej
    quarantined += quar
    rej, quar = _show_reasons(model, candidate, probe, rights_license)
    rejected += rej
    quarantined += quar
    return rejected, quarantined
