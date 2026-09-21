# Local-model admission

Before a locally served model (for example an Ollama-served Hermes weight) may
be used as a trajectory provider, `scripts/verify_local_model_admission.py`
must admit it. The gate is fail-closed: every candidate is classified
`accepted`, `quarantined` (evidence incomplete), or `rejected` (evidence
contradictory) with explicit reason codes.

`--out` is the canonical **singular** `local_model_admission_v1` decision
report for the single candidate admitted — the exact object downstream
consumers (e.g. #74) hash and validate. The structured shape is locked:
`model: {name, tag, ollama_digest, quantization, upstream_revision}`,
`runtime: {name, version, endpoint}`, `rights: {identifier, terms_source,
terms_sha256}`, `provider: {name: "hermes-agent", config: <sanitized>}`,
`probe: {timestamp, endpoint}`, plus top-level `schema_version`, `decision`,
`reasons`, `cloud_fallback_allowed`, `fallback_evidence`, `input_digests`,
and `evidence_digest`. Each decision binds:

- distinct model name and tag plus the Ollama manifest digest
  (`sha256:` + 64 lowercase hex);
- quantization level (matched against the probe's `show` details) and the
  upstream revision when known;
- runtime name and version plus the canonical loopback endpoint
  (`http://127.0.0.1:<port>`, `http://localhost:<port>`, `http://[::1]:<port>`);
- rights identifier, terms source, and terms-document SHA-256 from frozen
  rights evidence (SPDX id or `LicenseRef-*` with a matching terms text
  digest — never guessed);
- the sanitized provider configuration (strict key allowlist: no secret
  material, no remote endpoints) with explicit `no_cloud: true` and literal
  `cloud_fallback_allowed: false` plus a `fallback_evidence` proof object;
- the validated probe timestamp and SHA-256 digests of every frozen input,
  including the inputs manifest itself;
- `evidence_digest` — SHA-256 of the complete emitted report object
  (minus the digest field itself).

`decision` is `accepted` only when every binding holds; missing or
conflicting identity/rights/endpoint/fallback evidence always yields
`quarantined` or `rejected` with machine-readable `reasons`. The root schema
(`schemas/local_model_admission.schema.json`) validates the singular report
and conditionally constrains `accepted` reports: every mandatory field
non-null and valid, empty `reasons`, literal `cloud_fallback_allowed: false`
with a coherent `fallback_evidence`, required frozen-input digests,
canonical loopback endpoint, and a closed/sanitized provider config.

`--admissions` must contain exactly one candidate; zero or multiple
candidates fail closed with exit 2. `--diagnostics <path>` optionally emits
the aggregate bundle (`closed`, `counts`, `decisions[]`, `license_families`,
`evidence_digests`, `bundle_errors`) alongside the singular report.

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

`--live` (mutually exclusive with `--probe`) queries `/api/version`,
`/api/tags`, and `/api/show` on the given endpoint with environment proxies
disabled and all redirects refused. It performs no model pulls, no GPU work,
and no network access beyond the loopback daemon. Live responses are parsed
with the same strict parser as frozen inputs (duplicate keys, non-finite
numbers such as `1e999`, and non-finite constants rejected).

## Reason codes

Rejection (contradictory evidence): `candidate_not_object`, `model_missing`,
`rights_conflict`, `terms_digest_mismatch`, `probe_digest_conflict`,
`probe_digest_mismatch`, `probe_quantization_mismatch`,
`probe_license_conflict`, `probe_runtime_mismatch`, `runtime_unsupported`,
`endpoint_not_loopback`, `provider_config_unknown_keys`,
`provider_config_invalid`, `provider_config_unsanitized`,
`cloud_endpoint_detected`, `cloud_fallback_not_disproven`.

Quarantine (incomplete evidence): `rights_evidence_missing`,
`license_missing`, `license_unknown`, `terms_digest_missing`,
`terms_source_missing`, `probe_evidence_missing`, `probe_schema_missing`,
`probe_schema_invalid`, `probe_runtime_missing`, `probe_duplicate`,
`probe_endpoint_missing`, `probe_endpoint_mismatch`,
`probe_quantization_missing`, `digest_missing`, `digest_invalid`,
`runtime_missing`, `endpoint_missing`, `endpoint_invalid`,
`provider_config_missing`, `no_cloud_evidence_missing`,
`probe_timestamp_missing`, `probe_timestamp_invalid`,
`probe_timestamp_mismatch`, `model_tag_missing`.

Envelope/integrity: `model_invalid`, `candidate_unknown_fields`,
`candidate_unsanitized`, `foreign_provider_declared`,
`upstream_revision_mismatch`, `inputs_manifest_mismatch`, `bundle_error`,
`no_candidates`.
