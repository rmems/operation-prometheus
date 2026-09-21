"""Hermes normalization policy and compatibility tests."""

from hermes_normalize_test_support import *  # noqa: F401,F403


def test_existing_v0_and_v1_validators_still_pass():
    v0, v1 = _strict_validators()
    _assert_legacy_fixture_valid(v0, v1)


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
    report = _run_report(paths)
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
    _assert_rejected_with_reason(paths, "model")


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
    _assert_rejected_with_reason(paths, "admission")


def test_non_accepted_decision_admission_is_rejected(tmp_path: Path):
    admission = default_admission(decision="quarantined")
    paths = write_scenario(
        tmp_path,
        [hermes_record(run_id="run-decision")],
        admission=admission,
    )
    _assert_rejected_with_reason(paths, "admission_rejected")


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
    _assert_rejected_with_reason(paths, "verifier")


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
    report = _run_report(paths)
    assert report["accepted_count"] == 0
    assert report["quarantined_count"] == 0
    assert report["rejected_count"] >= 1
    assert report["records"]
    assert report["records"][0]["reason_codes"]


def test_empty_input_with_valid_binding_is_explicitly_rejected(tmp_path: Path):
    paths = write_scenario(tmp_path, [])
    paths["input"].write_bytes(b"")
    report = _run_report(paths)
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
    report = _assert_secret_rejected(paths, "ordinarysecretvalue123")
    assert report["accepted_count"] == 0


@pytest.mark.parametrize(
    ("run_id", "url"),
    [
        ("run-path-secret", "https://example.test/token/ordinarysecretvalue123"),
        (
            "run-encoded-path-secret",
            "https://example.test/%74oken/ordinarysecretvalue123",
        ),
    ],
)
def test_credential_url_path_is_rejected(tmp_path: Path, run_id: str, url: str):
    record = hermes_record(
        run_id=run_id,
        extra_message={
            "role": "tool",
            "name": "fetch",
            "timestamp": "2026-09-21T12:00:30Z",
            "content": url,
        },
    )
    paths = write_scenario(tmp_path, [record])
    _assert_rejected_with_reason(paths, "secret_leakage")


@pytest.mark.parametrize("scheme", ["ftp", "ftps"])
def test_non_http_credential_query_url_is_sanitized(tmp_path: Path, scheme: str):
    record = hermes_record(
        run_id=f"run-{scheme}-secret",
        content=f"{scheme}://example.test/file?access_token=ordinarysecretvalue123",
    )
    paths = write_scenario(tmp_path, [record])
    assert _run(paths) == 0
    dumped = paths["output"].read_text(encoding="utf-8")
    assert dumped
    assert "access_token" not in dumped
    assert "ordinarysecretvalue123" not in dumped


def test_double_encoded_credential_url_path_is_rejected(tmp_path: Path):
    record = hermes_record(
        run_id="run-double-encoded-path-secret",
        content="https://example.test/%2574oken/ordinarysecretvalue123",
    )
    paths = write_scenario(tmp_path, [record])
    _assert_secret_rejected(paths, "ordinarysecretvalue123")


@pytest.mark.parametrize(
    "encoded_key",
    ["%61ccess_token", "%2561ccess_token", "%2525252561ccess_token"],
)
def test_encoded_credential_query_key_is_rejected(tmp_path: Path, encoded_key: str):
    secret = "ordinarysecretvalue123"
    record = hermes_record(
        run_id=f"run-query-{encoded_key}",
        content=f"https://example.test/file?{encoded_key}={secret}",
    )
    paths = write_scenario(tmp_path, [record])
    report = _assert_secret_rejected(paths, secret)
    assert "secret_leakage" in report["records"][0]["reason_codes"]


def test_casefolded_hidden_reasoning_and_manifest_hidden_fields_are_rejected(
    tmp_path: Path,
):
    record = hermes_record(run_id="run-reason-case")
    record["messages"][1]["Reasoning"] = "case-folded private plan"
    paths = write_scenario(
        tmp_path,
        [record],
        manifest_overrides={
            "reasoning_retention": {"hidden_reasoning": "keep this private"},
        },
    )
    assert _run(paths) == 0
    dumped = paths["output"].read_text(encoding="utf-8")
    assert "case-folded private plan" not in dumped
    assert "keep this private" not in dumped
    report = _report(paths)
    assert report["accepted_count"] == 0
    assert report["rejected_count"] >= 1


def test_malformed_identity_and_invalid_url_do_not_abort_batch(tmp_path: Path):
    bad_id = hermes_record(run_id="run-list-id")
    bad_id["run_id"] = []
    bad_url = hermes_record(
        run_id="run-bad-url",
        extra_message={
            "role": "tool",
            "name": "fetch",
            "timestamp": "2026-09-21T12:00:30Z",
            "content": "http://example.test:notaport/path",
        },
    )
    good = hermes_record(run_id="run-after-bad")
    paths = write_scenario(tmp_path, [bad_id, bad_url, good])
    assert _run(paths) == 0
    report = _report(paths)
    assert len(report["records"]) == 3
    assert report["records"][0]["status"] == "rejected"
    assert report["records"][1]["status"] == "rejected"
    assert report["records"][2]["status"] == "accepted"
    assert report["accepted_count"] == 1
    assert len(_load_jsonl(paths["output"])) == 1


def test_successful_disposition_requires_independent_verifier_evidence(tmp_path: Path):
    paths = write_scenario(
        tmp_path,
        [hermes_record(run_id="run-self-verify")],
        manifest_overrides={
            "verifier": {
                "artifact_sha256": [],
                "identity": "hermes-agent",
                "outcome": "pass",
                "version": "0.4.0",
            }
        },
    )
    _assert_rejected_with_reason(paths, "verifier")


def test_verifier_artifact_digest_must_match_supplied_content(tmp_path: Path):
    record = hermes_record(run_id="run-verifier-digest")
    verifier = default_verifier(subject=record)
    verifier["artifacts"][0]["content"] = "tampered verifier evidence"
    paths = write_scenario(
        tmp_path,
        [record],
        manifest_overrides={"verifier": verifier},
    )
    assert _run(paths) == 0
    assert paths["output"].read_text(encoding="utf-8") == ""
    assert "verifier_evidence" in _report(paths)["records"][0]["reason_codes"]


def test_manifest_verifier_subject_cannot_be_reused_for_another_trace(tmp_path: Path):
    verified = hermes_record(run_id="run-verified")
    unrelated = hermes_record(run_id="run-unrelated")
    paths = write_scenario(tmp_path, [verified])
    write_json(paths["input"], unrelated)
    assert _run(paths) == 0
    assert paths["output"].read_text(encoding="utf-8") == ""
    reasons = _report(paths)["records"][0]["reason_codes"]
    assert "verifier_subject_mismatch" in reasons


@pytest.mark.parametrize(
    ("overrides", "run_id"),
    [
        ({"rights": {"identifier": "MIT"}}, "run-rights-mismatch"),
        (
            {
                "rights": {"terms_sha256": "b" * 64},
                "input_digests": {"rights": "c" * 64},
            },
            "run-rights-digest-mismatch",
        ),
    ],
)
def test_admitted_rights_must_match_output_and_frozen_terms(
    tmp_path: Path, overrides: dict, run_id: str
):
    admission = default_admission(**overrides)
    paths = write_scenario(
        tmp_path,
        [hermes_record(run_id=run_id)],
        admission=admission,
    )
    _assert_rejected_with_reason(paths, "rights_mismatch")


def test_normalized_output_passes_strict_jsonl_validator(tmp_path: Path):
    paths = write_scenario(tmp_path, [hermes_record(run_id="run-validate")])
    assert _run(paths) == 0
    v0, v1 = _strict_validators()
    errors = validate_file(paths["output"], v0, v1, strict_policy=True)
    assert errors == []
    _assert_legacy_fixture_valid(v0, v1)


def test_strict_validator_rejects_hidden_reasoning_in_v1_1_event(tmp_path: Path):
    paths = write_scenario(tmp_path, [hermes_record(run_id="run-hidden-policy")])
    assert _run(paths) == 0
    record = _load_jsonl(paths["output"])[0]
    record["events"][0]["analysis"] = "private chain"
    injected = tmp_path / "hidden-v1-1.jsonl"
    write_json(injected, record)
    v0 = jsonschema.Draft7Validator(load_schema(V0_SCHEMA))
    v1 = jsonschema.Draft7Validator(load_schema(V1_SCHEMA))
    errors = validate_file(injected, v0, v1, strict_policy=True)
    assert any("hidden reasoning" in error for error in errors)


def test_trajectory_id_uses_full_identity_tuple(tmp_path: Path):
    first = hermes_record(run_id="same")
    second = hermes_record(run_id="same")
    second["session_id"] = "sess-other"
    second["task_id"] = "task-other"
    second["raw_trace_id"] = "trace-other"
    records = []
    for name, source in (("first", first), ("second", second)):
        paths = write_scenario(tmp_path / name, [source])
        assert _run(paths) == 0
        records.extend(_load_jsonl(paths["output"]))
    assert len(records) == 2
    assert records[0]["trajectory_id"] != records[1]["trajectory_id"]
    assert records[0]["trajectory_id"] != "hermes:same"
    assert "sess-same" in records[0]["trajectory_id"]
    assert "sess-other" in records[1]["trajectory_id"]


def test_non_object_message_is_rejected(tmp_path: Path):
    record = hermes_record(run_id="run-msg")
    record["messages"].append("not-an-object")
    paths = write_scenario(tmp_path, [record])
    assert _run(paths) == 0
    report = _report(paths)
    assert report["accepted_count"] == 0
    assert report["rejected_count"] >= 1
    assert paths["output"].read_text(encoding="utf-8") == ""


def test_ipv6_loopback_endpoint_keeps_brackets(tmp_path: Path):
    paths = write_scenario(
        tmp_path,
        [hermes_record(run_id="run-ipv6")],
        manifest_overrides={"ollama": {"endpoint": "http://[::1]:11434"}},
        admission=default_admission(),
    )
    admission = json.loads(paths["admission"].read_text(encoding="utf-8"))
    admission["runtime"]["endpoint"] = "http://[::1]:11434"
    admission["probe"]["endpoint"] = "http://[::1]:11434"
    write_json(paths["admission"], seal_admission(admission))
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    manifest["admission_report_sha256"] = sha256_bytes(paths["admission"].read_bytes())
    write_json(paths["manifest"], manifest)
    assert _run(paths) == 0
    record = _load_jsonl(paths["output"])[0]
    assert record["execution_provenance"]["ollama"]["endpoint"] == "http://[::1]:11434"
    assert "http://::1" not in paths["output"].read_text(encoding="utf-8")
