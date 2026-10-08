# Hugging Face export

`scripts/export_hf_dataset.py` turns the committed per-repo JSONL extracts into
a single Hub-ready dataset under `datasets/hf/`:

- `trajectories.jsonl` — all records, sorted by `id`, each carrying an injected
  `source_license` (SPDX expression of the *source* repository, per the data
  policy — the record license travels with the data);
- `README.md` — the Hugging Face dataset card, including the full set of
  represented source licenses (no blanket license claim);
- `manifest.json` — record/repo/bucket counts, sha256, and the license table.

```bash
python scripts/export_hf_dataset.py           # regenerate datasets/hf/
python scripts/export_hf_dataset.py --check   # fail if outputs are stale (CI)
python scripts/export_hf_dataset.py --upload \
    --repo-id <user>/<dataset> --attested <name> [--private]
```

`--upload` requires `huggingface_hub`, `HF_TOKEN` in the environment, and
`--attested` naming whoever ran the pre-publish manual inspection (recorded in
the upload commit message). It creates the dataset repo if needed — but never
flips an existing repo's visibility; if `--private` disagrees with the Hub it
exits instead of publishing. Uploads only the three export files — never
`datasets/raw/` or other gitignored material.

Re-extracts of the same PR across schema versions share a record `id`; the
export dedupes by `id` (later file wins) and rewrites renamed repos via
`REPO_ALIASES` so the corpus stays one row per trajectory.

## Before publishing

Per `docs/data-policy.md`, a manual inspection pass is required before any
generated dataset is published or used for training: confirm no excluded
material (secrets, private configs, weights, chat logs, bot boilerplate) is
present and that trajectories still carry useful engineering signal. The
per-source-repo license identities in `REPO_LICENSES` were verified against
each repo's LICENSE files; update the map when new repos land.
