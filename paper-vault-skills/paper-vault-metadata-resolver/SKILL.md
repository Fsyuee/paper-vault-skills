---
name: paper-vault-metadata-resolver
description: "当用户提供一篇文献 PDF、需要提取书目信息并在 Zotero 中只读匹配条目身份时使用。产出 zotero_key/pdf_key/collection/title/author/year/doi 与 zotero:// 链接，供下游全文与精读笔记使用。此 skill 不写入 Zotero、不翻译、不总结正文。通常由 paper-vault-orchestrator 调用。"
agent_created: true
version: 1.0.0
---

# Paper Vault Metadata Resolver

## 职责

把一篇本地 PDF 解析为**可信的书目身份**。本工作流假设用户已自行把文献导入 Zotero，因此权威元数据来自 Zotero 条目，PDF 文本只提供检索线索。

执行：`PDF -> 检索线索(DOI/标题) -> Zotero 只读匹配 -> 稳定身份 + URI`。

不执行：写入 Zotero、下载论文、中文翻译、正文总结。

## 核心原则

- **Zotero 条目是权威**：标题仅用于人工核对，绝不作为主键。`zotero_key`（父条目）是唯一稳定身份，`pdf_key` 是附件 key。禁止用标题猜 key，禁止把附件 key 当父 key。
- **只读**：Zotero SQLite 以 `mode=ro` + `query_only=ON` 打开。绝不写入、移动或覆盖附件。
- **不伪造**：线索提取是启发式的，只作为匹配键；匹配不到的字段留空并明确标注，不得构造。

## 使用脚本

脚本位于本 skill 的 `scripts/`。运行前先解析为绝对路径，使用当前环境可用的 Python 3.10+。

### 第一步：提取检索线索

```sh
python <abs>/scripts/resolve_meta.py clues --pdf "<PDF绝对路径>"
```

输出 JSON：`doi_candidate`、`title_candidate`、`year_candidates`、`pdf_sha256`。这些是**候选检索键**，不是最终元数据。若 `doi_candidate` 存在，优先用它匹配。

### 第二步：Zotero 只读匹配

优先 DOI，其次精确标题，最后（非 strict 时）标题子串：

```sh
python <abs>/scripts/resolve_meta.py match --doi "<doi>" --zotero-data-dir "<可选>"
python <abs>/scripts/resolve_meta.py match --title "<title>" --zotero-data-dir "<可选>"
```

数据源发现：显式 `--zotero-data-dir` > 环境变量 `ZOTERO_DATA_DIR` > `~/Zotero`（Windows 另查 `%APPDATA%/Zotero`）。数据库被锁定或升级中时报错，提示关闭 Zotero 或等待同步后重试，不切换到写模式。

## 交付契约

向编排器返回统一字段，缺失项留空并标注：

`zotero_key`、`pdf_key`、`title`、`author`、`year`、`doi`、`collection`、`pdf_path`、`zotero_item`、`zotero_pdf`、`status`。

- `status=UNIQUE`：唯一命中，可继续下游。
- `status=AMBIGUOUS`：多条命中，列出候选让用户选择，不自动挑一条。
- `status=NONE`：无命中。要求用户先把文献导入 Zotero 后重试；若编排器启用 `--no-zotero` 模式，则生成局部身份并明确标注无 Zotero 链接。
- 路径字段仅在确认文件真实存在时填写；远端附件或不可访问文件返回 URI 或标记不可用，不构造本机路径。

## 交付约束

- 整理为 `Raw_Metadata` 交给下游，保留原始语言与来源信息。
- 此阶段不翻译、不总结、不套用中文模板。
- 明确记录未访问到的字段；把"未取到"与"核实为空"区分表述。

## 下游衔接（图谱链）

稳定身份是后续所有节点的锚点：`zotero_key` 决定正式全文路径与精读笔记的 frontmatter，`collection` 决定 `02vault/<collection>/` 目录，`title` 仅作显示名。`paper-vault-graph-builder` 生成的知识节点以 `paper/` 前缀回链到笔记，其双链正确性依赖这里产出的 `note_path`/`zotero_key` 与后续 writer 写入的 frontmatter 完全一致。因此本 skill 必须保证 key 来自 Zotero 条目本体（非附件、非标题猜测），否则图谱回链会指向错误文件。若启用 `--no-zotero` 局部身份，须明确告知下游该文献不生成稳定图谱锚点。
