#!/usr/bin/env python3
"""G4.5 validation for the paper-vault knowledge graph.

Checks (read-only):
  1. managed block markers are paired and not duplicated within each Markdown file;
  2. every [[paper/...]] wikilink resolves to an existing file (no broken links);
  3. each 01knowledge/<kind>/_index.md matches the node files on disk.

Prints a JSON report with status PASS/FAIL. Exits non-zero on FAIL.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MANAGED_PAIRS = [
    ("<!-- paper-vault:refs:begin -->", "<!-- paper-vault:refs:end -->"),
    ("<!-- paper-vault:related:begin -->", "<!-- paper-vault:related:end -->"),
    ("<!-- paper-vault:concepts:begin -->", "<!-- paper-vault:concepts:end -->"),
]
LEGACY = ("<!-- paper-vault:managed:begin -->", "<!-- paper-vault:managed:end -->")
KINDS = ("concepts", "methods", "regions")
# Obsidian wikilink: [[paper/path|alias]]. In tables the pipe is escaped as \|.
# Capture the whole inner part, then split on an *unescaped* pipe only.
WIKILINK_RE = re.compile(r"\[\[paper/([^\]]+)\]\]")
PLACEHOLDER_TARGETS = {"概念名", "方法名", "脑区名"}
CODE_RE = re.compile(r"```.*?```|`[^`\n]*`", re.S)


def strip_code(text: str) -> str:
    """Remove fenced/inline code so example wikilinks in docs aren't treated as real."""
    return CODE_RE.sub(" ", text)


def is_placeholder(target: str) -> bool:
    stem = Path(target).name
    return stem in PLACEHOLDER_TARGETS or "<" in target or ">" in target or "{{" in target


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate the paper-vault knowledge graph")
    ap.add_argument("--vault", required=True, help="vault root (the paper directory)")
    args = ap.parse_args()

    vault = Path(args.vault).resolve()
    errors: list[str] = []
    warnings: list[str] = []
    if not vault.is_dir():
        print(json.dumps({"status": "FAIL", "errors": [f"vault not found: {vault}"]}, ensure_ascii=False, indent=2))
        return 2

    md_files = sorted(vault.rglob("*.md"))

    # 1) managed marker integrity
    for md in md_files:
        try:
            text = md.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        # skip template placeholders
        if md.parent.name == "模板":
            continue
        for begin, end in MANAGED_PAIRS:
            nb, ne = text.count(begin), text.count(end)
            if nb > 1 or ne > 1:
                errors.append(f"{md.relative_to(vault)}: duplicated marker pair {begin} ({nb}/{ne})")
            if nb != ne:
                errors.append(f"{md.relative_to(vault)}: unbalanced marker {begin} ({nb} begin / {ne} end)")
        if LEGACY[0] in text or LEGACY[1] in text:
            warnings.append(f"{md.relative_to(vault)}: legacy managed marker present; rerun build_graph.py to upgrade")

    # 2) wikilink resolution
    broken: list[str] = []
    total_links = 0
    for md in md_files:
        if md.parent.name == "模板":
            continue
        text = strip_code(md.read_text(encoding="utf-8", errors="ignore"))
        for inner in WIKILINK_RE.findall(text):
            # In Obsidian tables the alias separator is escaped as \|; unescape
            # first so it behaves like a normal pipe, then take the path part.
            target = inner.replace("\\|", "|").split("|")[0].strip()
            if is_placeholder(target):
                continue  # documentation placeholders, not real links
            total_links += 1
            rel = target[len("paper/") :] if target.startswith("paper/") else target
            candidate = vault / rel
            if candidate.suffix == "":
                candidate = candidate.with_suffix(".md")
            if not candidate.exists():
                broken.append(f"{md.relative_to(vault)} -> {target}")
    if broken:
        errors.extend(f"broken wikilink: {b}" for b in broken)

    # 3) index consistency
    index_report = {}
    for kind in KINDS:
        kdir = vault / "01knowledge" / kind
        node_files = (
            {p.stem for p in kdir.rglob("*.md") if p.stem not in ("_index", "_concepts_index")}
            if kdir.is_dir()
            else set()
        )
        idx = kdir / "_index.md"
        indexed: set[str] = set()
        if idx.is_file():
            for inner in WIKILINK_RE.findall(idx.read_text(encoding="utf-8", errors="ignore")):
                target = inner.replace("\\|", "|").split("|")[0].strip()
                name = Path(target).name
                if name and name not in PLACEHOLDER_TARGETS:
                    indexed.add(name)
        missing = sorted(node_files - indexed)
        extra = sorted(indexed - node_files)
        index_report[kind] = {"nodes": len(node_files), "indexed": len(indexed), "missing_in_index": missing, "extra_in_index": extra}
        for n in missing:
            errors.append(f"{kind} index missing node: {n}")
        for n in extra:
            errors.append(f"{kind} index references missing node: {n}")

    report = {
        "status": "FAIL" if errors else "PASS",
        "vault": str(vault),
        "markdown_files": len(md_files),
        "wikilinks_checked": total_links,
        "broken_links": len(broken),
        "index": index_report,
        "errors": errors,
        "warnings": warnings,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
