"""Recorded-probe checks for local-model admission (offline fixtures)."""

from __future__ import annotations

from typing import Any


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _models_entry(probe: dict[str, Any], model: str) -> dict[str, Any] | None:
    models = probe.get("models")
    if not isinstance(models, list):
        return None
    return next(
        (
            row
            for row in models
            if isinstance(row, dict) and row.get("name") == model
        ),
        None,
    )


def _show_entry(probe: dict[str, Any], model: str) -> dict[str, Any] | None:
    show = probe.get("show")
    entry = show.get(model) if isinstance(show, dict) else None
    return entry if isinstance(entry, dict) else None


def _digest_reasons(
    candidate: dict[str, Any], entry: dict[str, Any]
) -> tuple[list[str], list[str]]:
    candidate_digest = _text(candidate.get("ollama_digest"))
    if candidate_digest is None:
        return [], ["digest_missing"]
    if candidate_digest != _text(entry.get("digest")):
        return ["probe_digest_mismatch"], []
    return [], []


def _quantization_reasons(
    candidate: dict[str, Any], show_entry: dict[str, Any]
) -> tuple[list[str], list[str]]:
    candidate_quant = _text(candidate.get("quantization"))
    if candidate_quant is None:
        return [], ["quantization_missing"]
    details = show_entry.get("details")
    probe_quant = (
        _text(details.get("quantization_level"))
        if isinstance(details, dict)
        else None
    )
    if probe_quant is not None and candidate_quant != probe_quant:
        return ["quantization_mismatch"], []
    return [], []


def probe_reasons(
    model: str, candidate: dict[str, Any], probe: Any
) -> tuple[list[str], list[str]]:
    """Return (rejected, quarantined) for the probe-evidence binding."""
    if not isinstance(probe, dict):
        return [], ["probe_evidence_missing"]
    entry = _models_entry(probe, model)
    show_entry = _show_entry(probe, model)
    if entry is None or show_entry is None:
        return [], ["probe_evidence_missing"]

    rejected: list[str] = []
    quarantined: list[str] = []
    probe_endpoint = _text(probe.get("endpoint"))
    if probe_endpoint and probe_endpoint != _text(candidate.get("endpoint")):
        quarantined.append("probe_endpoint_mismatch")
    for r, q in (
        _digest_reasons(candidate, entry),
        _quantization_reasons(candidate, show_entry),
    ):
        rejected += r
        quarantined += q
    return rejected, quarantined
