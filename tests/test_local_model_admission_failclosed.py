"""Fail-closed regression tests for local-model admission boundaries."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from lib.model_admission import (
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
        "provider_config": {
            "no_cloud": True,
            "cloud_fallback_allowed": False,
            "num_ctx": 8192,
        },
        "probed_at": "2026-09-21T12:00:00Z",
    }
    candidate.update(overrides)
    return candidate


def _rights(**overrides):
    rights = {
        "schema_version": "model_rights_v1",
        "models": {
            MODEL: {
                "license": "Apache-2.0",
                "terms_sha256": TERMS,
                "terms_source": "upstream/LICENSE",
            },
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
        "show": {
            MODEL: {
                "details": {"quantization_level": "Q4_K_M"},
                "license": "Apache-2.0",
            }
        },
    }
    probe.update(overrides)
    return probe


def _inputs(rights=None, probe=None, digests=None):
    return AdmissionInputs(
        rights=rights if rights is not None else _rights(),
        probe=probe if probe is not None else _probe(),
        input_digests=digests or {},
    )


def _evaluate(candidate=None, rights=None, probe=None):
    return evaluate_admission(
        candidate if candidate is not None else _candidate(),
        inputs=_inputs(rights=rights, probe=probe),
    )


def _assert_never_accepted(row):
    assert row["disposition"] in ("quarantined", "rejected")


# --- 1. Complete emitted evidence bound into the digest --------------------

def test_accepted_evidence_is_complete_and_bound():
    row = _evaluate()
    report = row["report"]
    assert report["decision"] == "accepted"
    assert report["reasons"] == []
    assert report["runtime"]["name"] == "ollama"
    assert report["runtime"]["version"] == "0.5.4"
    assert report["runtime"]["endpoint"] == "http://127.0.0.1:11434"
    assert report["rights"]["terms_source"] == "upstream/LICENSE"
    assert report["rights"]["identifier"] == "Apache-2.0"
    assert report["rights"]["terms_sha256"] == TERMS
    assert report["provider"]["name"] == "hermes-agent"
    assert report["provider"]["config"]["cloud_fallback_allowed"] is False
    assert report["cloud_fallback_allowed"] is False
    assert report["fallback_evidence"]["no_cloud"] is True
    assert report["evidence_digest"]


def test_digest_computed_from_emitted_evidence():
    row = _evaluate()
    report = dict(row["report"])
    digest = report.pop("evidence_digest")
    canonical = json.dumps(
        report, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    assert digest == hashlib.sha256(canonical).hexdigest()


# --- 2. no-cloud proof fails closed ----------------------------------------

@pytest.mark.parametrize(
    "config",
    [
        {"no_cloud": True, "cloud_fallback_allowed": True},
        {"no_cloud": True},
        {"no_cloud": True, "cloud_fallback_allowed": "false"},
        {"no_cloud": True, "fallback_url": "https://api.example.com/v1"},
        {"no_cloud": True, "api_key": ["sk-secret"]},
        {"no_cloud": True, "unknown_knob": 1},
    ],
)
def test_no_cloud_counterexamples_never_accept(config):
    row = _evaluate(_candidate(provider_config=config))
    _assert_never_accepted(row)


def test_missing_cloud_fallback_disproof_rejected():
    config = {"no_cloud": True}
    row = _evaluate(_candidate(provider_config=config))
    assert row["disposition"] == "rejected"
    assert "cloud_fallback_not_disproven" in row["reason_codes"]


def test_unknown_config_key_rejected():
    row = _evaluate(
        _candidate(
            provider_config={
                "no_cloud": True,
                "cloud_fallback_allowed": False,
                "mystery": True,
            }
        )
    )
    assert row["disposition"] == "rejected"
    assert "provider_config_unknown_keys" in row["reason_codes"]


def test_list_secret_value_unsanitized():
    row = _evaluate(
        _candidate(
            provider_config={
                "no_cloud": True,
                "cloud_fallback_allowed": False,
                "api_key": ["sk-secret"],
            }
        )
    )
    assert row["disposition"] == "rejected"
    assert "provider_config_unsanitized" in row["reason_codes"]


# --- 3. Coherent probe evidence --------------------------------------------

def test_probe_missing_schema_version_quarantines():
    probe = _probe()
    del probe["schema_version"]
    _assert_never_accepted(_evaluate(probe=probe))


def test_probe_missing_runtime_version_quarantines():
    probe = _probe()
    del probe["version"]
    row = _evaluate(probe=probe)
    _assert_never_accepted(row)
    assert "probe_runtime_missing" in row["reason_codes"]


def test_duplicate_model_rows_conflicting_digests_rejected():
    probe = _probe()
    probe["models"].append({"name": MODEL, "digest": "sha256:" + "f" * 64})
    row = _evaluate(probe=probe)
    assert row["disposition"] == "rejected"
    assert "probe_digest_conflict" in row["reason_codes"]


def test_duplicate_model_rows_same_digest_quarantine():
    probe = _probe()
    probe["models"].append({"name": MODEL, "digest": DIGEST})
    row = _evaluate(probe=probe)
    assert row["disposition"] == "quarantined"
    assert "probe_duplicate" in row["reason_codes"]


def test_conflicting_show_license_rejected():
    probe = _probe()
    probe["show"][MODEL]["license"] = "MIT"
    row = _evaluate(probe=probe)
    assert row["disposition"] == "rejected"
    assert "probe_license_conflict" in row["reason_codes"]


def test_missing_probe_timestamp_quarantines():
    probe = _probe()
    del probe["probed_at"]
    row = _evaluate(probe=probe)
    assert row["disposition"] == "quarantined"
    assert "probe_timestamp_missing" in row["reason_codes"]


def test_emitted_probe_timestamp_is_probe_value():
    probe = _probe(probed_at="2026-09-21T09:30:00Z")
    row = _evaluate(
        _candidate(probed_at="2026-09-21T09:30:00Z"), probe=probe
    )
    assert row["report"]["probe"]["timestamp"] == "2026-09-21T09:30:00Z"


def test_missing_probe_quantization_quarantines():
    probe = _probe()
    del probe["show"][MODEL]["details"]["quantization_level"]
    row = _evaluate(probe=probe)
    _assert_never_accepted(row)
    assert "probe_quantization_missing" in row["reason_codes"]


def test_missing_probe_endpoint_quarantines():
    probe = _probe()
    del probe["endpoint"]
    row = _evaluate(probe=probe)
    _assert_never_accepted(row)
    assert "probe_endpoint_missing" in row["reason_codes"]


# --- 6. Canonical identity values ------------------------------------------

def test_malformed_digest_quarantines():
    row = _evaluate(_candidate(ollama_digest="not-a-sha256"))
    _assert_never_accepted(row)
    assert "digest_invalid" in row["reason_codes"]


def test_uppercase_endpoint_rejected_as_noncanonical():
    row = _evaluate(_candidate(endpoint="HTTP://LOCALHOST:11434/"))
    _assert_never_accepted(row)
    assert "endpoint_invalid" in row["reason_codes"]


def test_date_only_timestamp_rejected():
    probe = _probe(probed_at="2026-09-21")
    row = _evaluate(_candidate(probed_at="2026-09-21"), probe=probe)
    _assert_never_accepted(row)
    assert "probe_timestamp_missing" in row["reason_codes"]


def test_timezone_naive_timestamp_rejected():
    probe = _probe(probed_at="2026-09-21T12:00:00")
    row = _evaluate(
        _candidate(probed_at="2026-09-21T12:00:00"), probe=probe
    )
    _assert_never_accepted(row)


# --- report integrity --------------------------------------------------------

def test_input_digests_include_manifest_self():
    report = build_admission_report(
        [_candidate()],
        _inputs(digests={
            "admissions": "e" * 64,
            "inputs_manifest": "f" * 64,
        }),
    )
    assert report["input_digests"]["inputs_manifest"] == "f" * 64
    decision = report["decisions"][0]
    assert decision["input_digests"]["inputs_manifest"] == "f" * 64


# --- locked #74 contract: singular report -----------------------------------

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "local_model_admission"


ROOT_SCHEMA = json.loads(
    (Path(__file__).resolve().parent.parent
     / "schemas" / "local_model_admission.schema.json").read_text()
)


def test_accepted_report_fixture_matches_locked_schema():
    import jsonschema

    report = json.loads((FIXTURE_DIR / "accepted_report.json").read_text())
    jsonschema.validate(report, ROOT_SCHEMA)
    assert report["decision"] == "accepted"
    assert report["reasons"] == []
    assert report["model"]["name"] == "hermes-3-llama-3.1-8b"
    assert report["model"]["tag"] == "q4_k_m"
    assert report["cloud_fallback_allowed"] is False
    assert report["fallback_evidence"]["cloud_fallback_allowed"] is False


def test_schema_rejects_forged_accepted_with_nulls():
    import jsonschema
    import pytest as _pytest

    forged = {
        "schema_version": "local_model_admission_v1",
        "decision": "accepted",
        "reasons": [],
        "model": {
            "name": None,
            "tag": None,
            "ollama_digest": None,
            "quantization": None,
            "upstream_revision": None,
        },
        "runtime": {"name": None, "version": None, "endpoint": None},
        "rights": {
            "identifier": None,
            "terms_source": None,
            "terms_sha256": None,
        },
        "provider": {"name": "hermes-agent", "config": None},
        "cloud_fallback_allowed": None,
        "fallback_evidence": {
            "no_cloud": None,
            "cloud_fallback_allowed": None,
            "unsanitized_keys": [],
            "remote_endpoints": [],
        },
        "probe": {"timestamp": None, "endpoint": None},
        "input_digests": {},
        "evidence_digest": "0" * 64,
    }
    with _pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(forged, ROOT_SCHEMA)


def test_emitted_decision_is_verbatim_reproducible():
    row = _evaluate()
    report = row["report"]
    assert report["schema_version"] == "local_model_admission_v1"
    clone = dict(report)
    digest = clone.pop("evidence_digest")
    canonical = json.dumps(
        clone, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    assert digest == hashlib.sha256(canonical).hexdigest()


# --- 3. value-level credential scanning and strict config types --------------

def test_credential_in_stop_list_rejected():
    row = _evaluate(
        _candidate(
            provider_config={
                "no_cloud": True,
                "cloud_fallback_allowed": False,
                "stop": ["ghp_abcdefghijklmnopqrstuvwxyz0123456789"],
            }
        )
    )
    assert row["disposition"] == "rejected"
    assert "provider_config_unsanitized" in row["reason_codes"]


def test_credential_in_allowed_scalar_key_rejected():
    row = _evaluate(
        _candidate(
            provider_config={
                "no_cloud": True,
                "cloud_fallback_allowed": False,
                "stop": "sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
            }
        )
    )
    assert row["disposition"] == "rejected"
    assert "provider_config_unsanitized" in row["reason_codes"]


def test_nested_wrapper_under_allowed_leaf_rejected():
    row = _evaluate(
        _candidate(
            provider_config={
                "no_cloud": True,
                "cloud_fallback_allowed": False,
                "wrapper": {"num_ctx": 1},
            }
        )
    )
    assert row["disposition"] == "rejected"
    assert "provider_config_unknown_keys" in row["reason_codes"]


def test_wrong_type_for_numeric_knob_rejected():
    row = _evaluate(
        _candidate(
            provider_config={
                "no_cloud": True,
                "cloud_fallback_allowed": False,
                "num_ctx": "big",
            }
        )
    )
    assert row["disposition"] == "rejected"
    assert "provider_config_invalid" in row["reason_codes"]


# --- 4. probe/candidate runtime identity -------------------------------------

def test_foreign_probe_runtime_rejected():
    row = _evaluate(probe=_probe(runtime="cloud-runtime"))
    assert row["disposition"] == "rejected"
    assert "probe_runtime_mismatch" in row["reason_codes"]


# --- 6. IPv6 loopback canonicalization ---------------------------------------

def test_ipv6_endpoint_emitted_with_brackets():
    candidate = _candidate(endpoint="http://[::1]:11434")
    probe = _probe(endpoint="http://[::1]:11434")
    row = _evaluate(candidate, probe=probe)
    assert row["report"]["runtime"]["endpoint"] == "http://[::1]:11434"
    assert row["disposition"] == "accepted"


# --- 5. empty candidate input fails closed ------------------------------------

def test_empty_candidates_fail_closed():
    report = build_admission_report([], _inputs())
    assert report["closed"] is False
    assert "no_candidates" in report["bundle_errors"]


# --- model identity grammar ---------------------------------------------------

@pytest.mark.parametrize(
    "model,expected",
    [
        ("foo", "model_tag_missing"),
        ("foo:", "model_invalid"),
        (":tag", "model_invalid"),
        ("foo:tag:extra", "model_invalid"),
    ],
)
def test_model_identity_grammar_never_accepts(model, expected):
    row = _evaluate(_candidate(model=model))
    _assert_never_accepted(row)
    assert expected in row["reason_codes"]


def test_upstream_revision_conflict_rejected():
    rights = _rights()
    rights["models"][MODEL]["upstream_revision"] = "rev-a"
    row = _evaluate(_candidate(upstream_revision="rev-b"), rights=rights)
    assert row["disposition"] == "rejected"
    assert "upstream_revision_mismatch" in row["reason_codes"]


def test_upstream_revision_bound_from_frozen_evidence():
    rights = _rights()
    rights["models"][MODEL]["upstream_revision"] = "rev-a"
    row = _evaluate(rights=rights)
    assert row["report"]["model"]["upstream_revision"] == "rev-a"


# --- closed candidate envelope -------------------------------------------------

@pytest.mark.parametrize(
    "extra",
    [
        {"fallback_url": "https://api.openai.com/v1"},
        {"api_key": "sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"},
        {"cloud_fallback_allowed": True},
        {"provider": "openai"},
    ],
)
def test_unknown_candidate_fields_rejected(extra):
    candidate = _candidate(**extra)
    row = _evaluate(candidate)
    assert row["disposition"] == "rejected"


# --- config: credential-bearing URLs and nested containers --------------------

def test_credential_url_in_stop_list_rejected():
    row = _evaluate(
        _candidate(
            provider_config={
                "no_cloud": True,
                "cloud_fallback_allowed": False,
                "stop": ["https://api.example.com/v1?api_key=supersecret"],
            }
        )
    )
    assert row["disposition"] == "rejected"


def test_remote_url_under_arbitrary_key_rejected():
    row = _evaluate(
        _candidate(
            provider_config={
                "no_cloud": True,
                "cloud_fallback_allowed": False,
                "keep_alive": "https://api.example.com/v1",
            }
        )
    )
    assert row["disposition"] == "rejected"


def test_nested_allowlisted_mapping_rejected():
    row = _evaluate(
        _candidate(
            provider_config={
                "no_cloud": True,
                "cloud_fallback_allowed": False,
                "num_ctx": {"temperature": 1},
            }
        )
    )
    assert row["disposition"] == "rejected"
