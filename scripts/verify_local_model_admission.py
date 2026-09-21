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
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.model_admission import build_admission_report  # noqa: E402
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


def build_parser() -> argparse.ArgumentParser:
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
    return parser


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


def _inputs_manifest_errors(manifest: Any, digests: dict[str, str]) -> list[str]:
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


def _check_args(args: argparse.Namespace) -> str | None:
    if args.live and not is_loopback_endpoint(args.endpoint):
        return f"--live endpoint must be loopback, got {args.endpoint}"
    if not args.live and args.probe is None:
        return "--probe is required unless --live is set"
    return None


def _input_paths(args: argparse.Namespace) -> dict[str, Path]:
    paths = {"admissions": args.admissions, "rights": args.rights}
    if args.probe is not None:
        paths["probe"] = args.probe
    if args.inputs_manifest is not None:
        paths["inputs_manifest"] = args.inputs_manifest
    return paths


def _collision_error(input_paths: dict[str, Path], out: Path) -> str | None:
    for name, path in input_paths.items():
        if paths_collide(out, path):
            return f"--out collides with {name} input {path}"
    return None


def _load_inputs(input_paths: dict[str, Path]) -> dict[str, Any]:
    inputs = {
        "candidates": load_jsonl_strict(input_paths["admissions"]),
        "rights": load_json_strict(input_paths["rights"]),
        "probe": (
            load_json_strict(input_paths["probe"])
            if "probe" in input_paths
            else None
        ),
        "inputs_manifest": (
            load_json_strict(input_paths["inputs_manifest"])
            if "inputs_manifest" in input_paths
            else None
        ),
    }
    inputs["digests"] = {
        name: sha256_bytes(path.read_bytes())
        for name, path in input_paths.items()
        if name != "inputs_manifest"
    }
    return inputs


def _resolve_live_probe(args: argparse.Namespace, candidates: list[Any]) -> dict:
    models = [
        str(c.get("model"))
        for c in candidates
        if isinstance(c, dict) and c.get("model")
    ]
    try:
        return _probe_live(args.endpoint, models)
    except (OSError, ValueError) as exc:
        raise ValueError(f"live probe failed: {exc}") from exc


def _emit(args: argparse.Namespace, rendered: bytes, closed: bool) -> int:
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
        return 0 if closed else 1
    args.out.write_bytes(rendered)
    return 0 if closed else 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if error := _check_args(args):
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    input_paths = _input_paths(args)
    if error := _collision_error(input_paths, args.out):
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    try:
        inputs = _load_inputs(input_paths)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    digests = inputs["digests"]
    probe = inputs["probe"]
    if args.live:
        try:
            probe = _resolve_live_probe(args, inputs["candidates"])
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        digests["probe"] = sha256_bytes(render_report(probe))

    bundle_errors = (
        _inputs_manifest_errors(inputs["inputs_manifest"], digests)
        if inputs["inputs_manifest"] is not None
        else []
    )
    report = build_admission_report(
        inputs["candidates"],
        rights=inputs["rights"],
        probe=probe,
        input_digests=digests,
        bundle_errors=bundle_errors,
    )
    rendered = render_report(report)
    if not args.check:
        print(
            f"{args.out.name}: {report['counts']['accepted']} accepted, "
            f"{report['counts']['quarantined']} quarantined, "
            f"{report['counts']['rejected']} rejected."
        )
    return _emit(args, rendered, report["closed"])


if __name__ == "__main__":
    raise SystemExit(main())
