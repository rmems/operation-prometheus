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


def _probe_endpoint_reasons(
    probe: dict[str, Any], candidate: dict[str, Any]
) -> tuple[list[str], list[str]]:
    probe_endpoint = canonical_loopback_endpoint(probe.get("endpoint"))
    if probe_endpoint is None:
        return [], ["probe_endpoint_missing"]
    if canonical_loopback_endpoint(candidate.get("endpoint")) != probe_endpoint:
        return [], ["probe_endpoint_mismatch"]
    return [], []


def _probe_runtime_reasons(
    probe: dict[str, Any], candidate: dict[str, Any]
) -> tuple[list[str], list[str]]:
    """Probe must report the exact same supported runtime + a version."""
    probe_runtime = _text(probe.get("runtime"))
    if probe_runtime is None or not _text(probe.get("version")):
        return [], ["probe_runtime_missing"]
    if probe_runtime != _text(candidate.get("runtime")):
        return ["probe_runtime_mismatch"], []
    return [], []


def _probe_timestamp_reasons(
    probe: dict[str, Any], candidate: dict[str, Any]
) -> tuple[list[str], list[str]]:
    probed_at = probe.get("probed_at")
    if not parse_rfc3339_tz(probed_at):
        return [], ["probe_timestamp_missing"]
    declared_at = candidate.get("probed_at")
    if not isinstance(declared_at, str) or not declared_at.strip():
        return [], ["probe_timestamp_missing"]
    if not parse_rfc3339_tz(declared_at):
        return [], ["probe_timestamp_invalid"]
    if declared_at.strip() != probed_at.strip():
        return [], ["probe_timestamp_mismatch"]
    return [], []


def _meta_reasons(
    probe: dict[str, Any], candidate: dict[str, Any]
) -> tuple[list[str], list[str]]:
    """Loopback endpoint / runtime identity / probe timestamp."""
    rejected, quarantined = [], []
    for check in (
        _probe_endpoint_reasons,
        _probe_runtime_reasons,
        _probe_timestamp_reasons,
    ):
        rej, quar = check(probe, candidate)
        rejected += rej
        quarantined += quar
    return rejected, quarantined


def _matching_rows(
    probe: dict[str, Any], model: str
) -> list[dict[str, Any]]:
    return [
        entry
        for entry in _models_entries(probe)
        if _text(entry.get("name")) == model
    ]


def _duplicate_reasons(
    matches: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    digests = {_text(entry.get("digest")) for entry in matches}
    if len(digests) > 1:
        return ["probe_digest_conflict"], []
    return [], ["probe_duplicate"]


def _declared_digest_reasons(candidate: dict[str, Any]) -> list[str] | None:
    if ollama_digest_or_none(candidate.get("ollama_digest")) is not None:
        return None
    if _text(candidate.get("ollama_digest")) is None:
        return ["digest_missing"]
    return ["digest_invalid"]


def _digest_match_reasons(
    entry: dict[str, Any], candidate: dict[str, Any]
) -> tuple[list[str], list[str]]:
    invalid = _declared_digest_reasons(candidate)
    if invalid is not None:
        return [], invalid
    if _text(entry.get("digest")) != candidate["ollama_digest"].strip():
        return ["probe_digest_mismatch"], []
    return [], []


def _identity_reasons(
    model: str, probe: dict[str, Any], candidate: dict[str, Any]
) -> tuple[list[str], list[str]]:
    """Exactly one matching model row with a valid, matching digest."""
    matches = _matching_rows(probe, model)
    if not matches:
        return [], ["probe_evidence_missing"]
    if len(matches) > 1:
        return _duplicate_reasons(matches)
    return _digest_match_reasons(matches[0], candidate)


def _quantization_reasons(
    candidate: dict[str, Any], show: dict[str, Any]
) -> tuple[list[str], list[str]]:
    details = show.get("details")
    observed = _text(show.get("quantization_level"))
    if observed is None and isinstance(details, dict):
        observed = _text(details.get("quantization_level"))
    declared = _text(candidate.get("quantization"))
    if observed is None:
        return [], ["probe_quantization_missing"]
    if declared is None or observed != declared:
        return ["probe_quantization_mismatch"], []
    return [], []


def _license_reasons(
    rights_license: str | None, show: dict[str, Any]
) -> list[str]:
    probe_license = show.get("license")
    if _text(probe_license) is None:
        return []
    if rights_license is None or normalize_license_id(
        probe_license
    ) != rights_license:
        return ["probe_license_conflict"]
    return []


def _show_reasons(
    model: str,
    candidate: dict[str, Any],
    probe: dict[str, Any],
    rights_license: str | None,
) -> tuple[list[str], list[str]]:
    """Cross-check `/api/show` details against the candidate/rights row."""
    show = _show_entry(probe, model)
    if show is None:
        return [], ["probe_evidence_missing"]
    rejected, quarantined = _quantization_reasons(candidate, show)
    rejected += _license_reasons(rights_license, show)
    return rejected, quarantined


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
