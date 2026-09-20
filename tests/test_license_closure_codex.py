"""Codex fail-closed holes against the current license-closure HEAD."""

from __future__ import annotations

import json

import pytest

from license_closure_fixtures import (
    BASE_OID,
    CUSTOM_TEXT_SHA256,
    HEAD_OID,
    MERGE_OID,
    SOURCE_HASH,
    STALE_DIGEST,
    WRONG_HEAD_OID,
    bind_pr_source_hash,
    bind_source_hash,
    custom_license_bundle,
    inventory_alias,
    inventory_pr,
    repository,
    spdx_known_bundle,
    with_code_state,
)
from license_closure_helpers import ROOT, _assert_schema, _report
from lib.eligibility_repositories import _repository_row
from lib.license_closure import (
    classify_license_family,
    inventory_row_source_hash,
    validate_positive_release,
)

def test_inventory_source_hash_matches_eligibility_producer():
    raw = {
        "archived": False,
        "created_at": "2026-01-01T00:00:00Z",
        "database_id": 1,
        "default_branch": "main",
        "disabled": False,
        "fork": False,
        "id": "R_kgDOwidget",
        "license": {
            "name": "MIT License",
            "spdx_id": "MIT",
            "url": "https://api.github.com/licenses/mit",
        },
        "name": "widget",
        "name_with_owner": "rmems/widget",
        "owner_kind": "Organization",
        "owner_login": "rmems",
        "pull_request_total_count": 3,
        "pushed_at": "2026-01-02T00:00:00Z",
        "updated_at": "2026-01-03T00:00:00Z",
        "url": "https://github.com/rmems/widget",
        "visibility": "public",
    }
    row = _repository_row(raw)
    assert inventory_row_source_hash(row) == row["source_hash"]


def test_v07_inventory_source_hashes_match_producer_payload():
    path = ROOT / "datasets/inventory/v0.7/repositories.jsonl"
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows
    assert all(row["source_hash"] == inventory_row_source_hash(row) for row in rows)


def test_malformed_singular_license_cannot_close():
    bundle = spdx_known_bundle()
    bundle["card"]["source_license"] = {}
    bundle["card"]["source_licenses"] = {"rmems/widget": "MIT"}
    report = _report(bundle)
    _assert_schema(report)
    assert "declarations_disagree" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_misplaced_spdx_parentheses_are_unknown():
    assert classify_license_family("MIT ( AND Apache-2.0)") == "unknown"
    assert classify_license_family("(MIT OR Apache-2.0)") == "spdx"
    assert classify_license_family("(MIT OR Apache-2.0) AND BSD-3-Clause") == "spdx"
    assert classify_license_family("(MIT) OR (Apache-2.0)") == "spdx"
    assert classify_license_family("(MIT)(Apache-2.0)") == "unknown"
    assert classify_license_family("((MIT)(Apache-2.0))") == "unknown"


def test_parenthesized_with_operands_are_unknown():
    assert classify_license_family("MIT WITH Apache-2.0") == "unknown"
    assert classify_license_family("MIT WITH (Apache-2.0)") == "unknown"
    assert classify_license_family("(MIT) WITH Apache-2.0") == "unknown"


def test_duplicate_repository_id_is_rejected():
    bundle = spdx_known_bundle()
    current = bind_source_hash(
        {**bundle["repositories"][0], "repository_id": "R_kgDOshared"}
    )
    other = bind_source_hash(
        {
            **repository(
                "rmems/other",
                spdx_id="MIT",
                license_name="MIT License",
                url="https://api.github.com/licenses/mit",
            ),
            "repository_id": "R_kgDOshared",
        }
    )
    bundle["repositories"] = [current, other]
    with pytest.raises(ValueError, match="Duplicate inventory repository id"):
        _report(bundle)


def test_missing_merge_commit_does_not_fall_back_to_head():
    bundle = spdx_known_bundle()
    bundle["records"][0] = with_code_state(bundle["records"][0], commit_oid=HEAD_OID)
    pr = inventory_pr("rmems/widget", 1)
    del pr["merge_commit_oid"]
    bundle["pull_requests"] = [bind_pr_source_hash(pr)]
    report = _report(bundle)
    _assert_schema(report)
    assert "snapshot_provenance_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_stale_pr_inventory_source_hash_cannot_close():
    bundle = spdx_known_bundle()
    bundle["records"][0] = with_code_state(bundle["records"][0])
    pr = inventory_pr("rmems/widget", 1, head_oid=WRONG_HEAD_OID)
    pr["head_oid"] = HEAD_OID
    bundle["pull_requests"] = [pr]
    with pytest.raises(ValueError, match="source_hash"):
        _report(bundle)


def test_pr_inventory_requires_source_hash():
    bundle = spdx_known_bundle()
    bundle["records"][0] = with_code_state(bundle["records"][0])
    pr = inventory_pr("rmems/widget", 1)
    del pr["source_hash"]
    bundle["pull_requests"] = [pr]
    with pytest.raises(ValueError, match="source_hash"):
        _report(bundle)


def test_custom_report_validates_with_frozen_custom_object():
    report = _report(custom_license_bundle())
    _assert_schema(report)
    released = report["released_positives"][0]
    assert released["custom_license"]["text_sha256"] == CUSTOM_TEXT_SHA256
    assert released["inventory_license"]["spdx_id"] == "LicenseRef-TemporalFocus"
    assert not validate_positive_release(report)


def test_quarantined_custom_license_retains_frozen_evidence():
    bundle = custom_license_bundle()
    bundle["card"]["license_evidence_digest"] = STALE_DIGEST
    bundle["manifest"]["license_evidence_digest"] = STALE_DIGEST
    report = _report(bundle)
    _assert_schema(report)
    row = report["quarantined"][0]
    assert "source_license_changed" in row["reason_codes"]
    assert row["evidence"]["custom_license"]["text_sha256"] == CUSTOM_TEXT_SHA256
    assert report["released_positives"] == []


def test_spdx_report_validates_with_frozen_inventory_license():
    report = _report(spdx_known_bundle())
    _assert_schema(report)
    released = report["released_positives"][0]
    assert released["inventory_license"]["spdx_id"] == "MIT"
    assert not validate_positive_release(report)


def test_malformed_plural_license_map_cannot_close():
    bundle = spdx_known_bundle()
    bundle["card"]["source_licenses"] = []
    report = _report(bundle)
    _assert_schema(report)
    assert "declarations_disagree" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_card_license_families_must_match_closed_evidence():
    bundle = spdx_known_bundle()
    bundle["card"]["license_families"] = ["custom"]
    bundle["card"]["unresolved_license_count"] = 5
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is False
    assert report["bundle_errors"]


def test_stale_prior_inventory_source_hash_cannot_close():
    bundle = spdx_known_bundle()
    prior = dict(bundle["repositories"][0])
    prior["source_hash"] = SOURCE_HASH
    bundle["prior_repositories"] = [prior]
    report = _report(bundle)
    _assert_schema(report)
    assert "source_license_changed" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_pr_inventory_follows_repository_aliases():
    bundle = spdx_known_bundle()
    current = dict(bundle["repositories"][0])
    current["name_with_owner"] = "rmems/widget-renamed"
    current["aliases"] = [inventory_alias("rmems/widget")]
    bundle["repositories"] = [bind_source_hash(current)]
    bundle["records"][0] = with_code_state(bundle["records"][0])
    bundle["records"][0]["repo"] = "rmems/widget-renamed"
    bundle["card"]["source_repo"] = "rmems/widget-renamed"
    bundle["manifest"]["source_repo"] = "rmems/widget-renamed"
    bundle["pull_requests"] = [inventory_pr("rmems/widget", 1)]
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is True


def test_prior_inventory_matches_repository_id_not_reused_name():
    bundle = spdx_known_bundle()
    current = dict(bundle["repositories"][0])
    current["repository_id"] = "R_kgDOwidget"
    bundle["repositories"] = [bind_source_hash(current)]
    name_holder = bind_source_hash(
        {
            **repository(
                "rmems/widget",
                spdx_id="MIT",
                license_name="MIT License",
                url="https://api.github.com/licenses/mit",
            ),
            "repository_id": "R_kgDOunrelated",
        }
    )
    actual_prior = bind_source_hash(
        {
            **repository(
                "rmems/widget-old",
                spdx_id="Apache-2.0",
                license_name="Apache License 2.0",
                url="https://api.github.com/licenses/apache-2.0",
            ),
            "repository_id": "R_kgDOwidget",
        }
    )
    bundle["prior_repositories"] = [name_holder, actual_prior]
    report = _report(bundle)
    _assert_schema(report)
    assert "source_license_changed" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_conflicting_pr_rows_across_aliases_are_rejected():
    bundle = spdx_known_bundle()
    current = dict(bundle["repositories"][0])
    current["aliases"] = [inventory_alias("rmems/widget-old")]
    bundle["repositories"] = [bind_source_hash(current)]
    bundle["records"][0] = with_code_state(bundle["records"][0])
    bundle["pull_requests"] = [
        inventory_pr("rmems/widget", 1),
        inventory_pr("rmems/widget-old", 1, head_oid=WRONG_HEAD_OID),
    ]
    with pytest.raises(ValueError, match="Duplicate inventory pull request"):
        _report(bundle)


def test_card_declaration_follows_inventory_aliases():
    bundle = spdx_known_bundle()
    current = dict(bundle["repositories"][0])
    current["name_with_owner"] = "rmems/widget-renamed"
    current["aliases"] = [inventory_alias("rmems/widget")]
    bundle["repositories"] = [bind_source_hash(current)]
    digest = bundle["card"]["license_evidence_digest"]
    bundle["card"] = {
        "name": "fixture",
        "source_repo": "rmems/widget-renamed",
        "source_licenses": {"rmems/widget-renamed": "MIT"},
        "license_evidence_digests": {"rmems/widget-renamed": digest},
    }
    bundle["manifest"] = {
        "name": "fixture",
        "source_repo": "rmems/widget-renamed",
        "source_licenses": {"rmems/widget-renamed": "MIT"},
        "license_evidence_digests": {"rmems/widget-renamed": digest},
        "license_families": ["spdx"],
        "unresolved_license_count": 0,
    }
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is True


def test_non_string_license_families_are_bundle_errors():
    bundle = spdx_known_bundle()
    bundle["card"]["license_families"] = ["spdx", 1]
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is False
    assert report["bundle_errors"]


def test_unhashable_license_families_are_bundle_errors():
    bundle = spdx_known_bundle()
    bundle["card"]["license_families"] = [{}]
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is False
    assert report["bundle_errors"]


def test_uppercase_record_oid_matches_inventory_pr():
    base_oid = "abc" + "1" * 37
    head_oid = "def" + "2" * 37
    merge_oid = "a1b" + "3" * 37
    bundle = spdx_known_bundle()
    bundle["records"][0] = with_code_state(
        bundle["records"][0],
        base_oid=base_oid.upper(),
        head_oid=head_oid.upper(),
        commit_oid=merge_oid.upper(),
    )
    bundle["pull_requests"] = [
        inventory_pr(
            "rmems/widget",
            1,
            base_oid=base_oid,
            head_oid=head_oid,
            merge_commit_oid=merge_oid,
        )
    ]
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is True


_DECLARATION_EDITS = (
    pytest.param(
        [("card", "source_repos", ["rmems/widget", "a/one"]),
         ("manifest", "source_repos", ["rmems/widget", "b/two"])],
        id="card-manifest-repos-disagree",
    ),
    pytest.param([("card", "source_repos", {})], id="malformed-plural-map"),
    pytest.param(
        [("card", "source_repos", ["rmems/widget", 1])],
        id="non-string-element",
    ),
    pytest.param(
        [("card", "source_repos", ["rmems/widget", "  "])],
        id="blank-element",
    ),
    pytest.param(
        [("card", "source_repos", ["rmems/widget", "evil/unknown"]),
         ("manifest", "source_repos", ["rmems/widget", "evil/unknown"])],
        id="unknown-repo",
    ),
    pytest.param(
        [("card", "source_repo", {}), ("card", "source_repos", ["rmems/widget"]),
         ("manifest", "source_repo", {}), ("manifest", "source_repos", ["rmems/widget"])],
        id="malformed-singular",
    ),
    pytest.param(
        [("card", "source_repo", None), ("card", "source_repos", None)],
        id="omitted-card-coverage",
    ),
    pytest.param(
        [("manifest", "source_repo", None), ("manifest", "source_repos", None)],
        id="omitted-manifest-coverage",
    ),
    pytest.param(
        [("card", "source_repo", None), ("card", "source_repos", [])],
        id="empty-coverage",
    ),
)


@pytest.mark.parametrize("edits", _DECLARATION_EDITS)
def test_conflicting_source_repo_declarations_cannot_close(edits):
    bundle = spdx_known_bundle()
    for doc, key, value in edits:
        if value is None:
            bundle[doc].pop(key, None)
        else:
            bundle[doc][key] = value
    report = _report(bundle)
    _assert_schema(report)
    assert "declarations_disagree" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def _record_with_base_only(bundle: dict) -> None:
    bundle["records"][0] = with_code_state(bundle["records"][0])
    bundle["records"][0]["repository"] = {"base_oid": BASE_OID}
    bundle["pull_requests"] = [inventory_pr("rmems/widget", 1)]


def _record_with_truncated_oids(bundle: dict) -> None:
    bundle["records"][0] = with_code_state(
        bundle["records"][0], base_oid="abc", head_oid="def", commit_oid="123"
    )
    bundle["pull_requests"] = [
        inventory_pr("rmems/widget", 1, base_oid="abc", head_oid="def",
                     merge_commit_oid="123")
    ]


def _record_with_malformed_role_oids(bundle: dict) -> None:
    bundle["records"][0] = with_code_state(
        bundle["records"][0], base_oid="abc", head_oid="def",
        commit_oid=MERGE_OID,
    )
    bundle["pull_requests"] = [inventory_pr("rmems/widget", 1)]


def _pr_row_repo_id_mismatch(bundle: dict) -> None:
    current = dict(bundle["repositories"][0])
    current["repository_id"] = "R_kgDOwidget"
    bundle["repositories"] = [bind_source_hash(current)]
    bundle["records"][0] = with_code_state(bundle["records"][0])
    pr = inventory_pr("rmems/widget", 1)
    pr["repository_id"] = "R_kgDOother"
    bundle["pull_requests"] = [bind_pr_source_hash(pr)]


def _alias_pr_repo_id_mismatch(bundle: dict) -> None:
    _pr_row_repo_id_mismatch(bundle)
    current = dict(bundle["repositories"][0])
    current["aliases"] = [inventory_alias("rmems/widget-old")]
    bundle["repositories"] = [bind_source_hash(current)]
    canonical = bundle["pull_requests"][0]
    alias = inventory_pr("rmems/widget-old", 1)
    alias["repository_id"] = "R_kgDOother"
    bundle["pull_requests"] = [
        canonical,
        bind_pr_source_hash(alias),
    ]


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(_record_with_base_only, id="base-only-record"),
        pytest.param(_record_with_truncated_oids, id="truncated-oids"),
        pytest.param(
            _record_with_malformed_role_oids, id="malformed-role-oids"
        ),
        pytest.param(_pr_row_repo_id_mismatch, id="pr-repo-id-mismatch"),
        pytest.param(_alias_pr_repo_id_mismatch, id="alias-repo-id-mismatch"),
    ],
)
def test_provenance_blocked_records_quarantine(mutate):
    bundle = spdx_known_bundle()
    mutate(bundle)
    report = _report(bundle)
    _assert_schema(report)
    assert "snapshot_provenance_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_card_and_manifest_source_repos_follow_aliases():
    bundle = spdx_known_bundle()
    current = dict(bundle["repositories"][0])
    current["aliases"] = [inventory_alias("rmems/widget-old")]
    bundle["repositories"] = [bind_source_hash(current)]
    bundle["card"]["source_repo"] = "rmems/widget"
    bundle["manifest"]["source_repo"] = "rmems/widget-old"
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is True


def test_pr_inventory_repository_id_match_can_close():
    bundle = spdx_known_bundle()
    current = dict(bundle["repositories"][0])
    current["repository_id"] = "R_kgDOwidget"
    bundle["repositories"] = [bind_source_hash(current)]
    bundle["records"][0] = with_code_state(bundle["records"][0])
    pr = inventory_pr("rmems/widget", 1)
    pr["repository_id"] = "R_kgDOwidget"
    bundle["pull_requests"] = [bind_pr_source_hash(pr)]
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is True


def test_duplicate_record_ids_keep_inventory_license():
    bundle = spdx_known_bundle()
    bundle["records"].append(dict(bundle["records"][0]))
    report = _report(bundle)
    _assert_schema(report)
    assert report["released_positives"] == []
    assert all(
        row["evidence"]["inventory_license"]["spdx_id"] == "MIT"
        for row in report["quarantined"]
    )


def test_malformed_manifest_record_entry_cannot_close():
    bundle = spdx_known_bundle()
    bundle["manifest"]["records"] = [
        {"id": bundle["records"][0]["id"]},
        {},
    ]
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is False
    assert any("record ids" in error for error in report["bundle_errors"])


