"""Local-model admission evaluation for Operation Prometheus.

Evaluates proposed local-model providers (e.g. Ollama-served Hermes weights)
against frozen rights evidence and a recorded loopback probe. Fail-closed:
every candidate lands in ``accepted``, ``quarantined`` (evidence incomplete)
or ``rejected`` (evidence contradictory) with explicit reason codes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .model_admission_evidence import (
    endpoint_host,
    is_loopback_endpoint,
    remote_config_endpoints,
    sha256_json,
    sha256_or_none,
    unsanitized_config_keys,
)
from .model_admission_rights import (
    classify_license_family,
    normalize_license_id,
)

SCHEMA_VERSION = "local_model_admission_v1"
SUPPORTED_RUNTIME = "ollama"
DISPOSITIONS = ("accepted", "quarantined", "rejected")

REJECT_REASONS = frozenset(
    {
        "candidate_not_object",
        "model_missing",
        "rights_conflict",
        "terms_digest_mismatch",
        "probe_digest_mismatch",
        "quantization_mismatch",
        "runtime_unsupported",
        "endpoint_not_loopback",
        "provider_config_unsanitized",
        "cloud_endpoint_detected",
    }
)
QUARANTINE_REASONS = frozenset(
    {
        "rights_evidence_missing",
        "license_missing",
        "license_unknown",
        "terms_digest_missing",
        "probe_evidence_missing",
        "probe_endpoint_mismatch",
        "digest_missing",
        "quantization_missing",
        "runtime_missing",
        "endpoint_missing",
        "endpoint_invalid",
        "provider_config_missing",
        "no_cloud_evidence_missing",
        "probe_timestamp_missing",
        "probe_timestamp_invalid",
    }
)

_EVIDENCE_FIELDS = (
    "model",
    "ollama_digest",
    "quantization",
    "runtime",
    "endpoint",
    "license",
    "terms_sha256",
    "probed_at",
)


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _timestamp_ok(value: Any) -> bool | None:
    """True for a parseable RFC3339 timestamp, None when absent."""
    if value is None:
        return None
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _rights_reasons(
    candidate_license: str | None,
    rights_row: Any,
) -> tuple[list[str], list[str], str, str | None]:
    rejected: list[str] = []
    quarantined: list[str] = []
    if not isinstance(rights_row, dict):
        quarantined.append("rights_evidence_missing")
        return rejected, quarantined, "missing", None

    rights_license = normalize_license_id(rights_row.get("license"))
    custom = rights_row.get("custom_license")
    has_custom = isinstance(custom, dict) and bool(
        sha256_or_none(custom.get("text_sha256"))
    )
    if (
        isinstance(custom, dict)
        and normalize_license_id(custom.get("identifier"))
        and normalize_license_id(custom.get("identifier")) != rights_license
    ):
        rejected.append("rights_conflict")

    if rights_license is None:
        quarantined.append("license_missing")
        family = "missing"
    else:
        family = classify_license_family(
            rights_license, has_custom_evidence=has_custom
        )
        if family == "unknown":
            quarantined.append("license_unknown")

    if candidate_license is None:
        quarantined.append("license_missing")
    elif rights_license is not None and candidate_license != rights_license:
        rejected.append("rights_conflict")

    terms = sha256_or_none(rights_row.get("terms_sha256"))
    if terms is None:
        quarantined.append("terms_digest_missing")
    elif (
        isinstance(custom, dict)
        and sha256_or_none(custom.get("text_sha256"))
        and sha256_or_none(custom.get("text_sha256")) != terms
    ):
        rejected.append("terms_digest_mismatch")
    return rejected, quarantined, family, terms


def _probe_reasons(
    model: str,
    candidate: dict[str, Any],
    probe: Any,
) -> tuple[list[str], list[str]]:
    rejected: list[str] = []
    quarantined: list[str] = []
    if not isinstance(probe, dict):
        return rejected, ["probe_evidence_missing"]
    models = probe.get("models")
    entry = next(
        (
            row
            for row in (models if isinstance(models, list) else [])
            if isinstance(row, dict) and row.get("name") == model
        ),
        None,
    )
    show = probe.get("show")
    show_entry = show.get(model) if isinstance(show, dict) else None
    if entry is None or not isinstance(show_entry, dict):
        return rejected, ["probe_evidence_missing"]

    probe_endpoint = _text(probe.get("endpoint"))
    if probe_endpoint and probe_endpoint != _text(candidate.get("endpoint")):
        quarantined.append("probe_endpoint_mismatch")

    candidate_digest = _text(candidate.get("ollama_digest"))
    if candidate_digest is None:
        quarantined.append("digest_missing")
    elif candidate_digest != _text(entry.get("digest")):
        rejected.append("probe_digest_mismatch")

    details = show_entry.get("details")
    probe_quant = (
        _text(details.get("quantization_level"))
        if isinstance(details, dict)
        else None
    )
    candidate_quant = _text(candidate.get("quantization"))
    if candidate_quant is None:
        quarantined.append("quantization_missing")
    elif probe_quant is not None and candidate_quant != probe_quant:
        rejected.append("quantization_mismatch")

    return rejected, quarantined


def _config_reasons(config: Any) -> tuple[list[str], list[str]]:
    rejected: list[str] = []
    quarantined: list[str] = []
    if not isinstance(config, dict):
        return rejected, ["provider_config_missing"]
    if unsanitized_config_keys(config):
        rejected.append("provider_config_unsanitized")
    if remote_config_endpoints(config):
        rejected.append("cloud_endpoint_detected")
    if config.get("no_cloud") is not True:
        quarantined.append("no_cloud_evidence_missing")
    return rejected, quarantined


def evaluate_admission(
    candidate: Any,
    *,
    rights: Any,
    probe: Any,
) -> dict[str, Any]:
    """Classify one admission candidate as accepted/quarantined/rejected."""
    if not isinstance(candidate, dict):
        return {
            "model": None,
            "disposition": "rejected",
            "reason_codes": ["candidate_not_object"],
            "license_family": "missing",
            "evidence": {},
            "evidence_digest": None,
        }

    rejected: list[str] = []
    quarantined: list[str] = []
    model = _text(candidate.get("model"))
    if model is None:
        rejected.append("model_missing")
        model = ""

    r_rej, r_quar, family, terms = _rights_reasons(
        normalize_license_id(candidate.get("license")),
        (rights.get("models") or {}).get(model)
        if isinstance(rights, dict)
        else None,
    )
    rejected += r_rej
    quarantined += r_quar

    if model:
        p_rej, p_quar = _probe_reasons(model, candidate, probe)
        rejected += p_rej
        quarantined += p_quar

    runtime = _text(candidate.get("runtime"))
    if runtime is None:
        quarantined.append("runtime_missing")
    elif runtime != SUPPORTED_RUNTIME:
        rejected.append("runtime_unsupported")

    endpoint = candidate.get("endpoint")
    if _text(endpoint) is None:
        quarantined.append("endpoint_missing")
    elif endpoint_host(endpoint) is None:
        quarantined.append("endpoint_invalid")
    elif not is_loopback_endpoint(endpoint):
        rejected.append("endpoint_not_loopback")

    c_rej, c_quar = _config_reasons(candidate.get("provider_config"))
    rejected += c_rej
    quarantined += c_quar

    stamp = _timestamp_ok(candidate.get("probed_at"))
    if stamp is None:
        quarantined.append("probe_timestamp_missing")
    elif stamp is False:
        quarantined.append("probe_timestamp_invalid")

    evidence = {
        "model": model or None,
        "ollama_digest": _text(candidate.get("ollama_digest")),
        "quantization": _text(candidate.get("quantization")),
        "runtime": runtime,
        "endpoint": _text(endpoint),
        "license": normalize_license_id(candidate.get("license")),
        "terms_sha256": terms,
        "probed_at": _text(candidate.get("probed_at")),
    }
    digest = sha256_json(evidence)
    reason_codes = sorted(set(rejected) | set(quarantined))
    if rejected:
        disposition = "rejected"
    elif quarantined:
        disposition = "quarantined"
    else:
        disposition = "accepted"

    return {
        "model": model or None,
        "disposition": disposition,
        "reason_codes": reason_codes,
        "license_family": family,
        "evidence": evidence,
        "evidence_digest": digest,
    }


def _accepted_row(row: dict[str, Any]) -> dict[str, Any]:
    evidence = row["evidence"]
    return {
        "model": row["model"],
        "license_family": row["license_family"],
        "evidence_digest": row["evidence_digest"],
        "ollama_digest": evidence["ollama_digest"],
        "quantization": evidence["quantization"],
        "runtime": evidence["runtime"],
        "endpoint": evidence["endpoint"],
        "probed_at": evidence["probed_at"],
    }


def _unresolved_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": row["model"],
        "reason_codes": row["reason_codes"],
        "license_family": row["license_family"],
        "evidence": row["evidence"],
        "evidence_digest": row["evidence_digest"],
    }


def build_admission_report(
    candidates: list[Any],
    *,
    rights: Any,
    probe: Any,
    input_digests: dict[str, str],
    bundle_errors: list[str] | None = None,
) -> dict[str, Any]:
    """Build the ``local_model_admission_v1`` report for a candidate list."""
    rows = [evaluate_admission(c, rights=rights, probe=probe) for c in candidates]
    accepted = [_accepted_row(r) for r in rows if r["disposition"] == "accepted"]
    quarantined = [
        _unresolved_row(r) for r in rows if r["disposition"] == "quarantined"
    ]
    rejected = [
        _unresolved_row(r) for r in rows if r["disposition"] == "rejected"
    ]
    families = sorted(
        {r["license_family"] for r in rows if r["license_family"]}
    )
    digests = sorted(
        {r["evidence_digest"] for r in rows if r["evidence_digest"]}
    )
    errors = list(bundle_errors or [])
    closed = not quarantined and not rejected and not errors
    return {
        "schema_version": SCHEMA_VERSION,
        "closed": closed,
        "counts": {
            "candidate_count": len(rows),
            "accepted": len(accepted),
            "quarantined": len(quarantined),
            "rejected": len(rejected),
        },
        "accepted": accepted,
        "quarantined": quarantined,
        "rejected": rejected,
        "license_families": families,
        "evidence_digests": digests,
        "input_digests": dict(sorted(input_digests.items())),
        "bundle_errors": errors,
    }
