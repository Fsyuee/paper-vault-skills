#!/usr/bin/env python3
"""Create a canonical Obsidian vault layout for the paper-to-vault workflow.

Creates only missing directories and a config file. Never modifies or deletes
existing research files. Prints a JSON summary of what was created vs present.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

DIRS = [
    "01knowledge",
    "01knowledge/.meta",
    "02vault",
    "03fulltext",
    "模板",
]
CONFIG_TEMPLATE = """# paper-vault local configuration (safe to edit; do not commit personal paths)
[vault]
root = "{root}"

[zotero]
# Leave empty to auto-discover ~/Zotero, or set an explicit data directory.
data_dir = ""

[tools]
# MinerU executable path. Empty = rely on PATH/PDFTOTEXT fallback.
mineru = ""
# Prefer MinerU when available; fall back to pdftotext automatically.
prefer_mineru = true
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vault", required=True, help="vault root directory to initialize")
    ap.add_argument("--force-config", action="store_true", help="overwrite an existing config file")
    args = ap.parse_args()

    root = Path(args.vault).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)

    created, existing = [], []
    for rel in DIRS:
        d = root / rel
        if d.exists():
            existing.append(rel)
        else:
            d.mkdir(parents=True, exist_ok=True)
            created.append(rel)

    cfg_path = root / "01knowledge" / ".meta" / "paper-vault.toml"
    if cfg_path.exists() and not args.force_config:
        cfg_status = "exists"
    else:
        cfg_status = "overwritten" if cfg_path.exists() else "created"
        cfg_path.write_text(CONFIG_TEMPLATE.format(root=str(root)), encoding="utf-8")

    index = root / "02vault" / "_index.md"
    if not index.exists():
        index.write_text(
            "# 文献精读索引\n\n由 paper-vault 工作流维护。每篇文献的精读笔记位于本目录或子文件夹中。\n",
            encoding="utf-8",
        )

    print(json.dumps({
        "vault_root": str(root),
        "created_dirs": created,
        "existing_dirs": existing,
        "config": str(cfg_path),
        "config_status": cfg_status,
        "note": "No existing research files were modified or deleted.",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
