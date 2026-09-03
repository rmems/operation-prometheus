#!/usr/bin/env python3
"""Regenerate the derived docs: STATUS.md and docs/source-repos/_index.md.

Usage:
    python scripts/build_status.py            # rewrite the generated blocks
    python scripts/build_status.py --check    # fail if any block is stale (pipeline)

Every data extract used to hand-edit STATUS.md: it rewrote the "Last updated"
line, renumbered the accomplishments list, and *replaced* the trajectory-quality
table with its own repo's rows. That made STATUS.md conflict between any two
extract PRs and quietly dropped earlier extracts' tables (GH #37).

So the inventory is derived instead. Everything between the BEGIN/END markers is
generated from the manifests each extract already ships; the narrative sections
outside the markers stay hand-written, because "what we accomplished" and "what
is still missing" are not derivable from a manifest.

The Index table in docs/source-repos/_index.md is derived the same way — from an
``<!-- index: <repo link> | <status> -->`` line each per-repo doc carries — so an
extract adds only its own doc file and never edits the shared index.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_DIR = ROOT / "datasets" / "manifests"
STATUS_PATH = ROOT / "STATUS.md"
DOCS_DIR = ROOT / "docs" / "source-repos"

BEGIN_MARKER = "<!-- BEGIN GENERATED: scripts/build_status.py -->"
END_MARKER = "<!-- END GENERATED -->"
INDEX_BEGIN_MARKER = "<!-- BEGIN GENERATED INDEX: scripts/build_status.py -->"
INDEX_END_MARKER = "<!-- END GENERATED INDEX -->"
INDEX_ENTRY_RE = re.compile(r"<!--\s*index:\s*(.+?)\s*\|\s*(.+?)\s*-->")


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
    if total is None:
        return str(unique)
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

    out: list[str] = [
        BEGIN_MARKER,
        "",
        f"**Last updated:** {last_updated or 'unknown'}  ",
        f"**Extracts:** {len(manifests)} · **Trajectories:** {total_records}  ",
        "",
        "<!-- Derived from datasets/manifests/*.manifest.json — do not edit by hand. -->",
        "",
        "## Extracted datasets",
        "",
        "| dataset | source repo | records | schema | extracted |",
        "|---------|-------------|---------|--------|-----------|",
    ]
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


def load_index_entries(docs_dir: Path) -> list[tuple[str, str, str]]:
    """(source-repo cell, doc filename, status cell) for every per-repo doc."""
    entries: list[tuple[str, str, str]] = []
    for path in sorted(docs_dir.glob("*.md")):
        if path.name == "_index.md":
            continue
        match = INDEX_ENTRY_RE.search(path.read_text(encoding="utf-8"))
        if not match:
            raise SystemExit(
                f"ERROR: {path} has no index line, so it would silently drop out of\n"
                f"       the generated Index table. Add one near the top, e.g.:\n"
                f"         <!-- index: [owner/repo](https://github.com/owner/repo)"
                f" | v0 extracted -->"
            )
        entries.append((match.group(1), path.name, match.group(2)))
    return entries


def render_index_block(entries: list[tuple[str, str, str]]) -> str:
    """Build the generated Index table for _index.md (markers included)."""
    out: list[str] = [
        INDEX_BEGIN_MARKER,
        "",
        "<!-- Derived from the index line in each per-repo doc - do not edit by hand. -->",
        "",
        "| Source repo | Doc | Status |",
        "|-------------|-----|--------|",
    ]
    for repo, doc, status in entries:
        out.append(f"| {repo} | [{doc}]({doc}) | {status} |")
    out.append("")
    out.append(INDEX_END_MARKER)
    return "\n".join(out)


def splice(
    text: str,
    block: str,
    begin: str = BEGIN_MARKER,
    end_marker: str = END_MARKER,
    name: str = "STATUS.md",
) -> str:
    """Replace the marked region of a derived doc with a freshly rendered block."""
    start = text.find(begin)
    end = text.find(end_marker)
    if start == -1 or end == -1:
        raise SystemExit(
            f"ERROR: {name} is missing the generated-block markers.\n"
            f"       Add these two lines where the generated content belongs:\n"
            f"         {begin}\n"
            f"         {end_marker}"
        )
    if text.count(begin) > 1 or text.count(end_marker) > 1:
        # With two blocks, only the first would be refreshed — the second would
        # stay stale forever while --check reports success.
        raise SystemExit(
            f"ERROR: {name} contains more than one generated block; "
            f"keep exactly one {begin} / {end_marker} pair."
        )
    if end < start:
        raise SystemExit(f"ERROR: {name} markers are out of order.")
    return text[:start] + block + text[end + len(end_marker) :]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the generated block is stale instead of rewriting it",
    )
    parser.add_argument("--manifest-dir", type=Path, default=MANIFEST_DIR)
    parser.add_argument("--status", type=Path, default=STATUS_PATH)
    parser.add_argument("--docs-dir", type=Path, default=DOCS_DIR)
    args = parser.parse_args(argv)

    manifests = load_manifests(args.manifest_dir)
    if not manifests and args.check:
        # Fail closed: a typo'd --manifest-dir must not pass the gate.
        print(
            f"ERROR: no manifests found in {args.manifest_dir}; "
            f"refusing to report {args.status.name} as up to date.",
            file=sys.stderr,
        )
        return 1

    # (path, current text, freshly rendered text) per derived doc.
    targets: list[tuple[Path, str, str]] = []
    if manifests:
        current = args.status.read_text(encoding="utf-8")
        targets.append(
            (args.status, current, splice(current, render_block(manifests), name=args.status.name))
        )
    else:
        print(f"No manifests in {args.manifest_dir}; skipping {args.status.name}.", file=sys.stderr)

    index_path = args.docs_dir / "_index.md"
    index_current = index_path.read_text(encoding="utf-8")
    index_block = render_index_block(load_index_entries(args.docs_dir))
    targets.append(
        (
            index_path,
            index_current,
            splice(
                index_current, index_block, INDEX_BEGIN_MARKER, INDEX_END_MARKER, index_path.name
            ),
        )
    )

    stale = [path.name for path, current, updated in targets if updated != current]
    if args.check:
        if stale:
            print(
                f"ERROR: {', '.join(stale)} out of date with the source files. "
                f"Run: python scripts/build_status.py",
                file=sys.stderr,
            )
            return 1
        print(f"{', '.join(p.name for p, _, _ in targets)} up to date ({len(manifests)} extracts).")
        return 0

    for path, current, updated in targets:
        if updated == current:
            print(f"{path.name} already up to date.")
        else:
            path.write_text(updated, encoding="utf-8")
            print(f"Wrote {path.name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
