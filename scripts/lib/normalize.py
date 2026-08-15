"""Normalize raw PR records into schema v0 trajectory objects."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .bots import extract_section, is_bot_user, strip_bot_boilerplate
from .quality import score_quality
from .secrets import sanitize_text

DEFAULT_MAX_TRAJECTORY_PATCH = 96 * 1024

# Product wrappers from allowlisted engineering bots that are not actionable.
_CODEX_REVIEW_WRAPPER = re.compile(
    r"(?is)^\s*###\s*(?:💡\s*)?Codex Review\b"
    r"|About Codex in GitHub"
    r"|Your team has set up Codex to review"
)

# Check-run names that are review bots, not build/test/security validation.
# Security scanners (CodeQL, Snyk, …) stay in CI — they are validation signals.
_REVIEW_APP_CHECK_MARKERS: tuple[str, ...] = (
    "code review",
    "coderabbit",
    "kilo code",
    "kilo",
    "gitar",
    "codacy",
    "codeant",
    "macroscope",
    "devin",
    "semgrep",
    "sonar",
    "cursor bugbot",
    "bugbot",
    "greptile",
    "qodo",
    "chatgpt-codex",
    "codex",
    # Exact reviewer check name: a bare "copilot" would also swallow real CI
    # such as "Copilot integration tests".
    "copilot-pull-request-reviewer",
)


def _is_review_app_check(name: str | None) -> bool:
    low = (name or "").lower()
    if not low:
        return False
    return any(m in low for m in _REVIEW_APP_CHECK_MARKERS)

FEATURE_BUCKET_TO_TRAINING = {
    "repair": "repair",
    "validation": "validation",
    "feature": "other",
    "review-to-patch": "review-to-patch",
    "autocomplete": "autocomplete",
    "bug-prediction": "bug-prediction",
    "other": "other",
}

# GitHub repo slugs are case-insensitive and the collector stores whatever casing
# the CLI was given, so every override table below is keyed on a lower-cased
# "owner/name" and must be looked up through ``_override_key``.
def _override_key(repo: str, pr: int) -> tuple[str, int]:
    """Build a case-folded (repo, pr) key for the per-PR override tables."""
    return (str(repo).strip().lower(), pr)


# Per-PR overrides live on the dataset card first, so a new extract ships its
# labelling decisions in its own card JSON instead of appending to the shared
# tables below — that is what lets extracts land in parallel without touching a
# common file. The module-level dicts remain as the fallback for the extracts
# that predate card-based overrides. A (repo, pr) pair must never appear in both
# sources; ``test_no_card_and_dict_override_overlap`` enforces that.
CARD_OVERRIDE_KEYS: dict[str, str] = {
    "domain": "domain_by_pr",
    "task_type": "task_type_by_pr",
    "linked_issues": "linked_issues_by_pr",
}


def card_pr_map(card: dict[str, Any], key: str) -> dict[int, Any]:
    """Read a per-PR override map off the card (JSON keys may be str or int)."""
    raw_map = card.get(key)
    if not isinstance(raw_map, dict):
        return {}
    out: dict[int, Any] = {}
    for k, v in raw_map.items():
        try:
            out[int(k)] = v
        except (TypeError, ValueError):
            continue
    return out


def card_override(card: dict[str, Any], key: str, pr: int) -> Any:
    """Look up one per-PR card override; ``None`` means "not set on the card"."""
    return card_pr_map(card, key).get(pr)


# Per-PR overrides for corinth-canal shortlist training_use (schema enums).
TRAINING_USE_OVERRIDE: dict[tuple[str, int], str] = {
    ("rmems/corinth-canal", 82): "repair",
    ("rmems/corinth-canal", 89): "validation",
    ("rmems/corinth-canal", 91): "other",
    ("rmems/corinth-canal", 94): "repair",
    ("rmems/corinth-canal", 95): "other",
    ("rmems/corinth-canal", 96): "validation",
}

# Fallback only — new extracts set ``task_type_by_pr`` on their card instead.
TASK_TYPE_OVERRIDE: dict[tuple[str, int], str] = {
    ("rmems/corinth-canal", 82): "feature",
    ("rmems/corinth-canal", 89): "test",
    ("rmems/corinth-canal", 91): "feature",
    ("rmems/corinth-canal", 94): "feature",
    ("rmems/corinth-canal", 95): "feature",
    ("rmems/corinth-canal", 96): "feature",
    # Non-conventional title ("Verify grok-ozempic aligns with xai-dissect
    # inventory") falls through to "other"; the PR adds grok1_inventory.rs and
    # alignment.rs, so feature is the accurate label.
    ("rmems/grok-ozempic", 26): "feature",
    # WIP title + mostly-doc path mix falls to "docs"; PR lands CUDA/cust code.
    ("rmems/myelin-accelerator", 7): "feature",
    ("rmems/myelin-accelerator", 6): "feature",
}

# Per-PR issue provenance for bodies that name their originating issue without a
# GitHub close keyword ("Implements GitHub #22", "addressing issues #28 and #20").
# ``parse_linked_issue_numbers`` only recognises close keywords by design, so
# these trajectories would otherwise ship with the PR URL as their only source.
# Numbers are the ones documented in docs/source-repos.md and each dataset card's
# ``related_issues``; entries here are references, not close-links, so the stubs
# they produce carry ``closed_by_pr: False``.
# Fallback only — new extracts set ``linked_issues_by_pr`` on their card instead.
LINKED_ISSUE_OVERRIDE: dict[tuple[str, int], tuple[int, ...]] = {
    ("rmems/grok-ozempic", 26): (22,),
    ("rmems/grok-ozempic", 29): (16, 22, 27),
    ("rmems/grok-ozempic", 33): (28, 20),
    ("rmems/grok-ozempic", 43): (38,),
    # Body links GH #37 / RM-189 via full URL + "Supports #37", not a close keyword.
    ("rmems/grok-ozempic", 42): (37,),
    # Title lists Implement #16,#13,#12,#10,#11 without close keywords.
    ("rmems/myelin-accelerator", 18): (16, 13, 12, 10, 11),
    # Body references GH #9 / LIM-890 for packed ternary kernels.
    ("rmems/myelin-accelerator", 26): (9,),
}

# Fallback only — new extracts set ``domain_by_pr`` on their card instead.
DOMAIN_OVERRIDE: dict[tuple[str, int], str] = {
    ("rmems/corinth-canal", 82): "gpu-compute",
    ("rmems/corinth-canal", 89): "gpu-compute",
    ("rmems/corinth-canal", 91): "ml-infra",
    ("rmems/corinth-canal", 94): "ml-infra",
    ("rmems/corinth-canal", 95): "ml-infra",
    ("rmems/corinth-canal", 96): "tools",
}

TITLE_TASK_HINTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)^fix\b"), "bugfix"),
    (re.compile(r"(?i)^feat\b"), "feature"),
    (re.compile(r"(?i)^refactor\b"), "refactor"),
    (re.compile(r"(?i)^docs?\b"), "docs"),
    (re.compile(r"(?i)^test\b"), "test"),
    (re.compile(r"(?i)^perf\b"), "perf"),
    # Conventional commit: security | sec(scope):
    (re.compile(r"(?i)^sec(?:urity)?\b"), "security"),
    (re.compile(r"(?i)^chore\b"), "chore"),
]


def load_card(path: Path | None) -> dict[str, Any]:
    """Load a dataset card JSON.

    ``path is None`` means no card (optional). A supplied path that does not
    exist raises ``FileNotFoundError`` so typos fail fast.
    """
    if path is None:
        return {}
    if not path.exists():
        raise FileNotFoundError(f"dataset card not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_raw_record(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _bucket_map(card: dict[str, Any]) -> dict[int, str]:
    buckets = card.get("training_use_buckets") or {}
    out: dict[int, str] = {}
    for bucket, prs in buckets.items():
        for n in prs or []:
            out[int(n)] = str(bucket)
    return out


def training_use_for(repo: str, pr: int, card: dict[str, Any]) -> str:
    key = _override_key(repo, pr)
    if key in TRAINING_USE_OVERRIDE:
        return TRAINING_USE_OVERRIDE[key]
    bucket = _bucket_map(card).get(pr)
    if bucket:
        return FEATURE_BUCKET_TO_TRAINING.get(bucket, "other")
    return "other"


def domain_for(repo: str, pr: int, card: dict[str, Any], raw: dict[str, Any]) -> str:
    # Card first, then the legacy shared table (see CARD_OVERRIDE_KEYS).
    carded = card_override(card, CARD_OVERRIDE_KEYS["domain"], pr)
    if isinstance(carded, str) and carded.strip():
        return carded.strip()
    key = _override_key(repo, pr)
    if key in DOMAIN_OVERRIDE:
        return DOMAIN_OVERRIDE[key]
    domains = card.get("domains") or []
    if domains:
        return str(domains[0])
    labels = (raw.get("pull") or {}).get("labels") or []
    if "CUDA" in labels or "cuda" in labels:
        return "gpu-compute"
    return "systems"


def task_type_for(
    repo: str, pr: int, raw: dict[str, Any], card: dict[str, Any] | None = None
) -> str:
    # Card first, then the legacy shared table (see CARD_OVERRIDE_KEYS).
    carded = card_override(card or {}, CARD_OVERRIDE_KEYS["task_type"], pr)
    if isinstance(carded, str) and carded.strip():
        return carded.strip()
    key = _override_key(repo, pr)
    if key in TASK_TYPE_OVERRIDE:
        return TASK_TYPE_OVERRIDE[key]
    title = (raw.get("pull") or {}).get("title") or ""
    for pattern, task in TITLE_TASK_HINTS:
        if pattern.search(title):
            return task
    labels = [str(x).lower() for x in ((raw.get("pull") or {}).get("labels") or [])]
    if "bug" in labels:
        return "bugfix"
    if "enhancement" in labels:
        return "feature"
    if "documentation" in labels:
        return "docs"
    return "other"


def build_source_urls(repo: str, pr: int, linked_issues: list[dict[str, Any]]) -> list[str]:
    urls = [f"https://github.com/{repo}/pull/{pr}"]
    for issue in linked_issues:
        url = issue.get("html_url")
        if isinstance(url, str) and url.startswith("https://github.com/") and url not in urls:
            # Only keep if matches schema pattern
            if re.match(
                r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/(pull|issues)/[0-9]+",
                url,
            ):
                urls.append(url)
    return urls


def enrich_linked_issues(
    raw: dict[str, Any], card: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Merge API-fetched linked issues with close-keyword refs from PR/commits.

    Older raw records may have empty ``linked_issues`` when bodies used multi-issue
    lists (``Closes: #75, #76``) or gerunds (``closing #80``). Reconstruct stubs so
    ``source_urls`` keeps issue→patch provenance without re-collecting.
    """
    from .raw_record import parse_linked_issue_numbers, parse_repo

    source = raw.get("source") or {}
    repo = str(source.get("repo") or "")
    try:
        owner, name = parse_repo(repo)
    except Exception:
        return list(raw.get("linked_issues") or [])

    self_repo = f"{owner}/{name}".lower()
    try:
        self_pr = int(source.get("pr_number") or (raw.get("pull") or {}).get("number"))
    except (TypeError, ValueError):
        self_pr = None

    def _key(repo_i: str, num: Any) -> tuple[str, int] | None:
        try:
            return (str(repo_i).lower(), int(num))
        except (TypeError, ValueError):
            return None

    # Issues and PRs share one number space, so /issues/<pr> resolves back to the
    # PR itself — a self-reference is provenance noise, never an issue. Applied to
    # pre-collected entries too, not just synthesized ones: a raw record may carry
    # one from an older collector run that predates the API-side guard.
    linked: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for issue in raw.get("linked_issues") or []:
        key = _key(issue.get("repo") or "", issue.get("number"))
        if key is not None:
            if key == (self_repo, self_pr):
                continue
            seen.add(key)
        linked.append(issue)

    def _stub(i_owner: str, i_repo: str, num: int, *, closed_by_pr: bool) -> None:
        key = (f"{i_owner}/{i_repo}".lower(), num)
        if key in seen or key == (self_repo, self_pr):
            return
        seen.add(key)
        linked.append(
            {
                "number": num,
                "repo": f"{i_owner}/{i_repo}",
                "title": "",
                "body": "",
                "state": "unknown",
                "html_url": f"https://github.com/{i_owner}/{i_repo}/issues/{num}",
                "closed_by_pr": closed_by_pr,
                "synthetic": True,
            }
        )

    parts = [(raw.get("pull") or {}).get("body") or ""]
    for c in raw.get("commits") or []:
        msg = c.get("message") if isinstance(c, dict) else None
        if msg:
            parts.append(str(msg))
    for i_owner, i_repo, num in parse_linked_issue_numbers(
        "\n".join(parts), owner, name
    ):
        _stub(i_owner, i_repo, num, closed_by_pr=True)

    if self_pr is not None:
        # Card first, then the legacy shared table (see CARD_OVERRIDE_KEYS).
        carded = card_override(
            card or {}, CARD_OVERRIDE_KEYS["linked_issues"], self_pr
        )
        if isinstance(carded, (list, tuple)):
            refs: tuple[int, ...] = tuple(
                int(n) for n in carded if str(n).strip().lstrip("-").isdigit()
            )
        else:
            refs = LINKED_ISSUE_OVERRIDE.get(_override_key(self_repo, self_pr), ())
        for num in refs:
            _stub(owner, name, num, closed_by_pr=False)
    return linked


def extract_issue_context(raw: dict[str, Any]) -> str | None:
    parts: list[str] = []
    for issue in raw.get("linked_issues") or []:
        title = (issue.get("title") or "").strip()
        body = strip_bot_boilerplate(issue.get("body") or "")
        if title:
            parts.append(f"Issue #{issue.get('number')}: {title}")
        if body:
            parts.append(body[:1500])
    pull = raw.get("pull") or {}
    body = strip_bot_boilerplate(pull.get("body") or "")
    # Prefer problem/motivation sections over local verification tables.
    # "what changed" before bare "summary" so parenthetical headings never win.
    for keywords in (
        ("what changed", "user description", "motivation", "problem", "overview"),
        ("summary",),
    ):
        summary = extract_section(body, keywords)
        if summary:
            parts.append(summary[:2500])
            break
    else:
        if body:
            parts.append(body[:2000])
    title = (pull.get("title") or "").strip()
    if title and not parts:
        parts.append(title)
    if not parts:
        return None
    text = "\n\n".join(parts).strip()
    text, _ = sanitize_text(text)
    return text or None


# Maintainer ack-only replies consume review-signal budget without review content.
# Optional "commit" token matches "Fixed in commit <sha>." (Bugbot / GH #18 follow-up).
_BARE_FIXED_IN_REPLY = re.compile(
    r"(?is)^\s*(?:\*\*)?(?:addressed|fixed)\s+in\s+(?:commit\s+)?`?[0-9a-f]{7,40}`?"
    r"(?:\*\*)?\s*\.?\s*$"
)
# Ack-shaped replies that may still carry fix rationale after the SHA.
_ACK_SHAPED_PREFIX = re.compile(
    r"(?is)^\s*(?:\*\*)?(?:addressed|fixed)\s+in\s+(?:commit\s+)?`?[0-9a-f]{7,40}`?"
)
# Leading ack prefix stripped for dedupe keys (issue #18).
_ACK_PREFIX_FOR_KEY = re.compile(
    r"(?is)^(?:\*\*)?(?:addressed|fixed)\s+in\s+(?:commit\s+)?`?[0-9a-f]{7,40}`?"
    r"(?:\*\*)?\s*:?\s*"
)


def _is_non_actionable_review_body(body: str) -> bool:
    """True for product wrappers or bare fixed-in acks without review signal."""
    if not body or not body.strip():
        return True
    if _CODEX_REVIEW_WRAPPER.search(body):
        return True
    # "Fixed in 0b05325." / "**Addressed in `abc1234`**" — outcome, not review.
    if _BARE_FIXED_IN_REPLY.match(body.strip()):
        return True
    return False


def _is_ack_shaped_review_body(body: str) -> bool:
    """True when the body starts as an Addressed/Fixed-in-SHA ack (may have rationale)."""
    return bool(body and _ACK_SHAPED_PREFIX.match(body.strip()))


def _signal_body_key(body: str) -> str:
    """Normalize body for dedupe: collapse whitespace, strip ack prefix.

    Only ``suggestion`` fences are removed so a prose review and its inline
    twin share a key. Other fenced blocks stay part of the signal identity
    (Bugbot: do not collapse distinct fence-only reviews).
    """
    text = body or ""
    text = re.sub(
        r"```suggestion\s*\n.*?```",
        " ",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    text = re.sub(r"\s+", " ", text.strip())
    text = _ACK_PREFIX_FOR_KEY.sub("", text, count=1)
    key = text.strip().lower()
    # Empty / punctuation-only after strip is not a usable signal key.
    if not re.search(r"[a-z0-9]", key):
        return ""
    return key


def _select_deduped_signals(
    candidates: list[dict[str, Any]],
    *,
    max_items: int,
) -> list[dict[str, str]]:
    """Dedupe by body key; prefer problem statements over acks; keep one ack if useful.

    Implements GH #18: identical multi-thread acks must not fill all slots.
    """
    if max_items < 1 or not candidates:
        return []

    # Preserve first-seen order; if same key appears as both ack and problem, keep problem.
    # Merge non-empty suggestion onto the retained candidate when duplicates arrive.
    by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for c in candidates:
        key = c["key"]
        if key not in by_key:
            by_key[key] = dict(c)
            order.append(key)
            continue
        prev = by_key[key]
        if prev.get("ack") and not c.get("ack"):
            merged = dict(c)
            if not merged.get("suggestion") and prev.get("suggestion"):
                merged["suggestion"] = prev["suggestion"]
            by_key[key] = merged
        elif not prev.get("suggestion") and c.get("suggestion"):
            prev["suggestion"] = c["suggestion"]

    problems = [by_key[k] for k in order if not by_key[k].get("ack")]
    acks = [by_key[k] for k in order if by_key[k].get("ack")]

    selected: list[dict[str, Any]] = []
    # Reserve an ack slot only when max_items > 1 so a lone slot stays problem-first.
    reserve = 1 if acks and problems and max_items > 1 else 0
    for p in problems:
        if len(selected) >= max_items - reserve:
            break
        selected.append(p)
    if acks:
        if len(selected) < max_items:
            selected.append(acks[0])
        for a in acks[1:]:
            if len(selected) >= max_items:
                break
            selected.append(a)

    out: list[dict[str, str]] = []
    for s in selected[:max_items]:
        item: dict[str, str] = {
            "author": str(s.get("author") or "unknown"),
            "comment": str(s.get("comment") or "")[:2000],
        }
        suggestion = s.get("suggestion")
        if isinstance(suggestion, str) and suggestion.strip():
            item["suggestion"] = suggestion.strip()[:2000]
        out.append(item)
    return out


def extract_review_signals(raw: dict[str, Any], *, max_items: int = 8) -> list[dict[str, str]]:
    """Collect review-shaped comments, dedupe, and rank problems above acks (GH #18)."""
    candidates: list[dict[str, Any]] = []

    def _push(
        author: str | None,
        body: str,
        *,
        suggestion: str | None = None,
    ) -> None:
        body = (body or "").strip()
        if not body or _is_non_actionable_review_body(body):
            return
        key = _signal_body_key(body)
        if not key and suggestion:
            # Suggestion-only bodies remain valid schema signals.
            key = "suggestion:" + (_signal_body_key(suggestion) or suggestion.strip().lower()[:120])
        if not key:
            return
        entry: dict[str, Any] = {
            "author": author or "unknown",
            "comment": body[:2000],
            "key": key,
            "ack": _is_ack_shaped_review_body(body),
        }
        if suggestion:
            entry["suggestion"] = suggestion
        candidates.append(entry)

    # Process reviews first to preserve maintainer approve/request-changes signals
    # (including short LGTM / Approved bodies that still carry decision state).
    for r in raw.get("reviews") or []:
        if is_bot_user(r.get("user_login"), r.get("user_type")):
            continue
        body = (r.get("body") or "").strip()
        state = str(r.get("state") or "").upper()
        if not body or len(body) < 20:
            if state in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
                if body:
                    body = f"{body} (review state: {state})"
                else:
                    body = f"Review state: {state}"
            else:
                continue
        body, _ = sanitize_text(strip_bot_boilerplate(body))
        _push(r.get("user_login"), body)

    for c in raw.get("review_comments") or []:
        if is_bot_user(c.get("user_login"), c.get("user_type")):
            continue
        body = strip_bot_boilerplate((c.get("body") or "").strip())
        if not body or _is_non_actionable_review_body(body):
            continue
        body, _ = sanitize_text(body)
        if not body or _is_non_actionable_review_body(body):
            continue
        suggestion: str | None = None
        if "```suggestion" in body:
            m = re.search(r"```suggestion\s*\n(.*?)```", body, re.DOTALL)
            if m:
                sug = m.group(1).strip()[:2000]
                if sug:
                    suggestion = sug
        _push(c.get("user_login"), body, suggestion=suggestion)

    for c in raw.get("issue_comments") or []:
        if is_bot_user(c.get("user_login"), c.get("user_type")):
            continue
        body = strip_bot_boilerplate((c.get("body") or "").strip())
        if not body or len(body) < 20 or _is_non_actionable_review_body(body):
            continue
        body, _ = sanitize_text(body)
        if not body or _is_non_actionable_review_body(body):
            continue
        _push(c.get("user_login"), body)

    return _select_deduped_signals(candidates, max_items=max_items)


# Negative-test prose. A fixture that is *supposed* to fail, and did, is evidence
# the suite behaved correctly — it must not invert the validation result.
#
# Every alternative must carry an explicit intentionality marker. A reporting verb
# alone is not one: "CI checks failed on Linux" and "Verified that cargo test
# failed" are ordinary failure reports, and matching them here would systematically
# invert them to `pass`.
_EXPECTED_FAILURE_CUE = re.compile(
    r"(?:"
    # Deliberately NOT widened to allow modifiers between the marker and the
    # fail word: "expected to be failing on Linux until the runner is repaired"
    # describes a known-broken run, and suppressing it fabricates a pass.
    r"\b(?:expected|intended|intentional|deliberate)(?:ly)?\s+(?:to\s+)?"
    r"fail(?:ure|ed|ing|s)?\b"
    r"|\bfail(?:s|ed|ing)?\s+as\s+(?:expected|intended|designed)\b"
    # A deliberately bad *fixture* asserted to produce a failure — the assertion
    # succeeding, not a failed run. The adjective alone is not enough: the fixture
    # must be the subject of a confirming verb whose object is the failure, so
    # "Invalid fixture was repaired, but cargo test failed" stays a failure. The
    # \w+ gaps cannot cross a comma, which keeps the match inside one clause.
    r"|\b(?:invalid|malformed|corrupt(?:ed)?|bad|broken|mismatched)\s+"
    r"(?:\w+\s+){0,2}fixtures?\s+(?:\w+\s+){0,2}"
    r"(?:confirms?|confirmed|verif(?:y|ies|ied)|demonstrates?|exercises?"
    r"|triggers?|shows?|proves?)\s+(?:\w+\s+){0,3}\bfail(?:ure|ed|ing|s)?\b"
    # A negative test asserted to produce a failure. Needs an explicit
    # observing/confirming verb, same shape as the fixture alternative, so
    # "Negative test suite reported 3 failures" is not a cue. The bare
    # "negative test" alternative stays for prose with no fail word.
    r"|\bnegative\s+tests?\b(?:\s+\w+){0,2}\s+"
    r"(?:confirms?|confirmed|observed|observes?|demonstrates?|shows?"
    r"|triggers?|verif(?:y|ies|ied))(?:\s+\w+){0,3}\s+\w*"
    r"fail(?:ure|ed|ing|s)?\b"
    r"|\bnegative\s+tests?\b"
    r")"
)

_FAIL_WORD = re.compile(r"\b(?:failed|failing|failures?)\b")

# An expected failure that did not occur — the negative test accepted input it was
# supposed to reject. Intent alone does not prove the failure happened.
_EXPECTED_FAILURE_CONTRADICTED = re.compile(
    r"(?:"
    r"\bbut\s+(?:it\s+)?(?:passed|succeeded|was\s+accepted)\b"
    r"|\b(?:passed|succeeded)\s+unexpectedly\b"
    r"|\bunexpectedly\s+(?:passed|succeeded)\b"
    # Absence of the expected failure, however worded: "did not occur",
    # "was not observed", "never triggered" all mean the negative test passed
    # input it should have rejected.
    r"|\b(?:did\s+not|does\s+not|was\s+not|were\s+not|never)\s+(?:\w+\s+){0,2}"
    r"(?:fail|fails|failed|occur|occurred|observed|seen|triggered|raised"
    r"|reported|happen|happened)\b"
    r")"
)


# Statement boundaries: sentence end, blank line, or the start of a list item.
# A bare newline is NOT a boundary — Markdown soft-wraps prose, and splitting on
# it would separate "The expected failure\nwas not observed" into two halves and
# lose the contradiction.
_SENTENCE_SPLIT = re.compile(
    r"(?<=[.!?])\s+"
    r"|\n\s*\n"
    r"|\n(?=\s*(?:[-*+]|\d+[.)])\s)"
)


def _expected_failure_was_contradicted(low: str) -> bool:
    """True when one sentence both sets up an expected failure and reports it absent.

    Scoped per sentence, not per section: "Invalid fixture fails as expected. The
    warning did not occur" is a passing validation whose second clause is unrelated,
    so a section-wide check would wrongly force it to ``fail``.
    """
    return any(
        _EXPECTED_FAILURE_CUE.search(part) and _EXPECTED_FAILURE_CONTRADICTED.search(part)
        for part in _SENTENCE_SPLIT.split(low)
    )


def _fail_words_all_expected(low: str) -> bool:
    """True when every fail/failure mention sits inside expected-failure prose.

    Checked per occurrence rather than section-wide so a test plan that reports a
    real failure alongside a deliberate one still classifies as ``fail``.
    """
    spans = [m.span() for m in _EXPECTED_FAILURE_CUE.finditer(low)]
    mentions = list(_FAIL_WORD.finditer(low))
    if not spans or not mentions:
        return False
    return all(
        any(start <= m.start() and m.end() <= end for start, end in spans)
        for m in mentions
    )


# Unchecked markdown task items; text capture may be empty (bare `- [ ]`).
_UNCHECKED_CHECKBOX_LINE = re.compile(
    r"^(?P<full>\s*[-*]\s*\[\s\]\s*(?P<text>.*?))\s*$"
)
# Negated / required phrasing that must never be treated as optional.
_NEGATED_OPTIONAL_CUE = re.compile(
    r"(?:"
    r"\bnot\s+optional\b"
    r"|\bisn'?t\s+optional\b"
    r"|\bnon[- ]optional\b"
    r"|\bno\s+longer\s+optional\b"
    r"|\bnot\s+out\s+of\s+scope\b"
    r"|\bisn'?t\s+out\s+of\s+scope\b"
    r"|\bnot\s+(?:a\s+)?nice[- ]to[- ]have\b"
    r"|\bnot\s+if\s+time\s+permits\b"
    r")",
    re.IGNORECASE,
)
# Explicit "required" (except inside "not required…") forces blocking.
_REQUIRED_WORK_CUE = re.compile(r"\brequired\b", re.IGNORECASE)
_NOT_REQUIRED_CUE = re.compile(r"\bnot\s+required\b", re.IGNORECASE)


def _line_indent(line: str) -> int:
    """Leading whitespace width (tabs count as 2 spaces)."""
    n = 0
    for ch in line:
        if ch == " ":
            n += 1
        elif ch == "\t":
            n += 2
        else:
            break
    return n


# Optionality must lead the task text — mid-sentence "optional coverage" is not
# a whole-item deferral (Codex P2 on #35).
_LEADING_OPTIONAL_CUE = re.compile(
    r"^(?:"
    r"optional\b"
    r"|out\s+of\s+scope\b"
    r"|if\s+time\s+permits\b"
    r"|nice[- ]to[- ]have\b"
    r")",
    re.IGNORECASE,
)
_WHOLE_ITEM_NOT_REQUIRED = re.compile(
    r"^not\s+required(?:\s+for\s+merge)?\.?$",
    re.IGNORECASE,
)
# Observed failure (not bare "failure-recovery" nouns in deferred task names).
_OBSERVED_FAIL_VERB = re.compile(r"\b(?:failed|failing)\b", re.IGNORECASE)
_NONZERO_ERROR_COUNT = re.compile(
    r"\b[1-9]\d*\s+(?:tests?\s+)?(?:errors?|failures?)\b", re.IGNORECASE
)
_ZERO_FAIL_SUMMARY = re.compile(
    r"\b(?:0|no)\s+(?:tests?\s+)?fail(?:ed|ing|ures?)\b", re.IGNORECASE
)
_RESOLVED_FAILED_LINE = re.compile(
    r"(?:"
    r"\b(?:previously|formerly|no longer)\s+fail(?:ed|ing|ures?)?\b"
    r"|\bfail(?:ed|ing)\s+(?:tests?\s+)?(?:are\s+)?now\s+pass"
    r"|\bhas\s+not\s+fail(?:ed|ing)\b"
    r"|\bnot\s+fail(?:ed|ing)\b"
    r"|\bnever\s+fail(?:ed|ing)\b"
    r")",
    re.IGNORECASE,
)


def _is_optional_checkbox_text(text: str) -> bool:
    """True only when optionality qualifies the *whole* unchecked task.

    Leading ``Optional …`` / ``Out of scope …`` count. Mentions like
    ``with optional coverage`` or ``(GPU not required)`` do not exempt a
    required task (Codex P2 on #35).
    """
    item = (text or "").strip()
    if not item:
        return False
    if _NEGATED_OPTIONAL_CUE.search(item):
        return False
    # "Required follow-up: …" is required work.
    if _REQUIRED_WORK_CUE.search(item) and not _NOT_REQUIRED_CUE.search(item):
        return False
    if _WHOLE_ITEM_NOT_REQUIRED.match(item):
        return True
    return bool(_LEADING_OPTIONAL_CUE.match(item))


def _has_blocking_unchecked_checkbox(section: str) -> bool:
    """True when an unchecked task item is required (not self-declared optional).

    Bare ``- [ ]`` (no text) is blocking. Negated optionality and explicit
    required work are never treated as optional. Callers should pass a section
    that already had optional subtrees removed so nested children under optional
    parents are not double-scanned as required work.
    """
    for line in section.splitlines():
        m = _UNCHECKED_CHECKBOX_LINE.match(line)
        if m is not None and not _is_optional_checkbox_text(m.group("text") or ""):
            return True
    return False


def _strip_optional_unchecked_lines(section: str) -> str:
    """Drop optional unchecked items and their full indented subtrees.

    Blank lines inside an optional item do not end the subtree; only a
    non-blank sibling at indent ≤ base does (Codex P2 on #35).
    """
    lines = section.splitlines()
    kept: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _UNCHECKED_CHECKBOX_LINE.match(line)
        if m is not None and _is_optional_checkbox_text(m.group("text") or ""):
            base_indent = _line_indent(line)
            i += 1
            while i < len(lines):
                cont = lines[i]
                if not cont.strip():
                    # Blank line may sit between parent and indented child.
                    i += 1
                    continue
                if _line_indent(cont) > base_indent:
                    i += 1
                    continue
                break
            continue
        kept.append(line)
        i += 1
    return "\n".join(kept)


def _line_has_observed_failure(line: str) -> bool:
    """True when this single line reports an actual failed run / nonzero errors.

    Order matters: expected/resolved handling first, then nonzero error counts and
    observed fail verbs, and only then zero-failure suppression for the *verb*
    path. That way ``0 failures, 1 error`` still fails, and a ``0 failures``
    summary cannot mask evidence on another line (line-scoped callers).
    """
    low = line.lower()
    if not low.strip():
        return False
    # 1) Expected / resolved — not an observed product failure.
    if _RESOLVED_FAILED_LINE.search(low):
        return False
    if _fail_words_all_expected(low):
        return False
    if _expected_failure_was_contradicted(low):
        return True
    # 2) Nonzero error/failure counts win over a co-located zero-fail phrase.
    if _NONZERO_ERROR_COUNT.search(low):
        return True
    # 3) Observed fail verbs — suppressed only by a zero-fail summary *on this line*.
    if _ZERO_FAIL_SUMMARY.search(low) or "no fail" in low:
        return False
    if _OBSERVED_FAIL_VERB.search(low):
        return True
    return False


def _line_has_bare_failure_noun(line: str) -> bool:
    """Bare ``failure(s)`` on this line (required text only; line-scoped)."""
    low = line.lower()
    if not re.search(r"\bfailures?\b", low):
        return False
    if _RESOLVED_FAILED_LINE.search(low):
        return False
    if _fail_words_all_expected(low):
        return False
    # Zero-fail summary on *this* line only (not another required line).
    if _ZERO_FAIL_SUMMARY.search(low) or "no fail" in low:
        return False
    return True


def _section_has_observed_failure(section: str) -> bool:
    """Line-scoped observed-failure scan (does not let one zero-fail line mask another)."""
    return any(_line_has_observed_failure(line) for line in section.splitlines())


def _section_has_bare_failure_noun(section: str) -> bool:
    """Line-scoped bare failure-noun scan on required (already stripped) text."""
    return any(_line_has_bare_failure_noun(line) for line in section.splitlines())


def extract_validation(raw: dict[str, Any]) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    pull_body = strip_bot_boilerplate((raw.get("pull") or {}).get("body") or "")
    val_section = extract_section(
        pull_body,
        ("validation", "validations", "test plan", "test plans", "verification", "verifications", "testing", "tests"),
    )
    if val_section:
        # Optional unchecked subtrees: ignored for deferred-work cues and for
        # incomplete-checkbox blocking. Observed failures still use the full
        # section, line-scoped, so attempted optional work that blew up fails
        # while bare "failure-recovery" names on deferred items do not.
        required_section = _strip_optional_unchecked_lines(val_section)
        low_deferred = required_section.lower()
        result = "pass"
        if _has_blocking_unchecked_checkbox(required_section):
            result = "fail"
        non_pass_res = (
            re.compile(r"\bnot\s+run\b(?!ning)"),
            re.compile(r"\bnot\s+executed\b"),
            re.compile(r"\buntested\b"),
            re.compile(r"\bunchecked\b"),
            re.compile(r"\bn/?a\b"),
            re.compile(r"\btodo\b"),
            re.compile(r"\bpending\b"),
        )
        if any(rx.search(low_deferred) for rx in non_pass_res):
            result = "fail"
        # "skipped" is non-pass only when not explicitly zero (e.g. "0 skipped").
        if re.search(r"\bskipped\b", low_deferred) and not re.search(
            r"\b0\s+skipped\b", low_deferred
        ):
            result = "fail"
        # Observed failed/failing / nonzero error counts — line-scoped on full text
        # so one "0 failures" line cannot mask "Optional X failed" / "1 error" elsewhere.
        if _section_has_observed_failure(val_section):
            result = "fail"
        # Bare "failure(s)" nouns on *required* text only (optional deferred
        # titles like "failure-recovery benchmark; not run" are stripped).
        # Line-scoped: "0 failures" on line A must not suppress "reported failures" on B.
        if _section_has_bare_failure_noun(required_section):
            result = "fail"
        if _expected_failure_was_contradicted(low_deferred) or (
            _expected_failure_was_contradicted(val_section.lower())
        ):
            result = "fail"
        truncated = len(val_section) > 1500
        detail, _ = sanitize_text(val_section[:1500])
        if truncated and detail:
            detail = detail.rstrip() + " […]"
        events.append({"type": "test", "result": result, "detail": detail})

    checks = (raw.get("checks") or {}).get("check_runs") or []
    # Split build/test CI from review-app checks (CodeRabbit, Kilo, Codacy, …).
    ci_checks = [c for c in checks if not _is_review_app_check(c.get("name"))]
    review_checks = [c for c in checks if _is_review_app_check(c.get("name"))]
    if ci_checks:
        incomplete = any(
            (c.get("status") or "completed")
            not in ("completed", "neutral", "skipped")
            or (
                (c.get("status") or "completed") == "completed"
                and not c.get("conclusion")
            )
            for c in ci_checks
        )
        conclusions = [c.get("conclusion") for c in ci_checks if c.get("conclusion")]
        # Require at least one real success. All-skipped / all-neutral is not pass.
        if incomplete or not conclusions:
            result = "fail"
        elif any(c == "success" for c in conclusions) and all(
            c in ("success", "neutral", "skipped") for c in conclusions
        ):
            result = "pass"
        else:
            result = "fail"
        names = ", ".join(
            f"{c.get('name')}={c.get('conclusion') or c.get('status')}"
            for c in ci_checks[:12]
            if c.get("name")
        )
        events.append(
            {
                "type": "ci",
                "result": result,
                "detail": names or "check runs collected",
            }
        )
    # Combined commit status: GitHub returns state=pending with empty statuses[] when
    # only Checks API is used. Surface combined status only when there are real status
    # contexts, or when there is no Checks API evidence at all.
    combined = (raw.get("checks") or {}).get("combined_status") or {}
    state = str(combined.get("state") or "")
    status_contexts = combined.get("statuses") or []
    if state and (status_contexts or not checks):
        c_result = "pass" if state == "success" else "fail"
        events.append(
            {
                "type": "ci",
                "result": c_result,
                "detail": f"combined_status={state}",
            }
        )

    # Review apps are supplemental only — never the sole "validation" evidence.
    has_primary = any(e.get("type") in ("test", "ci") for e in events)
    if not has_primary:
        # Schema requires ≥1 validation event; never invent "pass" without evidence.
        events.append(
            {
                "type": "other",
                "result": "fail",
                "detail": "No structured validation evidence collected",
            }
        )
    if review_checks:
        r_conclusions = [c.get("conclusion") for c in review_checks if c.get("conclusion")]
        if r_conclusions and all(
            c in ("success", "neutral", "skipped") for c in r_conclusions
        ):
            r_result = "pass"
        else:
            r_result = "fail"
        r_names = ", ".join(
            f"{c.get('name')}={c.get('conclusion') or c.get('status')}"
            for c in review_checks[:12]
            if c.get("name")
        )
        events.append(
            {
                "type": "other",
                "result": r_result,
                "detail": f"review_apps: {r_names}" if r_names else "review_apps",
            }
        )
    return events


def extract_before_context(raw: dict[str, Any]) -> str:
    pull = raw.get("pull") or {}
    title = pull.get("title") or ""
    files = [
        f
        for f in (raw.get("files") or [])
        if not _is_noise_patch_path(f.get("filename"))
    ]
    names = [f.get("filename") for f in files[:20] if f.get("filename")]
    body = strip_bot_boilerplate(pull.get("body") or "")
    summary = extract_section(body, ("summary", "user description", "what changed"))
    bits = [
        f"PR title: {title}",
        f"Changed files ({len(files)}): {', '.join(names)}" if names else "Changed files: (none listed)",
    ]
    if summary:
        bits.append("Motivation/summary:\n" + summary[:1200])
    text = "\n".join(bits)
    text, _ = sanitize_text(text)
    return text


def _safe_sidecar_path(raw_path: Path, sidecar: str) -> Path | None:
    """Return sidecar path only if it resolves under the raw-record directory."""
    if not sidecar or not str(sidecar).strip():
        return None
    # Reject absolute paths and empty components before join.
    side_raw = Path(str(sidecar))
    if side_raw.is_absolute() or ".." in side_raw.parts:
        return None
    base = raw_path.parent.resolve()
    side = (raw_path.parent / side_raw).resolve()
    try:
        side.relative_to(base)
    except ValueError:
        return None
    if side.is_file():
        return side
    return None


# Local-ephemeral paths that must not appear in curated training patches.
_NOISE_PATCH_BASENAMES: frozenset[str] = frozenset(
    {
        "remotes.txt",
        ".env",
        ".env.local",
    }
)

# Local agent / tracker state directories. These carry machine-specific config,
# hook scripts and tracker exports (assignee emails, local paths) rather than any
# engineering trajectory; docs/data-policy.md excludes private local configuration.
# Matched as path *components*, so a monorepo's pkg/.claude/ is caught too.
_NOISE_PATCH_DIRS: tuple[str, ...] = (".beads", ".claude", ".kilo")


def _decode_git_path(token: str) -> str:
    """Decode a path token from a ``diff --git`` header.

    Handles Git C-quoted paths such as ``\"a/caf\\303\\251/remotes.txt\"`` so
    basename checks see ``remotes.txt`` rather than ``remotes.txt\"``.
    """
    s = (token or "").strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        # Git uses C-style escapes inside double quotes (octal + common escapes).
        inner = s[1:-1]
        try:
            # unicode_escape understands \\303 style octal as in Git's quoted paths.
            s = (
                inner.encode("utf-8")
                .decode("unicode_escape")
                .encode("latin-1")
                .decode("utf-8", errors="replace")
            )
        except Exception:
            s = inner.replace('\\"', '"').replace("\\\\", "\\")
    # Strip a/ or b/ prefix used by unified diffs.
    if s.startswith("a/") or s.startswith("b/"):
        s = s[2:]
    return s


def _is_noise_patch_path(path: str | None) -> bool:
    if not path:
        return False
    decoded = _decode_git_path(str(path)) if str(path).startswith('"') else str(path)
    # Also tolerate tokens that already include a/ or trailing quote fragments.
    cleaned = decoded.replace("\\", "/").strip().strip('"')
    if cleaned.startswith("a/") or cleaned.startswith("b/"):
        cleaned = cleaned[2:]
    base = Path(cleaned).name.lower().rstrip('"')
    if base in _NOISE_PATCH_BASENAMES:
        return True
    # removeprefix, not lstrip: lstrip("./") would eat the leading dot of ".beads".
    low = cleaned.lower().removeprefix("./")
    # Any *directory* component, so nested agent state (pkg/.claude/settings.json)
    # is filtered as well as repo-root state.
    if any(seg in _NOISE_PATCH_DIRS for seg in low.split("/")[:-1]):
        return True
    # Recognize .env.*.local patterns (e.g., .env.development.local, .env.test.local)
    # but preserve .env.example
    return base.startswith(".env.") and base.endswith(".local") and base != ".env.example"


def _parse_diff_git_paths(header_line: str) -> list[str]:
    """Return a/ and b/ path fields from a ``diff --git`` header.

    Handles C-quoted paths and unquoted paths that contain spaces (Git emits
    ``diff --git a/foo bar b/foo bar``). Never splits mid-path on whitespace.
    """
    line = header_line.strip()
    if not line.startswith("diff --git "):
        return []
    rest = line[len("diff --git ") :]
    # Two C-quoted paths (standard for spaces / special chars).
    quoted = re.fullmatch(
        r'"([^"\\]*(?:\\.[^"\\]*)*)"\s+"([^"\\]*(?:\\.[^"\\]*)*)"',
        rest,
    )
    if quoted:
        return [
            _decode_git_path(f'"{quoted.group(1)}"'),
            _decode_git_path(f'"{quoted.group(2)}"'),
        ]
    # Unquoted: split only at the a/... → b/... boundary so paths may contain spaces.
    if rest.startswith("a/"):
        sep = rest.find(" b/")
        if sep != -1:
            return [
                _decode_git_path(rest[:sep]),
                _decode_git_path(rest[sep + 1 :]),
            ]
    # Fallback: whitespace tokens (legacy / malformed headers).
    tokens = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"|(\S+)', rest)
    paths: list[str] = []
    for q, plain in tokens:
        token = f'"{q}"' if q else plain
        if token:
            paths.append(_decode_git_path(token))
    return paths


def _diff_header_has_noise_path(header_line: str) -> bool:
    """True if a ``diff --git`` header touches a noise basename (exact).

    Parses ``a/...`` and ``b/...`` paths (including C-quoted forms and spaces)
    so ``.env.example`` / ``.env template`` are kept while ``.env`` is dropped.
    """
    return any(_is_noise_patch_path(p) for p in _parse_diff_git_paths(header_line))


def _filter_noise_from_diff(diff_text: str) -> str:
    """Drop unified-diff hunks for local-only files (e.g. remotes.txt)."""
    if not diff_text:
        return diff_text
    # Cheap case-insensitive prefilter: skip the scan only when no noise basename
    # *and* no noise directory appears. Basenames alone would let a diff touching
    # only .beads/ or .claude/ files bypass header filtering entirely.
    low = diff_text.lower()
    if not any(
        token in low for token in (*_NOISE_PATCH_BASENAMES, *_NOISE_PATCH_DIRS)
    ):
        return diff_text
    out: list[str] = []
    skip = False
    for line in diff_text.splitlines(keepends=True):
        if line.startswith("diff --git "):
            skip = _diff_header_has_noise_path(line)
            if skip:
                continue
            out.append(line)
            continue
        if skip:
            continue
        out.append(line)
    return "".join(out)


def _load_diff_text(raw: dict[str, Any], raw_path: Path | None) -> str:
    diff = raw.get("diff") or {}
    inline = diff.get("inline")
    if isinstance(inline, str) and inline.strip():
        return _filter_noise_from_diff(inline)
    sidecar = diff.get("sidecar_path")
    if sidecar and raw_path is not None:
        side = _safe_sidecar_path(raw_path, str(sidecar))
        if side is not None:
            return _filter_noise_from_diff(
                side.read_text(encoding="utf-8", errors="replace")
            )
    # Fall back to concatenating file patches; mark omitted/truncated files explicitly.
    chunks: list[str] = []
    for f in raw.get("files") or []:
        name = f.get("filename") or "unknown"
        if _is_noise_patch_path(name):
            continue
        patch = f.get("patch")
        if patch:
            chunks.append(f"--- a/{name}\n+++ b/{name}\n{patch}")
        elif f.get("patch_truncated") or (
            f.get("status") not in (None, "removed") and not patch
        ):
            # Files API often drops large/binary patches — do not pretend they are absent.
            reason = "patch unavailable / truncated from files API"
            chunks.append(f"# omitted: {name} ({reason})")
    return "\n".join(chunks)


def extract_patch(
    raw: dict[str, Any],
    *,
    raw_path: Path | None = None,
    max_bytes: int = DEFAULT_MAX_TRAJECTORY_PATCH,
) -> str:
    full = _load_diff_text(raw, raw_path)
    full, _ = sanitize_text(full)
    if not full.strip():
        # Same noise filter as the files-API path so remotes.txt/.env never reappear.
        names = [
            f.get("filename")
            for f in (raw.get("files") or [])
            if f.get("filename") and not _is_noise_patch_path(f.get("filename"))
        ]
        return (
            f"# Patch unavailable from API; changed files: {', '.join(names) or '(none)'}\n"
        )
    encoded = full.encode("utf-8")
    if len(encoded) <= max_bytes:
        return full
    # Prefer first portion + file list footer (omit local-noise paths).
    files = [
        f
        for f in (raw.get("files") or [])
        if not _is_noise_patch_path(f.get("filename"))
    ]
    header_lines = [
        f"# Truncated unified diff for training (full raw under datasets/raw/; "
        f"{len(encoded)} bytes, {len(files)} files)",
    ]
    for f in files[:40]:
        header_lines.append(
            f"# {f.get('status')}: {f.get('filename')} "
            f"(+{f.get('additions')}/-{f.get('deletions')})"
        )
    header = "\n".join(header_lines) + "\n\n"
    budget = max_bytes - len(header.encode("utf-8")) - 80
    if budget < 1024:
        budget = 1024
    truncated = full.encode("utf-8")[:budget].decode("utf-8", errors="ignore")
    footer = "\n\n# … truncated …\n"
    return header + truncated + footer


def outcome_for(raw: dict[str, Any]) -> str:
    pull = raw.get("pull") or {}
    if pull.get("merged"):
        return "merged"
    state = str(pull.get("state") or "").lower()
    if state == "closed":
        # Closed without merge (includes abandoned drafts that were closed).
        return "closed"
    if state == "open":
        # Active drafts remain open; do not map draft=true → abandoned.
        return "open"
    # Unknown/missing state: conservative non-merged terminal-ish label.
    return "abandoned"


def language_for(card: dict[str, Any], raw: dict[str, Any]) -> str:
    """Resolve language: language_by_pr → card language → file extensions (GH #19)."""
    # Per-PR override (keys may be str or int in JSON), same pattern as domain_for.
    by_pr = card.get("language_by_pr") or {}
    if by_pr:
        pr = int((raw.get("source") or {}).get("pr_number") or 0)
        if pr:
            for k, v in by_pr.items():
                try:
                    if int(k) == pr and isinstance(v, str) and v.strip():
                        return v.strip()
                except (TypeError, ValueError):
                    continue
    if card.get("language"):
        return str(card["language"])
    files = [f.get("filename") or "" for f in (raw.get("files") or [])]
    exts = {Path(f).suffix.lower() for f in files if f}
    if ".rs" in exts:
        return "Rust"
    if ".jl" in exts:
        return "Julia"
    if ".py" in exts:
        return "Python"
    if ".cu" in exts or ".cuh" in exts:
        return "CUDA"
    return "unknown"


def normalize_record(
    raw: dict[str, Any],
    card: dict[str, Any] | None = None,
    *,
    raw_path: Path | None = None,
    max_patch_bytes: int = DEFAULT_MAX_TRAJECTORY_PATCH,
) -> dict[str, Any]:
    """Build a schema-v0 trajectory dict from a raw PR record."""
    card = card or {}
    source = raw.get("source") or {}
    repo = source.get("repo") or card.get("source_repo") or "unknown/unknown"
    pr = int(source.get("pr_number") or 0)
    # Include owner so multi-repo extracts never collide (alice/widget#12 vs bob/widget#12).
    owner_repo = repo.replace("/", "-") if "/" in repo else repo
    traj_id = f"{owner_repo}-{pr}"

    linked_issues = enrich_linked_issues(raw, card)
    # Prefer enriched list for context/URLs without mutating caller's raw dict.
    raw_for_ctx = {**raw, "linked_issues": linked_issues}
    issue_context = extract_issue_context(raw_for_ctx)
    review_signals = extract_review_signals(raw)
    training_use = training_use_for(repo, pr, card)
    if training_use == "review-to-patch" and not review_signals:
        # Schema requires non-empty review_signals for review-to-patch; fall back
        # to "other" when there are no retained (non-bot) review comments.
        training_use = "other"
    traj: dict[str, Any] = {
        "id": traj_id,
        "repo": repo,
        "pr_number": pr,
        "source_urls": build_source_urls(repo, pr, linked_issues),
        "language": language_for(card, raw),
        "domain": domain_for(repo, pr, card, raw),
        "task_type": task_type_for(repo, pr, raw, card),
        "before_context": extract_before_context(raw),
        "patch": extract_patch(raw, raw_path=raw_path, max_bytes=max_patch_bytes),
        "validation": extract_validation(raw),
        "outcome": outcome_for(raw),
        "training_use": training_use,
    }
    if issue_context:
        traj["issue_context"] = issue_context
    if review_signals:
        traj["review_signals"] = review_signals
    # Ensure anyOf: need issue_context or review_signals
    if "issue_context" not in traj and "review_signals" not in traj:
        title = (raw.get("pull") or {}).get("title") or traj_id
        traj["issue_context"] = f"PR {repo}#{pr}: {title}"

    traj["quality_score"] = score_quality(traj, raw)
    # Final sanitize pass
    for key in ("issue_context", "before_context", "patch"):
        if key in traj and isinstance(traj[key], str):
            traj[key], _ = sanitize_text(traj[key])
    return traj
