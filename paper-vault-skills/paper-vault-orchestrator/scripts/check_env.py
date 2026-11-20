#!/usr/bin/env python3
"""Check the local environment for the paper-to-vault workflow. Read-only.

Emits a JSON envelope describing what is actually available so the agent can
plan the ingest without guessing paths or tools. No capability is assumed.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path


def find_zotero_data_dir(explicit: str | None) -> Path | None:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    candidates.append(Path.home() / "Zotero")
    if sys.platform == "win32":
        appdata = Path(__import__("os").environ.get("APPDATA", ""))
        profiles = appdata / "Zotero" / "Zotero" / "Profiles"
        if profiles.is_dir():
            candidates.extend(p / "zotero" for p in profiles.iterdir() if p.is_dir())
    for p in candidates:
        try:
            if (p / "zotero.sqlite").is_file():
                return p.resolve()
        except OSError:
            continue
    return None


def probe(cmd: str) -> str | None:
    return shutil.which(cmd)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vault", help="vault root to report; does not create anything")
    ap.add_argument("--zotero-data-dir", help="override Zotero data directory")
    ap.add_argument("--mineru", help="explicit path to the MinerU executable")
    args = ap.parse_args()

    zdata = find_zotero_data_dir(args.zotero_data_dir)
    zdb_ok = False
    item_count = None
    if zdata:
        try:
            uri = "file:" + str((zdata / "zotero.sqlite").resolve()).replace(" ", "%20") + "?mode=ro"
            con = sqlite3.connect(uri, uri=True, timeout=3)
            con.execute("PRAGMA query_only = ON")
            try:
                item_count = con.execute("SELECT count(*) FROM items").fetchone()[0]
                zdb_ok = True
            finally:
                con.close()
        except sqlite3.Error:
            zdb_ok = False

    mineru = args.mineru or probe("mineru")
    if not mineru:
        # Probe common conda locations without assuming an environment name.
        conda_bases = [Path.home() / "miniconda3", Path.home() / "anaconda3", Path("/opt/conda")]
        for base in conda_bases:
            envs = base / "envs"
            if envs.is_dir():
                for env in sorted(envs.iterdir()):
                    candidate = env / "bin" / "mineru"
                    if candidate.is_file():
                        mineru = str(candidate)
                        break
            if mineru:
                break
    mineru_exists = bool(mineru and Path(mineru).is_file()) if mineru and "/" in mineru else bool(mineru)

    env = {
        "vault_root": str(Path(args.vault).expanduser().resolve()) if args.vault else None,
        "vault_exists": bool(args.vault and Path(args.vault).expanduser().is_dir()),
        "zotero": {
            "data_dir": str(zdata) if zdata else None,
            "sqlite_readable": zdb_ok,
            "item_count": item_count,
            "note": "write access is NOT performed by this workflow; Zotero is read-only here",
        },
        "tools": {
            "pdftotext": probe("pdftotext"),
            "mineru": mineru,
            "mineru_exists": mineru_exists,
            "uv": probe("uv"),
            "uvx": probe("uvx"),
            "zotero_cli": probe("zotero-cli"),
            "zotero_cli_note": "can be invoked via: uvx --from zotero-mcp-server zotero-cli",
        },
        "python": sys.version.split()[0],
    }
    print(json.dumps(env, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
