#!/usr/bin/env python3
"""Regenerate the derived section of STATUS.md from datasets/manifests/*.json.

Usage:
    python scripts/build_status.py            # rewrite the generated block
    python scripts/build_status.py --check    # fail if the block is stale (CI)

Every data extract used to hand-edit STATUS.md: it rewrote the "Last updated"
line, renumbered the accomplishments list, and *replaced* the trajectory-quality
table with its own repo's rows. That made STATUS.md conflict between any two
extract PRs and quietly dropped earlier extracts' tables (GH #37).

So the inventory is derived instead. Everything between the BEGIN/END markers is
generated from the manifests each extract already ships; the narrative sections
outside the markers stay hand-written, because "what we accomplished" and "what
is still missing" are not derivable from a manifest.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_DIR = ROOT / "datasets" / "manifests"
STATUS_PATH = ROOT / "STATUS.md"

BEGIN_MARKER = "<!-- BEGIN GENERATED: scripts/build_status.py -->"
END_MARKER = "<!-- END GENERATED -->"


def load_manifests(manifest_dir: Path) -> list[dict[str, Any]]:
    """Load every extract manifest, oldest extract first."""
    manifests: list[dict[str, Any]] = []
    for path in sorted(manifest_dir.glob("*.manifest.json")):
        try:
            manifests.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"ERROR: cannot read manifest {path}: {exc}") from exc
    manifests.sort(key=lambda m: (str(m.get("created_at") or ""), str(m.get("name") or "")))
    return manifests


def _fmt_signals(record: dict[str, Any]) -> str:
    """Review-signal count, showing the deduped total when it differs (GH #18)."""
    total = record.get("review_signal_count")
    unique = record.get("unique_review_signal_count")
    if total is None and unique is None:
        return "—"
    if unique is None or unique == total:
        return str(total)
    return f"{unique} of {total}"


def _quality_table(manifest: dict[str, Any]) -> list[str]:
    records = manifest.get("records") or []
    lines = [
        "| PR | domain | training_use | task_type | quality | signals | validation |",
        "|----|--------|--------------|-----------|---------|---------|------------|",
    ]
    for rec in sorted(records, key=lambda r: -int(r.get("pr_number") or 0)):
        quality = rec.get("quality_score")
        lines.append(
            "| #{pr} | {domain} | {use} | {task} | {quality} | {signals} | {validation} |".format(
                pr=rec.get("pr_number", "?"),
                domain=rec.get("domain") or "—",
                use=rec.get("training_use") or "—",
                task=rec.get("task_type") or "—",
                quality=f"{quality:.2f}" if isinstance(quality, (int, float)) else "—",
                signals=_fmt_signals(rec),
                validation=rec.get("validation_count", "—"),
            )
        )
    return lines


def render_block(manifests: list[dict[str, Any]]) -> str:
    """Build the generated block (markers included)."""
    total_records = sum(int(m.get("record_count") or 0) for m in manifests)
    last_updated = max((str(m.get("created_at") or "") for m in manifests), default="")

    out: list[str] = [BEGIN_MARKER, ""]
    out.append(f"**Last updated:** {last_updated or 'unknown'}  ")
    out.append(
        f"**Extracts:** {len(manifests)} · **Trajectories:** {total_records}  "
    )
    out.append("")
    out.append("<!-- Derived from datasets/manifests/*.manifest.json — do not edit by hand. -->")
    out.append("")
    out.append("## Extracted datasets")
    out.append("")
    out.append("| dataset | source repo | records | schema | extracted |")
    out.append("|---------|-------------|---------|--------|-----------|")
    for m in manifests:
        out.append(
            "| `{name}` | {repo} | {count} | {schema} | {created} |".format(
                name=m.get("name") or "?",
                repo=m.get("source_repo") or "—",
                count=m.get("record_count", "—"),
                schema=m.get("schema_version") or "—",
                created=m.get("created_at") or "—",
            )
        )
    out.append("")
    out.append("## Trajectory quality")
    for m in manifests:
        out.append("")
        out.append(f"### {m.get('name') or '?'}")
        out.append("")
        out.extend(_quality_table(m))
    out.append("")
    out.append(END_MARKER)
    return "\n".join(out)


def splice(status_text: str, block: str) -> str:
    """Replace the marked region of STATUS.md with a freshly rendered block."""
    start = status_text.find(BEGIN_MARKER)
    end = status_text.find(END_MARKER)
    if start == -1 or end == -1:
        raise SystemExit(
            f"ERROR: {STATUS_PATH.name} is missing the generated-block markers.\n"
            f"       Add these two lines where the inventory belongs:\n"
            f"         {BEGIN_MARKER}\n"
            f"         {END_MARKER}"
        )
    if end < start:
        raise SystemExit(f"ERROR: {STATUS_PATH.name} markers are out of order.")
    return status_text[:start] + block + status_text[end + len(END_MARKER) :]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the generated block is stale instead of rewriting it",
    )
    parser.add_argument("--manifest-dir", type=Path, default=MANIFEST_DIR)
    parser.add_argument("--status", type=Path, default=STATUS_PATH)
    args = parser.parse_args(argv)

    manifests = load_manifests(args.manifest_dir)
    if not manifests:
        print(f"No manifests in {args.manifest_dir}; nothing to generate.", file=sys.stderr)
        return 0

    current = args.status.read_text(encoding="utf-8")
    updated = splice(current, render_block(manifests))

    if args.check:
        if updated != current:
            print(
                f"ERROR: {args.status.name} is out of date with "
                f"{args.manifest_dir.name}/. Run: python scripts/build_status.py",
                file=sys.stderr,
            )
            return 1
        print(f"{args.status.name} is up to date ({len(manifests)} extracts).")
        return 0

    if updated == current:
        print(f"{args.status.name} already up to date ({len(manifests)} extracts).")
        return 0
    args.status.write_text(updated, encoding="utf-8")
    print(f"Wrote {args.status.name} ({len(manifests)} extracts).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
