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
(127.0.0.1, ::1, localhost) with proxies disabled and redirects refused.
Validation is deterministic; exit 0 means every candidate was accepted, 1
means the report is not closed, 2 means an input or usage error.
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

from lib.model_admission import (  # noqa: E402
    AdmissionInputs,
    build_admission_report,
)
from lib.model_admission_report import validate_decision_report  # noqa: E402
from lib.model_admission_evidence import (  # noqa: E402
    canonical_loopback_endpoint,
    loads_strict,
    paths_collide,
    read_frozen_json,
    read_frozen_jsonl,
    render_report,
    sha256_bytes,
    sha256_or_none,
)

DEFAULT_LIVE_ENDPOINT = "http://127.0.0.1:11434"


class _LoopbackOnlyRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect: the live probe must stay on loopback."""

    def redirect_request(self, *_args, **_kwargs):  # noqa: D102
        return None


def _loopback_opener() -> urllib.request.OpenerDirector:
    """Opener with proxy use disabled and redirects refused."""
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _LoopbackOnlyRedirect(),
    )


def _fetch_strict(
    opener: urllib.request.OpenerDirector,
    request: Any,
    *,
    timeout: int,
) -> Any:
    with opener.open(request, timeout=timeout) as resp:
        if not canonical_loopback_endpoint(resp.geturl()):
            raise ValueError(f"live response redirected off loopback: {resp.geturl()}")
        return loads_strict(resp.read().decode("utf-8"))


def _probe_live(endpoint: str, models: list[str]) -> dict[str, Any]:
    """Query a loopback Ollama daemon (version, tags, per-model show)."""
    base = canonical_loopback_endpoint(endpoint)
    if base is None:
        raise ValueError(f"endpoint is not a canonical loopback URL: {endpoint}")
    base = base.rstrip("/")
    opener = _loopback_opener()

    tags = _fetch_strict(opener, f"{base}/api/tags", timeout=10)
    try:
        version = _fetch_strict(opener, f"{base}/api/version", timeout=10)
    except (OSError, ValueError):
        version = None

    show: dict[str, Any] = {}
    for model in models:
        body = json.dumps({"model": model}).encode("utf-8")
        req = urllib.request.Request(
            f"{base}/api/show",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        show[model] = _fetch_strict(opener, req, timeout=30)
    return {
        "schema_version": "ollama_probe_v1",
        "endpoint": base,
        "runtime": "ollama",
        "version": (
            version.get("version")
            if isinstance(version, dict)
            else None
        ),
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
        if name == "inputs_manifest":
            continue
        entry = files.get(name)
        if not isinstance(entry, dict) or sha256_or_none(entry.get("sha256")) is None:
            errors.append(f"inputs manifest missing sha256 for {name}")
        elif entry["sha256"] != digest:
            errors.append(f"inputs manifest sha256 mismatch for {name}")
    return errors


def _check_args(args: argparse.Namespace) -> str | None:
    if args.live and args.probe is not None:
        return "--live and --probe are mutually exclusive"
    if args.live and canonical_loopback_endpoint(args.endpoint) is None:
        return f"--live endpoint must be a canonical loopback URL, got {args.endpoint}"
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


def _output_vs_input_error(
    flag: str, out: Path, input_paths: dict[str, Path]
) -> str | None:
    for name, path in input_paths.items():
        if paths_collide(out, path):
            return f"{flag} collides with {name} input {path}"
    return None


def _output_pairs_error(out_paths: dict[str, Path]) -> str | None:
    flags = list(out_paths)
    pairs = (
        (flag_a, flag_b)
        for index, flag_a in enumerate(flags)
        for flag_b in flags[index + 1 :]
    )
    for flag_a, flag_b in pairs:
        if paths_collide(out_paths[flag_a], out_paths[flag_b]):
            return f"{flag_a} collides with {flag_b}"
    return None


def _collision_error(
    input_paths: dict[str, Path], out_paths: dict[str, Path]
) -> str | None:
    """No output may collide with an input or another output."""
    for flag, out in out_paths.items():
        if error := _output_vs_input_error(flag, out, input_paths):
            return error
    return _output_pairs_error(out_paths)


def _load_inputs(input_paths: dict[str, Path]) -> dict[str, Any]:
    """Read each frozen input once; hash and parse the same bytes."""
    candidates, admissions_bytes = read_frozen_jsonl(input_paths["admissions"])
    rights, rights_bytes = read_frozen_json(input_paths["rights"])
    probe, probe_bytes = (
        read_frozen_json(input_paths["probe"])
        if "probe" in input_paths
        else (None, b"")
    )
    has_manifest = "inputs_manifest" in input_paths
    manifest, manifest_bytes = (
        read_frozen_json(input_paths["inputs_manifest"])
        if has_manifest
        else (None, b"")
    )
    digests = {
        "admissions": sha256_bytes(admissions_bytes),
        "rights": sha256_bytes(rights_bytes),
    }
    if "probe" in input_paths:
        digests["probe"] = sha256_bytes(probe_bytes)
    if has_manifest:
        digests["inputs_manifest"] = sha256_bytes(manifest_bytes)
    return {
        "candidates": candidates,
        "rights": rights,
        "probe": probe,
        "inputs_manifest": manifest,
        "manifest_supplied": has_manifest,
        "digests": digests,
    }


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


def _resolve_probe(
    args: argparse.Namespace, inputs: dict[str, Any]
) -> dict[str, Any] | None:
    """Frozen probe, or a live loopback probe hashed into input_digests."""
    if not args.live:
        return inputs["probe"]
    try:
        probe = _resolve_live_probe(args, inputs["candidates"])
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return None
    inputs["digests"]["probe"] = sha256_bytes(render_report(probe))
    return probe


def _evaluate(
    inputs: dict[str, Any], probe: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Build the aggregate report; returns (report, candidate)."""
    candidates = inputs["candidates"]
    if not isinstance(candidates, list) or len(candidates) != 1:
        print(
            "ERROR: --admissions must contain exactly one candidate "
            "(the singular admission report covers one model)",
            file=sys.stderr,
        )
        return None
    bundle_errors = (
        _inputs_manifest_errors(inputs["inputs_manifest"], inputs["digests"])
        if inputs["manifest_supplied"]
        else []
    )
    report = build_admission_report(
        candidates,
        AdmissionInputs(
            rights=inputs["rights"],
            probe=probe,
            input_digests=inputs["digests"],
            bundle_errors=bundle_errors,
        ),
    )
    return report, candidates[0]


def _validated_decision(report: dict[str, Any]) -> bytes | None:
    """Re-validate the emitted decision through the shared contract."""
    decision = report["decisions"][0]
    errors = validate_decision_report(decision)
    if errors:
        print(
            "ERROR: emitted decision report fails contract validation: "
            + "; ".join(errors),
            file=sys.stderr,
        )
        return None
    return render_report(decision)


def _load_or_fail(input_paths: dict[str, Path]) -> dict[str, Any] | None:
    try:
        return _load_inputs(input_paths)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    input_paths = _input_paths(args)
    out_paths = {"--out": args.out}
    if args.diagnostics is not None:
        out_paths["--diagnostics"] = args.diagnostics
    if error := _check_args(args) or _collision_error(input_paths, out_paths):
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    inputs = _load_or_fail(input_paths)
    if inputs is None:
        return 2

    probe = _resolve_probe(args, inputs)
    if probe is None:
        return 2
    evaluated = _evaluate(inputs, probe)
    if evaluated is None:
        return 2
    report, candidate = evaluated
    decision = report["decisions"][0]
    rendered = _validated_decision(report)
    if rendered is None:
        return 2

    if not args.check:
        print(
            f"{args.out.name}: decision={decision['decision']}"
            + (f" reasons={decision['reasons']}" if decision["reasons"] else "")
        )
        args.diagnostics and args.diagnostics.write_bytes(
            render_report(report)
        )
    return _emit(args, rendered, report["closed"])


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
    parser.add_argument(
        "--out", type=Path, required=True,
        help="canonical singular local_model_admission_v1 report path",
    )
    parser.add_argument(
        "--diagnostics", type=Path,
        help="optional bundle diagnostics path (aggregate accounting only)",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="exit non-zero if --out differs instead of rewriting it",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
