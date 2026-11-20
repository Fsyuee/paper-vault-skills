---
name: paper-vault-orchestrator
description: "当用户提供一篇文献 PDF 并希望把它写入 Obsidian 知识库时使用。总控 skill：从 PDF 出发，编排元数据解析与 Zotero 只读关联、全文抽取、中文精读笔记生成与校验。触发词：把这篇 PDF 导入知识库、这篇文献入库、paper to vault、导入 zotero 和 obsidian。不负责下载论文，也不写入 Zotero 数据库。"
agent_created: true
version: 1.0.0
---

# Paper Vault Orchestrator

## 目的与边界

这是"**一篇 PDF → Obsidian 知识库**"工作流的控制平面。它编排四个专职 skill，不重复实现它们的逻辑：

1. `paper-vault-metadata-resolver` — 从 PDF 提取检索线索，在 Zotero 中只读匹配，产出可信身份。
2. `paper-vault-fulltext-archiver` — PDF → 正式 Fulltext Markdown。
3. `paper-vault-analytical-writer` — 按模板生成中文精读笔记，并产出结构化重点 JSON 块。
4. `paper-vault-graph-builder` — 由结构化重点建知识节点与双链，形成 Obsidian 知识图谱。

硬边界：
- **Zotero 只读**：本工作流不写入 Zotero。用户自行把文献导入 Zotero；skill 只读取条目身份用于建立 `zotero://` 链接。绝不修改 `zotero.sqlite`、不移动或覆盖附件。
- **起点是用户给定的 PDF**：不搜索、不下载新论文。除非用户另有明确要求。
- **vault 路径运行时确定**：绝不写死本机路径。每次运行先向用户确认或从当前工作区解析 vault 根目录。
- **原文不伪造**：全文只来自真实转换；引用只来自真实正文。

## 前置：解析 vault 与共享资源

1. 确定 `vault_root`：用户显式指定 > 当前 agent 工作区中包含 `.obsidian` 或 `02vault/` 的目录 > 询问用户。不要猜测。
2. 若 vault 尚未初始化，运行共享脚本 `scripts/init_vault.py --vault <root>` 创建 `01knowledge/ 02vault/ 03fulltext/ 模板/`。它只补建缺失目录，不改动已有文件。
3. 共享脚本均位于**本 skill 目录**的 `scripts/` 下；其他 skill 通过相对路径 `../paper-vault-orchestrator/scripts/` 复用。所有相对路径先解析为绝对路径再执行。
4. 需要环境信息时运行 `scripts/check_env.py`（只读），确认 pdftotext / MinerU / Zotero 数据目录的真实可用性；不要假设任何工具已安装。

## 稳定身份

`zotero_key`（父条目 key）是唯一稳定身份；`pdf_key` 标识附件。标题仅用于人工核对。所有路径与链接必须由这两个 key 派生，禁止用标题猜 key，禁止把附件 key 当父 key。

## 工作流门控

按顺序执行；任一门失败即停止下游写入，并给出准确的可重试状态，不得把部分结果标为成功。

```text
给定 PDF
  -> [G0] vault 与身份解析（vault_root + PDF 存在）
  -> [G1] 元数据与 Zotero 只读匹配 -> zotero_key / pdf_key / collection
  -> [G2] Fulltext：已有则复用校验，缺失才转换 -> 03fulltext/<collection>/<zotero_key>.md
  -> [G3] 精读笔记：按模板新建或就地补全，产出结构化重点 JSON -> 02vault/<collection>/<paper>.md
  -> [G3.5] 建图：结构化重点 -> 知识节点/索引/双链（幂等）
  -> [G4] 校验：双向链接、身份一致、正文与图片
  -> [G4.5] 图谱校验：受管区块闭合、双链无断链、索引一致
  -> 追加日志 01knowledge/log.md（人类可读，中文）
```

各门细则：

- **G1**：调用 `paper-vault-metadata-resolver`。匹配结果 `UNIQUE` 才继续；`AMBIGUOUS` 让用户选择；`NONE` 时要求用户先把文献导入 Zotero，或用 `--no-zotero` 模式以本地伪 key 继续（此时不生成 Zotero 链接，并明确标注）。
- **G2**：调用 `paper-vault-fulltext-archiver`。若 `03fulltext/` 下对应 `zotero_key` 的文件已存在且 frontmatter、正文、图片有效，直接复用，不得因笔记模板问题重新转换。转换只做一次。
- **G3**：调用 `paper-vault-analytical-writer`。新建笔记从模板起步；更新已有笔记就地调整，不制造重复笔记。必须写出 `## 结构化重点` 的合法 JSON 块（三类实体 + claims + comparison_dimensions），并按"作者报告/我的评估/未决问题"三声部分离书写研究结论。
- **G3.5**：调用 `paper-vault-graph-builder`：
  ```sh
  python ../paper-vault-graph-builder/scripts/build_graph.py --vault <root> --note <note_rel>
  ```
  仅含结构化重点的笔记即被解析为节点；可先 `--dry-run` 预览。结构化重点缺失或 JSON 非法时，先回 G3 修正，不得跳过建图直接声称完成图谱。
- **G4**：运行 `scripts/validate_vault.py --vault <root> --note <rel> --fulltext <rel> --zotero-key <key>`。任何 ERROR 都必须修复后重跑；无自动校验器时执行等效人工检查并声明。
- **G4.5**：图谱校验。检查 (1) 每个知识节点的 `paper-vault:refs` / `paper-vault:related` 与文献笔记的 `paper-vault:concepts` 区块起止 marker 成对且无重复；(2) 所有 `[[paper/...]]` 双链目标文件存在、无断链；(3) 各 `01knowledge/<kind>/_index.md` 与节点文件一一对应。可用 `scripts/validate_graph.py --vault <root>` 自动检查；失败则修正结构化重点或重跑 G3.5，禁止手工编辑受管区块。

## 增量与幂等

| 观察到的状态 | 应采取的动作 |
|---|---|
| Note + Fulltext 均有效且身份一致、笔记符合模板 | `ALREADY_COMPLETE`，不重复处理 |
| Fulltext 有效但 Note 缺失/不合模板 | 只跑 G3 |
| Note 存在但 Fulltext 缺失/无效 | 只跑 G2，再回填 G3 的全文链接 |
| 身份未解析 | 从 G1 起按需执行 |
| Fulltext 转换能力不可用 | 记为 `FULLTEXT_DEFERRED`，说明缺少的工具，不伪造正文 |

## 目录约定（相对于 vault_root）

- 精读笔记：`02vault/<collection>/<paper>.md`
- 正式全文：`03fulltext/<collection>/<zotero_key>.md`
- 全文图片：`03fulltext/<collection>/images/<zotero_key>/`
- 知识节点：`01knowledge/concepts/`（概念）、`01knowledge/methods/`（方法）、`01knowledge/regions/`（脑区与网络），各含 `_index.md`
- 日志：`01knowledge/log.md`
- 模板：`模板/论文精读模板.md`（缺失时用 analytical-writer 自带 asset）

所有写入路径必须位于活动 vault 内；Obsidian 链接使用 `/` 分隔符与 vault 相对路径。

## 日志与完成

全部校验通过后，向 `01knowledge/log.md` 追加一条中文事件：日期、文献标题、`zotero_key`、Fulltext 状态、Note 状态、图谱节点数、校验结果。只追加，不重写历史。

完成的定义：G4 与 G4.5 均 PASS，Note/Fulltext 双向入口与身份字段一致，且结构化重点已建图为可跳转的知识节点。若 Fulltext 缺失或结构化重点为空，必须如实报告部分状态，不得声称全文或图谱已验证。
