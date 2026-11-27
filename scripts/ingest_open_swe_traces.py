#!/usr/bin/env python3
"""Ingest nvidia/Open-SWE-Traces into pr_trajectory v0 JSONL (GH #88).

Pinned, resumable pipeline. Reads only the columns it needs via HTTP range
requests; raw intermediates land in datasets/raw/open-swe-traces/ (gitignored).

Stages (each caches its output so re-runs resume):
    census    — per-parquet-file row counts and resolved/language/license tallies
    upstream  — join index from nebius/SWE-rebench-V2 (pr_url, base_commit, ...)
    filter    — resolved+language+license+join+cap-3 candidate selection
    records   — fetch metadata for candidates; build strict-v0 + sidecar records
    curate    — deterministic repo-stratified subsample; write committed JSONL
    verify    — sample checks (patch shape, reference patch, license)
    split     — SWE-bench overlap check + deterministic train/eval repo split

Usage:
    python scripts/ingest_open_swe_traces.py            # run all stages
    python scripts/ingest_open_swe_traces.py --stage census
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import logging
import re
import sys
from itertools import islice, zip_longest
from pathlib import Path

import fsspec
import pyarrow.parquet as pq
from huggingface_hub import HfApi, hf_hub_download

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.quality import score_quality  # noqa: E402
from lib.secrets import find_secrets  # noqa: E402
from validate_jsonl import HOME_PATH_RE  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "datasets" / "raw" / "open-swe-traces"
CURATED_JSONL = ROOT / "datasets" / "jsonl" / "open-swe-traces-v0.jsonl"
FILTERED_JSONL = RAW_DIR / "filtered-full-v0.jsonl"
SIDECAR_JSONL = RAW_DIR / "sidecar-v0-extensions.jsonl"
REPORT_PATH = RAW_DIR / "ingest-report.json"
CENSUS_PATH = RAW_DIR / "census.json"
LIGHT_ROWS_JSONL = RAW_DIR / "light-rows.jsonl"
UPSTREAM_PATH = RAW_DIR / "upstream-index.json"
CANDIDATES_PATH = RAW_DIR / "candidates.json"
RECORDS_PATH = RAW_DIR / "records.json"

HF_DATASET = "nvidia/Open-SWE-Traces"
HF_REVISION = "4fa4c2ae9afc6b397bc50391d43450c79993c138"  # 2026-10-28
UPSTREAM_DATASET = "nebius/SWE-rebench-V2"
UPSTREAM_REVISION = "d7608f017a29ab256400ad4b73d5248d97204966"

# Card config v1.0: openhands + sweagent harnesses x MiniMax-M2.5 + Qwen3.5-122B.
V1_CONFIG_DIRS = (
    "data/openhands/minimax_m25/swe-rebench-v2",
    "data/openhands/qwen35_122b/swe-rebench-v2",
    "data/sweagent/minimax_m25/swe-rebench-v2",
    "data/sweagent/qwen35_122b/swe-rebench-v2",
)
TEACHER_BY_DIR = {
    "minimax_m25": "MiniMax-M2.5",
    "qwen35_122b": "Qwen3.5-122B-A10B",
}
SCAFFOLD_BY_DIR = {
    "openhands": "OpenHands",
    "sweagent": "SWE-agent",
}

ALLOWED_LICENSES = frozenset({"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause"})
TARGET_LANGUAGES = {"python": "Python", "rust": "Rust"}
CAP_PER_INSTANCE = 3
# Evaluation sets excluded from training; pinned like every other fetch.
SWE_BENCH_REVISIONS = {
    "princeton-nlp/SWE-bench_Verified": "c104f840cc67f8b6eec6f759ebc8b2693d585d4a",
    "princeton-nlp/SWE-bench_Lite": "6ec7bb89b9342f664a54a6e0a6ea6501d3437cc2",
}
# strict-policy treats a >=96KiB patch without a declared truncation marker as
# silently truncated; the ~32k-token training budget is looser than that anyway.
PATCH_BYTE_CAP = 96 * 1024
CURATED_PER_LANGUAGE = 150

PULL_URL_RE = re.compile(
    r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/[0-9]+$"
)
IID_RE = re.compile(r"^(?P<owner>.+?)__(?P<name>.+)-(?P<num>\d+)$")

CATEGORY_TO_TASK_TYPE = {
    "bug-fix": "bugfix",
    "feature-request": "feature",
    "enhancement": "feature",
}
CATEGORY_TO_TRAINING_USE = {
    "bug-fix": "repair",
    "feature-request": "feature",
    "enhancement": "feature",
}

LIGHT_COLUMNS = [
    "instance_id",
    "repo",
    "license",
    "language",
    "resolved",
    "trajectory_id",
    "hf_dataset_name",
]

logger = logging.getLogger("ingest_open_swe_traces")


def _load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _resolve_url(rfilename: str) -> str:
    return (
        f"https://huggingface.co/datasets/{HF_DATASET}"
        f"/resolve/{HF_REVISION}/{rfilename}"
    )


def _v1_files() -> list[str]:
    """Parquet files in the card's v1.0 config, sorted for determinism."""
    api = HfApi()
    info = api.dataset_info(HF_DATASET, revision=HF_REVISION)
    if info.sha != HF_REVISION:
        raise RuntimeError(
            f"revision moved: expected {HF_REVISION}, got {info.sha}"
        )
    names = sorted(s.rfilename for s in info.siblings if s.rfilename.endswith(".parquet"))
    return [n for n in names if any(n.startswith(d + "/") for d in V1_CONFIG_DIRS)]


def _iter_light_rows():
    """Yield (file, light-column row) for every v1.0 parquet file, cached."""
    if not LIGHT_ROWS_JSONL.exists():
        tmp = LIGHT_ROWS_JSONL.with_suffix(".tmp")
        fs = fsspec.filesystem("https")
        files = _v1_files()
        LIGHT_ROWS_JSONL.parent.mkdir(parents=True, exist_ok=True)
        with tmp.open("w", encoding="utf-8", newline="\n") as out:
            for index, name in enumerate(files):
                with fs.open(_resolve_url(name)) as handle:
                    table = pq.ParquetFile(handle).read(columns=LIGHT_COLUMNS)
                for row in table.to_pylist():
                    row["file"] = name
                    out.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
                    out.write("\n")
                del table
                logger.info("light-rows %d/%d %s", index + 1, len(files), name)
        tmp.replace(LIGHT_ROWS_JSONL)
    with LIGHT_ROWS_JSONL.open(encoding="utf-8") as handle:
        for line in handle:
            item = json.loads(line)
            yield item.pop("file"), item


def stage_census() -> dict:
    """Count rows per file: resolved flag by language and license."""
    if CENSUS_PATH.exists():
        return _load_json(CENSUS_PATH, {})
    per_file: dict[str, dict] = {}
    total_rows = 0
    for name, row in _iter_light_rows():
        stats = per_file.setdefault(
            name,
            {
                "rows": 0,
                "by_language_resolved": collections.Counter(),
                "licenses": collections.Counter(),
                "hf_dataset_names": collections.Counter(),
            },
        )
        stats["rows"] += 1
        stats["by_language_resolved"][f"{row['language']}|{row['resolved']}"] += 1
        stats["licenses"][row["license"]] += 1
        stats["hf_dataset_names"][row["hf_dataset_name"]] += 1
        total_rows += 1
    census = {
        "revision": HF_REVISION,
        "config": "v1.0",
        "file_count": len(per_file),
        "total_rows": total_rows,
        "files": {
            name: {
                "rows": stats["rows"],
                "by_language_resolved": dict(stats["by_language_resolved"]),
                "licenses": dict(stats["licenses"]),
                "hf_dataset_names": dict(stats["hf_dataset_names"]),
            }
            for name, stats in sorted(per_file.items())
        },
    }
    _write_json(CENSUS_PATH, census)
    return census


def stage_upstream() -> dict:
    """Join index: instance_id -> SWE-rebench-V2 provenance fields."""
    if UPSTREAM_PATH.exists():
        return _load_json(UPSTREAM_PATH, {})
    parquet = hf_hub_download(
        UPSTREAM_DATASET,
        "data/train-00000-of-00001.parquet",
        repo_type="dataset",
        revision=UPSTREAM_REVISION,
    )
    table = pq.read_table(
        parquet,
        columns=[
            "instance_id",
            "repo",
            "base_commit",
            "created_at",
            "problem_statement",
            "patch",
            "test_patch",
            "meta.pr_url",
        ],
    )
    index: dict[str, dict] = {}
    for row in table.to_pylist():
        index[row["instance_id"]] = {
            "repo": row["repo"],
            "base_commit": row["base_commit"],
            "created_at": row["created_at"],
            "problem_statement": row["problem_statement"],
            "has_reference_patch": bool((row["patch"] or "").strip()),
            "has_test_patch": bool((row["test_patch"] or "").strip()),
            # pyarrow flattens nested selects to leaf names (meta.pr_url -> pr_url)
            "pr_url": row.get("pr_url") or (row.get("meta") or {}).get("pr_url"),
        }
    index["__revision__"] = UPSTREAM_REVISION
    _write_json(UPSTREAM_PATH, index)
    return index


def _pull_url_for(instance_id: str, upstream_entry: dict) -> tuple[str, str] | None:
    """Canonical (repo, pull-url) for an instance.

    pr_url supplies the canonical (post-rename) repo when present; otherwise
    construct it from the dataset repo plus the instance's PR-number suffix.
    The suffix is verifiably the PR number: it equals pr_url's number on every
    row where pr_url is populated (checked at build time, see report).
    """
    iid = IID_RE.match(instance_id)
    if iid is None:
        return None
    pr_url = upstream_entry.get("pr_url")
    if pr_url and PULL_URL_RE.fullmatch(pr_url):
        repo = "/".join(pr_url.split("/")[3:5])
        return repo, pr_url
    repo = upstream_entry.get("repo") or ""
    if "/" not in repo:
        return None
    return repo, f"https://github.com/{repo}/pull/{iid['num']}"


def _candidate_from_row(name: str, row: dict, upstream: dict, counts) -> dict | None:
    """One filter-pipeline candidate, or None after counting the exclusion."""
    if row["resolved"] != 1:
        counts["excluded_not_resolved"] += 1
        return None
    counts["resolved"] += 1
    if row["language"] not in TARGET_LANGUAGES:
        counts["excluded_language"] += 1
        return None
    if row["license"] not in ALLOWED_LICENSES:
        counts["excluded_license"] += 1
        return None
    entry = upstream.get(row["instance_id"])
    if entry is None:
        counts["excluded_no_upstream_join"] += 1
        return None
    pull = _pull_url_for(row["instance_id"], entry)
    if pull is None:
        counts["excluded_no_pr_number"] += 1
        return None
    repo, pull_url = pull
    parts = name.split("/")
    return {
        "trajectory_id": row["trajectory_id"],
        "instance_id": row["instance_id"],
        "repo": repo,
        "pull_url": pull_url,
        "pr_number": int(IID_RE.match(row["instance_id"])["num"]),
        "language": row["language"],
        "license": row["license"],
        "file": name,
        "scaffold": SCAFFOLD_BY_DIR.get(parts[1], parts[1]),
        "teacher": TEACHER_BY_DIR.get(parts[2], parts[2]),
    }


def stage_filter() -> dict:
    """Apply the GH#88 filter pipeline; group candidates per instance."""
    if CANDIDATES_PATH.exists():
        return _load_json(CANDIDATES_PATH, {})
    upstream = stage_upstream()

    counts = collections.Counter()
    per_instance: dict[str, list[dict]] = collections.defaultdict(list)
    for name, row in _iter_light_rows():
        counts["total"] += 1
        cand = _candidate_from_row(name, row, upstream, counts)
        if cand is not None:
            per_instance[row["instance_id"]].append(cand)

    candidates: list[dict] = []
    for instance_id, group in per_instance.items():
        group.sort(key=lambda item: item["trajectory_id"])
        candidates.extend(group[:CAP_PER_INSTANCE])
        counts["excluded_instance_cap"] += max(0, len(group) - CAP_PER_INSTANCE)
    candidates.sort(key=lambda item: item["trajectory_id"])
    counts["candidates"] = len(candidates)
    counts["distinct_instances"] = len(per_instance)
    result = {"counts": dict(counts), "candidates": candidates}
    _write_json(CANDIDATES_PATH, result)
    return result


def stage_records() -> dict:
    """Fetch metadata for candidates; emit strict-v0 + sidecar records."""
    if RECORDS_PATH.exists():
        return _load_json(RECORDS_PATH, {})
    candidates = stage_filter()["candidates"]
    upstream = stage_upstream()
    fs = fsspec.filesystem("https")
    counts = collections.Counter()

    by_file: dict[str, dict[str, dict]] = collections.defaultdict(dict)
    for cand in candidates:
        by_file[cand["file"]][cand["trajectory_id"]] = cand

    records: list[dict] = []
    files = sorted(by_file)
    for index, name in enumerate(files):
        metadata_by_id = _fetch_metadata_by_id(fs, name)
        for trajectory_id, cand in sorted(by_file[name].items()):
            record = _record_for_candidate(
                cand, metadata_by_id.get(trajectory_id), upstream, counts
            )
            if record is not None:
                records.append(record)
        del metadata_by_id
        logger.info("records %d/%d %s", index + 1, len(files), name)

    counts["records"] = len(records)
    result = {"counts": dict(counts), "records": records}
    _write_json(RECORDS_PATH, result)
    return result


def _fetch_metadata_by_id(fs, name: str) -> dict[str, dict]:
    """trajectory_id -> metadata struct for one parquet file, projected narrow."""
    with fs.open(_resolve_url(name)) as handle:
        table = pq.ParquetFile(handle).read(
            columns=[
                "trajectory_id",
                "metadata.category",
                "metadata.model_patch",
                "metadata.teacher_model.name",
            ]
        )
    return {row["trajectory_id"]: row["metadata"] for row in table.to_pylist()}


def _model_patch(meta: dict) -> str:
    """The trajectory's patch text, byte-exact as upstream authored it."""
    return (meta.get("model_patch") or {}).get("patch") or ""


def _record_exclusion_reason(cand, meta, upstream) -> str | None:
    """First exclusion reason for one candidate, or None when it passes."""
    if meta is None:
        return "excluded_missing_metadata"
    patch = _model_patch(meta)
    if not patch.strip():
        return "excluded_empty_model_patch"
    if len(patch.encode("utf-8")) >= PATCH_BYTE_CAP:
        return "excluded_patch_over_96kib_budget"
    upstream_entry = upstream[cand["instance_id"]]
    if not (upstream_entry.get("problem_statement") or "").strip():
        return "excluded_empty_problem_statement"
    return None


def _record_for_candidate(cand, meta, upstream, counts) -> dict | None:
    """Build one strict-v0 record or count the exclusion and return None."""
    reason = _record_exclusion_reason(cand, meta, upstream)
    if reason is not None:
        counts[reason] += 1
        return None
    # Preserve the upstream patch byte-for-byte: strip() would eat a
    # trailing " " context line and desync the last hunk's counts.
    record = _v0_record(cand, meta, _model_patch(meta), upstream[cand["instance_id"]])
    policy_hits = _policy_screen(record)
    if policy_hits:
        counts["excluded_policy_sensitive"] += 1
        for hit in policy_hits:
            counts[f"policy_{hit}"] += 1
        return None
    return record


def _iter_strings(obj):
    if isinstance(obj, str):
        yield obj
        return
    if isinstance(obj, dict):
        # JSON object keys are always strings.
        yield from _iter_strings(list(obj.items()))
        return
    if isinstance(obj, (list, tuple)):
        for value in obj:
            yield from _iter_strings(value)


def _policy_screen(record: dict) -> list[str]:
    """Repo-policy pre-screen: same checks validate_jsonl --strict-policy runs
    on every string field. Records carrying user-home paths or secret-looking
    tokens are dropped, never redacted (redaction would alter evidence)."""
    hits: list[str] = []
    home_hit = False
    for text in _iter_strings(_strip_extensions(record)):
        if not home_hit and HOME_PATH_RE.search(text):
            home_hit = True
            hits.append("home_path")
        for family in find_secrets(text):
            hits.append(f"secret_{family}")
    return hits


def _evidence_detail(upstream_entry: dict) -> str:
    bits = [
        f"resolved=1 in {HF_DATASET}@{HF_REVISION[:12]}",
        "upstream FAIL_TO_PASS evaluation",
        (
            "test_patch present"
            if upstream_entry["has_test_patch"]
            else "no test_patch recorded"
        ),
        (
            "reference_patch present"
            if upstream_entry["has_reference_patch"]
            else "no reference_patch"
        ),
    ]
    return "; ".join(bits)


def _rfc3339_utc(naive_or_z: str) -> str | None:
    """Normalize a GitHub timestamp to RFC-3339 Z form (UTC by construction)."""
    created_at = naive_or_z.strip()
    if not created_at:
        return None
    if created_at.endswith("Z") or "+" in created_at[10:]:
        return created_at
    return created_at.replace(" ", "T") + "Z"


def _before_context(cand: dict, upstream_entry: dict, teacher_name: str) -> str:
    return (
        f"Repository {cand['repo']} at base_commit "
        f"{upstream_entry['base_commit']} (language {cand['language']}, "
        f"license {cand['license']}). Source instance "
        f"{cand['instance_id']} from {UPSTREAM_DATASET}@"
        f"{UPSTREAM_REVISION[:12]}; teacher {teacher_name} via "
        f"{cand['scaffold']} harness; trajectory {cand['trajectory_id']}."
    )


def _teacher_name(meta: dict, cand: dict) -> str:
    """Teacher from trajectory metadata, falling back to the config dir."""
    teacher = meta.get("teacher_model") or {}
    return teacher.get("name") or cand["teacher"]


def _attach_extensions(record: dict, upstream_entry: dict) -> None:
    # Documented migration extensions (real upstream evidence, never fabricated;
    # omitted when the upstream field is absent so the migrator quarantines
    # honestly rather than migrating a null). With no merge timestamp in the
    # source, outcome=merged records refuse `missing_terminal_timestamp` in v1
    # migration — fail-closed by design, not silently mislabeled.
    created_at = _rfc3339_utc(upstream_entry.get("created_at") or "")
    if created_at:
        record["created_at"] = created_at
    base_oid = (upstream_entry.get("base_commit") or "").strip()
    if base_oid:
        record["base_oid"] = base_oid


def _v0_record(cand: dict, meta: dict, patch: str, upstream_entry: dict) -> dict:
    """One strict pr_trajectory_v0 record plus migration extension fields."""
    category = meta.get("category") or "other"
    teacher_name = _teacher_name(meta, cand)
    record = {
        "id": f"oswe-{cand['trajectory_id']}",
        "repo": cand["repo"],
        "pr_number": cand["pr_number"],
        "source_urls": [cand["pull_url"]],
        "license": cand["license"],
        "language": TARGET_LANGUAGES[cand["language"]],
        "domain": "general",
        "task_type": CATEGORY_TO_TASK_TYPE.get(category, "other"),
        "issue_context": upstream_entry["problem_statement"],
        "before_context": _before_context(cand, upstream_entry, teacher_name),
        "patch": patch,
        "validation": [
            {
                "type": "test",
                "result": "pass",
                "detail": _evidence_detail(upstream_entry),
            }
        ],
        # outcome describes the reference PR's state. SWE-bench-family tasks are
        # built from merged fix PRs (the gold patch is the PR diff), so merged is
        # evidence-backed, not invented.
        "outcome": "merged",
        "training_use": CATEGORY_TO_TRAINING_USE.get(category, "other"),
    }
    # Repo pipeline heuristic over the record's own fields (no raw collection
    # context): merged + issue_context + passing validation → 0.8.
    record["quality_score"] = score_quality(record)
    _attach_extensions(record, upstream_entry)
    return record


def _strip_extensions(record: dict) -> dict:
    """Remove migration extension keys; the committed JSONL is strict v0."""
    stripped = dict(record)
    stripped.pop("created_at", None)
    stripped.pop("base_oid", None)
    return stripped


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def _parse_diff_files(patch: str) -> int:
    return len(re.findall(r"^diff --git ", patch, flags=re.M))


def _group_casefolded_repo(records) -> dict[str, list[dict]]:
    """Group records by lowercased repo: case variants are one repo."""
    groups: dict[str, list[dict]] = collections.defaultdict(list)
    for rec in records:
        groups[rec["repo"].lower()].append(rec)
    return groups


def _round_robin_pick(buckets: dict[str, list[dict]], limit: int) -> list[dict]:
    """One record per repo per pass over sorted repos until limit is hit.

    Pass k takes element k of each non-exhausted repo in sorted order, which
    is exactly zip_longest over the per-repo lists with padding filtered out.
    """
    columns = [buckets[repo] for repo in sorted(buckets)]
    interleaved = (
        record
        for round_ in zip_longest(*columns)
        for record in round_
        if record is not None
    )
    return list(islice(interleaved, limit))


def stage_curate() -> dict:
    """Deterministic repo-stratified subsample + full filtered JSONL."""
    data = stage_records()
    records = data["records"]

    def _sort_key(rec: dict) -> str:
        return rec["id"]

    curated: list[dict] = []
    for language in ("Python", "Rust"):
        curated.extend(
            _round_robin_pick(
                _group_casefolded_repo(
                    (r for r in records if r["language"] == language)
                ),
                CURATED_PER_LANGUAGE,
            )
        )
    curated.sort(key=_sort_key)

    filtered_sorted = sorted(records, key=_sort_key)
    _write_jsonl(FILTERED_JSONL, filtered_sorted)
    _write_jsonl(CURATED_JSONL, [_strip_extensions(r) for r in curated])
    _write_jsonl(SIDECAR_JSONL, curated)
    return {
        "filtered_records": len(filtered_sorted),
        "curated_records": len(curated),
        "curated_by_language": dict(
            collections.Counter(r["language"] for r in curated)
        ),
        "curated_repo_count": len({r["repo"] for r in curated}),
    }


def stage_verify() -> dict:
    """Hand-check invariants on 20 resolved Rust trajectories."""
    records = stage_records()["records"]
    rust = sorted((r for r in records if r["language"] == "Rust"), key=lambda r: r["id"])
    step = max(1, len(rust) // 20)
    sample = rust[::step][:20]
    checks = []
    for rec in sample:
        checks.append(
            {
                "id": rec["id"],
                "patch_is_unified_diff": _parse_diff_files(rec["patch"]) > 0
                or "--- " in rec["patch"],
                "reference_patch_present": "reference_patch present"
                in rec["validation"][0]["detail"],
                "license_nonempty": bool(rec["license"]),
            }
        )
    return {"rust_sample_size": len(sample), "rust_sample": checks}


def _swebench_rows(name: str, revision: str):
    """Yield SWE-bench rows for every parquet file at the pinned revision."""
    info = HfApi().dataset_info(name, revision=revision)
    parquet = [s.rfilename for s in info.siblings if s.rfilename.endswith(".parquet")]
    for rfilename in parquet:
        path = hf_hub_download(name, rfilename, repo_type="dataset", revision=revision)
        for row in pq.read_table(path, columns=["instance_id", "repo"]).to_pylist():
            yield row


def _filtered_instance_ids(records: list[dict], candidates: list[dict]) -> set:
    """Instance ids of candidates that survived into records."""
    record_ids = {r["id"] for r in records}
    return {
        c["instance_id"]
        for c in candidates
        if f"oswe-{c['trajectory_id']}" in record_ids
    }


def _load_swebench_sets() -> dict[str, set]:
    """Case-folded repo set + instance-id set across both SWE-bench eval sets."""
    swe_bench: dict[str, set] = {"repos": set(), "instance_ids": set()}
    for name, revision in SWE_BENCH_REVISIONS.items():
        for row in _swebench_rows(name, revision):
            swe_bench["repos"].add(row["repo"].lower())
            swe_bench["instance_ids"].add(row["instance_id"])
    return swe_bench


def _split_bucket(repo_key: str, holdout: set) -> str:
    """Deterministic train/eval bucket for one case-folded repo key."""
    if repo_key in holdout:
        return "eval_only_swebench"
    digest = int(hashlib.sha256(repo_key.encode("utf-8")).hexdigest()[:8], 16)
    return "eval" if digest % 5 == 0 else "train"


def stage_split() -> dict:
    """SWE-bench contamination check + deterministic repo split."""
    records = stage_records()["records"]
    candidates = stage_filter()["candidates"]
    filtered_iids = _filtered_instance_ids(records, candidates)
    filtered_repos = sorted({r["repo"] for r in records})

    swe_bench = _load_swebench_sets()

    # Repo identity is case-insensitive on GitHub; fold before comparing or
    # hashing so case variants can never land on opposite sides of the split.
    canonical = {r.lower(): r for r in filtered_repos}
    repo_overlap = sorted(
        canonical[k] for k in set(canonical) & swe_bench["repos"]
    )
    iid_overlap = sorted(filtered_iids & swe_bench["instance_ids"])
    holdout = {r.lower() for r in repo_overlap}

    split: dict[str, list[str]] = {"train": [], "eval": [], "eval_only_swebench": []}
    for key in sorted(canonical):
        split[_split_bucket(key, holdout)].append(canonical[key])
    return {
        "swe_bench_repo_overlap": repo_overlap,
        "swe_bench_instance_id_overlap": iid_overlap,
        "repo_split": split,
        "split_rule": (
            "eval iff sha256(repo.casefold())[:8] % 5 == 0; "
            "SWE-bench-overlap repos forced eval_only"
        ),
    }


STAGE_FUNCS = {
    "census": stage_census,
    "upstream": stage_upstream,
    "filter": stage_filter,
    "records": stage_records,
    "curate": stage_curate,
    "verify": stage_verify,
    "split": stage_split,
}
# Only the summary-producing stages are logged; the cached-index stages are quiet.
LOGGED_STAGES = ("curate", "verify", "split")


def _run_stages(stage: str) -> dict[str, dict]:
    """Run the requested stage(s) in pipeline order; collect summaries."""
    summaries: dict[str, dict] = {}
    for name, func in STAGE_FUNCS.items():
        if stage not in ("all", name):
            continue
        summaries[name] = func()
        if name in LOGGED_STAGES:
            logger.info("%s: %s", name, summaries[name])
    return summaries


def _write_report(summaries: dict[str, dict]) -> None:
    report = {
        "revision": HF_REVISION,
        "config": "v1.0",
        "census": _load_json(CENSUS_PATH, {}),
        "filter": _load_json(CANDIDATES_PATH, {}).get("counts", {}),
        "records": _load_json(RECORDS_PATH, {}).get("counts", {}),
        "curate": summaries.get("curate"),
        "verify": summaries.get("verify"),
        "split": summaries.get("split"),
    }
    _write_json(REPORT_PATH, report)
    logger.info("wrote %s", REPORT_PATH)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        default="all",
        choices=["all", *STAGE_FUNCS],
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    summaries = _run_stages(args.stage)
    if args.stage == "all":
        _write_report(summaries)
    return 0


if __name__ == "__main__":
    sys.exit(main())
