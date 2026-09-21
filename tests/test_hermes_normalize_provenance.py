"""Normalize verified Hermes traces into trajectory v1.1 (Linear RM-1348)."""

from hermes_normalize_test_support import *  # noqa: F403


def test_credential_url_path_is_rejected(tmp_path: Path):
    record = hermes_record(
        run_id="run-path-secret",
        extra_message={
            "role": "tool",
            "name": "fetch",
            "timestamp": "2026-09-21T12:00:30Z",
            "content": "https://example.test/token/ordinarysecretvalue123",
        },
    )
    paths = write_scenario(tmp_path, [record])
    assert _run(paths) == 0
    dumped = paths["output"].read_text(encoding="utf-8")
    assert dumped == ""
    assert "ordinarysecretvalue123" not in dumped
    report = _report(paths)
    assert report["rejected_count"] >= 1


def test_percent_encoded_credential_url_path_is_rejected(tmp_path: Path):
    record = hermes_record(
        run_id="run-encoded-path-secret",
        extra_message={
            "role": "tool",
            "name": "fetch",
            "timestamp": "2026-09-21T12:00:30Z",
            "content": "https://example.test/%74oken/ordinarysecretvalue123",
        },
    )
    paths = write_scenario(tmp_path, [record])
    assert _run(paths) == 0
    dumped = paths["output"].read_text(encoding="utf-8")
    assert dumped == ""
    assert "ordinarysecretvalue123" not in dumped
    assert _report(paths)["rejected_count"] >= 1


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
    assert _run(paths) == 0
    assert paths["output"].read_text(encoding="utf-8") == ""
    assert _report(paths)["rejected_count"] >= 1


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
    assert _run(paths) == 0
    dumped = paths["output"].read_text(encoding="utf-8")
    assert dumped == ""
    assert secret not in dumped
    assert "secret_leakage" in _report(paths)["records"][0]["reason_codes"]


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
    assert _run(paths) == 0
    assert paths["output"].read_text(encoding="utf-8") == ""
    report = _report(paths)
    assert report["accepted_count"] == 0
    joined = ",".join(report["records"][0]["reason_codes"])
    assert "verifier" in joined


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


def test_output_license_cannot_disagree_with_admitted_rights(tmp_path: Path):
    admission = default_admission(rights={"identifier": "MIT"})
    paths = write_scenario(
        tmp_path,
        [hermes_record(run_id="run-rights-mismatch")],
        admission=admission,
    )
    assert _run(paths) == 0
    assert paths["output"].read_text(encoding="utf-8") == ""
    assert "rights_mismatch" in _report(paths)["records"][0]["reason_codes"]


def test_rights_terms_digest_must_match_frozen_rights_input(tmp_path: Path):
    admission = default_admission(
        rights={"terms_sha256": "b" * 64},
        input_digests={"rights": "c" * 64},
    )
    paths = write_scenario(
        tmp_path,
        [hermes_record(run_id="run-rights-digest-mismatch")],
        admission=admission,
    )
    assert _run(paths) == 0
    assert paths["output"].read_text(encoding="utf-8") == ""
    assert "rights_mismatch" in _report(paths)["records"][0]["reason_codes"]


def test_normalized_output_passes_strict_jsonl_validator(tmp_path: Path):
    paths = write_scenario(tmp_path, [hermes_record(run_id="run-validate")])
    assert _run(paths) == 0
    v0 = jsonschema.Draft7Validator(
        load_schema(V0_SCHEMA),
        format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER,
    )
    v1 = jsonschema.Draft7Validator(
        load_schema(V1_SCHEMA),
        format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER,
    )
    errors = validate_file(paths["output"], v0, v1, strict_policy=True)
    assert errors == []
    v0_errors = validate_file(
        ROOT / "tests" / "fixtures" / "v1" / "software_valid.jsonl",
        v0,
        v1,
        strict_policy=True,
    )
    assert v0_errors == []


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
