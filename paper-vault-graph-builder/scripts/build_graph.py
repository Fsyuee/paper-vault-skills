#!/usr/bin/env python3
"""Build/maintain the Obsidian knowledge graph from literature notes' machine-readable
'structured highlights' JSON block. Read/write only inside the given vault. Idempotent.

Highlight block contract (in a literature note, a ```json block after a
'结构化重点' heading):

    {
      "schema_version": 1,
      "concepts": [{"name": "预测编码", "why": "..."}],
      "methods":  [{"name": "VASO", "why": "..."}],
      "regions":  [{"name": "dlPFC", "why": "..."}],
      "claims":   [{"claim": "...", "contrast": "...", "source": "...", "stat": "..."}],
      "comparison_dimensions": {"field_strength": "7T"}
    }

Kinds -> node directories (topic subdirectories):
    concepts -> 01knowledge/concepts/<topic>/
    methods  -> 01knowledge/methods/<topic>/
    regions  -> 01knowledge/regions/<topic>/

MIN-CITATIONS: an entity cited by fewer than N literature notes does NOT get a
node file, a co-occurrence edge, or a wikilink in the note's '关联概念' block.
It is still preserved in each note's structured-highlights JSON (data fidelity).
Use --min-citations 1 to restore the legacy "every entity gets a node" behavior.

All wikilinks use the `paper/` prefix because the real Obsidian vault root is
`paper`'s parent. Auto-maintained regions are wrapped in named managed markers,
so repeated runs never duplicate links and never overwrite human-authored prose.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

KINDS = {"concepts": "概念", "methods": "方法", "regions": "脑区与网络"}
BLOCK_RE = re.compile(r"```json\s*\n(.*?)\n```", re.S)

# Named managed blocks: key -> (begin marker, end marker, heading)
MANAGED = {
    "refs": ("<!-- paper-vault:refs:begin -->", "<!-- paper-vault:refs:end -->", "关联文献"),
    "related": ("<!-- paper-vault:related:begin -->", "<!-- paper-vault:related:end -->", "相关节点"),
    "concepts": ("<!-- paper-vault:concepts:begin -->", "<!-- paper-vault:concepts:end -->", "关联概念"),
}

# Topic subdirectories. Rules are evaluated in order; first substring match wins.
SUBDIR_RULES = {
    "concepts": [
        ("预测与学习", ["预测编码", "预测误差", "贝叶斯推断", "前馈与反馈", "层级加工",
                     "输入与输出层分离", "编码与提取", "模式分离", "信息整合", "学习", "标记线学说", "群体编码"]),
        ("感觉与体感", ["触觉", "体感", "topographic", "低阈值机械感受器", "多感觉整合",
                     "振动触觉", "非线性响应", "感觉衰老", "空间特异性", "表面积"]),
        ("认知与注意", ["工作记忆", "注意", "知觉觉察", "意识", "情景记忆", "图像记忆",
                     "选择性注意", "双加工", "跨模态", "自上而下", "知觉与想象", "个体差异",
                     "反应抑制", "抑制控制"]),
        ("血管与生理", ["神经血管耦合", "静脉", "血管", "血流", "热噪声", "基线血管", "灌注"]),
        ("脑网络与连接", ["功能连接", "静息态网络", "方向性连接", "网络", "连接"]),
        ("衰老与疾病", ["衰老", "dystonia", "精神疾病", "可塑性", "跨物种", "老化"]),
        ("信号与统计", ["功率谱", "aperiodic", "periodic", "E/I", "平衡", "噪声协方差",
                     "统计推断", "振荡", "跨频"]),
    ],
    "methods": [
        ("MRI序列与对比", ["VASO", "BOLD", "CBV", "CBF", "CMRO2", "ASL", "MP2RAGE",
                       "MPRAGE", "MP-RAGE", "T2prep", "MAGEC", "SS-SI", "line-scanning",
                       "EPIK", "3D-EPI", "3D-segmented", "qT1", "QSM", "MEMRI",
                       "相位编码映射", "高场 MRI", "7T 高分辨率 MRI", "CBV-fMRI",
                       "层 fMRI", "层fMRI", "laminar", "7T", "3T", "场强", "UHF"]),
        ("采集与加速", ["SMS", "CAIPIRINHA", "slice-GRAPPA", "并行采集", "多带",
                     "同时多层", "SMS/MB"]),
        ("去噪与预处理", ["NORDIC", "噪声", "low-rank", "SVD", "相位去静脉", "模型去静脉",
                      "层化", "柱化", "层特异平滑", "g 因子", "质量评估", "去静脉",
                      "平滑度估计", "空间与时间平滑", "MPPCA", "dwidenoise"]),
        ("统计与建模", ["GLM", "FOOOF", "Welch", "设计矩阵", "HRF", "FIR", "TENT", "PPI",
                     "gPPI", "仿真验证", "Leave-p-Out", "交叉验证", "中介分析", "GLSQ",
                     "参数化", "非参数", "Bayesian", "贝叶斯", "功率谱"]),
        ("电生理与行为", ["EEG", "MEG", "LFP", "电流源密度", "层状电生理", "微神经",
                      "在体电生理", "双光子", "经颅磁刺激", "多体素模式分析", "RDM",
                      "表征差异", "RIDE", "sLORETA", "心理物理", "功能连接分析"]),
        ("软件与工具", ["LayNii", "软件", "工具包", "FSL", "AFNI", "FreeSurfer"]),
    ],
    "regions": [
        ("感觉皮层", ["S1", "S2", "SII", "V1", "V2", "V3", "hMT+", "听觉皮层", "初级听觉",
                   "初级视觉", "视觉皮层", "桶状", "barrel", "area 3b", "area 1", "area 2",
                   "area 3a", "体感皮层", "感觉皮层", "Heschl", "颞平面", "STG", "颞极平面"]),
        ("联合皮层", ["dlPFC", "前额叶", "顶叶", "后顶叶", "顶内沟", "额下回", "前运动皮层",
                   "联合皮层", "角回", "楔前叶", "额顶", "后扣带"]),
        ("皮层下与脑干", ["丘脑", "LGN", "海马", "内嗅皮层", "背柱核", "外侧颈核",
                      "脊髓背角", "周缘皮层", "海马旁皮层", "基底节"]),
        ("脑网络", ["网络", "DMN", "默认模式", "执行控制", "感觉运动网络", "控制网络"]),
    ],
}
FALLBACK = {"concepts": "其他概念", "methods": "其他方法", "regions": "其他脑区"}

# 核心实体规范名 Aliases：把核心概念/方法的多种写法归一到单一规范节点。
# 在建图阶段归一，不改笔记里 source-grounded 的原始实体名（保真）。
# 格式：(kind, 原文名) -> (规范 kind, 规范名)；可跨类。
CANONICAL_ALIAS = {
    ("concepts", "NORDIC"): ("methods", "NORDIC 降噪"),
    ("methods", "NORDIC PCA"): ("methods", "NORDIC 降噪"),
    ("methods", "7T 高分辨率 MRI"): ("methods", "7T"),
}
# 规范节点显示名（覆盖合并后取自首个来源的 label，保证显示清晰）。
CANONICAL_LABEL = {
    ("methods", "NORDIC 降噪"): "NORDIC 降噪",
    ("methods", "7T"): "7T（超高场）",
    ("methods", "3T"): "3T 场强",
}
# 核心节点保底：这些实体无论引用数多少都各自成独立节点（用户明确要求）。
CORE_NODES = {
    ("methods", "NORDIC 降噪"),
    ("methods", "3T"),
    ("methods", "7T"),
    ("methods", "VASO"),
    ("concepts", "预测编码"),
    ("concepts", "工作记忆"),
}


def subdir_for(kind: str, name: str) -> str:
    for subdir, kws in SUBDIR_RULES.get(kind, []):
        if any(kw.lower() in name.lower() for kw in kws):
            return subdir
    return FALLBACK.get(kind, "其他")


def node_relpath(kind: str, name: str) -> str:
    return f"01knowledge/{kind}/{subdir_for(kind, name)}/{safe_name(name)}"


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


def read_highlights(note: Path) -> dict | None:
    text = note.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"结构化重点.*?" + BLOCK_RE.pattern, text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError as e:
        print(f"WARN: invalid JSON highlights in {note.name}: {e}", file=sys.stderr)
        return None


def safe_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "-", name.strip()).strip()


def wikilink(kind: str, name: str, label: str | None = None) -> str:
    return f"[[paper/{node_relpath(kind, name)}|{label or name}]]"


def upsert_section(text: str, key: str, body: str, empty: str = "（暂无）") -> str:
    """Idempotently replace one named managed section."""
    begin, end, heading = MANAGED[key]
    marker = "## " + heading
    payload = f"{begin}\n{body or empty}\n{end}"

    if begin in text and end in text:
        return re.sub(
            re.escape(begin) + r".*?" + re.escape(end),
            lambda _: payload,
            text,
            flags=re.S,
        )

    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == marker:
            j = i + 1
            while j < len(lines) and not lines[j].startswith("## "):
                j += 1
            new_lines = lines[: i + 1] + ["", payload, ""] + lines[j:]
            return "\n".join(new_lines).rstrip() + "\n"

    return text.rstrip() + "\n\n" + marker + "\n\n" + payload + "\n"


def node_body(kind: str, name: str, why: str, today: str) -> str:
    label = KINDS[kind]
    return (
        f'---\ntype: knowledge-node\nnode_kind: {kind[:-1]}\ntitle: "{name}"\n'
        f'aliases: []\ntags:\n  - knowledge-node\n  - {kind[:-1]}\n'
        f'created: "{today}"\n---\n\n# {name}\n\n'
        f"> 知识节点（{label}），由 paper-vault-graph-builder 自动维护；"
        f'带标记的区域请勿手工编辑。\n\n## 节点释义\n\n{why or "（待补充）"}\n'
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the paper-vault knowledge graph")
    ap.add_argument("--vault", required=True, help="vault root (the paper directory)")
    ap.add_argument("--note", help="specific literature note (vault-relative); omit = rebuild all")
    ap.add_argument("--min-citations", type=int, default=2,
                    help="min #literature notes citing an entity to create a node (default 2; 1=legacy)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    vault = Path(args.vault).resolve()
    if not vault.is_dir():
        print(f"ERROR: vault not found: {vault}", file=sys.stderr)
        return 2
    note_filter = (vault / args.note).resolve() if args.note else None
    if note_filter and not note_filter.is_file():
        print(f"ERROR: note not found: {note_filter}", file=sys.stderr)
        return 2

    # entity -> {sources: {rel: label}, why, label}
    entity_map: dict[tuple[str, str], dict] = {}
    # note -> ordered list of entities (for co-occurrence and note back-links)
    note_entities: dict[str, list[tuple[str, str]]] = {}
    cooc: dict[tuple[str, str], dict[tuple[str, str], int]] = defaultdict(
        lambda: defaultdict(int)
    )

    notes = [note_filter] if note_filter else sorted((vault / "02vault").rglob("*.md"))
    for note in notes:
        if not note.is_file():
            continue
        hl = read_highlights(note)
        if not hl:
            continue
        fm = parse_fm(note.read_text(encoding="utf-8", errors="ignore"))
        label = fm.get("title") or note.stem
        rel = str(note.relative_to(vault))
        ents: list[tuple[str, str]] = []
        for kind in KINDS:
            for ent in (hl.get(kind) or []):
                raw = ent.get("name", "") if isinstance(ent, dict) else str(ent)
                name = safe_name(raw)
                if not name:
                    continue
                # 规范名归一（跨类）：核心实体多种写法合并到单一节点
                kind, name = CANONICAL_ALIAS.get((kind, name), (kind, name))
                d = entity_map.setdefault((kind, name), {"sources": {}, "why": "", "label": name})
                d["sources"][rel] = label
                if isinstance(ent, dict):
                    if ent.get("why") and not d["why"]:
                        d["why"] = ent["why"]
                    if ent.get("label") and d["label"] == name:
                        d["label"] = ent["label"]
                ents.append((kind, name))
        note_entities[rel] = ents
        unique = sorted(set(ents))
        for a_i, a in enumerate(unique):
            for b in unique[a_i + 1 :]:
                cooc[a][b] += 1
                cooc[b][a] += 1

    # 应用规范显示名（覆盖合并后取自首个来源的 label）
    for key, label in CANONICAL_LABEL.items():
        if key in entity_map:
            entity_map[key]["label"] = label

    # MIN-CITATIONS filtering: only well-supported entities get nodes / edges / links.
    # 核心节点(CORE_NODES)保底：无论引用数多少都各自成独立节点。
    kept = {k for k, v in entity_map.items() if len(v["sources"]) >= max(1, args.min_citations)}
    kept |= {k for k in CORE_NODES if k in entity_map}
    dropped = {k: len(v["sources"]) for k, v in entity_map.items() if k not in kept}

    today = date.today().isoformat()
    created = updated = 0
    for (kind, name) in sorted(kept):
        info = entity_map[(kind, name)]
        node_path = vault / (node_relpath(kind, name) + ".md")
        backlinks = "\n".join(
            f"- [[paper/{rel[:-3]}|{label}]]" for rel, label in sorted(info["sources"].items())
        )
        related = sorted(
            ((k2, n2), cnt) for (k2, n2), cnt in cooc.get((kind, name), {}).items()
            if (k2, n2) in kept
        )
        related.sort(key=lambda kv: (-kv[1], kv[0][0], kv[0][1]))
        related_lines = [
            f"- {KINDS[k2]} {wikilink(k2, n2, entity_map[(k2, n2)]['label'])} （共现 {cnt} 篇）"
            for (k2, n2), cnt in related
        ]
        if node_path.exists():
            if not args.dry_run:
                txt = node_path.read_text(encoding="utf-8")
                txt = upsert_section(txt, "refs", backlinks)
                txt = upsert_section(txt, "related", "\n".join(related_lines))
                node_path.write_text(txt, encoding="utf-8")
            updated += 1
        else:
            if not args.dry_run:
                node_path.parent.mkdir(parents=True, exist_ok=True)
                txt = node_body(kind, info["label"], info["why"], today)
                txt = upsert_section(txt, "refs", backlinks)
                txt = upsert_section(txt, "related", "\n".join(related_lines))
                node_path.write_text(txt, encoding="utf-8")
            created += 1

    # ORPHAN CLEANUP: delete auto-managed node files no longer in `kept`.
    # Only removes files carrying the managed banner (safe: never touches hand-authored notes).
    orphans_removed = []
    if not args.dry_run:
        for kind in KINDS:
            kdir = vault / "01knowledge" / kind
            if not kdir.is_dir():
                continue
            for p in kdir.rglob("*.md"):
                if p.stem in ("_index", "_concepts_index"):
                    continue
                name = p.stem
                if (kind, name) in kept:
                    continue
                try:
                    body = p.read_text(encoding="utf-8")
                except OSError:
                    continue
                if "paper-vault-graph-builder 自动维护" not in body:
                    continue  # 非自动维护文件，绝不删除
                p.unlink()
                orphans_removed.append(str(p.relative_to(vault)))

    # Write managed entity links back into each literature note's '关联概念' section (kept only).
    notes_updated = 0
    for rel, ents in sorted(note_entities.items()):
        note = vault / rel
        if not note.is_file():
            continue
        lines_by_kind = []
        for kind in KINDS:
            names = sorted({n for k, n in ents if k == kind and (k, n) in kept})
            if names:
                links = "、".join(wikilink(kind, n, entity_map[(kind, n)]["label"]) for n in names)
                lines_by_kind.append(f"- **{KINDS[kind]}**：{links}")
        if args.dry_run:
            continue
        txt = note.read_text(encoding="utf-8")
        new_txt = upsert_section(txt, "concepts", "\n".join(lines_by_kind))
        if new_txt != txt:
            note.write_text(new_txt, encoding="utf-8")
            notes_updated += 1

    # Per-kind _index.md: recurse subdirectories, include every on-disk node file.
    if not args.dry_run:
        for kind in KINDS:
            kdir = vault / "01knowledge" / kind
            kdir.mkdir(parents=True, exist_ok=True)
            idx = kdir / "_index.md"
            node_files = [p for p in kdir.rglob("*.md")
                          if p.stem not in ("_index", "_concepts_index")]
            rows = []
            for p in sorted(node_files):
                name = p.stem
                info = entity_map.get((kind, name))
                if info:
                    label, count = info["label"], len(info["sources"])
                else:
                    label, count = name, 0
                    fm_title = parse_fm(p.read_text(encoding="utf-8", errors="ignore")).get("title")
                    if fm_title and fm_title != name:
                        label = fm_title
                rows.append(f"| {wikilink(kind, name, label)} | {count} |")
            header = (
                f'---\ntype: knowledge-index\ntitle: "{KINDS[kind]}索引"\n'
                f"tags: [knowledge-index]\n---\n\n# {KINDS[kind]}索引\n\n"
                f"> 由 paper-vault-graph-builder 自动维护，列出本类全部知识节点（按主题分目录）。\n\n"
                f"| 节点 | 关联文献数 |\n| --- | --- |\n"
            )
            idx.write_text(header + "\n".join(rows) + "\n", encoding="utf-8")

    print(json.dumps({
        "status": "OK",
        "vault": str(vault),
        "notes_with_highlights": len(note_entities),
        "min_citations": max(1, args.min_citations),
        "entities_total": len(entity_map),
        "entities_kept": len(kept),
        "entities_dropped": len(dropped),
        "dropped_detail": sorted([f"{k[0]}/{k[1]}({c})" for k, c in dropped.items()]),
        "cooccurrence_edges": sum(1 for a, nbrs in cooc.items() for b in nbrs if a < b and a in kept and b in kept),
        "nodes_created": created,
        "nodes_updated": updated,
        "orphans_removed": orphans_removed,
        "notes_updated": notes_updated,
        "dry_run": args.dry_run,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
