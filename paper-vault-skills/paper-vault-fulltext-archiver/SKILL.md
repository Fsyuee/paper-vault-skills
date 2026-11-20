---
name: paper-vault-fulltext-archiver
description: "当用户需要把一篇文献 PDF 转换为可追溯的 Fulltext Markdown 并写入 Obsidian 知识库时使用。优先 MinerU，自动降级 pdftotext，保留原文、身份字段与来源校验和。不翻译、不总结、不改写正文，不写入 Zotero。通常由 paper-vault-orchestrator 调用。"
agent_created: true
version: 1.0.0
---

# Paper Vault Fulltext Archiver

## 职责边界

执行：`可访问的 PDF -> 可用转换器 -> Fulltext Markdown -> frontmatter 身份与来源 -> 校验`。

不执行：中文翻译、精读笔记、文献发现、Zotero 写入。

## 来源完整性

- 原始 PDF 只读。转换器需要可写输入时，在工作临时目录中建立副本；绝不改动原文件。
- 脚本会记录原 PDF 的 SHA-256 并写入 frontmatter 的 `source_pdf_sha256`，作为来源追溯。
- 一次只处理当前请求的单篇文献。只清理本次调用启动的进程与临时文件。
- 转换结果必须非空；检查正文前/中/后是否存在、来源身份是否匹配。截断、乱码或空产物一律不标记为完成。
- 除 frontmatter 外保持抽取正文原样；不翻译、总结、润色或插入模型生成内容。

## 转换脚本

脚本位于本 skill 的 `scripts/`，运行前解析为绝对路径。使用当前环境可用的 Python 3.10+。

```sh
python <abs>/scripts/pdf_to_fulltext.py \
  --pdf "<PDF绝对路径>" \
  --output "<vault>/03fulltext/<collection>/<zotero_key>.md" \
  --vault "<vault 根目录>" \
  --zotero-key "<zotero_key>" \
  --pdf-key "<pdf_key>" \
  --title "<title>" \
  --doi "<doi>" \
  --collection "<collection>" \
  --note-path "02vault/<collection>/<paper>.md" \
  --zotero-item "zotero://select/library/items/<zotero_key>" \
  --zotero-pdf "zotero://open-pdf/library/items/<pdf_key>" \
  --mineru "<MinerU可执行文件路径，可选>" \
  --timeout 300
```

转换器选择（脚本自动处理，勿假设已安装）：
1. 若给出 `--mineru` 或 PATH 中存在 `mineru`，优先使用 MinerU，可获得较可靠的页码映射（`page_mapping: known`）。
2. 否则降级 `pdftotext -layout`，此时 `page_mapping: unknown`，禁止从 Markdown 推断页码。
3. 两者都不可用或产物为空时返回 `FULLTEXT_DEFERRED`，说明缺少的工具，不得用空壳或摘要冒充全文。

## 复用与正式归档

- 归档前先检查 `03fulltext/<collection>/<zotero_key>.md` 是否已存在且有效（frontmatter、`zotero_key`/`pdf_key`、正文、图片链接）。有效则复用，不因笔记问题重新转换。
- 正式路径固定为 `03fulltext/<collection>/<zotero_key>.md`，图片放同目录 `images/<zotero_key>/`。所有写入路径必须位于活动 vault 内。
- Vault 内链接用相对路径与 `/` 分隔符，不写机器绝对路径。
- 页码只有在转换器提供可靠映射时标记 `known`；否则保留 `unknown`。`unknown` 不阻止精读写作者直接访问原 PDF 核验引文，但禁止从全文 Markdown 推断页码。

## 完成状态

只有 PDF 可读、转换成功、正文非空、身份字段齐全时才向编排器报告 `COMPLETE`；否则返回准确的可重试状态（`FULLTEXT_DEFERRED` 等），并附脚本输出的原因。

## 下游衔接（结构化重点的证据层）

Formal Fulltext 是 writer 抽取结构化重点、进而由 graph-builder 建图的**原文证据层**。为保证重点可溯源：

- 保留图表标题、图注、表格、方法/序列名、脑区缩写与统计量原文，不因排版清理而删除；这些是 `claims.source`、`methods`、`regions` 的主要依据。
- `page_mapping: unknown` 时，正文不得推断页码；但原文仍可用于核验概念/方法/脑区是否真实出现，确保结构化重点 source-grounded。
- frontmatter 的 `note_path` 与 `zotero_key` 必须与 writer 写入的精读笔记一致，否则 graph-builder 的 `[[paper/...]]` 回链会断裂。MinerU 不可用时按既有降级路径处理，不要为追求页码映射反复排障。
