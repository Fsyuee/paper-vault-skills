#!/usr/bin/env python3
"""Validate the paper-vault artifacts for one paper. Read-only.

Checks: canonical paths, YAML frontmatter identity fields, Note<->Fulltext
reciprocal links, key equality, and body/image presence. Reports ERROR/WARN
without modifying files.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

FIELDS = ["type", "title", "zotero_key", "pdf_key", "collection", "note_path", "fulltext_path"]


def parse_fm(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.strip().startswith("#"):
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vault", required=True)
    ap.add_argument("--note", help="vault-relative path to the analytical note")
    ap.add_argument("--fulltext", help="vault-relative path to the fulltext markdown")
    ap.add_argument("--zotero-key", help="expected stable identity")
    args = ap.parse_args()

    root = Path(args.vault).expanduser().resolve()
    errors, warnings, checks = [], [], []

    def load(rel: str | None, kind: str):
        if not rel:
            return None, {}
        p = (root / rel) if not Path(rel).is_absolute() else Path(rel)
        if not p.is_file():
            errors.append(f"{kind} file missing: {rel}")
            return p, {}
        text = p.read_text(encoding="utf-8", errors="replace")
        return p, parse_fm(text)

    note_p, note_fm = load(args.note, "NOTE")
    ft_p, ft_fm = load(args.fulltext, "FULLTEXT")

    for label, fm in (("NOTE", note_fm), ("FULLTEXT", ft_fm)):
        if not fm:
            errors.append(f"{label} frontmatter missing or unparsable")
            continue
        for f in FIELDS:
            if f not in fm:
                errors.append(f"{label} frontmatter missing field: {f}")
        if label == "NOTE" and fm.get("type") != "literature-note":
            errors.append(f"NOTE type must be literature-note, got {fm.get('type')!r}")
        if label == "FULLTEXT" and fm.get("type") != "literature-fulltext":
            errors.append(f"FULLTEXT type must be literature-fulltext, got {fm.get('type')!r}")

    if note_fm and ft_fm:
        for k in ("zotero_key", "pdf_key"):
            if note_fm.get(k) and ft_fm.get(k) and note_fm[k] != ft_fm[k]:
                errors.append(f"{k} mismatch between NOTE and FULLTEXT")
        nft = note_fm.get("fulltext_path", "").replace("\\", "/")
        fself = ft_fm.get("fulltext_path", "").replace("\\", "/")
        if args.note and nft and nft != args.fulltext:
            errors.append(f"NOTE.fulltext_path ({nft}) != expected ({args.fulltext})")
        if fself and fself != args.fulltext:
            errors.append(f"FULLTEXT.fulltext_path ({fself}) != expected ({args.fulltext})")
        nself = note_fm.get("note_path", "").replace("\\", "/")
        if nself and nself != args.note:
            errors.append(f"NOTE.note_path ({nself}) != expected ({args.note})")
        if ft_fm.get("note_path", "").replace("\\", "/") != args.note:
            errors.append(f"FULLTEXT.note_path != expected ({args.note})")
        checks.append("reciprocal note/fulltext links checked")

    if args.zotero_key:
        for label, fm in (("NOTE", note_fm), ("FULLTEXT", ft_fm)):
            if fm and fm.get("zotero_key") != args.zotero_key:
                errors.append(f"{label} zotero_key != expected {args.zotero_key}")

    for p, label in ((note_p, "NOTE"), (ft_p, "FULLTEXT")):
        if p and p.is_file():
            body = p.read_text(encoding="utf-8", errors="replace")
            if len(body.strip()) < 80:
                warnings.append(f"{label} body is very short ({len(body.strip())} chars)")
            for im in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", body):
                if im.startswith("http"):
                    continue
                img = (p.parent / im).resolve()
                if not img.is_file():
                    errors.append(f"{label} broken image link: {im}")
    checks.append("image links checked")

    status = "PASS" if not errors else "FAIL"
    print(json.dumps({
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
    }, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
