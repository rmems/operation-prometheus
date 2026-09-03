from __future__ import annotations

from eligibility_fixtures import _policy, _repo_root, _snapshot
from lib.eligibility_artifacts import build_eligibility_artifacts
from lib.eligibility_classification import infer_task_family
from lib.source_inventory import sha256_json


def test_explicit_dependency_author_list_is_retained_but_markers_require_bot_type():
    policy = {"dependency_authors": ["explicit-human"]}
    human_marker = {
        "title": "feat: add user-facing behavior",
        "author": {"login": "human-dependabot-maintainer", "type": "User"},
    }
    explicit = {
        "title": "feat: add user-facing behavior",
        "author": {"login": "explicit-human", "type": "User"},
    }
    bot_marker = {
        "title": "feat: add user-facing behavior",
        "author": {"login": "renovate-helper", "type": "Bot"},
    }
    assert infer_task_family(human_marker, policy)[0] == "feature"
    assert infer_task_family(explicit, policy)[0] == "dependency"
    assert infer_task_family(bot_marker, policy)[0] == "dependency"


def test_terminal_draft_is_not_misclassified_as_open_watchlist(tmp_path):
    snapshot = _snapshot()
    snapshot["pull_requests"][0]["draft"] = True
    snapshot.pop("snapshot_sha256")
    snapshot["snapshot_sha256"] = sha256_json(snapshot)
    artifacts = build_eligibility_artifacts(snapshot, _policy(), _repo_root(tmp_path))
    candidate = next(row for row in artifacts["candidates"] if row["pull_request_number"] == 1)
    assert candidate["source_state"] == "merged"
    assert candidate["state"] == "quarantined"
