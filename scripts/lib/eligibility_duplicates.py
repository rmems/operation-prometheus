"""Duplicate-group detection: corpus rows, shared head OIDs, and title matches."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any

from .source_inventory import canonical_json_bytes

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


def _title_tokens(title: str) -> set[str]:
    return {
        token
        for token in _TOKEN_RE.findall(title.casefold())
        if token not in _STOP_TOKENS and not token.isdigit()
    }


def _normalized_exact_title(title: str) -> str:
    """Normalize only casing and whitespace for exact-title assertions."""
    return " ".join(title.split()).casefold()


def _current_corpus_duplicates(
    existing_rows: list[dict[str, Any]],
    by_repo_number: dict[tuple[str, int], str],
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
    return duplicates


def _head_oid_groups(candidates: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_head: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        head_oid = str(candidate.get("head_oid") or "")
        if head_oid:
            by_head[head_oid].append(candidate)
    return by_head


def _shared_head_group(head_oid: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if len(rows) < 2:
        return None
    ids = sorted(str(row["candidate_id"]) for row in rows)
    base_oids = sorted(
        {str(row.get("base_oid")) for row in rows if str(row.get("base_oid") or "")}
    )
    missing_base_candidate_ids = sorted(
        str(row["candidate_id"]) for row in rows if not str(row.get("base_oid") or "")
    )
    exact = len(base_oids) == 1 and not missing_base_candidate_ids
    group_id = "duplicate:" + hashlib.sha256(head_oid.encode()).hexdigest()[:20]
    return {
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


def _shared_head_duplicates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_head = _head_oid_groups(candidates)
    return [
        group
        for head_oid, rows in sorted(by_head.items())
        if (group := _shared_head_group(head_oid, rows)) is not None
    ]


def _title_entries_by_repository(
    candidates: list[dict[str, Any]],
) -> dict[str, list[tuple[str, set[str], str]]]:
    by_repository: dict[str, list[tuple[str, set[str], str]]] = defaultdict(list)
    for row in candidates:
        tokens = _title_tokens(row["title"])
        exact_title = _normalized_exact_title(str(row.get("title") or ""))
        if exact_title:
            by_repository[row["repository_name_with_owner"].casefold()].append(
                (row["candidate_id"], tokens, exact_title)
            )
    return by_repository


def _is_near_match(
    left_tokens: set[str],
    right_tokens: set[str],
    similarity: float,
    near_threshold: float,
) -> bool:
    return (
        len(left_tokens) >= 4
        and len(right_tokens) >= 4
        and similarity >= near_threshold
    )


def _title_adjacency(
    entries: list[tuple[str, set[str], str]],
    near_threshold: float,
) -> tuple[dict[str, set[str]], dict[tuple[str, str], float]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    edge_similarity: dict[tuple[str, str], float] = {}
    for index, (left_id, left_tokens, left_title) in enumerate(entries):
        for right_id, right_tokens, right_title in entries[index + 1 :]:
            union = left_tokens | right_tokens
            similarity = len(left_tokens & right_tokens) / len(union) if union else 0.0
            exact_match = left_title == right_title
            near_match = _is_near_match(left_tokens, right_tokens, similarity, near_threshold)
            if not exact_match and not near_match:
                continue
            pair = tuple(sorted((left_id, right_id)))
            adjacency[left_id].add(right_id)
            adjacency[right_id].add(left_id)
            edge_similarity[pair] = 1.0 if exact_match else similarity
    return adjacency, edge_similarity


def _component_from(
    start: str,
    adjacency: dict[str, set[str]],
    visited: set[str],
) -> set[str]:
    component: set[str] = set()
    pending = [start]
    while pending:
        current = pending.pop()
        if current in component:
            continue
        component.add(current)
        pending.extend(sorted(adjacency[current] - component, reverse=True))
    visited.update(component)
    return component


def _connected_components(adjacency: dict[str, set[str]]) -> list[set[str]]:
    visited: set[str] = set()
    return [
        _component_from(start, adjacency, visited)
        for start in sorted(adjacency)
        if start not in visited
    ]


def _title_duplicate_group(
    component: set[str],
    edge_similarity: dict[tuple[str, str], float],
    exact_titles_by_id: dict[str, str],
    near_threshold: float,
) -> dict[str, Any] | None:
    ids = sorted(component)
    if len(ids) < 2:
        return None
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
    return {
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


def _title_match_duplicates(
    candidates: list[dict[str, Any]],
    near_threshold: float,
) -> list[dict[str, Any]]:
    duplicates: list[dict[str, Any]] = []
    by_repository = _title_entries_by_repository(candidates)
    for _repository, entries in sorted(by_repository.items()):
        adjacency, edge_similarity = _title_adjacency(entries, near_threshold)
        exact_titles_by_id = {
            candidate_id: exact_title for candidate_id, _tokens, exact_title in entries
        }
        for component in _connected_components(adjacency):
            group = _title_duplicate_group(
                component, edge_similarity, exact_titles_by_id, near_threshold
            )
            if group is not None:
                duplicates.append(group)
    return duplicates


def _duplicate_records(
    candidates: list[dict[str, Any]],
    existing_rows: list[dict[str, Any]],
    by_repo_number: dict[tuple[str, int], str],
    *,
    near_threshold: float,
) -> list[dict[str, Any]]:
    duplicates = [
        *_current_corpus_duplicates(existing_rows, by_repo_number),
        *_shared_head_duplicates(candidates),
        *_title_match_duplicates(candidates, near_threshold),
    ]
    duplicates.sort(key=lambda row: row["group_id"])
    return duplicates
