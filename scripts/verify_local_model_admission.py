#!/usr/bin/env python3
"""Verify local-model admission against frozen rights and probe evidence.

Usage:
    python scripts/verify_local_model_admission.py \\
      --admissions <candidates.jsonl> \\
      --rights <rights.json> \\
      --probe <ollama_probe.json> \\
      [--inputs-manifest <manifest.json>] \\
      --out <report.json> [--check]

Offline by default: every input is a frozen local file. ``--live`` instead
probes a running Ollama daemon, and is restricted to loopback endpoints only
(127.0.0.1, ::1, localhost). Validation is deterministic; exit 0 means every
candidate was accepted, 1 means the report is not closed, 2 means an input
or usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
import urllib.request
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.model_admission import (  # noqa: E402
    build_admission_report,
)
from lib.model_admission_evidence import (  # noqa: E402
    is_loopback_endpoint,
    load_json_strict,
    load_jsonl_strict,
    paths_collide,
    render_report,
    sha256_bytes,
    sha256_or_none,
)

DEFAULT_LIVE_ENDPOINT = "http://127.0.0.1:11434"


def _probe_live(endpoint: str, models: list[str]) -> dict[str, Any]:
    """Query a loopback Ollama daemon (tags + per-model show)."""
    base = endpoint.rstrip("/")
    with urllib.request.urlopen(f"{base}/api/tags", timeout=10) as resp:
        tags = json.loads(resp.read().decode("utf-8"))
    show: dict[str, Any] = {}
    for model in models:
        body = json.dumps({"model": model}).encode("utf-8")
        req = urllib.request.Request(
            f"{base}/api/show",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            show[model] = json.loads(resp.read().decode("utf-8"))
    return {
        "schema_version": "ollama_probe_v1",
        "endpoint": endpoint,
        "probed_at": datetime.now(timezone.utc).isoformat(),
        "models": tags.get("models") if isinstance(tags, dict) else [],
        "show": show,
    }


def _inputs_manifest_errors(
    manifest: Any, digests: dict[str, str]
) -> list[str]:
    if not isinstance(manifest, dict):
        return ["inputs manifest is not a JSON object"]
    files = manifest.get("files")
    if not isinstance(files, dict):
        return ["inputs manifest has no files object"]
    errors: list[str] = []
    for name, digest in digests.items():
        entry = files.get(name)
        if not isinstance(entry, dict) or sha256_or_none(entry.get("sha256")) is None:
            errors.append(f"inputs manifest missing sha256 for {name}")
        elif entry["sha256"] != digest:
            errors.append(f"inputs manifest sha256 mismatch for {name}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--admissions", type=Path, required=True,
        help="JSONL of admission candidate records",
    )
    parser.add_argument(
        "--rights", type=Path, required=True,
        help="frozen rights/terms evidence JSON",
    )
    parser.add_argument(
        "--probe", type=Path,
        help="recorded Ollama probe JSON (offline; default path)",
    )
    parser.add_argument(
        "--inputs-manifest", type=Path,
        help="optional manifest binding sha256 of each frozen input",
    )
    parser.add_argument(
        "--live", action="store_true",
        help="probe a running loopback Ollama daemon instead of --probe",
    )
    parser.add_argument(
        "--endpoint", default=DEFAULT_LIVE_ENDPOINT,
        help="Ollama endpoint for --live (loopback only)",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--check", action="store_true",
        help="exit non-zero if --out differs instead of rewriting it",
    )
    args = parser.parse_args(argv)

    if args.live and not is_loopback_endpoint(args.endpoint):
        print(
            f"ERROR: --live endpoint must be loopback, got {args.endpoint}",
            file=sys.stderr,
        )
        return 2
    if not args.live and args.probe is None:
        print("ERROR: --probe is required unless --live is set", file=sys.stderr)
        return 2

    input_paths = {"admissions": args.admissions, "rights": args.rights}
    if args.probe is not None:
        input_paths["probe"] = args.probe
    if args.inputs_manifest is not None:
        input_paths["inputs_manifest"] = args.inputs_manifest
    for name, path in input_paths.items():
        if paths_collide(args.out, path):
            print(
                f"ERROR: --out collides with {name} input {path}",
                file=sys.stderr,
            )
            return 2

    try:
        candidates = load_jsonl_strict(args.admissions)
        rights = load_json_strict(args.rights)
        probe = (
            load_json_strict(args.probe)
            if args.probe is not None
            else None
        )
        inputs_manifest = (
            load_json_strict(args.inputs_manifest)
            if args.inputs_manifest is not None
            else None
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    digests = {
        name: sha256_bytes(path.read_bytes())
        for name, path in input_paths.items()
        if name != "inputs_manifest"
    }

    if args.live:
        models = [
            str(c.get("model"))
            for c in candidates
            if isinstance(c, dict) and c.get("model")
        ]
        try:
            probe = _probe_live(args.endpoint, models)
        except (OSError, ValueError) as exc:
            print(f"ERROR: live probe failed: {exc}", file=sys.stderr)
            return 2
        digests["probe"] = sha256_bytes(
            render_report(probe)
        )

    bundle_errors: list[str] = []
    if inputs_manifest is not None:
        bundle_errors.extend(
            _inputs_manifest_errors(inputs_manifest, digests)
        )

    report = build_admission_report(
        candidates,
        rights=rights,
        probe=probe,
        input_digests=digests,
        bundle_errors=bundle_errors,
    )
    rendered = render_report(report)

    if args.check:
        try:
            current = args.out.read_bytes()
        except OSError:
            current = None
        if current != rendered:
            print(
                f"ERROR: {args.out} is stale; re-run without --check",
                file=sys.stderr,
            )
            return 1
        return 0 if report["closed"] else 1

    args.out.write_bytes(rendered)
    print(
        f"{args.out.name}: {report['counts']['accepted']} accepted, "
        f"{report['counts']['quarantined']} quarantined, "
        f"{report['counts']['rejected']} rejected."
    )
    return 0 if report["closed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
