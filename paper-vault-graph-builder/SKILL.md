---
name: paper-vault-graph-builder
description: "当需要从 Obsidian 知识库中文献笔记的结构化重点，自动构建/更新知识图谱（概念、方法、脑区与网络节点及其互链）时使用。由 paper-vault-orchestrator 在精读笔记生成后调用；也可单独对已有 vault 重建图谱。仅读写指定 vault 内的 Markdown，幂等，不写入 Zotero。"
agent_created: true
version: 1.1.0
---

# Paper Vault Graph Builder

## 目的

把精读笔记里的**结构化重点**转成 Obsidian 里真正可见的**知识节点网络**，使关系图谱呈现"概念 ↔ 概念、概念 ↔ 文献"的语义结构，而不是只有文件名/标题之间的连线。

这是"抓取重点 → 形成图谱"闭环中的确定性执行层：LLM 负责从论文里抽取结构化重点（JSON），本 skill 的脚本负责把这个 JSON 稳定地物化成节点与双链。

## 何时调用

- 由 `paper-vault-orchestrator` 在 G3（精读笔记写入）之后、G4（校验）之前调用，作为 G3.5。
- 用户单独要求"重建/刷新知识图谱""把概念层建起来""图谱没显示概念"时，对已有 vault 直接运行。
- 新增或更新了带结构化重点块的笔记后，需要刷新节点回链。

## 输入契约：结构化重点块

脚本只认精读笔记中"结构化重点"标题之后的第一个 ```json 代码块。契约如下：

```json
{
  "schema_version": 1,
  "concepts": [{"name": "预测编码", "why": "以预测误差最小化解释皮层加工", "label": "预测编码"}],
  "methods":  [{"name": "VASO", "why": "基于血流舒张的层依赖 BOLD 对照", "label": "VASO"}],
  "regions":  [{"name": "dlPFC", "why": "背外侧前额叶，工作记忆执行控制核心", "label": "背外侧前额叶 dlPFC"}],
  "claims":   [{"claim": "...", "contrast": "...", "source": "Fig.3", "stat": "t(18)=3.1, p<.01"}],
  "comparison_dimensions": {"field_strength": "7T"}
}
```

- `name` 必填，作为节点文件名与双链目标（非法文件名字符会被替换为 `-`）。
- `why` 可选，写入节点的"节点释义"。
- `label` 可选，作为双链显示名（缺省用 `name`）。
- `claims` 与 `comparison_dimensions` 供 writer/校验参考，脚本本身不建 claim 节点（避免图谱爆炸）；重点通过概念/方法/脑区节点体现。

结构化重点块由 `paper-vault-analytical-writer` 按模板产出，写入 `## 结构化重点` 章节。

## 输出：图谱的三类节点

| 键 | 节点目录 | node_kind | 说明 |
|---|---|---|---|
| `concepts` | `01knowledge/concepts/` | concept | 复用已存在的概念 MOC 笔记，只刷新受管区块 |
| `methods` | `01knowledge/methods/` | method | VASO、层 fMRI、MP2RAGE 等 |
| `regions` | `01knowledge/regions/` | region | dlPFC、海马、默认网络等 |

每个节点包含三段：

1. **节点释义**（人工/LLM 撰写，`why` 初始化）；
2. **关联文献**（`paper-vault:refs` 受管区块）：所有提到该实体的文献双链；
3. **相关节点**（`paper-vault:related` 受管区块）：与本文其他实体共现的节点，构成概念间连边。

同时：
- 每类维护一个 `_index.md` 索引；
- 每篇文献笔记的 `## 关联概念` 章节写入 `paper-vault:concepts` 受管区块，回链全部实体节点。

所有 wikilink 一律带 `paper/` 前缀（真实 Obsidian vault 根是 `paper` 的父目录）。

## 图谱精简：最少引用阈值与规范节点

- `--min-citations N`（默认 2）：被少于 N 篇文献引用的实体**不生成节点/边/双链**，但仍保留在各笔记的结构化重点 JSON 中（数据保真）。设 1 可回到"每个实体都建节点"的旧行为。
- `CORE_NODES`：用户明确要求的核心节点（当前为 `NORDIC 降噪`、`3T`、`7T`、`VASO`、`预测编码`、`工作记忆`）**无论引用数多少都各自成独立节点**，不受阈值裁剪。
- `CANONICAL_ALIAS`：核心实体的多种写法在建图阶段归一到单一规范节点，不改笔记里的 source-grounded 原文。当前规则：
  - `concepts/NORDIC` + `methods/NORDIC PCA` → `methods/NORDIC 降噪`
  - `methods/7T 高分辨率 MRI` → `methods/7T`
  - 新增核心实体写法时，在此字典追加 `(kind, 原文名) -> (规范 kind, 规范名)`，并在 `CANONICAL_LABEL` 设置显示名。注意跨类归一会改变节点的 `kind` 与子目录。
- 目录归类由 `SUBDIR_RULES` 关键词表决定（首个命中胜出），未命中落入各类"其他"桶。

## 幂等与安全

- 三类受管区块各有独立 marker（`refs` / `related` / `concepts`）。脚本只替换 marker 之间或对应标题下的内容，绝不触碰人工撰写的正文。
- 对旧版概念 MOC 中手写的"关联文献"章节，脚本会用受管区块升级替换（不会重复叠加）。
- **孤儿节点清理**：不再属于 `kept` 的自动维护节点文件会被删除（仅删除带 `paper-vault-graph-builder 自动维护` 标记的文件，绝不删手写文件），避免阈值裁剪后残留断链。
- 可重复运行：节点已存在则更新回链，不重复创建；索引每次全量重写。
- 仅读写 `--vault` 指定目录；不存在则报错退出。

## Obsidian 图谱只显示知识点（可选配置）

Obsidian 原生关系图谱把每个 md 文件都当节点，因此 31 篇文献笔记会以"论文题目"形式出现在图里。若只想看知识点网络，在 vault 根的 `.obsidian/graph.json` 设置 `search` 过滤器：

```json
"search": "path:01knowledge -file:_index -file:log"
```

文献笔记文件本身保留（是知识库主体、且知识点通过回链引用它们），只是不在关系图谱中显示。⚠️ 该过滤器是全局图谱设置，会覆盖用户此前在 UI 上的自定义过滤。

## 用法

全库重建（默认）：

```sh
python <skill-dir>/scripts/build_graph.py \
  --vault "<你的 vault 根目录>"
```

只刷新一篇笔记涉及的节点：

```sh
python .../build_graph.py \
  --vault "<vault>" \
  --note "02vault/wm/论文名.md"
```

预演（不写盘，检查会创建/更新多少节点）：

```sh
python .../build_graph.py --vault "<vault>" --dry-run
```

脚本以 JSON 输出统计：`notes_with_highlights`、`entities_total/kept/dropped`、`cooccurrence_edges`、`nodes_created`、`nodes_updated`、`orphans_removed`、`notes_updated`。

## 校验衔接

建图后由 orchestrator 的 G4.5 检查：

- 每个受管区块成对闭合、无重复 marker；
- 所有 `[[paper/...]]` 双链目标文件真实存在（无断链）；
- `_index.md` 与节点文件一一对应。

发现断链先补节点或修正 `name`，再重跑本脚本，不要在 Obsidian 里手改受管区块。
