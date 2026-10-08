#!/usr/bin/env python3
"""Export the committed trajectory corpus as a Hugging Face dataset.

Usage:
    python scripts/export_hf_dataset.py                # write datasets/hf/
    python scripts/export_hf_dataset.py --check        # fail if outputs are stale
    python scripts/export_hf_dataset.py --upload --repo-id <user>/<name> [--private]

The merge step concatenates every committed per-repo JSONL under
``datasets/jsonl/``, injects a per-record ``source_license`` (the license of the
originating repository — see ``docs/data-policy.md``), and emits:

- ``datasets/hf/trajectories.jsonl`` — one record per line, sorted by record id;
- ``datasets/hf/README.md``         — the Hugging Face dataset card;
- ``datasets/hf/manifest.json``     — counts, digests, and the license table.

The card documents the full set of represented source licenses rather than a
single blanket license, per the data policy. ``--upload`` pushes those three
files to a Hub dataset repo; it needs ``huggingface_hub`` installed and
``HF_TOKEN`` in the environment. It never uploads ``datasets/raw/`` artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSONL_DIR = ROOT / "datasets" / "jsonl"
OUT_DIR = ROOT / "datasets" / "hf"
RECORDS_NAME = "trajectories.jsonl"
CARD_NAME = "README.md"
MANIFEST_NAME = "manifest.json"

# SPDX expression for each repo with at least one committed record, verified
# against the source repository's LICENSE files (2026-10). Dual-licensed Rust
# repos use the standard "MIT OR Apache-2.0" convention.
REPO_LICENSES = {
    "Limen-Neural/axon-encoder": "MIT OR Apache-2.0",
    "Limen-Neural/brainstem-daemon": "MIT OR Apache-2.0",
    "Limen-Neural/neuromod": "MIT OR Apache-2.0",
    "Limen-Neural/nir-rs": "MIT OR Apache-2.0",
    "Limen-Neural/synaptic-mesh": "MIT OR Apache-2.0",
    "rmems/LiquidCortex.jl": "MIT OR Apache-2.0",
    "rmems/SpikeStream.jl": "MIT OR Apache-2.0",
    "rmems/Theseus-Quarry": "MIT",
    "rmems/agoge-forger": "Apache-2.0",
    "rmems/corinth-canal": "MIT OR Apache-2.0",
    "rmems/engram-parser": "MIT OR Apache-2.0",
    "rmems/grok-ozempic": "MIT OR Apache-2.0",
    "rmems/kinetic-signals": "MIT OR Apache-2.0",
    "rmems/limbic-critic": "MIT OR Apache-2.0",
    "rmems/myelin-accelerator": "MIT OR Apache-2.0",
    "rmems/silicon-hdl": "MIT OR Apache-2.0",
    "rmems/spike-viz": "Apache-2.0",
    "rmems/synaptic-mesh": "MIT OR Apache-2.0",
    "rmems/thalamic-relay": "MIT OR Apache-2.0",
    "rmems/worktrees-hives": "Apache-2.0",
    "rmems/xai-dissect": "MIT OR Apache-2.0",
}


def load_records() -> list[dict]:
    records = []
    for path in sorted(JSONL_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            repo = rec["repo"]
            license_expr = REPO_LICENSES.get(repo)
            if license_expr is None:
                raise SystemExit(f"{path.name}: no license mapping for {repo}")
            # The record carries the source repo's license, not the tooling's.
            rec["source_license"] = license_expr
            records.append(rec)
    records.sort(key=lambda r: r["id"])
    return records


def records_jsonl(records: list[dict]) -> bytes:
    return "".join(
        json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in records
    ).encode("utf-8")


def _counts(records: list[dict], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in records:
        out[r.get(key) or "unknown"] = out.get(r.get(key) or "unknown", 0) + 1
    return dict(sorted(out.items()))


def build_manifest(records: list[dict], blob: bytes) -> dict:
    return {
        "name": "operation-prometheus-trajectories",
        "generated_at": date.today().isoformat(),
        "generator": "scripts/export_hf_dataset.py",
        "record_count": len(records),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "bytes": len(blob),
        "records_file": RECORDS_NAME,
        "training_use_counts": _counts(records, "training_use"),
        "repo_counts": _counts(records, "repo"),
        "language_counts": _counts(records, "language"),
        "repo_licenses": dict(sorted(REPO_LICENSES.items())),
    }


def build_card(records: list[dict], manifest: dict) -> str:
    repos = manifest["repo_counts"]
    uses = manifest["training_use_counts"]
    langs = manifest["language_counts"]
    repo_rows = "\n".join(
        f"| [{repo}](https://github.com/{repo}) | {n} | {REPO_LICENSES[repo]} |"
        for repo, n in repos.items()
    )
    use_rows = "\n".join(f"| `{k}` | {v} |" for k, v in uses.items())
    license_set = sorted(set(REPO_LICENSES[r] for r in repos))
    lang_list = ", ".join(langs)
    return f"""---
license:
- apache-2.0
- mit
pretty_name: Operation Prometheus trajectories
tags:
- code
- software-engineering
- pull-requests
- code-review
- trajectories
size_categories:
- n<1K
---

# Operation Prometheus — software-engineering trajectories

Pull-request engineering trajectories extracted from public GitHub history by
[operation-prometheus](https://github.com/rmems/operation-prometheus):
issue/review signal → code state → patch → validation → outcome.

- **Records:** {manifest['record_count']}
- **Format:** JSONL (`{RECORDS_NAME}`), schema `pr_trajectory_v0` / `trajectory_v1`
- **Languages:** {lang_list}
- **Generated:** {manifest['generated_at']} · sha256 `{manifest['sha256'][:16]}…`

## Record fields

`id`, `repo`, `pr_number`, `source_urls`, `language`, `domain`, `task_type`,
`before_context`, `patch`, `validation`, `outcome`, `training_use`,
`issue_context`, `review_signals`, `quality_score`, `source_license`.

`training_use` buckets:

| Bucket | Records |
|--------|---------|
{use_rows}

## Source repositories and license / provenance

Each record's `source_license` is the license of its originating repository —
this dataset is **not** under a single blanket license. The export tooling and
schemas are Apache-2.0; that does not relicense source-derived content.
License set represented: {"; ".join(license_set)}.

| Repository | Records | Source license |
|------------|---------|----------------|
{repo_rows}

## Intended use

SFT / process-supervision for coding agents: feature implementation, repair,
validation discipline, and especially **review-to-patch** — responding to human
review comments with corrective commits.

## Exclusions and limitations

Per the [data policy](https://github.com/rmems/operation-prometheus/blob/main/docs/data-policy.md):
no secrets, private configs, model weights, closed-model chat logs, or bot
boilerplate (review bots like Gemini/Codex are retained as signal). Large
patches may be truncated (~96 KiB cap). Solo-maintainer repos: limited
multi-human review. Inspect records before training use.
"""


def write_outputs(check: bool) -> int:
    records = load_records()
    blob = records_jsonl(records)
    manifest = build_manifest(records, blob)
    outputs = {
        OUT_DIR / RECORDS_NAME: blob,
        OUT_DIR / CARD_NAME: build_card(records, manifest).encode("utf-8"),
        OUT_DIR / MANIFEST_NAME: (json.dumps(manifest, indent=1) + "\n").encode("utf-8"),
    }
    stale = []
    for path, content in outputs.items():
        if path.read_bytes() != content if path.exists() else True:
            stale.append(path)
    if check:
        if stale:
            print("stale outputs:", *[str(p.relative_to(ROOT)) for p in stale])
            return 1
        print(f"up to date: {len(records)} records")
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path, content in outputs.items():
        path.write_bytes(content)
        print(f"wrote {path.relative_to(ROOT)}")
    print(f"{len(records)} records across {len(manifest['repo_counts'])} repos")
    return 0


def upload(repo_id: str, private: bool) -> None:
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise SystemExit("HF_TOKEN is not set")
    try:
        from huggingface_hub import HfApi
    except ImportError:
        raise SystemExit("pip install huggingface_hub first")
    api = HfApi(token=token)
    api.create_repo(repo_id, repo_type="dataset", private=private, exist_ok=True)
    api.upload_folder(
        repo_id=repo_id,
        repo_type="dataset",
        folder_path=str(OUT_DIR),
        commit_message="Export operation-prometheus trajectories",
    )
    print(f"uploaded to https://huggingface.co/datasets/{repo_id}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="fail if outputs are stale")
    ap.add_argument("--upload", action="store_true", help="push datasets/hf/ to the Hub")
    ap.add_argument("--repo-id", help="Hub dataset id, e.g. rmems/operation-prometheus-trajectories")
    ap.add_argument("--private", action="store_true", help="create the Hub repo as private")
    args = ap.parse_args()
    rc = write_outputs(check=args.check)
    if rc or args.check:
        return rc
    if args.upload:
        if not args.repo_id:
            ap.error("--upload requires --repo-id")
        upload(args.repo_id, args.private)
    return 0


if __name__ == "__main__":
    sys.exit(main())
