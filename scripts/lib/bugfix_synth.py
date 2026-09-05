"""Seed loading, teacher prompts, and reject/keep evaluation for EXP-PROM-BUGFIX-SWE-001."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXP_ID = "EXP-PROM-BUGFIX-SWE-001"
LOCKED_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
BEFORE_CONTEXT_MAX = 4000
PATCH_LEN_MIN = 200
PATCH_LEN_MAX = 80_000
GOLD_JACCARD_MAX = 0.85
VARIANT_KNOBS = (
    "same-root-different-surface",
    "narrower",
    "broader+tests",
)
HARD_CODES = (
    "schema_ok",
    "task_type_bugfix",
    "patch_nonempty",
    "no_gold_leak",
    "non_template",
    "provenance_complete",
)
SOFT_CODES = ("lang_match", "validation_present")
_DIFF_LINE = re.compile(r"^(?:diff --git|index |--- |\+\+\+ |@@ )")
_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)


class HarnessError(ValueError):
    """User-facing CLI / harness configuration error."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def assert_exp_id(exp_id: str) -> str:
    if exp_id != EXP_ID:
        raise HarnessError(
            f"Unsupported exp id {exp_id!r}; this harness only runs {EXP_ID}"
        )
    return exp_id


def load_seed_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise HarnessError(f"Seed manifest must be an object: {path}")
    if data.get("exp_id") != EXP_ID:
        raise HarnessError(f"Seed manifest exp_id must be {EXP_ID}: {path}")
    return data


def core_seed_ids(manifest: dict[str, Any]) -> list[str]:
    seeds = manifest.get("core_seeds") or []
    ids: list[str] = []
    for row in seeds:
        if isinstance(row, dict) and row.get("id"):
            ids.append(str(row["id"]))
        elif isinstance(row, str):
            ids.append(row)
    if not ids:
        raise HarnessError("Seed manifest core_seeds is empty")
    return ids


def _parse_jsonl_line(path: Path, line_no: int, line: str) -> dict[str, Any] | None:
    if not line.strip():
        return None
    try:
        rec = json.loads(line)
    except json.JSONDecodeError as exc:
        raise HarnessError(f"Invalid JSON in {path}:{line_no}") from exc
    if isinstance(rec, dict) and rec.get("id"):
        return rec
    return None


def load_jsonl_records(jsonl_dir: Path) -> list[dict[str, Any]]:
    paths = sorted(jsonl_dir.glob("*.jsonl"))
    if not paths:
        raise HarnessError(f"No JSONL files under {jsonl_dir}")
    records: list[dict[str, Any]] = []
    for path in paths:
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            rec = _parse_jsonl_line(path, line_no, line)
            if rec is not None:
                records.append(rec)
    return records


def meets_core_filters(
    rec: dict[str, Any],
    *,
    min_quality: float = 0.90,
) -> bool:
    if rec.get("task_type") != "bugfix":
        return False
    if rec.get("outcome") != "merged":
        return False
    score = rec.get("quality_score")
    if not isinstance(score, (int, float)):
        return False
    return float(score) >= min_quality


def is_holdout(rec: dict[str, Any]) -> bool:
    """Secondary holdout: training_use=repair AND task_type ≠ bugfix."""
    return rec.get("training_use") == "repair" and rec.get("task_type") != "bugfix"


def _index_wanted(records: list[dict[str, Any]], seed_ids: list[str]) -> dict[str, dict[str, Any]]:
    wanted = set(seed_ids)
    by_id: dict[str, dict[str, Any]] = {}
    for rec in records:
        rid = rec.get("id")
        if rid in wanted and rid not in by_id:
            by_id[str(rid)] = rec
    return by_id


def _eligible_core(rec: dict[str, Any], min_quality: float) -> bool:
    return (not is_holdout(rec)) and meets_core_filters(rec, min_quality=min_quality)


def select_core_seeds(
    records: list[dict[str, Any]],
    seed_ids: list[str],
    *,
    min_quality: float = 0.90,
) -> list[dict[str, Any]]:
    by_id = _index_wanted(records, seed_ids)
    missing = [sid for sid in seed_ids if sid not in by_id]
    if missing:
        raise HarnessError(f"Core seed ids not found in JSONL: {missing}")
    selected = [by_id[sid] for sid in seed_ids if _eligible_core(by_id[sid], min_quality)]
    rejected = [sid for sid in seed_ids if not _eligible_core(by_id[sid], min_quality)]
    if rejected:
        raise HarnessError(
            "Core seeds failed task_type=bugfix / quality_score>=0.90 / "
            f"outcome=merged (or are holdout): {rejected}"
        )
    return selected


def truncate_before_context(text: str, max_chars: int = BEFORE_CONTEXT_MAX) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _theme_from_signal(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None
    raw = str(item.get("comment") or item.get("suggestion") or "").strip()
    if not raw:
        return None
    first = raw.splitlines()[0].strip()
    if _DIFF_LINE.match(first) or first.startswith(("+", "-")):
        return None
    return first[:160] or None


def summarize_review_themes(review_signals: Any, *, limit: int = 8) -> list[str]:
    if not isinstance(review_signals, list):
        return []
    themes: list[str] = []
    for item in review_signals:
        theme = _theme_from_signal(item)
        if theme and theme not in themes:
            themes.append(theme)
        if len(themes) >= limit:
            break
    return themes


def _validation_kind(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None
    kind = item.get("type")
    if isinstance(kind, str) and kind:
        return kind
    return None


def validation_kinds(validation: Any) -> list[str]:
    if not isinstance(validation, list):
        return []
    kinds: list[str] = []
    for item in validation:
        kind = _validation_kind(item)
        if kind and kind not in kinds:
            kinds.append(kind)
    return kinds


def prompt_seed_view(seed: dict[str, Any]) -> dict[str, Any]:
    """Subset of a seed that is safe to send to the teacher (no gold patch)."""
    return {
        "seed_id": seed.get("id"),
        "repo": seed.get("repo"),
        "language": seed.get("language"),
        "domain": seed.get("domain"),
        "issue_context": seed.get("issue_context") or "",
        "before_context": truncate_before_context(str(seed.get("before_context") or "")),
        "review_themes": summarize_review_themes(seed.get("review_signals")),
        "validation_kinds": validation_kinds(seed.get("validation")),
    }


def build_teacher_messages(seed: dict[str, Any], variant: str) -> list[dict[str, str]]:
    if variant not in VARIANT_KNOBS:
        raise HarnessError(f"Unknown variant knob: {variant}")
    view = prompt_seed_view(seed)
    system = (
        "You write alternate bugfix SWE trajectories for Operation Prometheus "
        f"experiment {EXP_ID}. Reply with a single JSON object matching "
        "synth_bugfix_trajectory_v0. Do not invent a different experiment id. "
        f"teacher_model must be {LOCKED_MODEL}. task_type must be bugfix. "
        "training_use must be repair. outcome must be merged. "
        "provenance.kind must be synthetic and must link seed_id. "
        "Never reproduce a hidden gold patch; write a distinct alternate fix."
    )
    knob_help = {
        "same-root-different-surface": (
            "Keep the same root cause but change the surface of the fix "
            "(different files, API, or comments)."
        ),
        "narrower": "Produce a narrower, more conservative fix than a typical full PR.",
        "broader+tests": "Produce a broader fix that also adds or strengthens tests.",
    }
    user_payload = {
        **view,
        "exp_id": EXP_ID,
        "variant": variant,
        "variant_instruction": knob_help[variant],
        "output_schema": "synth_bugfix_trajectory_v0",
    }
    user = (
        "Write one alternate bugfix trajectory as JSON.\n\n"
        + json.dumps(user_payload, indent=2, ensure_ascii=False)
        + "\n\nDo not include any gold patch. The seed patch is withheld on purpose."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def messages_blob(messages: list[dict[str, str]]) -> str:
    return "\n".join(m.get("content") or "" for m in messages)


def gold_patch(seed: dict[str, Any]) -> str:
    return str(seed.get("patch") or "")


def patch_lines(text: str) -> set[str]:
    return {line.strip() for line in text.splitlines() if line.strip()}


def line_jaccard(left: str, right: str) -> float:
    a, b = patch_lines(left), patch_lines(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def patch_fingerprint(text: str) -> str:
    norm = "\n".join(sorted(patch_lines(text)))
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def parse_teacher_json(content: str) -> dict[str, Any]:
    text = content.strip()
    match = _JSON_FENCE.search(text)
    if match:
        text = match.group(1)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        obj = _loads_object_slice(text)
    if not isinstance(obj, dict):
        raise HarnessError("Teacher JSON root must be an object")
    return obj


def _loads_object_slice(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise HarnessError("Teacher content is not JSON")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise HarnessError("Teacher content is not valid JSON") from exc


def extract_message_content(response: dict[str, Any]) -> str:
    choices = response.get("choices") if isinstance(response, dict) else None
    first = choices[0] if isinstance(choices, list) and choices else None
    message = first.get("message") if isinstance(first, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str) and content.strip():
        return content
    raise HarnessError("Teacher response missing message content")


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def check_schema_ok(candidate: dict[str, Any]) -> bool:
    required = (
        "id",
        "seed_id",
        "exp_id",
        "teacher_model",
        "generated_at",
        "language",
        "domain",
        "task_type",
        "training_use",
        "issue_context",
        "before_context",
        "patch",
        "validation",
        "outcome",
        "provenance",
    )
    if any(not _nonempty_str(candidate.get(key)) for key in required if key not in {"validation", "provenance"}):
        return False
    if candidate.get("exp_id") != EXP_ID:
        return False
    if candidate.get("teacher_model") != LOCKED_MODEL:
        return False
    if candidate.get("training_use") != "repair":
        return False
    if candidate.get("outcome") != "merged":
        return False
    validation = candidate.get("validation")
    if not isinstance(validation, list):
        return False
    provenance = candidate.get("provenance")
    return isinstance(provenance, dict)


def check_task_type_bugfix(candidate: dict[str, Any]) -> bool:
    return candidate.get("task_type") == "bugfix"


def check_patch_nonempty(candidate: dict[str, Any]) -> bool:
    patch = candidate.get("patch")
    if not isinstance(patch, str):
        return False
    return PATCH_LEN_MIN <= len(patch) <= PATCH_LEN_MAX


def check_no_gold_leak(candidate: dict[str, Any], seed: dict[str, Any]) -> bool:
    patch = candidate.get("patch")
    gold = gold_patch(seed)
    if not isinstance(patch, str) or not gold:
        return isinstance(patch, str) and bool(patch)
    if patch == gold:
        return False
    return line_jaccard(patch, gold) < GOLD_JACCARD_MAX


def check_non_template(candidate: dict[str, Any], seen: set[str]) -> bool:
    patch = candidate.get("patch")
    if not isinstance(patch, str) or not patch.strip():
        return False
    return patch_fingerprint(patch) not in seen


def check_provenance_complete(candidate: dict[str, Any], seed: dict[str, Any]) -> bool:
    prov = candidate.get("provenance")
    if not isinstance(prov, dict):
        return False
    if prov.get("kind") != "synthetic":
        return False
    seed_id = seed.get("id")
    if prov.get("seed_id") != seed_id or candidate.get("seed_id") != seed_id:
        return False
    if candidate.get("exp_id") != EXP_ID:
        return False
    return True


def check_lang_match(candidate: dict[str, Any], seed: dict[str, Any]) -> bool:
    left = str(candidate.get("language") or "").casefold()
    right = str(seed.get("language") or "").casefold()
    return bool(left) and left == right


def check_validation_present(candidate: dict[str, Any]) -> bool:
    validation = candidate.get("validation")
    return isinstance(validation, list) and len(validation) > 0


@dataclass
class Evaluation:
    decision: str
    reject_codes: list[str] = field(default_factory=list)
    soft_codes: list[str] = field(default_factory=list)

    @property
    def keep(self) -> bool:
        return self.decision == "keep"


def _failed_codes(
    checks: list[tuple[str, bool]],
) -> list[str]:
    return [code for code, ok in checks if not ok]


def evaluate_synth(
    candidate: dict[str, Any],
    seed: dict[str, Any],
    seen_fingerprints: set[str] | None = None,
) -> Evaluation:
    seen = seen_fingerprints if seen_fingerprints is not None else set()
    failed = _failed_codes(
        [
            ("schema_ok", check_schema_ok(candidate)),
            ("task_type_bugfix", check_task_type_bugfix(candidate)),
            ("patch_nonempty", check_patch_nonempty(candidate)),
            ("no_gold_leak", check_no_gold_leak(candidate, seed)),
            ("non_template", check_non_template(candidate, seen)),
            ("provenance_complete", check_provenance_complete(candidate, seed)),
        ]
    )
    soft = _failed_codes(
        [
            ("lang_match", check_lang_match(candidate, seed)),
            ("validation_present", check_validation_present(candidate)),
        ]
    )
    decision = "keep" if not failed else "reject"
    return Evaluation(decision=decision, reject_codes=failed, soft_codes=soft)


def fixture_patch(seed_id: str, variant: str) -> str:
    lines = [
        f"--- a/experiments/dry-run/{seed_id}/{variant}.txt",
        f"+++ b/experiments/dry-run/{seed_id}/{variant}.txt",
        "@@ -0,0 +1,24 @@",
    ]
    for i in range(1, 25):
        lines.append(
            f"+dry-run fixture line {i} seed={seed_id} variant={variant} token={i * 31}"
        )
    return "\n".join(lines) + "\n"


def fixture_trajectory(seed: dict[str, Any], variant: str, *, generated_at: str | None = None) -> dict[str, Any]:
    seed_id = str(seed.get("id") or "unknown")
    view = prompt_seed_view(seed)
    return {
        "id": f"synth:{EXP_ID}:{seed_id}:{variant}",
        "seed_id": seed_id,
        "exp_id": EXP_ID,
        "teacher_model": LOCKED_MODEL,
        "generated_at": generated_at or utc_now(),
        "language": view["language"] or "unknown",
        "domain": view["domain"] or "unknown",
        "task_type": "bugfix",
        "training_use": "repair",
        "issue_context": view["issue_context"] or f"dry-run fixture for {seed_id}",
        "before_context": view["before_context"] or f"dry-run before_context for {seed_id}",
        "patch": fixture_patch(seed_id, variant),
        "validation": [
            {
                "type": "test",
                "result": "pass",
                "detail": "dry-run fixture; no live teacher call",
            }
        ],
        "outcome": "merged",
        "provenance": {
            "kind": "synthetic",
            "seed_id": seed_id,
            "seed_repo": seed.get("repo"),
            "seed_pr_number": seed.get("pr_number"),
        },
    }


def fixture_chat_response(seed: dict[str, Any], variant: str) -> dict[str, Any]:
    record = fixture_trajectory(seed, variant)
    return {
        "id": f"dry-run:{record['id']}",
        "model": LOCKED_MODEL,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": json.dumps(record, ensure_ascii=False),
                },
                "finish_reason": "stop",
            }
        ],
    }


def ledger_row(meta: dict[str, Any], evaluation: Evaluation) -> dict[str, Any]:
    return {
        **meta,
        "decision": evaluation.decision,
        "reject_codes": list(evaluation.reject_codes),
        "soft_codes": list(evaluation.soft_codes),
        "teacher_model": LOCKED_MODEL,
        "exp_id": EXP_ID,
    }


def attempt_id(seed_id: str, variant: str) -> str:
    return f"{EXP_ID}:{seed_id}:{variant}"
