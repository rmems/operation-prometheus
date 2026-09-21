"""Local-model admission evaluation for Operation Prometheus.

Evaluates proposed local-model providers (e.g. Ollama-served Hermes weights)
against frozen rights evidence and a recorded loopback probe. Fail-closed:
every candidate lands in ``accepted``, ``quarantined`` (evidence incomplete)
or ``rejected`` (evidence contradictory) with explicit reason codes.
"""

from __future__ import annotations

from typing import Any

from .model_admission_check_fields import (
    config_reasons,
    endpoint_reasons,
    runtime_reasons,
    timestamp_reasons,
)
from .model_admission_check_probe import probe_reasons
from .model_admission_check_rights import rights_reasons
from .model_admission_evidence import sha256_json
from .model_admission_rights import normalize_license_id

SCHEMA_VERSION = "local_model_admission_v1"
DISPOSITIONS = ("accepted", "quarantined", "rejected")


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _rights_row(rights: Any, model: str) -> Any:
    if not isinstance(rights, dict):
        return None
    models = rights.get("models")
    return models.get(model) if isinstance(models, dict) else None


def _evidence(candidate: dict[str, Any], model: str, terms: str | None) -> dict:
    return {
        "model": model or None,
        "ollama_digest": _text(candidate.get("ollama_digest")),
        "quantization": _text(candidate.get("quantization")),
        "runtime": _text(candidate.get("runtime")),
        "endpoint": _text(candidate.get("endpoint")),
        "license": normalize_license_id(candidate.get("license")),
        "terms_sha256": terms,
        "probed_at": _text(candidate.get("probed_at")),
    }


def _disposition(rejected: list[str], quarantined: list[str]) -> str:
    if rejected:
        return "rejected"
    if quarantined:
        return "quarantined"
    return "accepted"


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

    model = _text(candidate.get("model")) or ""
    rejected: list[str] = [] if model else ["model_missing"]
    quarantined: list[str] = []

    r_rej, r_quar, family, terms = rights_reasons(
        normalize_license_id(candidate.get("license")),
        _rights_row(rights, model),
    )
    rejected += r_rej
    quarantined += r_quar

    if model:
        p_rej, p_quar = probe_reasons(model, candidate, probe)
        rejected += p_rej
        quarantined += p_quar

    for check in (runtime_reasons, endpoint_reasons, timestamp_reasons):
        r, q = check(candidate)
        rejected += r
        quarantined += q
    r, q = config_reasons(candidate.get("provider_config"))
    rejected += r
    quarantined += q

    evidence = _evidence(candidate, model, terms)
    return {
        "model": model or None,
        "disposition": _disposition(rejected, quarantined),
        "reason_codes": sorted(set(rejected) | set(quarantined)),
        "license_family": family,
        "evidence": evidence,
        "evidence_digest": sha256_json(evidence),
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
    by_disposition = {
        name: [r for r in rows if r["disposition"] == name]
        for name in DISPOSITIONS
    }
    accepted = [_accepted_row(r) for r in by_disposition["accepted"]]
    quarantined = [_unresolved_row(r) for r in by_disposition["quarantined"]]
    rejected = [_unresolved_row(r) for r in by_disposition["rejected"]]
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
        "license_families": sorted(
            {r["license_family"] for r in rows if r["license_family"]}
        ),
        "evidence_digests": sorted(
            {r["evidence_digest"] for r in rows if r["evidence_digest"]}
        ),
        "input_digests": dict(sorted(input_digests.items())),
        "bundle_errors": errors,
    }
