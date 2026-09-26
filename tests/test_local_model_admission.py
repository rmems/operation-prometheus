"""Unit tests for the local-model admission evaluator."""

from __future__ import annotations

import pytest

from lib.model_admission import (
    SCHEMA_VERSION,
    AdmissionInputs,
    build_admission_report,
    evaluate_admission,
)

MODEL = "hermes-3-llama-3.1-8b:q4_k_m"
DIGEST = "sha256:" + "a" * 64
TERMS = "b" * 64


def _candidate(**overrides):
    candidate = {
        "model": MODEL,
        "ollama_digest": DIGEST,
        "quantization": "Q4_K_M",
        "runtime": "ollama",
        "endpoint": "http://127.0.0.1:11434",
        "license": "Apache-2.0",
        "provider_config": {"no_cloud": True, "cloud_fallback_allowed": False, "num_ctx": 8192},
        "probed_at": "2026-09-21T12:00:00Z",
    }
    candidate.update(overrides)
    return candidate


def _rights(**overrides):
    rights = {
        "schema_version": "model_rights_v1",
        "models": {
            MODEL: {"license": "Apache-2.0", "terms_sha256": TERMS, "terms_source": "upstream/LICENSE"},
        },
    }
    rights.update(overrides)
    return rights


def _probe(**overrides):
    probe = {
        "schema_version": "ollama_probe_v1",
        "runtime": "ollama",
        "version": "0.5.4",
        "endpoint": "http://127.0.0.1:11434",
        "probed_at": "2026-09-21T12:00:00Z",
        "models": [{"name": MODEL, "digest": DIGEST}],
        "show": {MODEL: {"details": {"quantization_level": "Q4_K_M"}}},
    }
    probe.update(overrides)
    return probe


def _inputs(rights=None, probe=None, digests=None, errors=None):
    return AdmissionInputs(
        rights=rights if rights is not None else _rights(),
        probe=probe if probe is not None else _probe(),
        input_digests=digests if digests is not None else {},
        bundle_errors=errors,
    )


def _evaluate(candidate=None, rights=None, probe=None):
    return evaluate_admission(
        candidate if candidate is not None else _candidate(),
        inputs=_inputs(rights=rights, probe=probe),
    )


def test_clean_candidate_is_accepted():
    row = _evaluate()
    assert row["disposition"] == "accepted"
    assert row["reason_codes"] == []
    assert row["license_family"] == "spdx"
    assert len(row["report"]["evidence_digest"]) == 64


def test_evidence_digest_changes_with_any_bound_field():
    digest = _evaluate()["report"]["evidence_digest"]
    for key, value in (
        ("ollama_digest", "sha256:" + "c" * 64),
        ("quantization", "Q8_0"),
        ("endpoint", "http://localhost:11434"),
        ("probed_at", "2026-09-21T13:00:00Z"),
    ):
        other = _evaluate(_candidate(**{key: value}))
        assert other["report"]["evidence_digest"] != digest


def test_missing_rights_row_quarantines():
    row = _evaluate(rights={"schema_version": "model_rights_v1", "models": {}})
    assert row["disposition"] == "quarantined"
    assert "rights_evidence_missing" in row["reason_codes"]


def test_unknown_license_quarantines_without_guessing():
    rights = _rights()
    rights["models"][MODEL]["license"] = "NOASSERTION"
    row = _evaluate(_candidate(license="NOASSERTION"), rights=rights)
    assert row["disposition"] == "quarantined"
    assert "license_unknown" in row["reason_codes"]
    assert row["license_family"] == "unknown"


def test_missing_license_quarantines():
    rights = _rights()
    del rights["models"][MODEL]["license"]
    row = _evaluate(rights=rights)
    assert row["disposition"] == "quarantined"
    assert "license_missing" in row["reason_codes"]


def test_conflicting_rights_rejected():
    row = _evaluate(_candidate(license="MIT"))
    assert row["disposition"] == "rejected"
    assert "rights_conflict" in row["reason_codes"]


def test_custom_license_ref_needs_matching_terms_digest():
    rights = _rights()
    rights["models"][MODEL] = {
        "terms_source": "upstream/LICENSE.txt",
        "license": "LicenseRef-Hermes-Community",
        "custom_license": {
            "identifier": "LicenseRef-Hermes-Community",
            "text_sha256": TERMS,
        },
        "terms_sha256": TERMS,
    }
    row = _evaluate(_candidate(license="LicenseRef-Hermes-Community"), rights=rights)
    assert row["disposition"] == "accepted"
    assert row["license_family"] == "custom"


def test_non_loopback_endpoint_rejected():
    row = _evaluate(_candidate(endpoint="https://api.openai.com/v1"))
    assert row["disposition"] == "rejected"
    assert "endpoint_not_loopback" in row["reason_codes"]


def test_probe_digest_mismatch_rejected():
    probe = _probe()
    probe["models"][0]["digest"] = "sha256:" + "d" * 64
    row = _evaluate(probe=probe)
    assert row["disposition"] == "rejected"
    assert "probe_digest_mismatch" in row["reason_codes"]


def test_quantization_mismatch_rejected():
    probe = _probe()
    probe["show"][MODEL]["details"]["quantization_level"] = "Q8_0"
    row = _evaluate(probe=probe)
    assert row["disposition"] == "rejected"
    assert "probe_quantization_mismatch" in row["reason_codes"]


def test_missing_probe_evidence_quarantines():
    probe = _probe(models=[], show={})
    row = _evaluate(probe=probe)
    assert row["disposition"] == "quarantined"
    assert "probe_evidence_missing" in row["reason_codes"]


def test_unsanitized_provider_config_rejected():
    row = _evaluate(
        _candidate(provider_config={"no_cloud": True, "cloud_fallback_allowed": False, "api_key": "sk-live"})
    )
    assert row["disposition"] == "rejected"
    assert "provider_config_unsanitized" in row["reason_codes"]


def test_missing_no_cloud_evidence_quarantines():
    row = _evaluate(_candidate(provider_config={"num_ctx": 8192, "cloud_fallback_allowed": False}))
    assert row["disposition"] == "quarantined"
    assert "no_cloud_evidence_missing" in row["reason_codes"]


def test_missing_probe_timestamp_quarantines():
    row = _evaluate(_candidate(probed_at=None))
    assert row["disposition"] == "quarantined"
    assert "probe_timestamp_missing" in row["reason_codes"]


def test_malformed_probe_timestamp_quarantines():
    row = _evaluate(_candidate(probed_at="not-a-date"))
    assert row["disposition"] == "quarantined"
    assert "probe_timestamp_invalid" in row["reason_codes"]


def test_report_shape_and_counts():
    report = build_admission_report(
        [
            _candidate(),
            _candidate(model="unknown-model:latest"),
        ],
        _inputs(digests={"admissions": "e" * 64}),
    )
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["counts"] == {
        "candidate_count": 2,
        "accepted": 1,
        "quarantined": 1,
        "rejected": 0,
    }
    assert report["closed"] is False
    assert "spdx" in report["license_families"]
    assert report["input_digests"] == {"admissions": "e" * 64}


def test_report_closed_when_all_accepted():
    report = build_admission_report([_candidate()], _inputs())
    assert report["closed"] is True


def test_rejected_row_keeps_reason_coded_evidence():
    row = _evaluate(_candidate(endpoint="https://example.com"))
    assert row["disposition"] == "rejected"
    assert row["report"]["runtime"]["endpoint"] is None


def test_non_object_candidate_fails_closed():
    row = evaluate_admission("not-an-object", inputs=_inputs())
    assert row["disposition"] == "rejected"
    assert "candidate_not_object" in row["reason_codes"]


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]"])
def test_loopback_hosts_accepted(host):
    row = _evaluate(_candidate(endpoint=f"http://{host}:11434"))
    assert "endpoint_not_loopback" not in row["reason_codes"]
    assert "endpoint_invalid" not in row["reason_codes"]
