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


def _identity_token_ok(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    return ":" not in value


def _model_identity_error(model: Any) -> str | None:
    if not isinstance(model, dict):
        return "model is not an object"
    name_ok = _identity_token_ok(model.get("name"))
    tag_ok = _identity_token_ok(model.get("tag"))
    if name_ok and tag_ok:
        return None
    return "model identity is not canonical name/tag"


def _without_evidence_digest(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if key != "evidence_digest"}


def _digest_recomputes(report: dict[str, Any]) -> bool:
    clone = _without_evidence_digest(report)
    return sha256_json(clone) == report.get("evidence_digest")


def _missing_nonaccepted_reasons(report: dict[str, Any]) -> bool:
    if report.get("decision") == "accepted":
        return False
    return not report.get("reasons")


def _semantic_errors(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    identity = _model_identity_error(report.get("model"))
    if identity:
        errors.append(identity)
    if not _digest_recomputes(report):
        errors.append("evidence_digest does not recompute")
    if _missing_nonaccepted_reasons(report):
        errors.append("non-accepted report must carry machine-readable reasons")
    return errors


def _canonical_emitted_endpoint(value: Any) -> bool:
    canonical = canonical_loopback_endpoint(value)
    return canonical is not None and canonical == value


def _endpoint_errors(report: dict[str, Any]) -> list[str]:
    runtime = report.get("runtime") or {}
    probe = report.get("probe") or {}
    runtime_endpoint = runtime.get("endpoint")
    if not _canonical_emitted_endpoint(runtime_endpoint):
        return ["runtime endpoint is not a canonical loopback URL"]
    probe_endpoint = canonical_loopback_endpoint(probe.get("endpoint"))
    if runtime_endpoint != probe_endpoint:
        return ["runtime and probe endpoints disagree"]
    return []


def _fallback_flags_closed(report: dict[str, Any], fallback: dict[str, Any]) -> bool:
    if report.get("cloud_fallback_allowed") is not False:
        return False
    if fallback.get("cloud_fallback_allowed") is not False:
        return False
    return fallback.get("no_cloud") is True


def _fallback_surface_clean(fallback: dict[str, Any]) -> bool:
    if fallback.get("unsanitized_keys"):
        return False
    return not fallback.get("remote_endpoints")


def _fallback_errors(report: dict[str, Any]) -> list[str]:
    fallback = report.get("fallback_evidence") or {}
    flags_closed = _fallback_flags_closed(report, fallback)
    if flags_closed and _fallback_surface_clean(fallback):
        return []
    return ["fallback evidence is not a coherent disproof"]


def _missing_digest_names(digests: dict[str, Any]) -> list[str]:
    return [name for name in _REQUIRED_ACCEPTED_DIGESTS if name not in digests]


def _digest_errors(report: dict[str, Any]) -> list[str]:
    digests = report.get("input_digests") or {}
    missing = _missing_digest_names(digests)
    if missing:
        return [f"missing required input digests: {missing}"]
    return []


def _provider_config_dirty(config: Any) -> bool:
    rejected, quarantined = config_reasons(config)
    if rejected:
        return True
    return bool(quarantined)


def _provider_errors(report: dict[str, Any]) -> list[str]:
    provider = report.get("provider") or {}
    if provider.get("name") != "hermes-agent":
        return ["provider name is not hermes-agent"]
    if _provider_config_dirty(provider.get("config")):
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
