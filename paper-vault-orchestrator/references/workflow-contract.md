# Workflow contract

## Skill call chain

```text
paper-vault-orchestrator
  ├─ paper-vault-metadata-resolver  (scripts/resolve_meta.py)
  ├─ paper-vault-fulltext-archiver  (scripts/pdf_to_fulltext.py)
  ├─ paper-vault-analytical-writer  (assets/论文精读模板.md)
  │    └─ emits "结构化重点" JSON block
  └─ paper-vault-graph-builder (G3.5) (scripts/build_graph.py)
       └─ validated by orchestrator/scripts/validate_graph.py (G4.5)
```

Shared scripts live in `paper-vault-orchestrator/scripts/` and are reused by
siblings via relative path `../paper-vault-orchestrator/scripts/`. Resolve every
relative path to an absolute path before execution.

## Status vocabulary

| Status | Meaning | Downstream |
| --- | --- | --- |
| `UNIQUE` | One Zotero item matched | Proceed |
| `AMBIGUOUS` | Multiple candidates | Ask user to choose; stop |
| `NONE` | No Zotero item | Ask user to import first, or `--no-zotero` mode |
| `COMPLETE` | Fulltext/Note produced and validated | Proceed |
| `FULLTEXT_DEFERRED` | No usable converter or empty output | Stop; report missing capability |
| `ALREADY_COMPLETE` | Valid artifacts already exist | Skip stage |
| `GRAPH_BUILT` | Structured highlights turned into knowledge nodes | Proceed to G4.5 |
| `GRAPH_EMPTY` | No structured highlights / JSON invalid | Fix G3, do not claim graph complete |
| `VALIDATION_FAIL` | G4 or G4.5 found ERRORs | Fix and re-run gate |

Statuses are workflow states only. Never write them into YAML schema fields.

## Path contract (relative to vault_root)

| Artifact | Path |
| --- | --- |
| Analytical note | `02vault/<collection>/<paper>.md` |
| Formal fulltext | `03fulltext/<collection>/<zotero_key>.md` |
| Fulltext images | `03fulltext/<collection>/images/<zotero_key>/` |
| Knowledge log | `01knowledge/log.md` |
| Knowledge nodes | `01knowledge/{concepts,methods,regions}/<节点名>.md` |
| Knowledge indexes | `01knowledge/{concepts,methods,regions}/_index.md` |
| Legacy concept index | `01knowledge/concepts/_concepts_index.md` |
| Template | `模板/论文精读模板.md` |
| Local config | `01knowledge/.meta/paper-vault.toml` |

### Knowledge layer (graph)

Obsidian's native graph draws nodes = Markdown files, edges = `[[wikilinks]]`.
To show concept↔concept and concept↔literature structure, the workflow builds a
knowledge layer driven by the note's `结构化重点` JSON (G3) via graph-builder
(G3.5). The writer no longer hand-maintains concept links.

- Structured highlights contract (in a `## 结构化重点` section, first ```json block):
  `schema_version`, `concepts[{name,why,label}]`, `methods[...]`, `regions[...]`,
  `claims[{claim,contrast,source,stat}]`, `comparison_dimensions{...}`.
  Only `name` is required; all entities must be source-grounded.
- Kind → directory: `concepts→01knowledge/concepts/` (reuses legacy MOC notes),
  `methods→01knowledge/methods/`, `regions→01knowledge/regions/`.
- Each node has human-authored `节点释义` plus three deterministic managed blocks:
  `paper-vault:refs` (关联文献 backlinks), `paper-vault:related` (co-occurring
  entities), and in the literature note `paper-vault:concepts` (links to all entities).
  Only text between markers (or under the matching heading) is rewritten; never
  hand-edit these sections.
- `build_graph.py` is idempotent (reuses existing nodes, full-rewrites `_index.md`).
  `validate_graph.py` (G4.5) checks marker pairing, zero broken `[[paper/...]]`
  links, and index↔node consistency.
- All wikilinks use the `paper/` prefix because the real Obsidian vault root is
  the parent of `paper/` (e.g. `[[paper/01knowledge/concepts/预测编码|预测编码]]`).
- Term normalization: reuse an existing node name across papers; put aliases in
  `label` to avoid duplicate nodes.

## Canonical frontmatter identity

Both Note and Fulltext must carry and agree on:

- `type` (`literature-note` / `literature-fulltext`)
- `zotero_key` (stable primary identity)
- `pdf_key`
- `collection`
- `note_path` and `fulltext_path` (reciprocal, vault-relative, `/` separators)

`validate_vault.py` enforces these. A title is display-only.

## Environment notes

Never assume a tool exists or a path is valid. Always run `scripts/check_env.py` (read-only) and confirm the vault path at runtime. The notes below are discovery hints, not hard-coded truth.

- Zotero data dir: by default `~/Zotero/zotero.sqlite`; override with `--zotero-data-dir` or `ZOTERO_DATA_DIR`. Open read-only (`mode=ro`, `query_only=ON`) — never write.
- `pdftotext`: the fallback converter; confirm its location via `check_env.py`.
- MinerU: optional. If installed (e.g. in a conda env), pass its executable via `--mineru`. Its local `server` mode can fail on machines with a small `/tmp` (tmpfs `Errno 28`) or a non-writable trash dir (stale `doclib.sock` / `endpoint.json`). If that happens, fall back to `pdf_to_fulltext.py --no-mineru` (pdftotext) rather than spending turns repairing the service for a routine import.
- Obsidian: not required to be running. A vault is a plain folder whose root the user chooses at runtime.
