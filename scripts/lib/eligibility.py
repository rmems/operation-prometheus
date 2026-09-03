"""Deterministic eligibility-ledger construction from a frozen source snapshot."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .source_inventory import canonical_json_bytes, sha256_json

LEDGER_SCHEMA_VERSION = "eligibility_ledger_v1"
REPOSITORY_SCHEMA_VERSION = "source_repository_v1"
MANIFEST_SCHEMA_VERSION = "eligibility_manifest_v1"

LEDGER_STATES = {
    "included_positive",
    "included_negative",
    "quarantined",
    "excluded",
    "watchlist_open",
}
QUALITY_DIMENSIONS = (
    "task_hypothesis_clarity",
    "before_state_completeness",
    "patch_action_fidelity",
    "chronology_confidence",
    "validation_strength",
    "outcome_confidence",
    "artifact_reproducibility",
    "license_clarity",
    "policy_privacy_result",
)
QUALITY_ASSESSMENTS = {
    "verified",
    "partial",
    "missing",
    "failed",
    "unknown",
    "not_applicable",
}

_TASK_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)^fix(?:\(|:|\b)"), "bugfix"),
    (re.compile(r"(?i)^feat(?:\(|:|\b)"), "feature"),
    (re.compile(r"(?i)^refactor(?:\(|:|\b)"), "refactor"),
    (re.compile(r"(?i)^test(?:s)?(?:\(|:|\b)"), "test"),
    (re.compile(r"(?i)^perf(?:\(|:|\b)"), "performance"),
    (re.compile(r"(?i)^sec(?:urity)?(?:\(|:|\b)"), "security"),
    (re.compile(r"(?i)^(?:ci|build)(?:\(|:|\b)"), "ci"),
    (re.compile(r"(?i)^data(?:\(|:|\b)"), "data"),
    (re.compile(r"(?i)^docs?(?:\(|:|\b)"), "documentation"),
    (re.compile(r"(?i)^(?:release|chore\(release\))(?:\(|:|\b)"), "release"),
    (re.compile(r"(?i)^(?:research|experiment|eval)(?:\(|:|\b)"), "research_experiment"),
)
_PR_REF_PATTERN = (
    r"(?:(?:https://github\.com/)?(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)"
    r"(?:/pull/|#)|(?:pull/|pr\s*#?|#))(?P<number>\d+)\b"
)
_REVERT_REF = re.compile(
    r"\brevert(?:s|ed|ing)?\b[^\n]{0,160}?" + _PR_REF_PATTERN,
    re.IGNORECASE,
)
_SUPERSEDE_REF = re.compile(
    r"\bsupersed(?:e|es|ed|ing)\b[^\n]{0,160}?" + _PR_REF_PATTERN,
    re.IGNORECASE,
)
_ISSUE_SCOPED_BARE_REF = re.compile(
    r"(?i)\b(?:issues?|bugs?|tickets?|close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?[ \t]*#\d+\b"
)
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP_TOKENS = {
    "a",
    "an",
    "and",
    "for",
    "from",
    "in",
    "of",
    "on",
    "pr",
    "the",
    "to",
    "with",
}


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        normalized = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def candidate_id(pr: dict[str, Any]) -> str:
    repo_id = str(pr.get("repository_id") or "").strip()
    pr_id = str(pr.get("id") or "").strip()
    if not repo_id or not pr_id:
        raise ValueError("Candidate is missing immutable repository or pull-request ID")
    return f"github:repository:{repo_id}:pull:{pr_id}"


def _source_ref(pr: dict[str, Any]) -> str:
    return f"sha256:{pr.get('source_hash') or ''}"


def _quality(
    assessment: str,
    reason_codes: list[str],
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    if assessment not in QUALITY_ASSESSMENTS:
        raise ValueError(f"Unknown quality assessment {assessment}")
    return {
        "assessment": assessment,
        "reason_codes": sorted(set(reason_codes)),
        "evidence_refs": sorted(set(evidence_refs or [])),
    }


def assess_quality(pr: dict[str, Any], repository: dict[str, Any]) -> dict[str, Any]:
    source = _source_ref(pr)
    linked = pr.get("linked_issues") or []
    title = str(pr.get("title") or "").strip()
    body = str(pr.get("body") or "").strip()
    base_oid = str(pr.get("base_oid") or "")
    head_oid = str(pr.get("head_oid") or "")
    state = str(pr.get("state") or "").lower()
    terminal_time = pr.get("merged_at") or pr.get("closed_at")

    if linked and (title or body):
        clarity = _quality(
            "partial",
            ["formal_issue_reference_without_issue_content", "pr_description_present"],
            [source, *[str(item.get("url") or item.get("id")) for item in linked]],
        )
    elif linked:
        clarity = _quality(
            "partial",
            ["formal_issue_reference_without_issue_content"],
            [str(item.get("url") or item.get("id")) for item in linked],
        )
    elif title and body:
        clarity = _quality("partial", ["pr_description_without_formal_issue_link"], [source])
    elif title:
        clarity = _quality("partial", ["pr_title_only"], [source])
    else:
        clarity = _quality("missing", ["task_signal_missing"])

    if base_oid and head_oid:
        before_state = _quality(
            "partial",
            ["source_oids_without_content_addressed_snapshot"],
            [f"git:{base_oid}", f"git:{head_oid}"],
        )
        patch = _quality(
            "partial",
            ["source_oids_without_full_patch_artifact"],
            [f"git:{base_oid}", f"git:{head_oid}"],
        )
    else:
        before_state = _quality("missing", ["base_or_head_oid_missing"])
        patch = _quality("missing", ["patch_and_code_state_missing"])

    timestamps = [pr.get("created_at"), pr.get("updated_at")]
    if state in {"merged", "closed"}:
        timestamps.append(terminal_time)
    if all(_parse_time(value) is not None for value in timestamps):
        chronology = _quality("partial", ["pr_level_chronology_only"], [source])
    else:
        chronology = _quality("missing", ["source_timestamp_missing_or_invalid"])

    validation = _quality("missing", ["check_and_validation_events_not_collected"])

    if state == "merged" and _parse_time(pr.get("merged_at")):
        outcome = _quality("verified", ["github_merged_terminal_state"], [str(pr.get("url") or source)])
    elif state == "closed" and _parse_time(pr.get("closed_at")):
        outcome = _quality("verified", ["github_closed_unmerged_terminal_state"], [str(pr.get("url") or source)])
    elif state == "open":
        outcome = _quality("partial", ["mutable_open_state"], [str(pr.get("url") or source)])
    else:
        outcome = _quality("unknown", ["terminal_state_unresolved"])

    if base_oid and head_oid:
        artifacts = _quality(
            "partial",
            ["git_oids_present_artifact_bundle_missing"],
            [f"git:{base_oid}", f"git:{head_oid}"],
        )
    else:
        artifacts = _quality("missing", ["reproducible_artifact_reference_missing"])

    spdx = str(((repository.get("license") or {}).get("spdx_id")) or "").strip()
    if spdx and spdx.upper() not in {"NOASSERTION", "OTHER"}:
        license_quality = _quality(
            "partial",
            ["current_repository_license_only"],
            [f"spdx:{spdx}", _source_ref(repository)],
        )
    else:
        license_quality = _quality("missing", ["source_license_unresolved"])

    warnings = pr.get("collection_warnings") or []
    if warnings:
        policy = _quality(
            "partial",
            ["source_metadata_sanitized", *[str(item) for item in warnings]],
            [source],
        )
    else:
        policy = _quality("partial", ["public_metadata_only_policy_scan"], [source])

    result = {
        "task_hypothesis_clarity": clarity,
        "before_state_completeness": before_state,
        "patch_action_fidelity": patch,
        "chronology_confidence": chronology,
        "validation_strength": validation,
        "outcome_confidence": outcome,
        "artifact_reproducibility": artifacts,
        "license_clarity": license_quality,
        "policy_privacy_result": policy,
    }
    if set(result) != set(QUALITY_DIMENSIONS):
        raise AssertionError("Quality assessment dimensions drifted")
    return result


def infer_task_family(pr: dict[str, Any], policy: dict[str, Any]) -> tuple[str, list[str]]:
    title = str(pr.get("title") or "").strip()
    author_record = pr.get("author") or {}
    author = str(author_record.get("login") or "").casefold()
    author_type = str(author_record.get("type") or "").casefold()
    dependency_authors = {
        str(item).casefold() for item in (policy.get("dependency_authors") or [])
    }
    if author in dependency_authors or (
        author_type == "bot"
        and any(marker in author for marker in ("dependabot", "renovate", "snyk-bot"))
    ):
        return "dependency", ["dependency_automation_author"]
    for pattern, family in _TASK_PATTERNS:
        if pattern.search(title):
            return family, [f"title_pattern:{family}"]
    labels = {str(item).casefold() for item in (pr.get("labels") or [])}
    label_map = {
        "bug": "bugfix",
        "enhancement": "feature",
        "documentation": "documentation",
        "security": "security",
        "ci": "ci",
        "data": "data",
    }
    for label, family in label_map.items():
        if label in labels:
            return family, [f"github_label:{label}"]
    return "other", ["no_deterministic_task_family_rule"]


def _automatic_state(
    pr: dict[str, Any],
    task_family: str,
) -> tuple[str, list[str]]:
    state = str(pr.get("state") or "").lower()
    title = str(pr.get("title") or "").strip()
    if state == "open":
        reasons = ["mutable_open_pull_request"]
        if pr.get("draft"):
            reasons.append("draft_pull_request")
        return "watchlist_open", reasons
    if task_family == "dependency":
        return "excluded", ["dependency_only"]
    if task_family == "release" and re.search(r"(?i)\b(?:release|version|changelog)\b", title):
        return "excluded", ["routine_release_only"]
    if task_family == "documentation":
        return "excluded", ["non_executable_documentation"]
    if re.search(r"(?i)^(?:style|format)(?:\(|:|\b)", title):
        return "excluded", ["formatting_only"]
    if state == "merged":
        return "quarantined", ["full_trajectory_collection_pending"]
    if state == "closed":
        return "quarantined", ["negative_trajectory_evidence_incomplete"]
    return "quarantined", ["source_disposition_unresolved"]


def _override_map(policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    overrides: dict[str, dict[str, Any]] = {}
    for raw in policy.get("overrides") or []:
        if not isinstance(raw, dict):
            raise ValueError("Eligibility override must be an object")
        target = str(raw.get("candidate_id") or "")
        if not target or target in overrides:
            raise ValueError(f"Missing or duplicate override candidate_id {target!r}")
        state = str(raw.get("state") or "")
        reasons = raw.get("reason_codes") or []
        evidence = raw.get("evidence_refs") or []
        if state not in LEDGER_STATES or not reasons or not evidence:
            raise ValueError(f"Override {target} lacks a valid state, reasons, or evidence")
        overrides[target] = raw
    return overrides


def _lineage(
    pr: dict[str, Any],
    by_repo_number: dict[tuple[str, int], str],
) -> dict[str, list[dict[str, str]]]:
    text = f"{pr.get('title') or ''}\n{pr.get('body') or ''}"
    repo_name = str(pr.get("repository_name_with_owner") or "").casefold()

    def edges(pattern: re.Pattern[str], relation: str) -> list[dict[str, str]]:
        found: list[dict[str, str]] = []
        seen: set[str] = set()
        for match in pattern.finditer(text):
            if match.group("repo") is None and _ISSUE_SCOPED_BARE_REF.search(match.group(0)):
                continue
            number = int(match.group("number"))
            referenced_repo = str(match.group("repo") or repo_name).casefold()
            target = by_repo_number.get((referenced_repo, number))
            if not target or target in seen:
                continue
            seen.add(target)
            found.append(
                {
                    "relation": relation,
                    "target_candidate_id": target,
                    "evidence_ref": _source_ref(pr),
                }
            )
        return found

    return {
        "reverts": edges(_REVERT_REF, "reverts"),
        "supersedes": edges(_SUPERSEDE_REF, "supersedes"),
        "multi_pr_links": [],
    }


def _load_existing_rows(repo_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((repo_root / "datasets" / "jsonl").glob("*.jsonl")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                continue
            repo = str(record.get("repo") or "")
            pr_number = record.get("pr_number")
            if not repo or not isinstance(pr_number, int):
                continue
            rows.append(
                {
                    "repo": repo,
                    "pr_number": pr_number,
                    "record_id": record.get("id"),
                    "file": path.relative_to(repo_root).as_posix(),
                    "line": line_number,
                    "canonical_sha256": sha256_json(record),
                }
            )
    return rows


def _title_tokens(title: str) -> set[str]:
    return {
        token
        for token in _TOKEN_RE.findall(title.casefold())
        if token not in _STOP_TOKENS and not token.isdigit()
    }


def _normalized_exact_title(title: str) -> str:
    """Normalize only casing and whitespace for exact-title assertions."""
    return " ".join(title.split()).casefold()


def _duplicate_records(
    candidates: list[dict[str, Any]],
    existing_rows: list[dict[str, Any]],
    by_repo_number: dict[tuple[str, int], str],
    *,
    near_threshold: float,
) -> list[dict[str, Any]]:
    duplicates: list[dict[str, Any]] = []
    by_source: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in existing_rows:
        resolved_repo = str(row.get("resolved_repository_name_with_owner") or row["repo"])
        by_source[(resolved_repo.casefold(), row["pr_number"])].append(row)
    for key, rows in sorted(by_source.items()):
        if len(rows) < 2:
            continue
        candidate = by_repo_number.get(key)
        digest_set = {row["canonical_sha256"] for row in rows}
        group_id = "duplicate:" + hashlib.sha256(
            canonical_json_bytes([key, sorted(row["file"] for row in rows)])
        ).hexdigest()[:20]
        duplicates.append(
            {
                "schema_version": "duplicate_group_v1",
                "group_id": group_id,
                "kind": "current_corpus_duplicate",
                "candidate_ids": [candidate] if candidate else [],
                "source_candidate": f"{key[0]}#{key[1]}",
                "exact": len(digest_set) == 1,
                "similarity": 1.0 if len(digest_set) == 1 else None,
                "evidence": rows,
            }
        )

    by_head: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        head_oid = str(candidate.get("head_oid") or "")
        if head_oid:
            by_head[head_oid].append(candidate)
    for head_oid, rows in sorted(by_head.items()):
        if len(rows) < 2:
            continue
        ids = sorted(str(row["candidate_id"]) for row in rows)
        base_oids = sorted(
            {str(row.get("base_oid")) for row in rows if str(row.get("base_oid") or "")}
        )
        missing_base_candidate_ids = sorted(
            str(row["candidate_id"]) for row in rows if not str(row.get("base_oid") or "")
        )
        exact = len(base_oids) == 1 and not missing_base_candidate_ids
        group_id = "duplicate:" + hashlib.sha256(head_oid.encode()).hexdigest()[:20]
        duplicates.append(
            {
                "schema_version": "duplicate_group_v1",
                "group_id": group_id,
                "kind": "shared_head_oid",
                "candidate_ids": sorted(ids),
                "source_candidate": None,
                "exact": exact,
                "similarity": 1.0 if exact else None,
                "evidence": [
                    {
                        "head_oid": head_oid,
                        "base_oids": base_oids,
                        "missing_base_candidate_ids": missing_base_candidate_ids,
                    }
                ],
            }
        )

    by_repository: dict[str, list[tuple[str, set[str], str]]] = defaultdict(list)
    for row in candidates:
        tokens = _title_tokens(row["title"])
        exact_title = _normalized_exact_title(str(row.get("title") or ""))
        if exact_title:
            by_repository[row["repository_name_with_owner"].casefold()].append(
                (row["candidate_id"], tokens, exact_title)
            )
    for _repository, entries in sorted(by_repository.items()):
        adjacency: dict[str, set[str]] = defaultdict(set)
        edge_similarity: dict[tuple[str, str], float] = {}
        exact_titles_by_id = {
            candidate_id: exact_title for candidate_id, _tokens, exact_title in entries
        }
        for index, (left_id, left_tokens, left_title) in enumerate(entries):
            for right_id, right_tokens, right_title in entries[index + 1 :]:
                union = left_tokens | right_tokens
                similarity = len(left_tokens & right_tokens) / len(union) if union else 0.0
                exact_match = left_title == right_title
                near_match = (
                    len(left_tokens) >= 4
                    and len(right_tokens) >= 4
                    and similarity >= near_threshold
                )
                if not exact_match and not near_match:
                    continue
                pair = tuple(sorted((left_id, right_id)))
                adjacency[left_id].add(right_id)
                adjacency[right_id].add(left_id)
                edge_similarity[pair] = 1.0 if exact_match else similarity

        visited: set[str] = set()
        for start in sorted(adjacency):
            if start in visited:
                continue
            pending = [start]
            component: set[str] = set()
            while pending:
                candidate_id = pending.pop()
                if candidate_id in component:
                    continue
                component.add(candidate_id)
                pending.extend(sorted(adjacency[candidate_id] - component, reverse=True))
            visited.update(component)
            ids = sorted(component)
            if len(ids) < 2:
                continue
            qualifying_edges = [
                {
                    "candidate_ids": list(pair),
                    "similarity": round(similarity, 6),
                }
                for pair, similarity in sorted(edge_similarity.items())
                if pair[0] in component and pair[1] in component
            ]
            exact_title = len({exact_titles_by_id[candidate_id] for candidate_id in ids}) == 1
            similarity = min(edge["similarity"] for edge in qualifying_edges)
            group_id = "duplicate:" + hashlib.sha256(canonical_json_bytes(ids)).hexdigest()[:20]
            duplicates.append(
                {
                    "schema_version": "duplicate_group_v1",
                    "group_id": group_id,
                    "kind": "exact_title_match" if exact_title else "near_title_match",
                    "candidate_ids": ids,
                    "source_candidate": None,
                    "exact": exact_title,
                    "similarity": similarity,
                    "evidence": [
                        {
                            "method": "normalized_title_equality_or_token_jaccard_components",
                            "exact_normalization": "unicode_casefold_and_whitespace",
                            "threshold": near_threshold,
                            "qualifying_edges": qualifying_edges,
                        }
                    ],
                }
            )
    duplicates.sort(key=lambda row: row["group_id"])
    return duplicates


def _multi_pr_lineage(candidates: list[dict[str, Any]]) -> None:
    by_issue: dict[str, list[str]] = defaultdict(list)
    for candidate in candidates:
        for issue in candidate.get("linked_issues") or []:
            issue_id = str(issue.get("id") or "")
            if issue_id:
                by_issue[issue_id].append(candidate["candidate_id"])
    by_id = {row["candidate_id"]: row for row in candidates}
    for issue_id, candidate_ids in by_issue.items():
        unique = sorted(set(candidate_ids))
        if len(unique) < 2:
            continue
        for source_id in unique:
            edges = by_id[source_id]["lineage"]["multi_pr_links"]
            for target_id in unique:
                if target_id == source_id:
                    continue
                edges.append(
                    {
                        "relation": "shares_formal_issue",
                        "target_candidate_id": target_id,
                        "evidence_ref": f"github:issue:{issue_id}",
                    }
                )


def _baseline_counts(
    repositories: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    existing_rows: list[dict[str, Any]],
    duplicates: list[dict[str, Any]],
) -> dict[str, int]:
    active_repositories = [
        row for row in repositories if not row.get("archived") and not row.get("disabled")
    ]
    merged_non_dependency = [
        row
        for row in candidates
        if row["source_state"] == "merged" and row["task_family"] != "dependency"
    ]
    linked_merged = [row for row in merged_non_dependency if row.get("linked_issues")]
    closed_unmerged = [row for row in candidates if row["source_state"] == "closed"]
    closed_unmerged = [row for row in closed_unmerged if row["task_family"] != "dependency"]
    unique_existing = {
        (
            str(row.get("resolved_repository_name_with_owner") or row["repo"]).casefold(),
            row["pr_number"],
        )
        for row in existing_rows
    }
    exact_current = [
        row
        for row in duplicates
        if row["kind"] == "current_corpus_duplicate" and row.get("exact")
    ]
    return {
        "public_repository_count": len(repositories),
        "active_public_repository_count": len(active_repositories),
        "merged_non_dependency_pr_count": len(merged_non_dependency),
        "formally_issue_linked_merged_pr_count": len(linked_merged),
        "closed_unmerged_pr_count": len(closed_unmerged),
        "existing_prometheus_row_count": len(existing_rows),
        "existing_unique_pr_count": len(unique_existing),
        "exact_current_duplicate_candidate_count": len(exact_current),
    }


def _post_cutoff_evidence(
    metric: str,
    cutoff: datetime,
    repositories: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if metric in {"public_repository_count", "active_public_repository_count"}:
        return [
            {"repository_id": row["repository_id"], "created_at": row.get("created_at")}
            for row in repositories
            if (
                metric != "active_public_repository_count"
                or (not row.get("archived") and not row.get("disabled"))
            )
            if _parse_time(row.get("created_at")) and _parse_time(row.get("created_at")) > cutoff
        ]
    if metric in {
        "merged_non_dependency_pr_count",
        "formally_issue_linked_merged_pr_count",
    }:
        return [
            {"candidate_id": row["candidate_id"], "merged_at": row.get("merged_at")}
            for row in candidates
            if row["source_state"] == "merged"
            and row["task_family"] != "dependency"
            and (metric != "formally_issue_linked_merged_pr_count" or row.get("linked_issues"))
            and _parse_time(row.get("merged_at"))
            and _parse_time(row.get("merged_at")) > cutoff
        ]
    if metric == "closed_unmerged_pr_count":
        return [
            {"candidate_id": row["candidate_id"], "closed_at": row.get("closed_at")}
            for row in candidates
            if row["source_state"] == "closed"
            and row["task_family"] != "dependency"
            and _parse_time(row.get("closed_at"))
            and _parse_time(row.get("closed_at")) > cutoff
        ]
    return []


def build_baseline_report(
    policy: dict[str, Any],
    actual: dict[str, int],
    repositories: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    baseline = policy.get("baseline") or {}
    expected = baseline.get("expected_counts") or {}
    cutoff = _parse_time(baseline.get("queried_at"))
    if cutoff is None:
        raise ValueError("Policy baseline.queried_at must be a valid timestamp")
    manual: dict[str, dict[str, Any]] = {}
    for item in baseline.get("drift_explanations") or []:
        if not isinstance(item, dict) or not item.get("metric"):
            continue
        metric = str(item["metric"])
        if metric in manual:
            raise ValueError(f"Duplicate baseline drift explanation metric {metric}")
        manual[metric] = item
    comparisons: list[dict[str, Any]] = []
    for metric, expected_value in expected.items():
        if metric not in actual:
            raise ValueError(f"Unknown baseline metric {metric}")
        expected_int = int(expected_value)
        actual_value = int(actual[metric])
        delta = actual_value - expected_int
        evidence = _post_cutoff_evidence(metric, cutoff, repositories, candidates)
        automatic_event_count = len(evidence)
        explained = delta == 0 or (delta > 0 and automatic_event_count == delta)
        explanation = "unchanged_from_baseline" if delta == 0 else "post_baseline_source_events"
        if not explained and metric in manual:
            entry = manual[metric]
            refs = entry.get("evidence_refs") or []
            declared_countervailing_delta = entry.get("countervailing_delta")
            if declared_countervailing_delta != delta - automatic_event_count:
                raise ValueError(
                    f"Baseline drift explanation for {metric} declares countervailing_delta "
                    f"{declared_countervailing_delta!r}, expected {delta - automatic_event_count}"
                )
            if refs:
                explained = True
                explanation = str(entry.get("reason_code") or "manual_evidence_backed_explanation")
                evidence.extend({"evidence_ref": str(ref)} for ref in refs)
        comparisons.append(
            {
                "metric": metric,
                "expected": expected_int,
                "actual": actual_value,
                "delta": delta,
                "post_cutoff_event_count": automatic_event_count,
                "countervailing_delta": delta - automatic_event_count,
                "explained": explained,
                "explanation": explanation if explained else "unexplained_drift",
                "evidence": evidence,
            }
        )
    return {
        "schema_version": "eligibility_baseline_report_v1",
        "baseline_queried_at": baseline.get("queried_at"),
        "snapshot_collected_at": policy.get("snapshot_collected_at"),
        "comparisons": comparisons,
        "complete": all(row["explained"] for row in comparisons),
    }


def _repository_row(raw: dict[str, Any]) -> dict[str, Any]:
    row = {
        "schema_version": REPOSITORY_SCHEMA_VERSION,
        "provider": "github",
        "repository_id": raw.get("id"),
        "repository_database_id": raw.get("database_id"),
        "name_with_owner": raw.get("name_with_owner"),
        "owner_login": raw.get("owner_login"),
        "owner_kind": raw.get("owner_kind"),
        "name": raw.get("name"),
        "url": raw.get("url"),
        "visibility": raw.get("visibility"),
        "archived": bool(raw.get("archived")),
        "disabled": bool(raw.get("disabled")),
        "fork": bool(raw.get("fork")),
        "default_branch": raw.get("default_branch"),
        "created_at": raw.get("created_at"),
        "updated_at": raw.get("updated_at"),
        "pushed_at": raw.get("pushed_at"),
        "license": raw.get("license") or {},
        "pull_request_total_count": int(raw.get("pull_request_total_count") or 0),
        "aliases": [],
    }
    source_payload = {key: value for key, value in raw.items() if key != "source_hash"}
    row["source_hash"] = sha256_json(source_payload)
    return row


def _apply_repository_aliases(
    policy: dict[str, Any],
    repositories: list[dict[str, Any]],
) -> dict[str, str]:
    by_id = {str(row["repository_id"]): row for row in repositories}
    current_names = {
        str(row["name_with_owner"]).casefold(): str(row["repository_id"])
        for row in repositories
    }
    alias_map = {name: name for name in current_names}
    seen_aliases: set[str] = set()
    for raw in policy.get("repository_aliases") or []:
        alias = str(raw.get("alias") or "").strip()
        alias_key = alias.casefold()
        repository_id = str(raw.get("repository_id") or "").strip()
        canonical = str(raw.get("canonical_name_with_owner") or "").strip()
        evidence_refs = sorted({str(item) for item in raw.get("evidence_refs") or []})
        if not alias or alias_key in seen_aliases:
            raise ValueError(f"Missing or duplicate repository alias {alias!r}")
        seen_aliases.add(alias_key)
        repository = by_id.get(repository_id)
        if repository is None:
            raise ValueError(f"Repository alias {alias} references unknown ID {repository_id}")
        actual_canonical = str(repository["name_with_owner"])
        if canonical.casefold() != actual_canonical.casefold():
            raise ValueError(
                f"Repository alias {alias} canonical name is stale: "
                f"declared {canonical}, snapshot has {actual_canonical}"
            )
        current_owner = current_names.get(alias_key)
        if current_owner is not None and current_owner != repository_id:
            raise ValueError(f"Repository alias {alias} collides with a different current repository")
        alias_map[alias_key] = actual_canonical.casefold()
        repository["aliases"].append(
            {
                "name_with_owner": alias,
                "evidence_refs": evidence_refs,
            }
        )
    for repository in repositories:
        repository["aliases"].sort(key=lambda row: row["name_with_owner"].casefold())
    return alias_map


def build_eligibility_artifacts(
    snapshot: dict[str, Any],
    policy: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    """Return all deterministic ledger artifacts as Python values."""
    if snapshot.get("schema_version") != "source_inventory_v1":
        raise ValueError("Unsupported source inventory schema")
    if not (snapshot.get("collection") or {}).get("complete"):
        raise ValueError("Refusing to build a ledger from an incomplete snapshot")
    if policy.get("schema_version") != "eligibility_policy_v1":
        raise ValueError("Unsupported eligibility policy schema")

    snapshot_owners = snapshot.get("owners") or []
    policy_owners = policy.get("owners") or []
    snapshot_owner_keys = {
        (str(row.get("kind") or ""), str(row.get("login") or "").casefold())
        for row in snapshot_owners
        if isinstance(row, dict)
    }
    policy_owner_keys = {
        (str(row.get("kind") or ""), str(row.get("login") or "").casefold())
        for row in policy_owners
        if isinstance(row, dict)
    }
    if (
        len(snapshot_owner_keys) != len(snapshot_owners)
        or len(policy_owner_keys) != len(policy_owners)
        or snapshot_owner_keys != policy_owner_keys
    ):
        raise ValueError("Source snapshot owners do not match eligibility policy owners")

    declared_snapshot_hash = snapshot.get("snapshot_sha256")
    snapshot_without_hash = dict(snapshot)
    snapshot_without_hash.pop("snapshot_sha256", None)
    actual_snapshot_hash = sha256_json(snapshot_without_hash)
    if not declared_snapshot_hash or declared_snapshot_hash != actual_snapshot_hash:
        raise ValueError(
            "Source snapshot sha256 does not match its canonical content "
            f"(declared={declared_snapshot_hash}, actual={actual_snapshot_hash})"
        )

    collection = snapshot.get("collection") or {}
    pages = snapshot.get("pages") or []
    if len(pages) != int(collection.get("page_count", -1)):
        raise ValueError("Source snapshot pagination evidence count does not conserve")

    repositories = [_repository_row(row) for row in (snapshot.get("repositories") or [])]
    repository_by_id = {str(row["repository_id"]): row for row in repositories}
    if len(repository_by_id) != len(repositories):
        raise ValueError("Repository inventory contains missing or duplicate immutable IDs")
    repository_aliases = _apply_repository_aliases(policy, repositories)

    raw_prs = snapshot.get("pull_requests") or []
    source_ids = [candidate_id(row) for row in raw_prs]
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("Source snapshot contains duplicate pull-request IDs")
    if len(raw_prs) != int(collection.get("pull_request_count", -1)):
        raise ValueError("Source snapshot pull-request count does not conserve")
    if len(repositories) != int(collection.get("repository_count", -1)):
        raise ValueError("Source snapshot repository count does not conserve")

    pull_request_counts: dict[str, int] = defaultdict(int)
    for raw in raw_prs:
        pull_request_counts[str(raw.get("repository_id") or "")] += 1
    for repository in repositories:
        repository_id = str(repository["repository_id"])
        declared_count = int(repository["pull_request_total_count"])
        actual_count = pull_request_counts.get(repository_id, 0)
        if declared_count != actual_count:
            raise ValueError(
                "Repository pull-request count does not conserve for "
                f"{repository['name_with_owner']}: declared {declared_count}, actual {actual_count}"
            )

    by_repo_number = {
        (str(row.get("repository_name_with_owner") or "").casefold(), int(row["number"])): candidate_id(row)
        for row in raw_prs
    }
    if len(by_repo_number) != len(raw_prs):
        raise ValueError("Source snapshot contains duplicate repository/PR aliases")
    for (repository_name, number), source_id in list(by_repo_number.items()):
        for alias, canonical in repository_aliases.items():
            if canonical == repository_name:
                by_repo_number[(alias, number)] = source_id
    overrides = _override_map(policy)
    stale_overrides = sorted(set(overrides) - set(source_ids))
    if stale_overrides:
        raise ValueError(f"Eligibility policy has stale overrides: {stale_overrides}")

    existing_rows = _load_existing_rows(repo_root)
    existing_by_source: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in existing_rows:
        repo_key = row["repo"].casefold()
        resolved_repo = repository_aliases.get(repo_key, repo_key)
        row["resolved_repository_name_with_owner"] = resolved_repo
        existing_by_source[(resolved_repo, row["pr_number"])].append(row)

    candidates: list[dict[str, Any]] = []
    for raw in raw_prs:
        cid = candidate_id(raw)
        repository = repository_by_id.get(str(raw.get("repository_id")))
        if repository is None:
            raise ValueError(f"Candidate {cid} references an unknown repository")
        task_family, task_basis = infer_task_family(raw, policy)
        state, reason_codes = _automatic_state(raw, task_family)
        if cid in overrides:
            override = overrides[cid]
            state = str(override["state"])
            reason_codes = [str(item) for item in override["reason_codes"]]
            if state == "included_positive" and str(raw.get("state") or "") != "merged":
                raise ValueError(f"Override cannot include non-merged candidate as positive: {cid}")
            if state == "included_negative" and str(raw.get("state") or "") == "open":
                raise ValueError(f"Override cannot include open candidate as negative: {cid}")
            if state == "watchlist_open" and str(raw.get("state") or "") != "open":
                raise ValueError(f"Override cannot watchlist a terminal candidate: {cid}")
        repo_alias = str(raw.get("repository_name_with_owner") or "")
        number = int(raw["number"])
        current_refs = existing_by_source.get((repo_alias.casefold(), number), [])
        candidate = {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "candidate_id": cid,
            "provider": "github",
            "repository_id": raw.get("repository_id"),
            "repository_database_id": raw.get("repository_database_id"),
            "repository_name_with_owner": repo_alias,
            "pull_request_id": raw.get("id"),
            "pull_request_database_id": raw.get("database_id"),
            "pull_request_number": number,
            "url": raw.get("url"),
            "source_state": raw.get("state"),
            "draft": bool(raw.get("draft")),
            "title": raw.get("title") or "",
            "body_sha256": raw.get("body_sha256"),
            "created_at": raw.get("created_at"),
            "updated_at": raw.get("updated_at"),
            "closed_at": raw.get("closed_at"),
            "merged_at": raw.get("merged_at"),
            "base_oid": raw.get("base_oid"),
            "head_oid": raw.get("head_oid"),
            "merge_commit_oid": raw.get("merge_commit_oid"),
            "change_summary": {
                "additions": raw.get("additions"),
                "deletions": raw.get("deletions"),
                "changed_files": raw.get("changed_files"),
            },
            "author": raw.get("author") or {},
            "labels": raw.get("labels") or [],
            "linked_issues": raw.get("linked_issues") or [],
            "state": state,
            "primary_reason": reason_codes[0],
            "reason_codes": sorted(set(reason_codes)),
            "task_family": task_family,
            "task_family_basis": task_basis,
            "lineage": _lineage(raw, by_repo_number),
            "quality": assess_quality(raw, repository),
            "existing_dataset_refs": current_refs,
            "duplicate_group_ids": [],
            "source_hash": raw.get("source_hash"),
            "policy_version": policy.get("policy_version"),
            "classification": {
                "method": "explicit_override" if cid in overrides else "deterministic_rules",
                "evidence_refs": (
                    [str(item) for item in overrides[cid].get("evidence_refs") or []]
                    if cid in overrides
                    else [_source_ref(raw)]
                ),
            },
        }
        candidates.append(candidate)
    candidates.sort(key=lambda row: row["candidate_id"])
    _multi_pr_lineage(candidates)

    duplicates = _duplicate_records(
        candidates,
        existing_rows,
        by_repo_number,
        near_threshold=float(policy.get("near_duplicate_threshold") or 0.9),
    )
    by_candidate_duplicate_groups: dict[str, list[str]] = defaultdict(list)
    for duplicate in duplicates:
        for cid in duplicate.get("candidate_ids") or []:
            by_candidate_duplicate_groups[cid].append(duplicate["group_id"])
    for candidate in candidates:
        candidate["duplicate_group_ids"] = sorted(by_candidate_duplicate_groups[candidate["candidate_id"]])

    policy_for_report = dict(policy)
    policy_for_report["snapshot_collected_at"] = snapshot.get("collected_at")
    actual_counts = _baseline_counts(repositories, candidates, existing_rows, duplicates)
    baseline_report = build_baseline_report(
        policy_for_report,
        actual_counts,
        repositories,
        candidates,
    )
    orphan_existing = sorted(
        {
            f"{row['repo']}#{row['pr_number']}"
            for row in existing_rows
            if (
                str(row["resolved_repository_name_with_owner"]).casefold(),
                row["pr_number"],
            )
            not in by_repo_number
        }
    )
    baseline_report["orphan_existing_dataset_candidates"] = orphan_existing

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "provider": "github",
        "snapshot_sha256": snapshot.get("snapshot_sha256"),
        "snapshot_collected_at": snapshot.get("collected_at"),
        "collector_version": snapshot.get("collector_version"),
        "policy_version": policy.get("policy_version"),
        "counts": {
            **actual_counts,
            "repository_record_count": len(repositories),
            "candidate_record_count": len(candidates),
            "duplicate_group_count": len(duplicates),
            "state_counts": {
                state: sum(1 for row in candidates if row["state"] == state)
                for state in sorted(LEDGER_STATES)
            },
        },
        "pagination": {
            "page_count": len(snapshot.get("pages") or []),
            "page_hashes": [str(row.get("response_sha256")) for row in snapshot.get("pages") or []],
            "complete": bool((snapshot.get("collection") or {}).get("complete")),
        },
        "baseline_report_complete": bool(baseline_report["complete"]),
        "orphan_existing_dataset_candidates": orphan_existing,
    }
    return {
        "repositories": repositories,
        "candidates": candidates,
        "duplicates": duplicates,
        "baseline_report": baseline_report,
        "manifest": manifest,
    }


def render_jsonl(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(row) + b"\n" for row in rows)


def render_json(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8") + b"\n"


def render_artifacts(artifacts: dict[str, Any]) -> dict[str, bytes]:
    rendered = {
        "repositories.jsonl": render_jsonl(artifacts["repositories"]),
        "candidates.jsonl": render_jsonl(artifacts["candidates"]),
        "duplicates.jsonl": render_jsonl(artifacts["duplicates"]),
        "baseline-report.json": render_json(artifacts["baseline_report"]),
    }
    manifest = dict(artifacts["manifest"])
    manifest["files"] = {
        name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        for name, data in sorted(rendered.items())
    }
    rendered["manifest.json"] = render_json(manifest)
    return rendered
