#!/usr/bin/env python3
"""Export the committed trajectory corpus as a Hugging Face dataset.

Usage:
    python scripts/export_hf_dataset.py                # write datasets/hf/
    python scripts/export_hf_dataset.py --check        # fail if outputs are stale
    python scripts/export_hf_dataset.py --upload --repo-id <user>/<name> \
        --attested <name> [--private]

The merge step concatenates every committed per-repo JSONL under
``datasets/jsonl/``, normalizes renamed source repositories (``REPO_ALIASES``),
injects a per-record ``source_license`` (the license of the originating
repository — see ``docs/data-policy.md``), and emits:

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
import re
import sys
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parent.parent
JSONL_DIR = ROOT / "datasets" / "jsonl"
OUT_DIR = ROOT / "datasets" / "hf"
RECORDS_NAME = "trajectories.jsonl"
CARD_NAME = "README.md"
MANIFEST_NAME = "manifest.json"

# Source repos renamed after their extracts were collected; records still carry
# the pre-rename ``repo`` value and ``source_urls``. The export rewrites both so
# the published dataset points at where the code lives now.
REPO_ALIASES = {
    "rmems/limbic-critic": "Limen-Neural/limbic-critic",
    "rmems/myelin-accelerator": "Limen-Neural/myelin-accelerator",
    "rmems/worktrees-hives": "rmems/writ",
}

# SPDX expression for each canonical repo with at least one committed record,
# verified against the source repository's LICENSE files (2026-10). Dual-
# licensed repos use the standard "MIT OR Apache-2.0" convention.
REPO_LICENSES = {
    "Limen-Neural/axon-encoder": "MIT OR Apache-2.0",
    "Limen-Neural/brainstem-daemon": "MIT OR Apache-2.0",
    "Limen-Neural/limbic-critic": "MIT OR Apache-2.0",
    "Limen-Neural/myelin-accelerator": "MIT OR Apache-2.0",
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
    "rmems/silicon-hdl": "MIT OR Apache-2.0",
    "rmems/spike-viz": "Apache-2.0",
    "rmems/thalamic-relay": "MIT OR Apache-2.0",
    "rmems/writ": "Apache-2.0",
    "rmems/xai-dissect": "MIT OR Apache-2.0",
}


def canonical_repo(repo: str) -> str:
    return REPO_ALIASES.get(repo, repo)


def _canonical_url(url: str) -> str:
    for old, new in REPO_ALIASES.items():
        url = re.sub(
            rf"github\.com/{re.escape(old)}(?=[/#?]|$)", f"github.com/{new}", url
        )
    return url


def _jsonl_version(path: Path) -> tuple[str, int]:
    # Order per-repo files by schema version (v0, v1, …) so dedupe keeps the
    # newest extract; unrelated repos sort by name as before.
    m = re.search(r"-v(\d+)\.jsonl$", path.name)
    return (path.name[: m.start()], int(m.group(1))) if m else (path.name, -1)


def _iter_records() -> Iterator[tuple[Path, dict]]:
    for path in sorted(JSONL_DIR.glob("*.jsonl"), key=_jsonl_version):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                yield path, json.loads(line)


def load_records() -> list[dict]:
    # Re-extracts of the same PR across schema versions share an ``id`` (e.g.
    # grok-ozempic #42 in both v0 and v1); the later file wins so the corpus
    # stays one row per trajectory.
    by_id: dict[str, dict] = {}
    for path, rec in _iter_records():
        rec["repo"] = canonical_repo(rec["repo"])
        rec["source_urls"] = [_canonical_url(u) for u in rec.get("source_urls", [])]
        license_expr = REPO_LICENSES.get(rec["repo"])
        if license_expr is None:
            raise SystemExit(f"{path.name}: no license mapping for {rec['repo']}")
        # The record carries the source repo's license, not the tooling's.
        rec["source_license"] = license_expr
        by_id[rec["id"]] = rec  # last (highest -vN) file wins
    return [by_id[k] for k in sorted(by_id)]


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
    # No timestamp: outputs must rebuild byte-identically or --check goes stale
    # every midnight.
    return {
        "name": "operation-prometheus-trajectories",
        "generator": "scripts/export_hf_dataset.py",
        "record_count": len(records),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "bytes": len(blob),
        "records_file": RECORDS_NAME,
        "training_use_counts": _counts(records, "training_use"),
        "repo_counts": _counts(records, "repo"),
        "language_counts": _counts(records, "language"),
        "repo_licenses": {
            repo: REPO_LICENSES[repo] for repo in _counts(records, "repo")
        },
    }


def build_card(records: list[dict], manifest: dict) -> str:
    repos = manifest["repo_counts"]
    use_rows = "\n".join(
        f"| `{k}` | {v} |" for k, v in manifest["training_use_counts"].items()
    )
    repo_rows = "\n".join(
        f"| [{repo}](https://github.com/{repo}) | {n} | {REPO_LICENSES[repo]} |"
        for repo, n in repos.items()
    )
    license_set = sorted(set(REPO_LICENSES[r] for r in repos))
    lang_list = ", ".join(manifest["language_counts"])
    return f"""---
license: other
license_name: mixed-per-record
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
- **sha256:** `{manifest['sha256'][:16]}…`

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
this dataset is **not** under a single blanket license, which is why the card
declares `license: other` / `mixed-per-record` rather than MIT or Apache-2.0
for the whole. The export tooling and schemas are Apache-2.0; that does not
relicense source-derived content.
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


def collect_outputs() -> dict[Path, bytes]:
    records = load_records()
    blob = records_jsonl(records)
    manifest = build_manifest(records, blob)
    return {
        OUT_DIR / RECORDS_NAME: blob,
        OUT_DIR / CARD_NAME: build_card(records, manifest).encode("utf-8"),
        OUT_DIR / MANIFEST_NAME: (json.dumps(manifest, indent=1) + "\n").encode("utf-8"),
    }


def _is_stale(path: Path, content: bytes) -> bool:
    return not path.exists() or path.read_bytes() != content


def _check(outputs: dict[Path, bytes]) -> int:
    stale = [p for p, c in outputs.items() if _is_stale(p, c)]
    if stale:
        print("stale outputs:", *[str(p.relative_to(ROOT)) for p in stale])
        return 1
    print("outputs up to date")
    return 0


def _emit(outputs: dict[Path, bytes]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path, content in outputs.items():
        path.write_bytes(content)
        print(f"wrote {path.relative_to(ROOT)}")


def _hf_api():
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise SystemExit("HF_TOKEN is not set")
    try:
        from huggingface_hub import HfApi
    except ImportError:
        raise SystemExit("pip install huggingface_hub first")
    return HfApi(token=token)


def _ensure_repo(api, repo_id: str, private: bool) -> None:
    api.create_repo(repo_id, repo_type="dataset", private=private, exist_ok=True)
    info = api.repo_info(repo_id, repo_type="dataset")
    if info.private != private:
        raise SystemExit(
            f"{repo_id} already exists with private={info.private}; "
            "create_repo does not change visibility — flip it on the Hub first"
        )


def upload(repo_id: str, private: bool, attested: str | None) -> None:
    # docs/data-policy.md requires a manual inspection pass before publish;
    # --attested records who did it.
    if not attested:
        raise SystemExit(
            "--upload requires --attested '<name>' attesting the manual "
            "inspection pass required by docs/data-policy.md"
        )
    api = _hf_api()
    _ensure_repo(api, repo_id, private)
    message = f"Export operation-prometheus trajectories (inspected by {attested})"
    # one create_commit for all artifacts: atomic (no half-published export)
    # and scoped to the known files, unlike upload_folder.
    from huggingface_hub import CommitOperationAdd

    api.create_commit(
        repo_id=repo_id,
        repo_type="dataset",
        commit_message=message,
        operations=[
            CommitOperationAdd(path_in_repo=name, path_or_fileobj=str(OUT_DIR / name))
            for name in (RECORDS_NAME, CARD_NAME, MANIFEST_NAME)
        ],
    )
    print(f"uploaded to https://huggingface.co/datasets/{repo_id}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="fail if outputs are stale")
    ap.add_argument("--upload", action="store_true", help="push datasets/hf/ to the Hub")
    ap.add_argument("--repo-id", help="Hub dataset id, e.g. rmems/operation-prometheus-trajectories")
    ap.add_argument("--private", action="store_true", help="create the Hub repo as private")
    ap.add_argument("--attested", help="name of whoever ran the pre-publish manual inspection")
    args = ap.parse_args()
    outputs = collect_outputs()
    if args.check:
        return _check(outputs)
    _emit(outputs)
    if args.upload:
        if not args.repo_id:
            ap.error("--upload requires --repo-id")
        if not args.attested:
            ap.error("--upload requires --attested")
        upload(args.repo_id, args.private, args.attested)
    return 0


if __name__ == "__main__":
    sys.exit(main())
