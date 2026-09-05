#!/usr/bin/env python3
"""Dry-run-first OpenRouter harness for EXP-PROM-BUGFIX-SWE-001.

Examples:
    python scripts/generate_bugfix_synth.py --exp EXP-PROM-BUGFIX-SWE-001
    python scripts/generate_bugfix_synth.py --exp EXP-PROM-BUGFIX-SWE-001 --dry-run

Live (opt-in; not for CI):
    export OPENROUTER_API_KEY=...
    python scripts/generate_bugfix_synth.py --exp EXP-PROM-BUGFIX-SWE-001 --live
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.bugfix_synth import (  # noqa: E402
    EXP_ID,
    LOCKED_MODEL,
    VARIANT_KNOBS,
    HarnessError,
    assert_exp_id,
    attempt_id,
    build_teacher_messages,
    core_seed_ids,
    evaluate_synth,
    extract_message_content,
    fixture_chat_response,
    gold_patch,
    ledger_row,
    load_jsonl_records,
    load_seed_manifest,
    messages_blob,
    parse_teacher_json,
    patch_fingerprint,
    select_core_seeds,
    utc_now,
)
from lib.paths import repo_root  # noqa: E402
from lib.secrets import redact_secrets  # noqa: E402
from providers.openrouter.client import (  # noqa: E402
    API_KEY_ENV,
    OpenRouterClient,
    OpenRouterError,
    assert_locked_model,
    build_chat_request,
    redact_planned_request,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("generate_bugfix_synth")


class LiveGatedError(HarnessError):
    """--live was requested without a usable credential or lock."""


@dataclass
class RunContext:
    dry_run: bool
    model: str
    out_dir: Path
    client: OpenRouterClient | None
    seen: set[str]
    ledger_path: Path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--exp",
        required=True,
        help=f"Experiment id (only {EXP_ID} is supported)",
    )
    p.add_argument(
        "--model",
        default=LOCKED_MODEL,
        help=f"Teacher model (locked to {LOCKED_MODEL})",
    )
    p.add_argument(
        "--variants-per-seed",
        type=int,
        default=3,
        help="Variant knobs per core seed (1-3, default 3; pilot live = 24 calls)",
    )
    p.add_argument(
        "--dry-run",
        dest="dry_run_flag",
        action="store_true",
        help="Explicit dry-run (already the default when --live is omitted)",
    )
    p.add_argument(
        "--live",
        action="store_true",
        help=f"Opt-in OpenRouter POST. Requires {API_KEY_ENV}. Refuses other models",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Generation directory (gitignored; default experiments/<exp>/generations/)",
    )
    p.add_argument(
        "--jsonl-dir",
        type=Path,
        default=None,
        help="Directory of committed trajectory JSONL (default datasets/jsonl)",
    )
    p.add_argument(
        "--seed-manifest",
        type=Path,
        default=None,
        help="Core seed manifest (default experiments/<exp>/seed-manifest.json)",
    )
    return p


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    root = repo_root()
    exp_dir = root / "experiments" / EXP_ID
    manifest = Path(args.seed_manifest) if args.seed_manifest else exp_dir / "seed-manifest.json"
    jsonl_dir = Path(args.jsonl_dir) if args.jsonl_dir else root / "datasets" / "jsonl"
    out_dir = Path(args.out_dir) if args.out_dir else exp_dir / "generations"
    return manifest, jsonl_dir, out_dir


def _redact_obj(obj: Any) -> Any:
    text, _count = redact_secrets(json.dumps(obj, ensure_ascii=False))
    return json.loads(text)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _variants_for(count: int) -> tuple[str, ...]:
    if count < 1 or count > len(VARIANT_KNOBS):
        raise HarnessError(
            f"--variants-per-seed must be between 1 and {len(VARIANT_KNOBS)}"
        )
    return VARIANT_KNOBS[:count]


def _require_model(model: str) -> None:
    try:
        assert_locked_model(model)
    except OpenRouterError as exc:
        raise HarnessError(str(exc)) from exc


def _open_live_client() -> OpenRouterClient:
    key = (os.environ.get(API_KEY_ENV) or "").strip()
    if not key:
        raise LiveGatedError(
            f"--live requires {API_KEY_ENV} in the environment; "
            "default --dry-run makes no network calls"
        )
    return OpenRouterClient(api_key=key)


def _load_seeds(manifest_path: Path, jsonl_dir: Path) -> list[dict[str, Any]]:
    manifest = load_seed_manifest(manifest_path)
    return select_core_seeds(load_jsonl_records(jsonl_dir), core_seed_ids(manifest))


def _prepare(args: argparse.Namespace) -> tuple[RunContext, list[dict[str, Any]], tuple[str, ...]]:
    assert_exp_id(args.exp)
    if args.live and args.dry_run_flag:
        raise HarnessError("Pass either --dry-run or --live, not both")
    dry_run = not args.live
    _require_model(args.model)
    client = None if dry_run else _open_live_client()
    manifest_path, jsonl_dir, out_dir = resolve_paths(args)
    ledger_path = out_dir / "yield-ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text("", encoding="utf-8")
    ctx = RunContext(
        dry_run=dry_run,
        model=args.model,
        out_dir=out_dir,
        client=client,
        seen=set(),
        ledger_path=ledger_path,
    )
    return ctx, _load_seeds(manifest_path, jsonl_dir), _variants_for(args.variants_per_seed)


def _seed_id(seed: dict[str, Any]) -> str:
    seed_id = str(seed.get("id") or "").strip()
    if not seed_id:
        raise HarnessError("Seed record missing required 'id' field")
    return seed_id


def _teacher_response(ctx: RunContext, seed: dict[str, Any], variant: str) -> dict[str, Any]:
    seed_id = _seed_id(seed)
    messages = build_teacher_messages(seed, variant)
    gold = gold_patch(seed)
    if gold and gold in messages_blob(messages):
        raise HarnessError(f"Refusing to send gold patch for seed {seed_id} (prompt leak)")
    planned = build_chat_request(messages, model=ctx.model)
    write_json(
        ctx.out_dir / "planned_requests" / f"{attempt_id(seed_id, variant)}.json",
        _redact_obj(redact_planned_request(planned)),
    )
    if ctx.dry_run:
        response = fixture_chat_response(seed, variant)
        write_json(
            ctx.out_dir / "fixture_responses" / f"{attempt_id(seed_id, variant)}.json",
            response,
        )
        return response
    if ctx.client is None:
        raise LiveGatedError("live client was not constructed")
    return ctx.client.complete(messages, model=ctx.model)


def _parse_candidate(response: dict[str, Any]) -> dict[str, Any]:
    try:
        return parse_teacher_json(extract_message_content(response))
    except HarnessError:
        return {}


def _record_attempt(ctx: RunContext, seed: dict[str, Any], variant: str) -> bool:
    started = utc_now()
    seed_id = _seed_id(seed)
    candidate = _parse_candidate(_teacher_response(ctx, seed, variant))
    evaluation = evaluate_synth(candidate, seed, ctx.seen)
    if evaluation.keep:
        ctx.seen.add(patch_fingerprint(str(candidate.get("patch") or "")))
    row = ledger_row(
        {
            "attempt_id": attempt_id(seed_id, variant),
            "seed_id": seed_id,
            "variant": variant,
            "started_at": started,
            "finished_at": utc_now(),
            "dry_run": ctx.dry_run,
        },
        evaluation,
    )
    append_jsonl(ctx.ledger_path, row)
    logger.info(
        "%s %s %s codes=%s soft=%s",
        row["decision"],
        seed_id,
        variant,
        row["reject_codes"],
        row["soft_codes"],
    )
    return evaluation.keep


def _write_summary(ctx: RunContext, counts: dict[str, int]) -> None:
    attempts = counts["seed_count"] * counts["variant_count"]
    summary = {
        "exp_id": EXP_ID,
        "teacher_model": ctx.model,
        "dry_run": ctx.dry_run,
        "seed_count": counts["seed_count"],
        "variants_per_seed": counts["variant_count"],
        "attempts": attempts,
        "kept": counts["kept"],
        "rejected": attempts - counts["kept"],
        "out_dir": str(ctx.out_dir),
        "network": not ctx.dry_run,
    }
    write_json(ctx.out_dir / "run-summary.json", summary)
    logger.info(
        "Finished %s attempts (%s keep / %s reject) dry_run=%s out=%s",
        attempts,
        counts["kept"],
        attempts - counts["kept"],
        ctx.dry_run,
        ctx.out_dir,
    )


def run(args: argparse.Namespace) -> int:
    ctx, seeds, variants = _prepare(args)
    kept = sum(_record_attempt(ctx, seed, variant) for seed in seeds for variant in variants)
    _write_summary(
        ctx,
        {"seed_count": len(seeds), "variant_count": len(variants), "kept": kept},
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except (HarnessError, OpenRouterError) as exc:
        logger.error("%s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
