"""Unit tests for EXP-PROM-BUGFIX-SWE-001 prompt, seed filter, and evaluator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.bugfix_synth import (
    EXP_ID,
    GOLD_JACCARD_MAX,
    LOCKED_MODEL,
    VARIANT_KNOBS,
    HarnessError,
    build_teacher_messages,
    check_no_gold_leak,
    check_patch_nonempty,
    core_seed_ids,
    evaluate_synth,
    fixture_chat_response,
    fixture_trajectory,
    gold_patch,
    is_holdout,
    line_jaccard,
    load_jsonl_records,
    load_seed_manifest,
    meets_core_filters,
    messages_blob,
    parse_teacher_json,
    patch_fingerprint,
    prompt_seed_view,
    select_core_seeds,
    summarize_review_themes,
)

ROOT = Path(__file__).resolve().parents[1]
JSONL = ROOT / "datasets" / "jsonl"
MANIFEST = ROOT / "experiments" / EXP_ID / "seed-manifest.json"

GOLD = (
    "--- a/src/broken.rs\n+++ b/src/broken.rs\n@@ -1,3 +1,8 @@\n"
    " fn main() {\n-    panic!(\"bug\");\n+    if flag { return; }\n"
    "+    let fixed = 1;\n+    let also = 2;\n+    let more = 3;\n }\n"
)


def _seed(**overrides: object) -> dict:
    rec = {
        "id": "test-seed-1",
        "repo": "rmems/ci-demo",
        "pr_number": 17,
        "language": "Rust",
        "domain": "infra",
        "task_type": "bugfix",
        "training_use": "repair",
        "outcome": "merged",
        "quality_score": 0.95,
        "issue_context": "CI was flaky on macOS.",
        "before_context": "The workflow file had no explicit FOO_NATIVE.",
        "review_signals": [
            {"author": "r", "comment": "Set the var explicitly in the workflow."},
            {"author": "r", "suggestion": "+++ leaked.diff\n@@ gold"},
        ],
        "validation": [{"type": "ci", "result": "pass", "detail": "green"}],
        "patch": GOLD,
    }
    rec.update(overrides)
    return rec


def test_prompt_never_includes_gold_patch():
    seed = _seed()
    for variant in VARIANT_KNOBS:
        messages = build_teacher_messages(seed, variant)
        blob = messages_blob(messages)
        assert GOLD not in blob
        assert seed["patch"] not in json.dumps(messages)
        assert "gold_patch" not in blob
        assert "panic!(\"bug\")" not in blob
        view = prompt_seed_view(seed)
        assert "patch" not in view
        assert variant in blob
        assert seed["id"] in blob
        assert seed["repo"] in blob
        assert seed["issue_context"] in blob


def test_review_themes_skip_diff_shaped_lines():
    themes = summarize_review_themes(_seed()["review_signals"])
    assert themes == ["Set the var explicitly in the workflow."]


def test_core_filter_and_holdout():
    assert meets_core_filters(_seed())
    assert not meets_core_filters(_seed(quality_score=0.89))
    assert not meets_core_filters(_seed(task_type="feature"))
    assert not meets_core_filters(_seed(outcome="closed"))
    assert not meets_core_filters(_seed(quality_score=None))
    holdout = _seed(task_type="feature", training_use="repair")
    assert is_holdout(holdout)
    assert not is_holdout(_seed())


def test_select_core_seeds_order_and_rejection(tmp_path: Path):
    wanted = ["keep-a", "keep-b"]
    records = [
        _seed(id="noise", task_type="feature"),
        _seed(id="keep-b"),
        _seed(id="keep-a"),
        _seed(id="hold", task_type="docs", training_use="repair"),
    ]
    selected = select_core_seeds(records, wanted)
    assert [r["id"] for r in selected] == wanted
    with pytest.raises(HarnessError, match="not found"):
        select_core_seeds(records, ["missing-id"])
    with pytest.raises(HarnessError, match="failed"):
        select_core_seeds(records, ["hold"])


def test_evaluator_keep_fixture_and_reject_codes():
    seed = _seed()
    seen: set[str] = set()
    good = fixture_trajectory(seed, VARIANT_KNOBS[0])
    kept = evaluate_synth(good, seed, seen)
    assert kept.keep
    assert kept.reject_codes == []
    assert kept.soft_codes == []
    seen.add(patch_fingerprint(good["patch"]))

    leak = dict(good)
    leak["id"] = "leak"
    leak["patch"] = GOLD
    leaked = evaluate_synth(leak, seed, seen)
    assert leaked.decision == "reject"
    assert "no_gold_leak" in leaked.reject_codes

    short = dict(good)
    short["patch"] = "too-short"
    assert "patch_nonempty" in evaluate_synth(short, seed, seen).reject_codes

    typed = dict(good)
    typed["task_type"] = "feature"
    assert "task_type_bugfix" in evaluate_synth(typed, seed, seen).reject_codes

    dup = dict(good)
    dup["id"] = "dup"
    assert "non_template" in evaluate_synth(dup, seed, seen).reject_codes

    bare = {"patch": good["patch"]}
    eval_bare = evaluate_synth(bare, seed, set())
    assert "schema_ok" in eval_bare.reject_codes
    assert "provenance_complete" in eval_bare.reject_codes


def test_soft_codes_do_not_flip_keep():
    seed = _seed()
    candidate = fixture_trajectory(seed, "narrower")
    candidate["language"] = "Python"
    candidate["validation"] = []
    result = evaluate_synth(candidate, seed, set())
    assert result.keep
    assert result.soft_codes == ["lang_match", "validation_present"]


def test_no_gold_leak_jaccard_threshold():
    seed = _seed()
    assert check_no_gold_leak({"patch": GOLD}, seed) is False
    tweaked = GOLD + "+extra unique line that barely changes overlap\n"
    assert line_jaccard(tweaked, GOLD) >= GOLD_JACCARD_MAX
    assert check_no_gold_leak({"patch": tweaked}, seed) is False
    assert check_no_gold_leak({"patch": fixture_trajectory(seed, "narrower")["patch"]}, seed)


def test_patch_nonempty_bounds():
    assert check_patch_nonempty({"patch": "x" * 200})
    assert not check_patch_nonempty({"patch": "x" * 199})
    assert not check_patch_nonempty({"patch": "x" * 80_001})


def test_parse_teacher_json_fenced():
    inner = {"id": "x", "task_type": "bugfix"}
    parsed = parse_teacher_json("```json\n" + json.dumps(inner) + "\n```")
    assert parsed["id"] == "x"


def test_fixture_response_roundtrip():
    seed = _seed()
    response = fixture_chat_response(seed, "broader+tests")
    content = response["choices"][0]["message"]["content"]
    parsed = parse_teacher_json(content)
    assert parsed["exp_id"] == EXP_ID
    assert parsed["teacher_model"] == LOCKED_MODEL
    assert GOLD not in content


def test_committed_core_seeds_resolve_and_prompts_omit_gold():
    manifest = load_seed_manifest(MANIFEST)
    ids = core_seed_ids(manifest)
    assert ids == [
        "Limen-Neural-axon-encoder-41",
        "Limen-Neural-brainstem-daemon-25",
        "rmems-spike-viz-23",
        "rmems-thalamic-relay-23",
        "rmems-Theseus-Quarry-12",
        "rmems-corinth-canal-142",
        "rmems-myelin-accelerator-22",
        "rmems-worktrees-hives-79",
    ]
    records = load_jsonl_records(JSONL)
    seeds = select_core_seeds(records, ids)
    assert len(seeds) == 8
    holdout_ids = {r["id"] for r in records if is_holdout(r)}
    assert holdout_ids.isdisjoint(set(ids))
    for seed in seeds:
        gold = gold_patch(seed)
        assert gold
        for variant in VARIANT_KNOBS:
            blob = messages_blob(build_teacher_messages(seed, variant))
            assert gold not in blob
            assert "\"patch\":" not in json.dumps(prompt_seed_view(seed))
