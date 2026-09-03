from __future__ import annotations

import pytest

from eligibility_fixtures import _policy, _repo_root, _snapshot
from lib.eligibility_artifacts import build_eligibility_artifacts


def test_open_candidate_cannot_be_overridden_as_included_negative(tmp_path):
    policy = _policy()
    policy["overrides"] = [
        {
            "candidate_id": "github:repository:R1:pull:PR3",
            "state": "included_negative",
            "reason_codes": ["explicit_negative"],
            "evidence_refs": ["https://github.com/rmems/repo-a/pull/3"],
        }
    ]
    with pytest.raises(ValueError, match="open candidate as negative"):
        build_eligibility_artifacts(_snapshot(), policy, _repo_root(tmp_path))


def test_duplicate_override_candidate_ids_fail_closed(tmp_path):
    override = {
        "candidate_id": "github:repository:R1:pull:PR1",
        "state": "excluded",
        "reason_codes": ["explicit_policy_exclusion"],
        "evidence_refs": ["https://example.invalid/evidence"],
    }
    policy = _policy()
    policy["overrides"] = [override, {**override, "state": "quarantined"}]
    with pytest.raises(ValueError, match="duplicate override candidate_id"):
        build_eligibility_artifacts(_snapshot(), policy, _repo_root(tmp_path))
