"""Normalize verified Hermes traces into trajectory v1.1 (Linear RM-1348)."""

from hermes_normalize_test_support import *  # noqa: F403


def test_existing_v0_and_v1_validators_still_pass():
    v0 = jsonschema.Draft7Validator(
        load_schema(V0_SCHEMA),
        format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER,
    )
    v1 = jsonschema.Draft7Validator(
        load_schema(V1_SCHEMA),
        format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER,
    )
    errors = validate_file(
        ROOT / "tests" / "fixtures" / "v1" / "software_valid.jsonl",
        v0,
        v1,
        strict_policy=True,
    )
    assert errors == []


def test_replacement_does_not_ship_github_page_cassettes():
    assert not (ROOT / "schemas" / "github_page_cassette.schema.json").exists()
    assert not (ROOT / "scripts" / "lib" / "github_page_fixtures.py").exists()
    assert not (
        ROOT / "tests" / "fixtures" / "github" / "pages" / "pr89_multipage.json"
    ).exists()


def test_custody_and_reasoning_docs_exist():
    assert (ROOT / "docs" / "hermes-raw-trace-custody.md").is_file()
    assert (ROOT / "docs" / "hermes-reasoning-retention.md").is_file()


def test_nonfinite_json_is_rejected(tmp_path: Path):
    paths = write_scenario(tmp_path, [hermes_record(run_id="run-nan")])
    text = paths["input"].read_text(encoding="utf-8").replace('"run-nan"', "NaN")
    paths["input"].write_text(text, encoding="utf-8")
    assert _run(paths) == 0
    report = _report(paths)
    assert report["rejected_count"] == 1
    assert "invalid_json" in report["records"][0]["reason_codes"]


def test_admission_model_mismatch_fails_closed(tmp_path: Path):
    admission = default_admission()
    admission["model"]["name"] = "other-model"
    paths = write_scenario(
        tmp_path,
        [hermes_record(run_id="run-model")],
        admission=admission,
    )
    assert _run(paths) == 0
    report = _report(paths)
    assert report["accepted_count"] == 0
    assert report["rejected_count"] >= 1
    joined = ",".join(report["records"][0]["reason_codes"])
    assert "model" in joined or "mismatch" in joined


def test_shared_admission_fixture_uses_singular_decision_interface():
    payload = json.loads(ADMISSION_FIXTURE.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "local_model_admission_v1"
    assert payload["decision"] == "accepted"
    assert payload["reasons"] == []
    assert payload["model"]["ollama_digest"].startswith("sha256:")
    assert payload["runtime"]["name"] == "ollama"
    assert payload["rights"]["identifier"] == "Apache-2.0"
    assert payload["provider"]["config"]["no_cloud"] is True
    assert payload["provider"]["config"]["cloud_fallback_allowed"] is False
    assert payload["cloud_fallback_allowed"] is False
    assert payload["fallback_evidence"]["cloud_fallback_allowed"] is False
    assert payload["fallback_evidence"]["no_cloud"] is True
    assert payload["probe"]["endpoint"].startswith("http://127.0.0.1")
    assert set(payload["input_digests"]) >= {"admissions", "rights", "probe"}
    assert payload["evidence_digest"] == seal_admission(payload)["evidence_digest"]
    assert default_admission()["decision"] == "accepted"
    assert "disposition" not in default_admission()


def test_legacy_disposition_admission_is_rejected(tmp_path: Path):
    admission = default_admission()
    admission.pop("decision")
    admission["disposition"] = "accepted"
    paths = write_scenario(
        tmp_path,
        [hermes_record(run_id="run-disposition")],
        admission=admission,
    )
    assert _run(paths) == 0
    report = _report(paths)
    assert report["accepted_count"] == 0
    assert report["rejected_count"] >= 1
    joined = ",".join(report["records"][0]["reason_codes"])
    assert "admission" in joined


def test_non_accepted_decision_admission_is_rejected(tmp_path: Path):
    admission = default_admission(decision="quarantined")
    paths = write_scenario(
        tmp_path,
        [hermes_record(run_id="run-decision")],
        admission=admission,
    )
    assert _run(paths) == 0
    report = _report(paths)
    assert report["accepted_count"] == 0
    assert report["rejected_count"] >= 1
    assert "admission_rejected" in report["records"][0]["reason_codes"]


def test_manifest_verifier_conflict_with_trace_is_rejected(tmp_path: Path):
    record = hermes_record(
        run_id="run-verifier-conflict",
        trace_verifier={
            "artifact_sha256": [
                "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
            ],
            "identity": "trace-self",
            "outcome": "pass",
            "version": "0.0.0",
        },
    )
    paths = write_scenario(
        tmp_path,
        [record],
        manifest_overrides={"verifier": default_verifier(outcome="fail")},
    )
    assert _run(paths) == 0
    assert paths["output"].read_text(encoding="utf-8") == ""
    report = _report(paths)
    assert report["accepted_count"] == 0
    assert report["rejected_count"] >= 1
    joined = ",".join(report["records"][0]["reason_codes"])
    assert "verifier" in joined


def test_manifest_repository_and_workspace_conflicts_are_rejected(tmp_path: Path):
    record = hermes_record(run_id="run-repo-conflict")
    record["repository"]["head_oid"] = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
    record["workspace"] = {"id": "ws-shared-home", "kind": "shared"}
    paths = write_scenario(tmp_path, [record])
    assert _run(paths) == 0
    dumped = paths["output"].read_text(encoding="utf-8")
    assert dumped == ""
    assert "deadbeef" not in dumped
    assert "ws-shared-home" not in dumped
    report = _report(paths)
    assert report["accepted_count"] == 0
    assert report["rejected_count"] >= 1
    joined = ",".join(report["records"][0]["reason_codes"])
    assert "repository" in joined or "workspace" in joined or "conflict" in joined


def test_manifest_ollama_credential_is_rejected_and_not_emitted(tmp_path: Path):
    paths = write_scenario(
        tmp_path,
        [hermes_record(run_id="run-manifest-secret")],
        manifest_overrides={
            "ollama": {"config": {"api_key": SYNTHETIC_GITHUB_TOKEN}},
        },
    )
    assert _run(paths) == 0
    assert paths["output"].read_text(encoding="utf-8") == ""
    report_text = paths["report"].read_text(encoding="utf-8")
    assert "ghp_" not in report_text
    report = json.loads(report_text)
    assert report["accepted_count"] == 0
    assert report["rejected_count"] >= 1
    assert "secret" in ",".join(report["records"][0]["reason_codes"])


def test_missing_ids_and_string_booleans_are_rejected(tmp_path: Path):
    record = hermes_record(run_id="run-coerced")
    del record["session_id"]
    del record["task_id"]
    del record["raw_trace_id"]
    record["completed"] = "false"
    record["partial"] = "false"
    paths = write_scenario(tmp_path, [record])
    assert _run(paths) == 0
    assert paths["output"].read_text(encoding="utf-8") == ""
    report = _report(paths)
    assert report["accepted_count"] == 0
    assert report["rejected_count"] >= 1
    joined = ",".join(report["records"][0]["reason_codes"])
    assert "identity" in joined or "execution" in joined or "invalid" in joined


def test_empty_input_with_invalid_binding_is_explicitly_rejected(tmp_path: Path):
    paths = write_scenario(tmp_path, [])
    paths["input"].write_bytes(b"")
    write_json(paths["manifest"], {"schema_version": "not-a-manifest"})
    write_json(paths["admission"], {"schema_version": "not-admission"})
    assert _run(paths) == 0
    report = _report(paths)
    assert report["accepted_count"] == 0
    assert report["quarantined_count"] == 0
    assert report["rejected_count"] >= 1
    assert report["records"]
    assert report["records"][0]["reason_codes"]


def test_empty_input_with_valid_binding_is_explicitly_rejected(tmp_path: Path):
    paths = write_scenario(tmp_path, [])
    paths["input"].write_bytes(b"")
    assert _run(paths) == 0
    report = _report(paths)
    assert report["accepted_count"] == 0
    assert report["quarantined_count"] == 0
    assert report["rejected_count"] >= 1
    assert "empty_input" in report["records"][0]["reason_codes"]


def test_structured_credential_content_is_rejected(tmp_path: Path):
    record = hermes_record(
        run_id="run-structured-secret",
        content={"api_key": "ordinarysecretvalue123", "answer": "visible"},
    )
    paths = write_scenario(tmp_path, [record])
    assert _run(paths) == 0
    dumped = paths["output"].read_text(encoding="utf-8")
    assert dumped == ""
    assert "ordinarysecretvalue123" not in dumped
    report = _report(paths)
    assert report["accepted_count"] == 0
    assert report["rejected_count"] >= 1
