#!/usr/bin/env python3
"""Convert one PDF to Fulltext Markdown using an actually-available converter.

Priority: MinerU (explicit --mineru or PATH) -> pdftotext fallback.
The source PDF is read-only. The converter writes to a staging directory first;
the resulting Markdown is promoted to the canonical 03fulltext path only when
non-empty and identity-checked. No translated/summarized/LLM-generated body text.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FM = """---
type: literature-fulltext
title: "{title}"
zotero_key: "{zotero_key}"
pdf_key: "{pdf_key}"
doi: "{doi}"
collection: "{collection}"
note_path: "{note_path}"
fulltext_path: "{fulltext_path}"
zotero_item: "{zotero_item}"
zotero_pdf: "{zotero_pdf}"
source_type: "{source_type}"
page_mapping: {page_mapping}
source_pdf_sha256: "{sha256}"
---

"""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def mineru_convert(exe: str, pdf: Path, workdir: Path, timeout: int) -> tuple[str | None, str]:
    out_dir = workdir / "mineru_out"
    cmd = [exe, "parse", str(pdf), "--output", str(out_dir), "--format", "markdown",
           "--pages", "all", "--wait", str(timeout)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 30)
    except (subprocess.SubprocessError, OSError) as exc:
        return None, f"mineru invocation failed: {exc}"
    if r.returncode != 0:
        return None, f"mineru exit {r.returncode}: {(r.stderr or r.stdout)[-500:]}"
    mds = sorted(out_dir.rglob("*.md"), key=lambda p: p.stat().st_size, reverse=True) if out_dir.exists() else []
    if not mds:
        return None, "mineru produced no .md output"
    return mds[0].read_text(encoding="utf-8", errors="replace"), "mineru"


def pdftotext_convert(pdf: Path, workdir: Path, timeout: int) -> tuple[str | None, str]:
    exe = shutil.which("pdftotext")
    if not exe:
        return None, "pdftotext not available"
    out = workdir / "pdftotext.md"
    try:
        r = subprocess.run([exe, "-layout", str(pdf), str(out)],
                           capture_output=True, text=True, timeout=timeout)
    except (subprocess.SubprocessError, OSError) as exc:
        return None, f"pdftotext failed: {exc}"
    if r.returncode != 0 or not out.is_file():
        return None, f"pdftotext exit {r.returncode}: {r.stderr[-300:]}"
    return out.read_text(encoding="utf-8", errors="replace"), "pdftotext"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--output", required=True, help="canonical 03fulltext/<collection>/<key>.md target")
    ap.add_argument("--vault", help="vault root; when given, frontmatter fulltext_path is written vault-relative")
    ap.add_argument("--mineru", help="path to MinerU executable; empty = PATH")
    ap.add_argument("--title", default="")
    ap.add_argument("--zotero-key", required=True)
    ap.add_argument("--pdf-key", default="")
    ap.add_argument("--doi", default="")
    ap.add_argument("--collection", default="未分类")
    ap.add_argument("--note-path", default="")
    ap.add_argument("--zotero-item", default="")
    ap.add_argument("--zotero-pdf", default="")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--no-mineru", action="store_true", help="force pdftotext fallback")
    args = ap.parse_args()

    pdf = Path(args.pdf).expanduser().resolve()
    if not pdf.is_file():
        print(json.dumps({"status": "FAIL", "error": f"PDF not found: {pdf}"}, ensure_ascii=False), file=sys.stderr)
        return 2
    digest = sha256(pdf)
    fulltext_path = Path(args.output).expanduser().resolve()
    fulltext_path.parent.mkdir(parents=True, exist_ok=True)

    body, source_type, notes = None, None, []
    mineru_exe = args.mineru or shutil.which("mineru")
    with tempfile.TemporaryDirectory(prefix="paper-vault-") as td:
        workdir = Path(td)
        if mineru_exe and not args.no_mineru:
            body, source_type = mineru_convert(mineru_exe, pdf, workdir, args.timeout)
            if body is None:
                notes.append(source_type)
                source_type = None
        if body is None:
            body, source_type = pdftotext_convert(pdf, workdir, args.timeout)
            notes.append("page_mapping unknown after pdftotext")
    if body is None or not body.strip():
        print(json.dumps({"status": "FULLTEXT_DEFERRED", "error": "no converter produced non-empty text",
                          "notes": notes}, ensure_ascii=False), file=sys.stderr)
        return 3

    page_mapping = "known" if source_type == "mineru" else "unknown"
    # Frontmatter paths must be vault-relative for portability and validation.
    try:
        fm_fulltext_path = fulltext_path.relative_to(Path(args.vault).expanduser().resolve()).as_posix() \
            if args.vault else str(fulltext_path)
    except ValueError:
        fm_fulltext_path = str(fulltext_path)
    header = FM.format(
        title=args.title.replace('"', "'"),
        zotero_key=args.zotero_key,
        pdf_key=args.pdf_key,
        doi=args.doi,
        collection=args.collection,
        note_path=args.note_path,
        fulltext_path=fm_fulltext_path,
        zotero_item=args.zotero_item,
        zotero_pdf=args.zotero_pdf,
        source_type=source_type,
        page_mapping=page_mapping,
        sha256=digest,
    )
    fulltext_path.write_text(header + body, encoding="utf-8")
    print(json.dumps({
        "status": "COMPLETE",
        "fulltext_path": str(fulltext_path),
        "source_type": source_type,
        "page_mapping": page_mapping,
        "char_count": len(body),
        "source_pdf_sha256": digest,
        "notes": notes,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
