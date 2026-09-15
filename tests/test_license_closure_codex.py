"""Codex fail-closed holes against the current license-closure HEAD."""

from __future__ import annotations

import json

import pytest

from license_closure_fixtures import (
    BASE_OID,
    CUSTOM_TEXT_SHA256,
    HEAD_OID,
    SOURCE_HASH,
    WRONG_HEAD_OID,
    bind_pr_source_hash,
    bind_source_hash,
    custom_license_bundle,
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


def test_custom_family_without_frozen_evidence_cannot_validate_release():
    report = _report(spdx_known_bundle())
    report["released_positives"][0]["spdx_id"] = "LicenseRef-Fake"
    report["released_positives"][0]["license_family"] = "custom"
    report["license_families"] = ["custom"]
    report["evidence_digests"][0]["spdx_id"] = "LicenseRef-Fake"
    report["evidence_digests"][0]["family"] = "custom"
    errors = validate_positive_release(report)
    assert errors
    assert any("license family" in error for error in errors)


def test_custom_report_validates_with_frozen_custom_object():
    report = _report(custom_license_bundle())
    _assert_schema(report)
    released = report["released_positives"][0]
    assert released["custom_license"]["text_sha256"] == CUSTOM_TEXT_SHA256
    assert released["inventory_license"]["spdx_id"] == "LicenseRef-TemporalFocus"
    assert not validate_positive_release(report)


def test_swapped_custom_text_digest_cannot_validate_release():
    report = _report(custom_license_bundle())
    released = report["released_positives"][0]
    released["custom_license"] = {
        **released["custom_license"],
        "text_sha256": "e" * 64,
    }
    _assert_schema(report)
    errors = validate_positive_release(report)
    assert errors
    assert any("license family" in error for error in errors)


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
    current["aliases"] = [{"name_with_owner": "rmems/widget"}]
    bundle["repositories"] = [bind_source_hash(current)]
    bundle["records"][0] = with_code_state(bundle["records"][0])
    bundle["records"][0]["repo"] = "rmems/widget-renamed"
    bundle["card"]["source_repo"] = "rmems/widget-renamed"
    bundle["manifest"]["source_repo"] = "rmems/widget-renamed"
    bundle["pull_requests"] = [inventory_pr("rmems/widget", 1)]
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is True


def test_html_comment_is_not_markdown_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = "## License / provenance\n\n<!-- MIT -->\n"
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_fenced_license_heading_is_not_markdown_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = "```\n## License / provenance\nMIT\n```\n"
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


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
    current["aliases"] = [{"name_with_owner": "rmems/widget-old"}]
    bundle["repositories"] = [bind_source_hash(current)]
    bundle["records"][0] = with_code_state(bundle["records"][0])
    bundle["pull_requests"] = [
        inventory_pr("rmems/widget", 1),
        inventory_pr("rmems/widget-old", 1, head_oid=WRONG_HEAD_OID),
    ]
    with pytest.raises(ValueError, match="Duplicate inventory pull request"):
        _report(bundle)


def test_h1_after_license_section_is_not_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = "## License / provenance\n\nNo license\n# Appendix\nMIT\n"
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_card_declaration_follows_inventory_aliases():
    bundle = spdx_known_bundle()
    current = dict(bundle["repositories"][0])
    current["name_with_owner"] = "rmems/widget-renamed"
    current["aliases"] = [{"name_with_owner": "rmems/widget"}]
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


def test_base_only_record_does_not_satisfy_pr_provenance():
    bundle = spdx_known_bundle()
    bundle["records"][0] = with_code_state(bundle["records"][0])
    bundle["records"][0]["repository"] = {"base_oid": BASE_OID}
    bundle["pull_requests"] = [inventory_pr("rmems/widget", 1)]
    report = _report(bundle)
    _assert_schema(report)
    assert "snapshot_provenance_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_non_string_license_families_are_bundle_errors():
    bundle = spdx_known_bundle()
    bundle["card"]["license_families"] = ["spdx", 1]
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is False
    assert report["bundle_errors"]


def test_markdown_link_destination_is_not_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = (
        "## License / provenance\n\n[license details](https://example.test/MIT)\n"
    )
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_markdown_link_text_is_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = (
        "## License / provenance\n\n[MIT](https://example.test/license)\n"
    )
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is True


def test_truncated_git_oids_cannot_close():
    bundle = spdx_known_bundle()
    bundle["records"][0] = with_code_state(
        bundle["records"][0],
        base_oid="abc",
        head_oid="def",
        commit_oid="123",
    )
    bundle["pull_requests"] = [
        inventory_pr(
            "rmems/widget",
            1,
            base_oid="abc",
            head_oid="def",
            merge_commit_oid="123",
        )
    ]
    report = _report(bundle)
    _assert_schema(report)
    assert "snapshot_provenance_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


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


def test_card_and_manifest_source_repos_must_agree():
    bundle = spdx_known_bundle()
    bundle["card"]["source_repos"] = ["rmems/widget", "a/one"]
    bundle["manifest"]["source_repos"] = ["rmems/widget", "b/two"]
    report = _report(bundle)
    _assert_schema(report)
    assert "declarations_disagree" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_malformed_source_repos_cannot_close():
    bundle = spdx_known_bundle()
    bundle["card"]["source_repos"] = {}
    report = _report(bundle)
    _assert_schema(report)
    assert "declarations_disagree" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_non_string_source_repos_elements_cannot_close():
    bundle = spdx_known_bundle()
    bundle["card"]["source_repos"] = ["rmems/widget", 1]
    report = _report(bundle)
    _assert_schema(report)
    assert "declarations_disagree" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_blank_source_repos_elements_cannot_close():
    bundle = spdx_known_bundle()
    bundle["card"]["source_repos"] = ["rmems/widget", "  "]
    report = _report(bundle)
    _assert_schema(report)
    assert "declarations_disagree" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_card_and_manifest_source_repos_follow_aliases():
    bundle = spdx_known_bundle()
    current = dict(bundle["repositories"][0])
    current["aliases"] = [{"name_with_owner": "rmems/widget-old"}]
    bundle["repositories"] = [bind_source_hash(current)]
    bundle["card"]["source_repo"] = "rmems/widget"
    bundle["manifest"]["source_repo"] = "rmems/widget-old"
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is True
