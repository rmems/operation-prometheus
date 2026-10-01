# CI contracts

Operation Prometheus enforces trajectory shape and the Hermes local-agent
boundary in pull-request CI. The jobs are CPU-only and offline: no model
download, Ollama daemon, GPU, network call, or token.

## Pull requests

These jobs run on every PR alongside `lint`, `test`, `validate`,
`status-up-to-date`, and `shared-files-guard`:

- `trajectory-contract` — v0/v1 schemas, fixture round-trips, unique IDs,
  SHA-256 references, license/policy, sourced actors, secrets, private URIs,
  local paths, and nonterminal positives.
- `local-agent-contract` — synthetic Hermes fixtures normalize to deterministic
  trajectory v1.1 records. An accepted admission report must match its
  evidence digest and the run-manifest digest. Independent verifier success
  decides a successful terminal; Hermes `completed=true` does not. Accepted,
  quarantined, and rejected rows are counted. Quarantined and rejected rows
  stay out of the trainable export. Exports are observable-action `messages`
  rows for the merged Agoge consumer, without hidden reasoning, secrets,
  credentials, local paths, private URIs, or cloud fallback.
- `consumer-contract` — sample `messages` and instruction/input/output rows,
  including the observable-action fixture, are loaded through Agoge Forger's
  `normalize_row` with provenance sidecars. No GPU and no model download.

Schema v1 software records need validation evidence: a validation outcome, an
independent verifier outcome, a validation or CI event, or an event
disposition. A bare issue statement and code-state event is rejected.
Research records may omit that array.
