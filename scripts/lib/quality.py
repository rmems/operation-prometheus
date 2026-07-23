"""Quality scoring heuristics for trajectory records."""

from __future__ import annotations

from typing import Any

# Manual overrides for corinth-canal shortlist (curated research scores).
SHORTLIST_QUALITY: dict[tuple[str, int], float] = {
    ("rmems/corinth-canal", 82): 0.86,
    ("rmems/corinth-canal", 89): 0.92,
    ("rmems/corinth-canal", 91): 0.62,
    ("rmems/corinth-canal", 94): 0.94,
    ("rmems/corinth-canal", 95): 0.58,
    ("rmems/corinth-canal", 96): 0.78,
}


def score_quality(traj: dict[str, Any], raw: dict[str, Any] | None = None) -> float:
    """Heuristic quality score in [0, 1], with optional shortlist overrides."""
    repo = traj.get("repo") or ""
    pr = int(traj.get("pr_number") or 0)
    key = (repo, pr)
    if key in SHORTLIST_QUALITY:
        return SHORTLIST_QUALITY[key]

    score = 0.5
    if traj.get("outcome") == "merged":
        score += 0.1
    if traj.get("issue_context"):
        score += 0.1
    reviews = traj.get("review_signals") or []
    if reviews:
        score += 0.1
    vals = traj.get("validation") or []
    if any(v.get("result") == "pass" for v in vals):
        score += 0.1
    if raw:
        commits = raw.get("commits") or []
        if len(commits) >= 3:
            score += 0.05
        warnings = (raw.get("collection_meta") or {}).get("warnings") or []
        if any("redacted" in str(w) for w in warnings):
            score -= 0.05
    return max(0.0, min(1.0, round(score, 2)))
