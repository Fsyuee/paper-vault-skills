---
name: paper-vault-analytical-writer
description: "当用户需要为一篇文献撰写中文精读笔记并写入 Obsidian 知识库时使用。基于 Zotero 元数据、Formal Fulltext 与必要时原 PDF，按标准模板生成可追溯的结构化笔记。不翻译全文、不做 PDF 转换、不写入 Zotero。通常由 paper-vault-orchestrator 调用。"
agent_created: true
version: 1.0.0
---

# Paper Vault Analytical Writer

## 权威模板

每次新建或更新笔记前，先读取活动 vault 的 `模板/论文精读模板.md`（若存在）；否则使用本 skill 自带 asset `assets/论文精读模板.md`。所选模板是结构权威。

严格保持章节顺序：
`基本信息 -> 一句话摘要 -> 研究对象 -> 研究方法（方法概述 -> 方法分析） -> 数据来源 -> 研究结论 -> 结构化重点 -> 关联概念 -> 关联精读笔记 -> 我的判断`。

保留模板的表格、字段标签、标题层级与 frontmatter 字段。替换所有占位符，删除未用的公式块、多余的"发现/引用"对和无确认关联的示例链接。不新增旧式标题（如"研究对象与问题""数据与证据定位""Zotero信息"）。局限只写在"方法局限""数据局限""我的判断"。

"研究结论"中每条主要发现按三声部分离书写：**作者报告**（authors report，客观转述作者主张）、**我的评估**（analyst assessment，读者判断）、**未决问题**（unresolved，证据不足或需追问处）；三者措辞必须可区分，不得混为一段。

## 职责与语料顺序

Writer 只负责分析层：`metadata + Formal Fulltext +（必要时）原 PDF -> 中文精读笔记`。

- Fulltext 是原文证据层，精读笔记是中文理解层；二者不得混同。
- 已有 Formal Fulltext 先复用；缺全文时交回编排器走 fulltext-archiver，不得自行伪造原文。
- 核对公式、页码、否定/条件/稳健性限定时，可读取原 PDF 直接核验。

## Frontmatter 与稳定身份

使用模板 frontmatter，并以已核实的 Zotero 身份填充关键字段：

```yaml
type: literature-note
zotero_key: "<zotero_key>"
pdf_key: "<pdf_key>"
doi: "<doi>"
collection: "<collection>"
note_path: "02vault/<collection>/<paper>.md"
fulltext_path: "03fulltext/<collection>/<zotero_key>.md"
zotero_item: "zotero://select/library/items/<zotero_key>"
zotero_pdf: "zotero://open-pdf/library/items/<pdf_key>"
```

新笔记只写入 `02vault/<collection>/<paper>.md`。路径均为 vault 相对路径，用 `/` 分隔符。

## 原文引用规则

- "主要发现 + 原文引用"中的原文必须真实出现在 Fulltext 或原 PDF 中。严禁根据中文摘要反向生成英文引文。
- 每条主要发现紧邻至少一条真实原文引用。定位不到时写"未在当前全文中定位到可核验原句"，不得虚构引文或页码。
- 引用保留必要上下文，检查否定、条件、稳健性限定、假设与局限。
- PDF 页码仅在可靠映射或原 PDF 核验后填写；否则写"PDF 页码未验证"。不得因 `page_mapping: unknown` 猜页码，也不得因页码未知而拒绝通过原 PDF 直接核验引文。

## 内容与格式约束

- `theme` 概括研究问题；`study_area`、`data_source`、`methodology`、`core_variable`、`key_finding`、`relevance` 必须来自真实材料，不照抄大段摘要。
- 过滤作者地址、单位、邮编、邮箱、基金号和排版垃圾；数据与方法缺失时如实说明。
- 公式仅在原文可靠时保留；乱码残片不强行解释。
- 写入前检查 YAML、美元符号配对、标题层级、占位符是否清除、结论是否成对，以及 Note↔Fulltext 双向入口是否存在。

## 结构化重点抽取（图谱数据源）

这是"抓取重点形成图谱"的核心步骤。writer 必须在 `## 结构化重点` 章节写出一个合法的 ```json 代码块，作为 graph-builder 建图的唯一数据源。抽取方法借鉴 `laminar-paper-reader`：

- **source-grounded**：每个实体和主张都必须能在 Fulltext 或原 PDF 中定位到依据；定位不到就不填，禁止凭标题或常识臆造。
- **三类实体**：
  - `concepts`：理论/机制/现象级概念（如"预测编码""工作记忆""情境依赖性"），非结论、非方法名；
  - `methods`：方法/技术/序列（如"层 fMRI""VASO""MP2RAGE-eGM""dcm2niix"）；
  - `regions`：脑区/网络（如"dlPFC""S1""默认模式网络"）。
- **字段**：每项至少 `name`（节点名，术语统一），建议 `why`（一句话说明其与本文的关联，写入节点释义），可选 `label`（双链显示名，放中英对照）。`claims` 保留原文要点及 `contrast`（对照条件）、`source`（图表/页码定位）、`stat`（统计量）；不建 claim 节点，但作为重点证据留存。`comparison_dimensions` 记录跨论文可归一化的维度（如 `field_strength`、`sequence`、`task`）。
- **术语归一**：同一概念在不同论文中可能有别名，优先采用已有节点名（参考 `01knowledge/<kind>/_index.md`），别名写入 `label`，避免图谱出现重复节点。
- **宁缺毋滥**：某类确无内容填 `[]`；不确定具体名称时宁可不填，也不写占位符式假实体。

写完后用 JSON 校验确认代码块可被解析；graph-builder 会据此新建/更新节点并回链。

## 写入与索引

1. 判定新建还是更新；两种情况都先读模板。更新时允许重排正文匹配模板，但不得改变稳定身份或制造重复笔记。
2. 基本信息区加入 `全文 Markdown：[[paper/03fulltext/<collection>/<zotero_key>|<显示名>]]`（路径存在时），并保留可验证的 Zotero 入口。**wikilink 一律带 `paper/` 前缀**（真实 Obsidian vault 根是 `paper` 的父目录，不带前缀将无法跳转）。
3. `## 关联概念` 章节由 `paper-vault-graph-builder` 依据结构化重点自动维护（`paper-vault:concepts` 受管区块）。writer **不要在此手写双链**，保留标题与说明、留空即可；建图步骤由 orchestrator 的 G3.5 统一执行，避免人工链接与结构化数据漂移。
4. 新建笔记后，在 `02vault/_index.md` 追加一行指向新笔记的链接；更新既有笔记不触发全库批量重写。概念/方法/脑区节点的"关联文献"回链由 graph-builder 统一维护，writer 不单独编辑。
