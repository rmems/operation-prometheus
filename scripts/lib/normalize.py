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

# Check-run names that are review bots, not build/test validation.
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
    "codeql",
    "snyk",
    "chatgpt-codex",
    "codex",
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

# Per-PR overrides for corinth-canal shortlist training_use (schema enums).
TRAINING_USE_OVERRIDE: dict[tuple[str, int], str] = {
    ("rmems/corinth-canal", 82): "repair",
    ("rmems/corinth-canal", 89): "validation",
    ("rmems/corinth-canal", 91): "other",
    ("rmems/corinth-canal", 94): "repair",
    ("rmems/corinth-canal", 95): "other",
    ("rmems/corinth-canal", 96): "validation",
}

TASK_TYPE_OVERRIDE: dict[tuple[str, int], str] = {
    ("rmems/corinth-canal", 82): "feature",
    ("rmems/corinth-canal", 89): "test",
    ("rmems/corinth-canal", 91): "feature",
    ("rmems/corinth-canal", 94): "feature",
    ("rmems/corinth-canal", 95): "feature",
    ("rmems/corinth-canal", 96): "feature",
}

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
    (re.compile(r"(?i)^security\b"), "security"),
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
    key = (repo, pr)
    if key in TRAINING_USE_OVERRIDE:
        return TRAINING_USE_OVERRIDE[key]
    bucket = _bucket_map(card).get(pr)
    if bucket:
        return FEATURE_BUCKET_TO_TRAINING.get(bucket, "other")
    return "other"


def domain_for(repo: str, pr: int, card: dict[str, Any], raw: dict[str, Any]) -> str:
    key = (repo, pr)
    if key in DOMAIN_OVERRIDE:
        return DOMAIN_OVERRIDE[key]
    domains = card.get("domains") or []
    if domains:
        return str(domains[0])
    labels = (raw.get("pull") or {}).get("labels") or []
    if "CUDA" in labels or "cuda" in labels:
        return "gpu-compute"
    return "systems"


def task_type_for(repo: str, pr: int, raw: dict[str, Any]) -> str:
    key = (repo, pr)
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
    summary = extract_section(body, ("summary", "user description"))
    if summary:
        parts.append(summary[:2500])
    elif body:
        parts.append(body[:2000])
    title = (pull.get("title") or "").strip()
    if title and not parts:
        parts.append(title)
    if not parts:
        return None
    text = "\n\n".join(parts).strip()
    text, _ = sanitize_text(text)
    return text or None


def _is_non_actionable_review_body(body: str) -> bool:
    """True for product review wrappers (e.g. Codex summary shell) without signal."""
    if not body or not body.strip():
        return True
    return bool(_CODEX_REVIEW_WRAPPER.search(body))


def extract_review_signals(raw: dict[str, Any], *, max_items: int = 8) -> list[dict[str, str]]:
    signals: list[dict[str, str]] = []
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
                    # Keep short human wording (e.g. LGTM) and annotate state.
                    body = f"{body} (review state: {state})"
                else:
                    body = f"Review state: {state}"
            else:
                continue
        body, _ = sanitize_text(strip_bot_boilerplate(body))
        if not body or _is_non_actionable_review_body(body):
            continue
        signals.append(
            {
                "author": r.get("user_login") or "unknown",
                "comment": body[:2000],
            }
        )
        if len(signals) >= max_items:
            break
    # Then add inline review_comments if space remains
    if len(signals) < max_items:
        for c in raw.get("review_comments") or []:
            if is_bot_user(c.get("user_login"), c.get("user_type")):
                continue
            body = (c.get("body") or "").strip()
            if not body or _is_non_actionable_review_body(body):
                continue
            body, _ = sanitize_text(body)
            if not body or _is_non_actionable_review_body(body):
                continue
            item: dict[str, str] = {
                "author": c.get("user_login") or "unknown",
                "comment": body[:2000],
            }
            if "```suggestion" in body:
                m = re.search(r"```suggestion\s*\n(.*?)```", body, re.DOTALL)
                if m:
                    suggestion = m.group(1).strip()[:2000]
                    # Empty suggestion blocks (delete-line) must not set the field —
                    # schema requires minLength 1 on suggestion when present.
                    if suggestion:
                        item["suggestion"] = suggestion
            signals.append(item)
            if len(signals) >= max_items:
                break
    # Finally non-bot PR conversation comments (often carry review signal)
    if len(signals) < max_items:
        for c in raw.get("issue_comments") or []:
            if is_bot_user(c.get("user_login"), c.get("user_type")):
                continue
            body = strip_bot_boilerplate((c.get("body") or "").strip())
            if not body or len(body) < 20 or _is_non_actionable_review_body(body):
                continue
            body, _ = sanitize_text(body)
            if not body or _is_non_actionable_review_body(body):
                continue
            signals.append(
                {
                    "author": c.get("user_login") or "unknown",
                    "comment": body[:2000],
                }
            )
            if len(signals) >= max_items:
                break
    return signals


def extract_validation(raw: dict[str, Any]) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    pull_body = strip_bot_boilerplate((raw.get("pull") or {}).get("body") or "")
    val_section = extract_section(
        pull_body,
        ("validation", "test plan", "verification", "testing", "tests"),
    )
    if val_section:
        low = val_section.lower()
        result = "pass"
        # Anchored/non-pass cues — avoid loose substrings ("not running…").
        non_pass_res = (
            re.compile(r"(?m)^\s*[-*]\s*\[\s\]"),  # unchecked checkbox lines
            re.compile(r"\bnot\s+run\b(?!ning)"),
            re.compile(r"\bnot\s+executed\b"),
            re.compile(r"\buntested\b"),
            re.compile(r"\bunchecked\b"),
            re.compile(r"\bn/?a\b"),
            re.compile(r"\btodo\b"),
            re.compile(r"\bpending\b"),
        )
        if any(rx.search(low) for rx in non_pass_res):
            result = "fail"
        # "skipped" is non-pass only when not explicitly zero (e.g. "0 skipped").
        if re.search(r"\bskipped\b", low) and not re.search(r"\b0\s+skipped\b", low):
            result = "fail"
        zero_failures = re.search(
            r"\b(?:0|no)\s+(?:tests?\s+)?fail(?:ed|ures?)\b", low
        )
        # Resolved/negated "failed" prose should not invert a passing summary.
        resolved_failed = re.search(
            r"(?:"
            r"\b(?:previously|formerly|no longer)\s+failed\b"
            r"|\bfailed\s+(?:tests?\s+)?(?:are\s+)?now\s+pass"
            r"|\bhas\s+not\s+failed\b"
            r"|\bnot\s+failed\b"
            r"|\bnever\s+failed\b"
            r")",
            low,
        )
        if (
            re.search(r"\bfailed\b", low)
            and not zero_failures
            and "no fail" not in low
            and not resolved_failed
        ):
            result = "fail"
        # Non-zero error/failure counts (sanitizer / pytest style): "1 error", "2 failures".
        if re.search(r"\b[1-9]\d*\s+(?:tests?\s+)?(?:errors?|failures?)\b", low):
            result = "fail"
        detail, _ = sanitize_text(val_section[:1500])
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
        if incomplete or not conclusions:
            result = "fail"
        elif all(c in ("success", "neutral", "skipped") for c in conclusions):
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
    if review_checks:
        r_conclusions = [c.get("conclusion") for c in review_checks if c.get("conclusion")]
        if r_conclusions and all(
            c in ("success", "neutral", "skipped") for c in r_conclusions
        ):
            r_result = "pass"
        else:
            r_result = "fail" if r_conclusions else "fail"
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

    if not events:
        # Schema requires ≥1 validation event; never invent "pass" without evidence.
        events.append(
            {
                "type": "other",
                "result": "fail",
                "detail": "No structured validation evidence collected",
            }
        )
    return events


def extract_before_context(raw: dict[str, Any]) -> str:
    pull = raw.get("pull") or {}
    title = pull.get("title") or ""
    files = raw.get("files") or []
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


def _load_diff_text(raw: dict[str, Any], raw_path: Path | None) -> str:
    diff = raw.get("diff") or {}
    inline = diff.get("inline")
    if isinstance(inline, str) and inline.strip():
        return inline
    sidecar = diff.get("sidecar_path")
    if sidecar and raw_path is not None:
        side = _safe_sidecar_path(raw_path, str(sidecar))
        if side is not None:
            return side.read_text(encoding="utf-8", errors="replace")
    # Fall back to concatenating file patches
    chunks: list[str] = []
    for f in raw.get("files") or []:
        name = f.get("filename") or "unknown"
        patch = f.get("patch")
        if patch:
            chunks.append(f"--- a/{name}\n+++ b/{name}\n{patch}")
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
        files = raw.get("files") or []
        names = [f.get("filename") for f in files if f.get("filename")]
        return (
            f"# Patch unavailable from API; changed files: {', '.join(names) or '(none)'}\n"
        )
    encoded = full.encode("utf-8")
    if len(encoded) <= max_bytes:
        return full
    # Prefer first portion + file list footer
    files = raw.get("files") or []
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
    slug = repo.split("/")[-1]
    traj_id = f"{slug}-{pr}"

    issue_context = extract_issue_context(raw)
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
        "source_urls": build_source_urls(repo, pr, raw.get("linked_issues") or []),
        "language": language_for(card, raw),
        "domain": domain_for(repo, pr, card, raw),
        "task_type": task_type_for(repo, pr, raw),
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
