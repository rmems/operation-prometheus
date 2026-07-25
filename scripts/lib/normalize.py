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
    # Per-PR domain map on the card (keys may be str or int in JSON).
    by_pr = card.get("domain_by_pr") or {}
    if by_pr:
        for k, v in by_pr.items():
            try:
                if int(k) == pr and isinstance(v, str) and v.strip():
                    return v.strip()
            except (TypeError, ValueError):
                continue
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


def enrich_linked_issues(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Merge API-fetched linked issues with close-keyword refs from PR/commits.

    Older raw records may have empty ``linked_issues`` when bodies used multi-issue
    lists (``Closes: #75, #76``) or gerunds (``closing #80``). Reconstruct stubs so
    ``source_urls`` keeps issue→patch provenance without re-collecting.
    """
    from .raw_record import parse_linked_issue_numbers, parse_repo

    linked = list(raw.get("linked_issues") or [])
    seen: set[tuple[str, int]] = set()
    for issue in linked:
        repo_i = str(issue.get("repo") or "")
        num = issue.get("number")
        if repo_i and num is not None:
            seen.add((repo_i.lower(), int(num)))

    source = raw.get("source") or {}
    repo = str(source.get("repo") or "")
    try:
        owner, name = parse_repo(repo)
    except Exception:
        return linked

    parts = [(raw.get("pull") or {}).get("body") or ""]
    for c in raw.get("commits") or []:
        msg = c.get("message") if isinstance(c, dict) else None
        if msg:
            parts.append(str(msg))
    for i_owner, i_repo, num in parse_linked_issue_numbers(
        "\n".join(parts), owner, name
    ):
        key = (f"{i_owner}/{i_repo}".lower(), num)
        if key in seen:
            continue
        seen.add(key)
        linked.append(
            {
                "number": num,
                "repo": f"{i_owner}/{i_repo}",
                "title": "",
                "body": "",
                "state": "unknown",
                "html_url": f"https://github.com/{i_owner}/{i_repo}/issues/{num}",
                "closed_by_pr": True,
                "synthetic": True,
            }
        )
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
_BARE_FIXED_IN_REPLY = re.compile(
    r"(?is)^\s*(?:\*\*)?(?:addressed|fixed)\s+in\s+`?[0-9a-f]{7,40}`?"
    r"(?:\*\*)?\s*\.?\s*$"
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
            body = strip_bot_boilerplate((c.get("body") or "").strip())
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
            r"\b(?:0|no)\s+(?:tests?\s+)?fail(?:ed|ing|ures?)\b", low
        )
        # Resolved/negated fail* prose should not invert a passing summary.
        resolved_failed = re.search(
            r"(?:"
            r"\b(?:previously|formerly|no longer)\s+fail(?:ed|ing|ures?)?\b"
            r"|\bfail(?:ed|ing)\s+(?:tests?\s+)?(?:are\s+)?now\s+pass"
            r"|\bhas\s+not\s+fail(?:ed|ing)\b"
            r"|\bnot\s+fail(?:ed|ing)\b"
            r"|\bnever\s+fail(?:ed|ing)\b"
            r")",
            low,
        )
        # Past-tense failed, active failing, or "failure" wording.
        if (
            re.search(r"\bfail(?:ed|ing|ures?)?\b", low)
            and not zero_failures
            and "no fail" not in low
            and not resolved_failed
        ):
            # Avoid matching "fail" inside unrelated words; require fail/failed/failing/failure.
            if re.search(r"\b(?:failed|failing|failures?)\b", low):
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
    return base in _NOISE_PATCH_BASENAMES


def _diff_header_has_noise_path(header_line: str) -> bool:
    """True if a ``diff --git`` header touches a noise basename (exact).

    Parses ``a/...`` and ``b/...`` paths (including C-quoted forms) so
    ``.env.example`` is kept while ``.env`` / ``remotes.txt`` are dropped.
    """
    line = header_line.strip()
    if not line.startswith("diff --git "):
        return False
    rest = line[len("diff --git ") :]
    # Prefer quoted tokens, then unquoted whitespace-separated a/ b/ paths.
    tokens = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"|(\S+)', rest)
    paths: list[str] = []
    for quoted, plain in tokens:
        token = f'"{quoted}"' if quoted else plain
        if not token:
            continue
        paths.append(_decode_git_path(token))
    return any(_is_noise_patch_path(p) for p in paths)


def _filter_noise_from_diff(diff_text: str) -> str:
    """Drop unified-diff hunks for local-only files (e.g. remotes.txt)."""
    if not diff_text:
        return diff_text
    # Cheap prefilter: only scan when a noise basename token might appear.
    if not any(
        f"/{name}" in diff_text or f" {name}" in diff_text or diff_text.endswith(name)
        for name in _NOISE_PATCH_BASENAMES
    ) and not any(
        f"a/{name}" in diff_text or f"b/{name}" in diff_text
        for name in _NOISE_PATCH_BASENAMES
    ):
        # Still handle bare basenames in headers.
        if not any(name in diff_text for name in _NOISE_PATCH_BASENAMES):
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
        files = raw.get("files") or []
        names = [f.get("filename") for f in files if f.get("filename")]
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

    linked_issues = enrich_linked_issues(raw)
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
