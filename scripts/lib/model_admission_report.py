"""Semantic validator for emitted ``local_model_admission_v1`` reports.

JSON Schema (``schemas/local_model_admission.schema.json``) validates shape
and the conditional accepted constraints; this module adds the relational
invariants a schema cannot express — combined identity consistency, evidence
digest recomputation, endpoint/fallback agreement, and provider-config
sanitization — so both the emitting CLI and downstream consumers (#74) run
the same contract.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model_admission_check_fields import config_reasons
from .model_admission_evidence import (
    canonical_loopback_endpoint,
    sha256_json,
)

_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "schemas"
    / "local_model_admission.schema.json"
)
_REQUIRED_ACCEPTED_DIGESTS = ("admissions", "rights", "probe")


def _schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _schema_errors(report: dict[str, Any]) -> list[str]:
    try:
        import jsonschema
    except ImportError:
        return ["jsonschema is required for report validation"]
    validator = jsonschema.validators.validator_for(_schema())(_schema())
    return [error.message for error in validator.iter_errors(report)]


def _semantic_errors(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    model = report.get("model")
    if not isinstance(model, dict):
        errors.append("model is not an object")
    else:
        name, tag = model.get("name"), model.get("tag")
        if (
            not isinstance(name, str)
            or not name
            or ":" in name
            or not isinstance(tag, str)
            or not tag
            or ":" in tag
        ):
            errors.append("model identity is not canonical name/tag")
    clone = {k: v for k, v in report.items() if k != "evidence_digest"}
    if sha256_json(clone) != report.get("evidence_digest"):
        errors.append("evidence_digest does not recompute")
    if report.get("decision") != "accepted" and not report.get("reasons"):
        errors.append("non-accepted report must carry machine-readable reasons")
    return errors


def _endpoint_errors(report: dict[str, Any]) -> list[str]:
    runtime = report.get("runtime") or {}
    probe = report.get("probe") or {}
    runtime_endpoint = canonical_loopback_endpoint(runtime.get("endpoint"))
    probe_endpoint = canonical_loopback_endpoint(probe.get("endpoint"))
    if runtime_endpoint is None or runtime_endpoint != runtime.get("endpoint"):
        return ["runtime endpoint is not a canonical loopback URL"]
    if runtime_endpoint != probe_endpoint:
        return ["runtime and probe endpoints disagree"]
    return []


def _fallback_errors(report: dict[str, Any]) -> list[str]:
    fallback = report.get("fallback_evidence") or {}
    coherent = (
        report.get("cloud_fallback_allowed") is False
        and fallback.get("cloud_fallback_allowed") is False
        and fallback.get("no_cloud") is True
        and not fallback.get("unsanitized_keys")
        and not fallback.get("remote_endpoints")
    )
    return [] if coherent else ["fallback evidence is not a coherent disproof"]


def _digest_errors(report: dict[str, Any]) -> list[str]:
    digests = report.get("input_digests") or {}
    missing = [name for name in _REQUIRED_ACCEPTED_DIGESTS if name not in digests]
    if missing:
        return [f"missing required input digests: {missing}"]
    return []


def _provider_errors(report: dict[str, Any]) -> list[str]:
    provider = report.get("provider") or {}
    if provider.get("name") != "hermes-agent":
        return ["provider name is not hermes-agent"]
    rejected, quarantined = config_reasons(provider.get("config"))
    if rejected or quarantined:
        return ["provider_config fails sanitization"]
    return []


def _accepted_errors(report: dict[str, Any]) -> list[str]:
    """Relational invariants that must hold for decision == accepted."""
    errors = _semantic_errors(report)
    for check in (
        _endpoint_errors,
        _fallback_errors,
        _digest_errors,
        _provider_errors,
    ):
        errors += check(report)
    return errors


def validate_decision_report(report: dict[str, Any]) -> list[str]:
    """Return validation errors; empty means the report satisfies the contract."""
    if not isinstance(report, dict):
        return ["report is not an object"]
    errors = _schema_errors(report)
    if report.get("decision") == "accepted":
        errors += _accepted_errors(report)
    return errors
