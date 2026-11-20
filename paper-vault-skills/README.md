# Paper Vault Skills

一组把**文献 PDF**导入 **Obsidian 知识库**并自动形成**概念级知识图谱**的 [WorkBuddy / Claude Code](https://claude.com/) Agent Skills。

A set of [WorkBuddy / Claude Code](https://claude.com/) Agent Skills that turn **paper PDFs** into an **Obsidian knowledge base** with an automatically generated **concept-level knowledge graph**.

**语言 / Language:** [中文](#zh) · [English](#en)

---

<a id="zh"></a>

## 中文文档

给一篇 PDF，工作流会：只读匹配你在 Zotero 里已有的条目身份 → 抽取可追溯全文 → 生成中文精读笔记与结构化重点 → 由结构化重点物化出概念/方法/脑区节点与双链，让 Obsidian 关系图谱呈现「概念 ↔ 概念、概念 ↔ 文献」的语义网络，而不只是文件标题之间的连线。

> 设计参考：Zotero-Analytical-Workflow-Skills 与 `laminar-paper-reader` 的三声部分离方法。

### 特性

- **Zotero 只读**：只读取条目身份建立 `zotero://` 链接，绝不写入或修改 `zotero.sqlite` 与附件。
- **来源可追溯**：全文保留原 PDF 的 SHA-256；`page_mapping: unknown` 时不臆造页码。
- **结构化重点 → 知识图谱**：LLM 从论文抽取 source-grounded 的 JSON，脚本确定性地生成节点与双链，幂等可重跑。
- **三声部分离**：精读笔记按「作者报告 / 我的评估 / 未决问题」区分每一条主要发现。
- **门控校验**：G0–G4.5 逐门把关，任一门失败即停止下游写入。
- **核心节点保底 + 别名归一**：指定核心概念各自独立成节点；同一实体的多种写法合并，避免节点碎片化。

### 五个 Skill

| Skill | 角色 |
|---|---|
| `paper-vault-orchestrator` | **入口 / 总控**：门控 G0–G4.5、幂等判断、编排其余四个 skill、校验与日志 |
| `paper-vault-metadata-resolver` | 从 PDF 提取 DOI/标题线索，Zotero 只读匹配，产出 `zotero_key` / `pdf_key` 等稳定身份 |
| `paper-vault-fulltext-archiver` | PDF → Fulltext Markdown；MinerU 优先、`pdftotext` 降级；记录来源校验和 |
| `paper-vault-analytical-writer` | 按模板生成中文精读笔记，产出 source-grounded 的结构化重点 JSON |
| `paper-vault-graph-builder` | 由结构化重点幂等建图：节点、共现连边、索引、文献回链；含 `validate_graph.py`（G4.5） |

### 安装

把这些 skill 文件夹放到 WorkBuddy / Claude Code 的 skills 目录之一：

- 用户级：`~/.workbuddy/skills/`（对本机所有项目可用）
- 项目级：`<project>/.workbuddy/skills/`（随项目共享）

每个 skill 是一个含 `SKILL.md` 的文件夹，直接复制即可，无需编译或安装依赖。运行脚本需要 **Python 3.10+**（仅标准库）。

```
~/.workbuddy/skills/
├── paper-vault-orchestrator/
├── paper-vault-metadata-resolver/
├── paper-vault-fulltext-archiver/
├── paper-vault-analytical-writer/
└── paper-vault-graph-builder/
```

### 用法

最省心的方式——把 PDF 路径和 vault 路径一起告诉 Agent：

```
把 /path/to/paper.pdf 导入知识库，vault 用 /path/to/MyVault
```

`paper-vault-orchestrator` 会被触发并按以下流程执行：

1. 初始化/确认 vault 结构（`01knowledge/ 02vault/ 03fulltext/ 模板/`）
2. 提取 DOI/标题 → 在 Zotero 中**只读**匹配（唯一命中继续；未命中则提示先导入）
3. 转换全文 → `03fulltext/<collection>/<zotero_key>.md`
4. 生成精读笔记 → `02vault/<collection>/<paper>.md`，含结构化重点 JSON
5. **[G3.5]** 由结构化重点建图：生成 `01knowledge/{concepts,methods,regions}/` 节点、共现连边与索引，并在笔记「关联概念」区回链
6. **[G4 + G4.5]** 校验身份一致、双向链接、图谱无断链；通过后追加日志

只想刷新已有 vault 的图谱：

```
用 paper-vault-graph-builder 重建 /path/to/MyVault 的知识图谱
```

脚本也可直接调用（先 `--dry-run` 预览）：

```sh
python <skill-dir>/scripts/build_graph.py \
  --vault "<你的 vault 根目录>" \
  --min-citations 2 --dry-run
```

### Vault 结构

```
MyVault/
├── 01knowledge/                 # 知识节点层（由 graph-builder 维护）
│   ├── concepts/<主题>/<节点>.md
│   ├── methods/<主题>/<节点>.md
│   ├── regions/<主题>/<节点>.md
│   └── log.md
├── 02vault/<collection>/        # 中文精读笔记（知识库主体）
├── 03fulltext/<collection>/     # 可追溯全文（证据层，<zotero_key>.md）
└── 模板/论文精读模板.md
```

- 节点类型：概念 `concepts`、方法 `methods`、脑区与网络 `regions`，各含 `_index.md`。
- 三类幂等受管区块（脚本只替换 marker 之间内容，不覆盖人工正文）：
  - 节点 `paper-vault:refs` → 关联文献回链
  - 节点 `paper-vault:related` → 同篇共现实体（构成概念间连边）
  - 笔记 `paper-vault:concepts` → 该文全部实体节点链接
- 真实 Obsidian vault 根通常是本目录的父目录，因此 wikilink 一律带 `paper/` 前缀；路径在 `init_vault.py` 时确定，不写死。

#### 图谱里显示论文标题怎么办

Obsidian 原生关系图谱把每个 md 文件都当节点，文献笔记的文件名即论文标题。文献笔记是知识库主体、不能删，可在 `.obsidian/graph.json` 设搜索过滤器只显示知识点：

```
path:01knowledge -file:_index -file:log
```

⚠️ 这是全局图谱设置，会覆盖 UI 上的自定义过滤；改前先备份 `graph.json`。

### 核心节点与命名（graph-builder v1.1.0+）

- `--min-citations`：少于 N 篇文献引用的实体保留在笔记 JSON 中，但不再生成独立节点/双链（默认 2），避免单篇孤儿节点造成图谱碎片。
- **核心节点保底**：`CANONICAL_ALIAS` / `CORE_NODES` 中声明的核心实体不受阈值裁剪，各自独立成节点。
- **别名归一**：核心实体的多种写法在建图阶段合并到规范节点名（不改笔记里的原文，保持 source-grounded 保真，支持跨类）。
- **孤儿节点清理**：被阈值裁剪后失效的节点文件会被自动删除，避免残留断链。

要新增核心节点，编辑 `paper-vault-graph-builder/scripts/build_graph.py` 顶部的 `CANONICAL_ALIAS` 与 `CORE_NODES`，改完重建图谱（**不要只移动节点文件**，否则 wikilink 会失配）。

### 环境

- Python 3.10+（仅标准库）
- Zotero（数据目录默认 `~/Zotero`，只读访问）
- 全文转换：`pdftotext`（降级必备）或 MinerU（可选，通过 `--mineru` 指定）
- Obsidian（仅查看时需要；vault 本身是普通文件夹）

具体可用性一律以 `paper-vault-orchestrator/scripts/check_env.py` 的探测结果为准。

### 许可

MIT — 见 [LICENSE](LICENSE)。

---

<a id="en"></a>

## English Documentation

Given a PDF, the workflow: read-only matches the identity of an entry you already have in Zotero → extracts traceable full text → generates a Chinese analytical note with structured highlights → materializes concept / method / brain-region nodes and wikilinks from those highlights, so Obsidian's graph view shows a semantic network of "concept ↔ concept, concept ↔ paper" rather than mere connections between file titles.

> Design references: Zotero-Analytical-Workflow-Skills and the three-voice separation method from `laminar-paper-reader`.

### Features

- **Zotero read-only**: Only reads entry identities to build `zotero://` links; never writes to or modifies `zotero.sqlite` or attachments.
- **Traceable sources**: Full text preserves the source PDF's SHA-256; no page numbers are invented when `page_mapping: unknown`.
- **Structured highlights → knowledge graph**: The LLM extracts source-grounded JSON from the paper; scripts deterministically materialize nodes and wikilinks, idempotently re-runnable.
- **Three-voice separation**: Each main finding in the analytical note distinguishes "authors report / analyst assessment / unresolved".
- **Gated validation**: Gates G0–G4.5; any failure stops all downstream writes.
- **Core-node guarantees + alias normalization**: Designated core concepts each get their own node; multiple spellings of one entity are merged to avoid node fragmentation.

### Five Skills

| Skill | Role |
|---|---|
| `paper-vault-orchestrator` | **Entry point / controller**: gates G0–G4.5, idempotency checks, orchestrates the other four skills, validation and logging |
| `paper-vault-metadata-resolver` | Extracts DOI/title clues from the PDF, read-only Zotero matching, emits stable identities such as `zotero_key` / `pdf_key` |
| `paper-vault-fulltext-archiver` | PDF → Fulltext Markdown; MinerU first, `pdftotext` fallback; records the source checksum |
| `paper-vault-analytical-writer` | Generates a Chinese analytical note from the template and emits source-grounded structured-highlights JSON |
| `paper-vault-graph-builder` | Idempotently builds the graph from structured highlights: nodes, co-occurrence edges, indexes, literature back-links; includes `validate_graph.py` (G4.5) |

### Installation

Copy these skill folders into one of the WorkBuddy / Claude Code skills directories:

- User level: `~/.workbuddy/skills/` (available to all projects on this machine)
- Project level: `<project>/.workbuddy/skills/` (shared with the project)

Each skill is simply a folder containing `SKILL.md` — copy it in directly; no compilation or dependency installation is required. Running the scripts needs **Python 3.10+** (standard library only).

```
~/.workbuddy/skills/
├── paper-vault-orchestrator/
├── paper-vault-metadata-resolver/
├── paper-vault-fulltext-archiver/
├── paper-vault-analytical-writer/
└── paper-vault-graph-builder/
```

### Usage

The easiest way — give the Agent both the PDF path and the vault path:

```
Import /path/to/paper.pdf into the knowledge base, vault at /path/to/MyVault
```

This triggers `paper-vault-orchestrator`, which runs:

1. Initialize/confirm the vault structure (`01knowledge/ 02vault/ 03fulltext/ 模板/`)
2. Extract DOI/title → **read-only** match in Zotero (unique hit continues; no hit prompts you to import first)
3. Convert full text → `03fulltext/<collection>/<zotero_key>.md`
4. Generate the analytical note → `02vault/<collection>/<paper>.md`, with structured-highlights JSON
5. **[G3.5]** Build the graph from structured highlights: generate `01knowledge/{concepts,methods,regions}/` nodes, co-occurrence edges and indexes, and write back-links in each note's "related concepts" section
6. **[G4 + G4.5]** Validate identity consistency, bidirectional links and a break-free graph; append the log only on success

To just refresh an existing vault's graph:

```
Use paper-vault-graph-builder to rebuild the knowledge graph of /path/to/MyVault
```

The script can also be called directly (preview with `--dry-run` first):

```sh
python <skill-dir>/scripts/build_graph.py \
  --vault "<your vault root>" \
  --min-citations 2 --dry-run
```

### Vault Structure

```
MyVault/
├── 01knowledge/                 # knowledge-node layer (maintained by graph-builder)
│   ├── concepts/<topic>/<node>.md
│   ├── methods/<topic>/<node>.md
│   ├── regions/<topic>/<node>.md
│   └── log.md
├── 02vault/<collection>/        # Chinese analytical notes (the knowledge base body)
├── 03fulltext/<collection>/     # traceable full text (evidence layer, <zotero_key>.md)
└── 模板/论文精读模板.md
```

- Node types: concepts `concepts`, methods `methods`, brain regions & networks `regions`, each with an `_index.md`.
- Three idempotent managed blocks (the script only replaces content between markers and never overwrites hand-written prose):
  - node `paper-vault:refs` → literature back-links
  - node `paper-vault:related` → other entities co-occurring in the same paper (forming concept-to-concept edges)
  - note `paper-vault:concepts` → links to all entity nodes of that paper
- The real Obsidian vault root is usually the parent of this directory, so wikilinks always carry the `paper/` prefix; the path is fixed at `init_vault.py` time and never hard-coded.

#### Paper titles showing up in the graph?

Obsidian's native graph treats every md file as a node, so the filenames of the analytical notes are paper titles. Those notes are the backbone of the knowledge base and must not be deleted; set a search filter in `.obsidian/graph.json` to show only knowledge nodes:

```
path:01knowledge -file:_index -file:log
```

⚠️ This is a global graph setting and will override any filter you set in the UI — back up `graph.json` first.

### Core Nodes and Naming (graph-builder v1.1.0+)

- `--min-citations`: entities cited by fewer than N papers stay in the note JSON but no longer get standalone nodes / wikilinks (default 2), preventing single-paper orphan nodes from fragmenting the graph.
- **Core-node guarantees**: core entities declared in `CANONICAL_ALIAS` / `CORE_NODES` are exempt from the threshold and each get a standalone node.
- **Alias normalization**: multiple spellings of a core entity are merged into one canonical node name at build time (the original text in notes is left untouched to preserve source-grounded fidelity; cross-category merging is supported).
- **Orphan cleanup**: node files invalidated by threshold pruning are automatically deleted, avoiding leftover broken links.

To add a core node, edit `CANONICAL_ALIAS` and `CORE_NODES` at the top of `paper-vault-graph-builder/scripts/build_graph.py`, then rebuild the graph (**do not just move node files**, or wikilinks will break).

### Requirements

- Python 3.10+ (standard library only)
- Zotero (data directory defaults to `~/Zotero`, read-only access)
- Full-text conversion: `pdftotext` (required fallback) or MinerU (optional, via `--mineru`)
- Obsidian (only needed to view; the vault itself is a plain folder)

Actual availability is always determined by `paper-vault-orchestrator/scripts/check_env.py`.

### License

MIT — see [LICENSE](LICENSE).
