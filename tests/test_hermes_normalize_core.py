"""Normalize verified Hermes traces into trajectory v1.1 (Linear RM-1348)."""

from hermes_normalize_test_support import *  # noqa: F403
from lib import hermes_normalize as hermes_normalize_module


def test_cli_contract_exposes_exact_flags():
    actions = {action.dest for action in build_parser()._actions}
    assert {
        "input",
        "run_manifest",
        "model_admission",
        "output",
        "report",
    }.issubset(actions)
    usage = build_parser().format_help()
    assert "--input" in usage
    assert "--run-manifest" in usage
    assert "--model-admission" in usage
    assert "--output" in usage
    assert "--report" in usage


def test_output_and_report_are_rolled_back_if_second_publish_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    paths = write_scenario(tmp_path, [hermes_record(run_id="run-pair-rollback")])
    paths["output"].write_text("old-output\n", encoding="utf-8")
    paths["report"].write_text("old-report\n", encoding="utf-8")
    original_replace = Path.replace
    failed = False

    def fail_first_report_replace(source: Path, target: Path):
        nonlocal failed
        if Path(target) == paths["report"] and not failed:
            failed = True
            raise OSError("synthetic report publish failure")
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_first_report_replace)
    with pytest.raises(OSError, match="synthetic report publish failure"):
        hermes_normalize_module.normalize_files(
            input_path=paths["input"],
            run_manifest_path=paths["manifest"],
            model_admission_path=paths["admission"],
            output_path=paths["output"],
            report_path=paths["report"],
        )
    assert paths["output"].read_text(encoding="utf-8") == "old-output\n"
    assert paths["report"].read_text(encoding="utf-8") == "old-report\n"


def test_successful_run_is_accepted_v1_1_and_binds_provenance(tmp_path: Path):
    paths = _scenario_from_fixture(tmp_path, "successful.jsonl")
    assert _run(paths) == 0
    records = _load_jsonl(paths["output"])
    assert len(records) == 1
    record = records[0]
    jsonschema.Draft7Validator(
        load_schema(V1_1_SCHEMA),
        format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER,
    ).validate(record)
    assert record["schema_version"] in ("1.1", "v1.1")
    assert record["execution_provenance"]["producer"]["profile"] == "Local Model Lab"
    assert record["terminal_disposition"] == "successful"
    assert record["execution"]["producer_completed"] is True
    assert record["execution"]["producer_partial"] is False
    assert "provenance_binding" not in record
    binding = record["execution_provenance"]
    assert binding["run_id"] == "run-success"
    assert binding["session_id"] == "sess-run-success"
    assert binding["task_id"] == "task-run-success"
    assert binding["raw_trace_id"] == "trace-run-success"
    assert binding["input_sha256"] == sha256_bytes(paths["input"].read_bytes())
    assert binding["run_manifest_sha256"] == sha256_bytes(
        paths["manifest"].read_bytes()
    )
    assert binding["admission_report_sha256"] == sha256_bytes(
        paths["admission"].read_bytes()
    )
    assert binding["raw_trace_sha256"] == sha256_bytes(
        paths["input"].read_bytes().splitlines()[0]
    )
    assert binding["producer"]["name"] == "hermes-agent"
    assert binding["producer"]["revision"]
    assert binding["model"]["ollama_digest"].startswith("sha256:")
    assert binding["model"]["upstream_revision"] == "synthetic-upstream-1"
    assert binding["repository"]["base_oid"] == BASE_OID
    assert binding["repository"]["head_oid"] == HEAD_OID
    assert binding["workspace"]["kind"] == "isolated"
    assert binding["ollama"]["endpoint"].startswith("http://127.0.0.1")
    assert binding["workspace"]["id"] == "ws-isolated-001"
    assert binding["reasoning_retention"]["policy"] == "strip_hidden"
    assert binding["verifier"]["identity"] == "pytest-local"
    assert binding["verifier"]["outcome"] == "pass"
    assert binding["verifier"]["artifact_sha256"] == [VERIFIER_ARTIFACT]
    report = _report(paths)
    assert report["accepted_count"] == 1
    assert report["quarantined_count"] == 0
    assert report["rejected_count"] == 0
    assert report["records"][0]["status"] == "accepted"


def test_completed_true_with_failing_verifier_is_not_successful(tmp_path: Path):
    paths = _scenario_from_fixture(tmp_path, "completed_true_verifier_failed.jsonl")
    assert _run(paths) == 0
    records = _load_jsonl(paths["output"])
    assert len(records) == 1
    assert records[0]["execution"]["producer_completed"] is True
    assert records[0]["terminal_disposition"] == "failed"
    assert records[0]["terminal_disposition"] != "successful"
    assert records[0]["execution_provenance"]["verifier"]["outcome"] == "fail"


def test_partial_and_interrupted_runs_keep_execution_metadata(tmp_path: Path):
    partial = _scenario_from_fixture(tmp_path / "partial", "partial.jsonl")
    interrupted = _scenario_from_fixture(tmp_path / "interrupted", "interrupted.jsonl")
    assert _run(partial) == 0
    assert _run(interrupted) == 0
    partial_record = _load_jsonl(partial["output"])[0]
    interrupted_record = _load_jsonl(interrupted["output"])[0]
    assert partial_record["execution"]["producer_partial"] is True
    assert partial_record["execution"]["producer_completed"] is False
    assert partial_record["terminal_disposition"] == "interrupted"
    assert interrupted_record["terminal_disposition"] == "interrupted"
    assert interrupted_record["execution"]["producer_completed"] is False


def test_unverified_run_is_quarantined(tmp_path: Path):
    paths = _scenario_from_fixture(tmp_path, "unverified.jsonl")
    assert _run(paths) == 0
    assert paths["output"].read_text(encoding="utf-8") == ""
    report = _report(paths)
    assert report["accepted_count"] == 0
    assert report["quarantined_count"] == 1
    assert report["records"][0]["status"] == "quarantined"
    assert "unverified" in ",".join(report["records"][0]["reason_codes"])


def test_hidden_reasoning_is_stripped_from_trainable_views(tmp_path: Path):
    paths = _scenario_from_fixture(tmp_path, "hidden_reasoning.jsonl")
    assert _run(paths) == 0
    dumped = paths["output"].read_text(encoding="utf-8")
    assert "<think>" not in dumped.lower()
    assert "</think>" not in dumped.lower()
    assert "hide this private chain" not in dumped
    assert "internal plan must not be trainable" not in dumped
    record = _load_jsonl(paths["output"])[0]
    assert "I'll inspect loop.py" in json.dumps(record)
    assert record["execution_provenance"]["reasoning_retention"]["policy"] == (
        "strip_hidden"
    )


def test_secret_leakage_is_rejected_and_not_emitted(tmp_path: Path):
    paths = _scenario_from_fixture(tmp_path, "secret_leak.jsonl")
    original = paths["input"].read_bytes()
    assert _run(paths) == 0
    assert paths["input"].read_bytes() == original
    assert paths["output"].read_text(encoding="utf-8") == ""
    report = _report(paths)
    assert report["rejected_count"] == 1
    assert "secret" in ",".join(report["records"][0]["reason_codes"])
    dumped = paths["report"].read_text(encoding="utf-8")
    assert "ghp_" not in dumped


def test_query_secrets_are_stripped_from_accepted_output(tmp_path: Path):
    paths = _scenario_from_fixture(tmp_path, "query_secret.jsonl")
    assert _run(paths) == 0
    dumped = paths["output"].read_text(encoding="utf-8")
    assert "supersecretvalue1" not in dumped
    assert "access_token" not in dumped
    record = _load_jsonl(paths["output"])[0]
    assert record["schema_version"] in ("1.1", "v1.1")


def test_malformed_and_truncated_jsonl_are_rejected(tmp_path: Path):
    malformed = _scenario_from_fixture(tmp_path / "malformed", "malformed.jsonl")
    truncated = _scenario_from_fixture(tmp_path / "truncated", "truncated.jsonl")
    assert _run(malformed) == 0
    assert _run(truncated) == 0
    malformed_report = _report(malformed)
    truncated_report = _report(truncated)
    assert malformed_report["rejected_count"] == 1
    assert truncated_report["rejected_count"] == 1
    assert malformed["output"].read_text(encoding="utf-8") == ""
    assert truncated["output"].read_text(encoding="utf-8") == ""
    assert "invalid_json" in malformed_report["records"][0]["reason_codes"]
    assert "invalid_json" in truncated_report["records"][0]["reason_codes"]


def test_duplicate_keys_and_duplicate_records_are_rejected(tmp_path: Path):
    keys = _scenario_from_fixture(tmp_path / "keys", "duplicate_keys.jsonl")
    records = _scenario_from_fixture(tmp_path / "records", "duplicate_records.jsonl")
    assert _run(keys) == 0
    assert _run(records) == 0
    keys_report = _report(keys)
    records_report = _report(records)
    assert keys_report["rejected_count"] == 1
    assert "duplicate_key" in ",".join(keys_report["records"][0]["reason_codes"])
    statuses = [row["status"] for row in records_report["records"]]
    assert statuses[0] == "accepted"
    assert statuses[1] == "rejected"
    assert "duplicate" in ",".join(records_report["records"][1]["reason_codes"])
    assert len(_load_jsonl(records["output"])) == 1


def test_admission_digest_mismatch_fails_closed(tmp_path: Path):
    paths = write_scenario(tmp_path, [hermes_record(run_id="run-mismatch")])
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    manifest["admission_report_sha256"] = "0" * 64
    write_json(paths["manifest"], manifest)
    assert _run(paths) == 0
    assert paths["output"].read_text(encoding="utf-8") == ""
    report = _report(paths)
    assert report["rejected_count"] >= 1
    assert any("digest" in ",".join(row["reason_codes"]) for row in report["records"])


def test_output_and_report_cannot_alias_inputs(tmp_path: Path):
    paths = write_scenario(tmp_path, [hermes_record(run_id="run-alias")])
    original = paths["input"].read_bytes()
    colliding = dict(paths)
    colliding["output"] = paths["input"]
    assert _run(colliding) == 2
    assert paths["input"].read_bytes() == original
    colliding_report = dict(paths)
    colliding_report["report"] = paths["manifest"]
    assert _run(colliding_report) == 2
    colliding_same = dict(paths)
    colliding_same["output"] = paths["report"]
    colliding_same["report"] = paths["report"]
    assert _run(colliding_same) == 2


def test_hard_link_output_collision_fails_closed(tmp_path: Path):
    paths = write_scenario(tmp_path, [hermes_record(run_id="run-link")])
    linked = tmp_path / "linked-output.jsonl"
    linked.hardlink_to(paths["input"])
    colliding = dict(paths)
    colliding["output"] = linked
    original = paths["input"].read_bytes()
    assert _run(colliding) == 2
    assert paths["input"].read_bytes() == original


def test_rerun_is_byte_identical_canonical_json(tmp_path: Path):
    paths = write_scenario(
        tmp_path,
        [hermes_record(run_id="run-stable", content="Stable observable answer.")],
    )
    assert _run(paths) == 0
    first_out = paths["output"].read_bytes()
    first_report = paths["report"].read_bytes()
    assert b"\r" not in first_out
    assert first_out.endswith(b"\n")
    assert first_report.endswith(b"\n")
    assert _run(paths) == 0
    assert paths["output"].read_bytes() == first_out
    assert paths["report"].read_bytes() == first_report
    line = first_out.strip()
    parsed = json.loads(line)
    assert line == canonical_dumps(parsed).encode("utf-8")
    assert list(json.loads(first_report).keys()) == sorted(
        json.loads(first_report).keys()
    )


def test_local_file_boundary_rejects_http_and_allows_injected_replay(tmp_path: Path):
    paths = write_scenario(tmp_path, [hermes_record(run_id="run-replay")])
    frozen = {
        paths["input"].resolve(): paths["input"].read_bytes(),
        paths["manifest"].resolve(): paths["manifest"].read_bytes(),
        paths["admission"].resolve(): paths["admission"].read_bytes(),
    }
    boundary = LocalFileBoundary(opener=lambda path: frozen[path.resolve()])
    report = normalize_files(
        input_path=paths["input"],
        run_manifest_path=paths["manifest"],
        model_admission_path=paths["admission"],
        output_path=paths["output"],
        report_path=paths["report"],
        source=boundary,
    )
    assert report["accepted_count"] == 1
    with pytest.raises(ValueError, match="local file"):
        LocalFileBoundary().read_bytes(Path("https://example.test/trace.jsonl"))
