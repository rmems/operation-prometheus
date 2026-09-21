# Local-model admission

Before a locally served model (for example an Ollama-served Hermes weight) may
be used as a trajectory provider, `scripts/verify_local_model_admission.py`
must admit it. The gate is fail-closed: every candidate is classified
`accepted`, `quarantined` (evidence incomplete), or `rejected` (evidence
contradictory) with explicit reason codes.

Each accepted candidate binds:

- exact model name and Ollama manifest digest;
- quantization level (matched against the probe's `show` details);
- runtime (`ollama`) and a loopback-only endpoint
  (`127.0.0.1`, `::1`, `localhost`);
- declared license resolved against frozen rights evidence (SPDX id or
  `LicenseRef-*` with a matching terms text digest — never guessed);
- a sanitized provider configuration (no secret-looking keys, no remote
  endpoints) with explicit `no_cloud: true` evidence;
- the probe timestamp and SHA-256 digests of every frozen input.

Quarantined and rejected rows keep their bound evidence and reason codes; a
quarantine is not a deletion. The report (`local_model_admission_v1`,
`schemas/local_model_admission.schema.json`) carries `license_families`,
`evidence_digests`, `input_digests`, and `bundle_errors` so consumers can
verify closure deterministically and offline.

## Run (offline, recorded probe — used by CI)

```bash
python scripts/verify_local_model_admission.py \
  --admissions <candidates.jsonl> \
  --rights <rights.json> \
  --probe <ollama_probe.json> \
  --out /tmp/local-model-admission.json
```

Exit status 0 means the report is closed (all candidates accepted). Exit 1
means evaluation completed but at least one candidate was quarantined or
rejected, or the inputs manifest disagreed. Exit 2 is an input/usage error.

`--inputs-manifest` optionally binds each frozen input file by SHA-256. `--check`
compares an existing `--out` instead of rewriting it. `--out` may not collide
with any input file (symlinks and hard links included).

## Live probe (loopback only)

```bash
python scripts/verify_local_model_admission.py \
  --admissions <candidates.jsonl> --rights <rights.json> \
  --live [--endpoint http://127.0.0.1:11434] --out <report.json>
```

`--live` queries `/api/tags` and `/api/show` on the given endpoint and refuses
any non-loopback address. It performs no model pulls, no GPU work, and no
network access beyond the loopback daemon.

## Reason codes

Rejection (contradictory evidence): `candidate_not_object`, `model_missing`,
`rights_conflict`, `terms_digest_mismatch`, `probe_digest_mismatch`,
`quantization_mismatch`, `runtime_unsupported`, `endpoint_not_loopback`,
`provider_config_unsanitized`, `cloud_endpoint_detected`.

Quarantine (incomplete evidence): `rights_evidence_missing`,
`license_missing`, `license_unknown`, `terms_digest_missing`,
`probe_evidence_missing`, `probe_endpoint_mismatch`, `digest_missing`,
`quantization_missing`, `runtime_missing`, `endpoint_missing`,
`endpoint_invalid`, `provider_config_missing`, `no_cloud_evidence_missing`,
`probe_timestamp_missing`, `probe_timestamp_invalid`.
