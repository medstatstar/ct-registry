---
slug: ct-registry
displayName: 临床试验注册检索专家 / Clinical Trial Registry Search
name: ct-registry
cn_name: 临床试验注册检索专家
version: 0.3.79
invocable: true
required_commands: [python]
summary: 跨源检索临床试验注册库（ClinicalTrials.gov / PubChem 自动直连；中国 CDE 经外部工作流自动化检索、ChiCTR 经用户粘贴页面本地解析；EU CTIS 按号富集）并归一化聚合，辅助立项查重、对照设计与竞品格局分析。检索公开注册库（B 档：普通数据输入 + 对外检索）。
license: MIT
description: "跨源检索全球临床试验注册库并归一化聚合。可自动化直连：ClinicalTrials.gov v2、PubChem（公开 REST API，零保密数据或信息输入）。中国 CDE 因 WAF 拦截自动化浏览器，改为外部工作流自动化检索（第三方端点，仅公开查询词出域，需 Bearer token，已实测无 token 返回 401）；ChiCTR 仍经用户粘贴公开页面→本机解析（不出域）；EU CTIS 仅支持按号 retrieve（无搜索）；ISRCTN 公开 API 已失效。聚合分期/状态/申办方/时间线/竞品格局，产出 JSON / Markdown（可选 PNG）。零保密数据或信息输入，B 档（普通数据输入 + 对外检索），可快速推广技能。 / Cross-source search of global clinical-trial registries, normalized and aggregated. Auto-direct sources: ClinicalTrials.gov v2, PubChem (public REST, ordinary input + public retrieval). China CDE blocks automated browsers via WAF → external workflow for automatable retrieval (third-party endpoint, public query terms only egress, Bearer token REQUIRED — verified: HTTP 401 without it); ChiCTR still user-pastes public page → local parse (no egress). EU CTIS supports retrieve-by-number only (no search). ISRCTN public API is dead. Aggregates phase / status / sponsor / timeline / competitor landscape into JSON / Markdown (optional PNG). B-tier (ordinary input + public retrieval), quickly-adoptable."
triggers:
  - "clinical trial registry search"
  - "临床试验注册库检索"
  - "查同类试验"
  - "竞品临床试验格局"
  - "ct-registry"
metadata:
  openclaw: { emoji: "🔍" }
  authors: ["medstatstar", "phoe-zip"]
  license: "MIT"
  tags: [clinical-trial, registry, ct-registry, ctgov, cde, public-data]
  homepage: "https://github.com/medstatstar/ct-registry"
permissions:
  scope: "user-space-only"
  network: "optional"
  network_note: "Auto-direct public-retrieval sources: ClinicalTrials.gov v2 + PubChem (public REST API, ordinary input + public retrieval, B-tier). EU CTIS supports retrieve-by-number only (no search). China CDE blocks automated browsers via WAF -> external workflow for automatable retrieval (third-party endpoint, only public query terms egress, Bearer token REQUIRED - verified: HTTP 401 without it; search/detail FIXED & verified 2026-07-23, all four modes end-to-end); ChiCTR still user-pastes public page -> local parse (no egress); ISRCTN public API is dead. All paths require zero confidential data or information input; only public query terms ever leave the environment (e.g. CDE via the Coze workflow)."
  filesystem: "read-only to its own files; writes report files only to current working directory"
  data: "no confidential data input; no external transmission of user data"

---

## Language

Pick the README that matches your language for human-readable, language-specific guides:

- **English guide** → [README.md](./README.md)
- **中文指南** → [README_zh-CN.md](./README_zh-CN.md)

This skill responds in the user's current input language and auto-detects / switches accordingly. The runtime scripts embed a locale check so all user-facing prompts switch to Chinese on a `zh-*` locale and to English otherwise. Code comments and documentation are English-only.

The SKILL.md body, `references/*.md`, and `AGENTS.md` are English-only and agent-facing; runtime command prompts switch to Chinese / English by locale. For end-to-end walkthroughs and troubleshooting in your language, open the README above.

# Clinical Trial Registry Search

> Safe by default: preview, not execute.

## Purpose

Search global clinical-trial registries in one pass, normalize heterogeneous records into a unified schema, and aggregate them into an actionable landscape (phase / status / sponsor / timeline / competitor map) to support trial planning, de-duplication, control-design benchmarking, and competitive intelligence.

## Architecture

**Principle: never use a headless browser / Playwright.** Chinese registries (CDE, ChiCTR) and WebForms portals (e.g. old ICTRP portal) block automated browsers via WAF fingerprint checks — a verified platform limitation, not a tooling gap. Where a registry has no clean HTTP API, retrieval is delegated to an external workflow (Tier 2) instead of scraping. The skill therefore uses two safe paths:

- **Tier 1 — direct-connect (pure HTTP, no browser):** `ClinicalTrials.gov v2` REST API (required); `EU CTR` legacy EudraCT search-result HTML parsed directly (`search_eu_ctr.py`, verified 2026-07-24); `PubChem` PUG-REST (drug → CID / targets, optional).
- **Tier 2 — external workflow service (Bearer token, POST JSON, no browser):** a third-party endpoint retrieves on our behalf and returns structured JSON. Shared client in `extsvc_client.py`; thin wrappers `search_cde_workflow.py` / `search_chictr.py` / `search_isrctn.py` / `search_drks.py` reuse it. **Only public query terms are sent — no confidential data — compliant with the ct-base confidentiality red line.** CDE + ChiCTR + ISRCTN + DRKS + WHO ICTRP are served by one unified Coze endpoint `https://ct-search.coze.site/run` (WHO via `--source who`, CDE via `--source chinadrugtrials`), sharing one long-lived token.

**Bridge + de-duplication:** `aggregate.py` normalizes UTN/TRN/registry numbers + fuzzy matches + scans embedded registration numbers on the `raw` field (CT.gov canonical), so the ICTRP feed and our own bridging reinforce each other.

> Full CDE external-workflow detail (endpoints, token mechanism, four calling modes, payload contract, decision flow, agent interaction contract, parameter mapping) → **`CDE/cde_workflow.md`** (archived, local reference only).

## Data Sources

| Source | Tier | Access | Token |
|---|---|---|---|
| ClinicalTrials.gov v2 | Tier 1 (direct) | Official REST API (stable) | — |
| EU CTR (legacy EudraCT) | Tier 1 (direct) | Pure-HTTP HTML parse (`search_eu_ctr.py`) | — |
| PubChem | Tier 1 (direct) | PUG-REST | — |
| China CDE | Tier 2 (ext-svc) | Unified Coze endpoint `https://ct-search.coze.site/run` (`--source chinadrugtrials`) | Bearer (long-lived) |
| WHO ICTRP | Tier 2 (ext-svc) | Unified Coze endpoint (`--source who`); mirrors 14+ registries | Bearer (same token as CDE) |
| ChiCTR | Tier 2 (ext-svc) | Unified Coze endpoint (`--source chictr`) | Bearer (same token) |
| ISRCTN | Tier 2 (ext-svc) | Public API dead → unified Coze endpoint (`--source isrctn`) | Bearer (same token) |
| DRKS | Tier 2 (ext-svc) | JS/redirect-only → unified Coze endpoint (`--source drks`) | Bearer (same token) |

> WHO ICTRP is the meta-aggregator: when `--with-ictrp` is set it is PRIMARY and the national registries it covers (CT.gov, EU-CTR, ISRCTN, DRKS, ChiCTR) become FALLBACK-ONLY (skipped on WHO success). **CDE is ALWAYS independent** (`--with-cde` never skipped) because WHO's English-title matching misses Chinese trials.

## Features

- Search by disease / intervention / sponsor across sources → de-duplicate similar trials, find control designs.
- Unified normalization → heterogeneous cross-registry records into one schema.
- Aggregation analysis → phase / status distribution, top sponsors, timeline, competitor landscape.
- Drug → target mapping (PubChem) → mechanism & competitor target comparison.
- Structured output → JSON / Markdown / optional PNG; chained to `ct-pipeline` and `ct-protocol`.
- **Status track / diff (P0-A, 纯本地):** `--track` 把归一化结果写入 `registry_snapshot.json`；`--diff <快照A> <快照B>` 按 NCT 集合比对两 `normalized.json`，输出 `status_delta`（新增/移除/状态变更/同义拼写变更），diff 按 `STATUS_EQUIV` 同义归一比较（RECRUITING≈ACTIVE_NOT_RECRUITING≈ONGOING 同桶，不误报）。零联网。
- **Tier-2 优雅降级兜底 (P0-B, 仅 --run 联网):** WHO 超时/异常自动降级为 CDE + ClinicalTrials.gov 出报告并置 `who_status=failed`（不隐藏）；CDE 返回 0 条触发一次自动重跑（`--cde-retry` 默认 1，限频 `--cde-retry-delay` 默认 2s），仍 0 则标 `zero_hit_unverified`；降级处均在 `report.md` 披露数据流向（另写 `run_status.json`）。

## Requirements

- Python 3.10+ (Anaconda `C:\Tools\anaconda3\python.exe` recommended).
- Required: `requests`, `pandas`, `beautifulsoup4`, `lxml`.
- Optional: `matplotlib` (PNG); `playwright` (CDE local scrape — last resort only, WAF-blocked).
- Network: read-only public data. **CDE / WHO / ChiCTR / ISRCTN / DRKS require a Bearer token** (unified endpoint).

## Coze key (unified-endpoint credential)

All Tier-2 retrieval (CDE, WHO ICTRP, ChiCTR, ISRCTN, DRKS) is served by one unified endpoint `https://ct-search.coze.site/run`, which requires a Bearer token. That token is a **shared public credential** — a Coze workload-identity issued by the author, bound to the endpoint (not to any individual user), not a personal secret.

- **Where it lives:** embedded in `config/keys.py` as an XOR+base64 obfuscated blob (`EMBEDDED_SECRETS["coze_unified"]`). `.py` is on every publishing platform's allow-list, so it ships with the package and works out-of-the-box. (The blob used to live in `config/ictrp.dat`, but platforms like SkillHub silently strip `*.dat`, which broke the shipped skill — hence the move to `config/keys.py`.)
- **Resolution order (ct-base §5.236):** `CLI --token` > env `CT_REGISTRY_COZE_TOKEN` (legacy `ICTRP_WORKFLOW_TOKEN`; CDE standalone `CDE_WORKFLOW_TOKEN`) > embedded blob > legacy `.dat`. The embedded blob is the default; you normally never touch it.
- **Keep it as-is — do not replace it with your own token** unless the author issues a new one. To override (e.g. after a re-issue), pass `--token <JWT>` on the CLI or export `CT_REGISTRY_COZE_TOKEN`; never paste tokens into chat.
- **Obfuscated, not encrypted (ct-base §5.234):** the XOR+base64 encoding only hides the string from casual directory-listing / grep, not from a determined reader. Public shared credentials are allowed to ship with the package (§5.239/§5.243); private tokens must come from CLI/env only and are never written to disk.

## ⚠️ Safety

- Default SAFE PREVIEW: scripts only generate / display; network runs only with explicit `--run`.
- Reads public registry data ONLY — **zero confidential data or information input** (B-tier: ordinary input + public retrieval).
- CDE automatable path is the unified endpoint (one long-lived token shared with WHO ICTRP via `config/keys.py`); the legacy standalone `search_cde_workflow.py` is archived locally under `CDE/` (NOT shipped with the package — local dev reference only, reachable via `--cde-legacy`). Only public query terms are sent; Bearer token REQUIRED (verified: HTTP 401 without it); still disclose "data via third party". CDE paste-mode (Playwright / `parse_cde.py`) remains a no-egress fallback.
- **Unified-endpoint token** — all Tier-2 sources share one long-lived Bearer token, embedded in `config/keys.py` as a public shared credential (XOR+base64 obfuscated, not a personal secret). Full resolution order, override, and history → **Coze key** above. Never paste tokens into chat — provide via CLI(`--token`) / env `CT_REGISTRY_COZE_TOKEN` only.
- Output is for reference only, not a regulatory submission (CSR / filing must be generated per GCP separately).

## Search procedure

Execute in **forced order** (scope → translate → search). Full three-step procedure + the mandatory Keyword-System Confirmation Gate → **`references/search_procedure.md`**.

1. **Scope** — pick registries. WHO+CDE already covers CT.gov/EU-CTR/ChiCTR/ISRCTN/DRKS (two endpoints only); WHO and CDE are **separate calls** (shared `demand_id`), never one request.
2. **Keywords** — translate per source (English for CT.gov/WHO/PubChem; CDE needs Chinese, strip "类" suffix, e.g. use `drugs_name=列汀` not `DPP-4抑制剂`).
3. **Execute** — direct sources free & unmetered; external-workflow sources counted once per `demand_id` (currently free, daily cap). Then `normalize → aggregate → report` (Excel final artifact; PDFs never auto-downloaded).

## Errors

| Error | Cause | Fix |
|---|---|---|
| `URLError` on CT.gov | No network / proxy | Confirm clinicaltrials.gov reachable; set proxy |
| CDE/ChiCTR WAF "access blocked" | SafeDog WAF blocks browsers | Use external workflow (unified endpoint); fallback: assisted paste → local parse (no egress) |
| WHO/CDE 403 invalid token | Rare corrupted/revoked blob (token is long-lived, normally never 403s) | Re-issue via env `CT_REGISTRY_COZE_TOKEN` / `--token`, then re-run |
| ISRCTN 404 | Public API dead | Unified endpoint (`--source isrctn`) |
| DRKS unreachable | JS/redirect-only | Unified endpoint (`--source drks`) |
| EU CTR | Pure-HTTP HTML parse, no API/token | `search_eu_ctr.py` (verified 2026-07-24) |
| CDE HTTP 401 | Missing/malformed `Authorization` | Send `Authorization: Bearer <token>` (one space after Bearer) |
| CDE HTTP 500 `字段类型错误` | Field sent as `{"value":x}` or `project_list` as array | Use plain strings; `project_list` as JSON **string**/file |
| CDE `total_count:0` | Legitimate empty hit-set (fixed 2026-07-23) | Treat 0 as valid "no match"; retry transient timeout with `--timeout 300` |
| CDE read timed out | Slow large set / ~300 s cap | Transient — retry with default 300 s |

## Implementation

Entry script: `ct_registry.py` (cross-source orchestration, auto keyword-localization, parallel batch retrieval, quota guard). Per-source wrappers live in `scripts/` (`search_ctgov.py`, `search_eu_ctr.py`, `search_ictrp.py`, `search_chictr.py`, `search_isrctn.py`, `search_drks.py`, `enrich_pubchem.py`, `normalize.py`, `aggregate.py`, `report.py`, `export_xlsx.py`, `download_docs.py`). The retired standalone CDE workflow is archived locally under `CDE/` (NOT shipped; `--cde-legacy` only).

- CDE external-workflow modes, payload contract, decision flow, parameter mapping → **`CDE/cde_workflow.md`** (archived, local reference only).
- Search procedure, scope rules, keyword gate → **`references/search_procedure.md`**.
- All CLI recipes, advanced-field inventory (WHO/CDE), detail/doc enrichment, resource-usage policy → **`references/cli_reference.md`**.

One-shot example:

```bash
python scripts/ct_registry.py --cond "NSCLC" --status RECRUITING --with-cde --out-dir ./out --run
```

## Pipeline

- `ct-registry` → `ct-pipeline`: `normalized.json` consumed by the intelligence layer for competitor discovery & landscape.
- `ct-registry` → `ct-protocol`: similar-trial design benchmarking, aiding protocol writing.

See `references/units.md` for the atomic-task unit index.
