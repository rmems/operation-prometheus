"""Local-model admission evaluation for Operation Prometheus.

Evaluates proposed local-model providers (e.g. Ollama-served Hermes weights)
against frozen rights evidence and a recorded loopback probe. Fail-closed:
every candidate is classified ``accepted``, ``quarantined`` (evidence
incomplete) or ``rejected`` (evidence contradictory) with explicit reason
codes, and each candidate emits the singular ``local_model_admission_v1``
report consumed by the #74 closure gate.
"""

from __future__ import annotations

from typing import Any, NamedTuple

from .model_admission_check_fields import (
    config_reasons,
    endpoint_reasons,
    runtime_reasons,
)
from .model_admission_check_probe import probe_reasons
from .model_admission_check_rights import rights_reasons
from .model_admission_evidence import (
    canonical_loopback_endpoint,
    ollama_digest_or_none,
    remote_config_endpoints,
    sha256_json,
    unsanitized_config_keys,
)
from .model_admission_rights import normalize_license_id

SCHEMA_VERSION = "local_model_admission_v1"
DISPOSITIONS = ("accepted", "quarantined", "rejected")


class AdmissionInputs(NamedTuple):
    """Frozen evidence bundle shared by every candidate in a report."""

    rights: Any
    probe: Any
    input_digests: dict[str, str]
    bundle_errors: list[str] | None = None


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _rights_row(rights: Any, model: str) -> Any:
    if not isinstance(rights, dict):
        return None
    models = rights.get("models")
    return models.get(model) if isinstance(models, dict) else None


def _provider_config(candidate: dict[str, Any]) -> Any:
    config = candidate.get("provider_config")
    return config if isinstance(config, dict) else None


def _fallback_evidence(config: dict[str, Any] | None) -> dict[str, Any]:
    """Proof object backing the emitted ``cloud_fallback_allowed`` flag."""
    return {
        "no_cloud": config.get("no_cloud") if isinstance(config, dict) else None,
        "cloud_fallback_allowed": (
            config.get("cloud_fallback_allowed")
            if isinstance(config, dict)
            else None
        ),
        "unsanitized_keys": unsanitized_config_keys(config),
        "remote_endpoints": remote_config_endpoints(config),
    }


def _disposition(rejected: list[str], quarantined: list[str]) -> str:
    if rejected:
        return "rejected"
    if quarantined:
        return "quarantined"
    return "accepted"


def _non_object_row() -> dict[str, Any]:
    return {
        "model": None,
        "disposition": "rejected",
        "reason_codes": ["candidate_not_object"],
        "license_family": "missing",
        "candidate": {},
        "terms": None,
    }


def evaluate_admission(candidate: Any, *, inputs: AdmissionInputs) -> dict:
    """Classify one admission candidate as accepted/quarantined/rejected."""
    if not isinstance(candidate, dict):
        row = _non_object_row()
        row["report"] = _decision_report(row, inputs)
        return row

    model = _text(candidate.get("model")) or ""
    rejected: list[str] = [] if model else ["model_missing"]
    quarantined: list[str] = []
    if model and _model_name_tag(model)[1] is None:
        quarantined.append("model_tag_missing")

    rights_license = normalize_license_id(candidate.get("license"))
    r_rej, r_quar, family, terms = rights_reasons(
        rights_license, _rights_row(inputs.rights, model)
    )
    rejected += r_rej
    quarantined += r_quar

    if model:
        p_rej, p_quar = probe_reasons(
            model, candidate, inputs.probe, rights_license
        )
        rejected += p_rej
        quarantined += p_quar

    for check in (runtime_reasons, endpoint_reasons):
        r, q = check(candidate)
        rejected += r
        quarantined += q
    r, q = config_reasons(candidate.get("provider_config"))
    rejected += r
    quarantined += q

    row = {
        "model": model or None,
        "disposition": _disposition(rejected, quarantined),
        "reason_codes": sorted(set(rejected) | set(quarantined)),
        "license_family": family,
        "candidate": candidate,
        "terms": terms,
    }
    row["report"] = _decision_report(row, inputs)
    return row


def _model_name_tag(model: str | None) -> tuple[str | None, str | None]:
    if not model or ":" not in model:
        return model, None
    name, _, tag = model.rpartition(":")
    return name or None, tag or None


def _decision_report(row: dict[str, Any], inputs: AdmissionInputs) -> dict:
    """The singular ``local_model_admission_v1`` report #74 consumes."""
    candidate = row["candidate"]
    probe = inputs.probe if isinstance(inputs.probe, dict) else {}
    rights_row = _rights_row(inputs.rights, row["model"] or "")
    rights_row = rights_row if isinstance(rights_row, dict) else {}
    config = _provider_config(candidate)
    model_name, model_tag = _model_name_tag(row["model"])
    report = {
        "schema_version": SCHEMA_VERSION,
        "decision": row["disposition"],
        "reasons": row["reason_codes"],
        "model": row["model"],
        "model_name": model_name,
        "model_tag": model_tag,
        "ollama_digest": ollama_digest_or_none(candidate.get("ollama_digest")),
        "quantization": _text(candidate.get("quantization")),
        "upstream_revision": _text(candidate.get("upstream_revision")),
        "runtime": {
            "name": _text(candidate.get("runtime")),
            "version": _text(probe.get("version")),
        },
        "endpoint": canonical_loopback_endpoint(candidate.get("endpoint")),
        "rights": {
            "identifier": normalize_license_id(rights_row.get("license")),
            "terms_source": _text(rights_row.get("terms_source")),
            "terms_sha256": row["terms"],
        },
        "license_family": row["license_family"],
        "provider_config": config,
        "cloud_fallback_allowed": (
            config.get("cloud_fallback_allowed")
            if isinstance(config, dict)
            else None
        ),
        "fallback_evidence": _fallback_evidence(config),
        "probed_at": _text(probe.get("probed_at")),
        "input_digests": dict(sorted(inputs.input_digests.items())),
    }
    report["evidence_digest"] = sha256_json(report)
    return report


def _rows_by_disposition(rows: list[dict[str, Any]]) -> dict[str, list]:
    return {
        name: [r for r in rows if r["disposition"] == name]
        for name in DISPOSITIONS
    }


def build_admission_report(
    candidates: list[Any], inputs: AdmissionInputs
) -> dict[str, Any]:
    """Build the bundle report wrapping each singular decision report."""
    rows = [evaluate_admission(c, inputs=inputs) for c in candidates]
    grouped = _rows_by_disposition(rows)
    decisions = [r["report"] for r in rows]
    errors = list(inputs.bundle_errors or [])
    if not rows:
        errors.append("no_candidates")
    closed = (
        not grouped["quarantined"] and not grouped["rejected"] and not errors
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "closed": closed,
        "counts": {
            "candidate_count": len(rows),
            "accepted": len(grouped["accepted"]),
            "quarantined": len(grouped["quarantined"]),
            "rejected": len(grouped["rejected"]),
        },
        "decisions": decisions,
        "license_families": sorted(
            {r["license_family"] for r in rows if r["license_family"]}
        ),
        "evidence_digests": sorted(
            {d["evidence_digest"] for d in decisions}
        ),
        "input_digests": dict(sorted(inputs.input_digests.items())),
        "bundle_errors": errors,
    }
