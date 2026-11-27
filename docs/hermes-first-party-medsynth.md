# First-party Hermes session artifacts from medsynth

Operation Prometheus can ingest deliberately recorded Hermes sessions from
medsynth teacher-generation runs as **first-party trajectory artifacts**. This
lane is separate from both PR-mined corpora and external trajectory datasets.

The producer-side contract is owned by medsynth: a teacher batch manifest
carries one rights envelope per written teacher draft, and a Hermes-routed
envelope names `session_file` plus the SHA-256 of the exact
`<key>.session.json` bytes. The session record itself uses the Hermes raw-trace
shape in `schemas/hermes_raw_trace.schema.json`.

## Artifact shape

`schemas/first_party_hermes_trajectory.schema.json` is the canonical artifact
shape. It is deliberately not a v0/v1 PR trajectory and not a medsynth draft
record:

- a medsynth draft record is the generated educational item and stays in
  medsynth's draft lane;
- this artifact is the engineering trace that produced it: ordered prompts,
  visible assistant decisions, tool events, and outputs, with hidden producer
  reasoning stripped;
- the artifact does not claim the draft is correct or admitted. Hermes
  `completed` and `partial` remain producer execution metadata only.

Every artifact binds:

- medsynth batch id and SHA-256 of the exact batch-manifest bytes;
- medsynth draft record id and the rights-envelope SHA-256;
- run, session, task, and raw-trace ids from the session record;
- session filename and exact session-file SHA-256;
- teacher variant, model id, served model when reported, route, serving vendor,
  pin id, pin-entry hash, exact pin entry, and terms citation fields.

The rights-envelope hash is the SHA-256 of the envelope's canonical sorted JSON
representation as emitted by the converter. The verification chain is:

```text
batch manifest bytes
  → rights envelope (hash)
  → session_file + session_sha256
  → exact Hermes session bytes
  → run/session/task/raw-trace identity
```

## Conversion

```bash
python scripts/convert_medsynth_hermes_sessions.py \
  --batch-manifest <medsynth-batch-manifest.json> \
  --session-root <fulfillment-directory> \
  --output datasets/jsonl/medsynth-hermes-teacher-v0.jsonl \
  --report <conversion-report.json>
```

The converter is offline and local-file only. It scans the fulfillment
directory for `*.session.json`, matches envelopes by exact basename and hash,
writes canonical sorted JSONL with LF bytes, and writes a machine-readable
accepted/refused report. It does not call medsynth, Hermes, Merge, DeepSeek, or
any network service.

Event `kind` is structural metadata, not invented evidence: system/user
messages are `prompt`, tool-role messages are `tool_event`, assistant messages
before the final assistant message are `decision`, and the final assistant
message is `output`. The original role and ordinal are preserved.

## Fail-closed refusals

A session never enters the JSONL output when its provenance chain is incomplete
or inconsistent. The report records refusals for cases including:

- a session file with no matching rights envelope;
- an envelope missing session provenance or another required field;
- envelope/pin mismatch, duplicate record or session binding, or pin-entry hash
  mismatch;
- unsafe session filenames, missing files, or session SHA-256 mismatch;
- malformed or schema-invalid Hermes records;
- secret, credential, home-path, or unremoved hidden-reasoning content;
- invalid batch manifests, incomplete teacher pins, non-Hermes teacher routes,
  or empty input.

Raw session files remain outside Git. Small invented fixtures may be committed
for tests. Real converted artifacts may be committed only after the medsynth
pilot produces the actual batch and the resulting JSONL passes strict policy
validation.
