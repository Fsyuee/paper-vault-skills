#!/usr/bin/env python3
"""Resolve a PDF to verified bibliographic identity via a read-only Zotero lookup.

Design principle (inherited from the reference workflow): the Zotero parent key
is the stable identity; a title is a display hint only. This workflow assumes
the user imports the paper into Zotero themselves first, so the authoritative
metadata always comes from Zotero, never from PDF text guessing.

Subcommands
  clues   Extract *candidate* DOI / title / year from a local PDF (best-effort,
          used only as lookup keys, never trusted as final metadata).
  match   Query Zotero SQLite in read-only mode by DOI or title and return
          candidate parent items with attachment keys and URIs.

All database access uses SQLite mode=ro with query_only=ON. Nothing is written.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", re.I)
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")


def discover_data_dir(explicit: str | None) -> Path | None:
    cands = [Path(explicit).expanduser()] if explicit else []
    cands.append(Path.home() / "Zotero")
    if sys.platform == "win32":
        import os
        appdata = os.environ.get("APPDATA")
        if appdata:
            profiles = Path(appdata) / "Zotero" / "Zotero" / "Profiles"
            if profiles.is_dir():
                cands.extend(p / "zotero" for p in profiles.iterdir() if p.is_dir())
    return next((p.resolve() for p in cands if (p / "zotero.sqlite").is_file()), None)


def cmd_clues(args: argparse.Namespace) -> int:
    pdf = Path(args.pdf).expanduser().resolve()
    if not pdf.is_file():
        print(json.dumps({"error": f"PDF not found: {pdf}"}, ensure_ascii=False), file=sys.stderr)
        return 2
    text = ""
    if shutil.which("pdftotext"):
        try:
            r = subprocess.run(
                ["pdftotext", "-f", "1", "-l", "2", str(pdf), "-"],
                capture_output=True, text=True, timeout=60,
            )
            text = r.stdout or ""
        except (subprocess.SubprocessError, OSError) as exc:
            text = ""
            print(f"WARN: pdftotext failed: {exc}", file=sys.stderr)

    doi_m = DOI_RE.search(text)
    years = YEAR_RE.findall(text[:4000])
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # Heuristic title: longest of the first ~15 lines, >= 25 chars, not a DOI line.
    title_candidate = None
    for ln in lines[:15]:
        if DOI_RE.search(ln):
            continue
        if len(ln) >= 25 and (title_candidate is None or len(ln) > len(title_candidate)):
            title_candidate = ln
    out = {
        "pdf_path": str(pdf),
        "pdf_sha256": None,
        "doi_candidate": doi_m.group(0).rstrip(".,);") if doi_m else None,
        "title_candidate": title_candidate,
        "year_candidates": sorted(set(years)),
        "extraction": "pdftotext first-2-pages" if text else "unavailable",
        "warning": "These are LOOKUP KEYS only. Confirm identity against Zotero before use.",
    }
    try:
        import hashlib
        h = hashlib.sha256()
        with pdf.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        out["pdf_sha256"] = h.hexdigest()
    except OSError:
        pass
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _connect(data_dir: Path) -> sqlite3.Connection:
    uri = "file:" + quote(str(data_dir / "zotero.sqlite").replace("\\", "/"), safe=":/") + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only = ON")
    con.execute("PRAGMA busy_timeout = 5000")
    return con


def _item_payload(con: sqlite3.Connection, data_dir: Path, item_id: int, key: str) -> dict:
    values = {r["fieldName"]: r["value"] for r in con.execute(
        "SELECT f.fieldName, v.value FROM itemData d "
        "JOIN fields f ON f.fieldID=d.fieldID "
        "JOIN itemDataValues v ON v.valueID=d.valueID WHERE d.itemID=?", (item_id,))}
    creators = []
    try:
        creators = [" ".join(filter(None, (r["firstName"], r["lastName"]))) for r in con.execute(
            "SELECT c.firstName, c.lastName FROM itemCreators ic "
            "JOIN creators c ON c.creatorID=ic.creatorID "
            "JOIN creatorTypes ct ON ct.creatorTypeID=ic.creatorTypeID "
            "WHERE ic.itemID=? AND ct.creatorType='author' ORDER BY ic.orderIndex", (item_id,))]
    except sqlite3.OperationalError:
        pass
    collections = [r[0] for r in con.execute(
        "SELECT c.collectionName FROM collectionItems ci JOIN collections c "
        "ON c.collectionID=ci.collectionID WHERE ci.itemID=?", (item_id,))]
    pdfs = []
    for a in con.execute(
        "SELECT i.key, a.path, a.contentType FROM items i "
        "JOIN itemAttachments a ON a.itemID=i.itemID WHERE a.parentItemID=?", (item_id,)):
        if a["contentType"] != "application/pdf":
            continue
        path_field = a["path"] or ""
        pdf_path = None
        if path_field.startswith("storage:"):
            candidate = data_dir / "storage" / a["key"] / path_field.split(":", 1)[-1]
            if candidate.is_file():
                pdf_path = str(candidate)
        pdfs.append({"pdf_key": a["key"], "pdf_path": pdf_path})
    primary = pdfs[0] if pdfs else {}
    pk = primary.get("pdf_key")
    return {
        "zotero_key": key,
        "pdf_key": pk,
        "title": values.get("title"),
        "author": "; ".join(creators),
        "year": (values.get("date", "")[:4] or None),
        "doi": values.get("DOI"),
        "collection": collections[0] if collections else None,
        "pdf_path": primary.get("pdf_path"),
        "zotero_item": f"zotero://select/library/items/{key}",
        "zotero_pdf": f"zotero://open-pdf/library/items/{pk}" if pk else None,
    }


def cmd_match(args: argparse.Namespace) -> int:
    data_dir = discover_data_dir(args.zotero_data_dir)
    if not data_dir:
        print(json.dumps({"error": "zotero.sqlite not found; pass --zotero-data-dir"}, ensure_ascii=False), file=sys.stderr)
        return 2
    if not args.doi and not args.title:
        print(json.dumps({"error": "provide --doi or --title"}, ensure_ascii=False), file=sys.stderr)
        return 2
    try:
        con = _connect(data_dir)
    except sqlite3.Error as exc:
        print(json.dumps({"error": f"Zotero DB unreadable (locked/upgrading?): {exc}"}, ensure_ascii=False), file=sys.stderr)
        return 2
    try:
        matches = []
        method = None
        if args.doi:
            method = "doi-exact"
            rows = con.execute(
                "SELECT i.itemID, i.key FROM items i "
                "JOIN itemData d ON d.itemID=i.itemID "
                "JOIN fields f ON f.fieldID=d.fieldID "
                "JOIN itemDataValues v ON v.valueID=d.valueID "
                "WHERE f.fieldName='DOI' AND lower(v.value)=lower(?)", (args.doi.strip(),)).fetchall()
            matches = [(r["itemID"], r["key"]) for r in rows]
        if not matches and args.title:
            method = "title-exact"
            t = args.title.strip()
            rows = con.execute(
                "SELECT i.itemID, i.key FROM items i "
                "JOIN itemData d ON d.itemID=i.itemID "
                "JOIN fields f ON f.fieldID=d.fieldID "
                "JOIN itemDataValues v ON v.valueID=d.valueID "
                "WHERE f.fieldName='title' AND lower(v.value)=lower(?)", (t,)).fetchall()
            matches = [(r["itemID"], r["key"]) for r in rows]
        if not matches and args.title and not args.strict:
            method = "title-substring"
            t = args.title.strip().lower()
            rows = con.execute(
                "SELECT i.itemID, i.key, v.value AS title FROM items i "
                "JOIN itemData d ON d.itemID=i.itemID "
                "JOIN fields f ON f.fieldID=d.fieldID "
                "JOIN itemDataValues v ON v.valueID=d.valueID "
                "WHERE f.fieldName='title' AND lower(v.value) LIKE ?", (f"%{t}%",)).fetchall()
            matches = [(r["itemID"], r["key"]) for r in rows]
        items = [_item_payload(con, data_dir, iid, key) for iid, key in matches]
        print(json.dumps({
            "method": method,
            "match_count": len(items),
            "status": "UNIQUE" if len(items) == 1 else ("NONE" if not items else "AMBIGUOUS"),
            "items": items,
            "guidance": "One item = use it. Ambiguous = ask user to pick. None = ask user to import into Zotero first.",
        }, ensure_ascii=False, indent=2))
        return 0
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("clues", help="extract candidate keys from a PDF")
    p1.add_argument("--pdf", required=True)
    p1.set_defaults(func=cmd_clues)
    p2 = sub.add_parser("match", help="read-only Zotero lookup")
    p2.add_argument("--doi")
    p2.add_argument("--title")
    p2.add_argument("--zotero-data-dir")
    p2.add_argument("--strict", action="store_true", help="disable title-substring fallback")
    p2.set_defaults(func=cmd_match)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
