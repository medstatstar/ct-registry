---
slug: ct-registry
displayName: Clinical Trial Registry Search / 临床试验注册检索专家
name: ct-registry
cn_name: 临床试验注册检索专家
version: 0.13.0
invocable: true
required_commands: [python]
summary: "跨源检索全球临床试验注册库（ClinicalTrials.gov、CDE/ChiCTR/ISRCTN/DRKS/WHO ICTRP、PubChem），归一化聚合分期/状态/申办方/时间线/竞品格局，产出 JSON / Markdown，用于立项查重、对照设计与竞品格局分析。可选集成 pytrials 批量拉取 CT.gov 字段。"
license: MIT
description: "Cross-source search of global clinical-trial registries (ClinicalTrials.gov, CDE/ChiCTR/ISRCTN/DRKS/WHO ICTRP, PubChem), normalizes and aggregates phase/status/sponsor/timeline/competitor landscape into JSON/Markdown for trial planning, de-duplication, control-design benchmarking, and competitive intelligence. / 跨源检索全球临床试验注册库（ClinicalTrials.gov、CDE/ChiCTR/ISRCTN/DRKS/WHO ICTRP、PubChem），归一化聚合分期/状态/申办方/时间线/竞品格局，产出 JSON / Markdown，用于立项查重、对照设计与竞品格局分析。"
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
  network_note: "Auto-direct public-retrieval sources: ClinicalTrials.gov v2 + PubChem (public REST API, ordinary input + public retrieval, B-tier). EU CTIS supports retrieve-by-number only (no search). China CDE blocks automated browsers via WAF -> external workflow for automatable retrieval (third-party endpoint, only public query terms egress, Bearer token REQUIRED - verified: HTTP 401 without it; search/detail FIXED & verified 2026-07-23, all four modes end-to-end). ChiCTR / ISRCTN / DRKS are ALSO served by the same unified endpoint (source=chictr|isrctn|drks, third-party, shared Bearer) - so their public query terms egress too. The bundled Bearer is a long-lived SHARED public credential issued by the author (XOR+base64 obfuscated, recoverable from the package); treat it as the endpoint's key, NOT your personal secret, and rotate/stop using if abused. CDE also supports an optional commercial API key (--cde-api-key) sent only to the official CDE API. All paths require zero confidential data or information input; only public query terms ever leave the environment."
  filesystem: "read-only to its own files; writes report/Excel files to current working directory; download_docs.py can optionally write retrieved EU-CTR PDFs to a user-specified --out-dir"
  data: "no confidential data input; only public query terms are transmitted (via the unified endpoint / optional CDE API); no user files or secrets are sent"

---

## Language

- **English guide** → [README.md](https://github.com/medstatstar/ct-registry/blob/main/README.md) · **Chinese guide** → [README_zh-CN.md](https://github.com/medstatstar/ct-registry/blob/main/README_zh-CN.md)
- Bilingual auto-switch: the answer language follows the user's question language (English question → English answer, Chinese question → Chinese answer).

This skill responds in the user's current input language and auto-detects / switches accordingly. The runtime scripts embed a locale check so all user-facing prompts switch to Chinese on a `zh-*` locale and to English otherwise. Code comments and documentation are English-only.

The SKILL.md body, `references/*.md`, and `AGENTS.md` are English-only and agent-facing; runtime command prompts switch to Chinese / English by locale. For end-to-end walkthroughs and troubleshooting in your language, open the README above.

# Clinical Trial Registry Search

## Published Application

| Item | Value |
|---|---|
| Share link | `https://ct-registry.app.workbuddy.host/` |
| appId | `wbapp_39NhpDKvmNZ4AjTmsODgqH` |
| domainPrefix | `ct-registry` |
| Deploy metadata | `workbench/app.config.json` |
| Deployed as | http-service (`python app.py`, entry bootstraps `workbench/server.py`) |
| startCmd | `python app.py` |
| publishDir | `workbench/publish-dist` |
| Payload | `workbench/publish-dist/` (built by `workbench/publish-kit/build_publish.py`: `app.py` + `adapters/` + `scripts/` + `references/` + `workbench/`) |
| Publish infra | `workbench/publish-kit/` (`.wbapp_*.genie` marker + `install_genie.py` + `build_publish.py`) |

> **Re-publish rule (ct-base §13.5 方案 B)**: always overwrite with the existing `appId` — the link
> must stay `https://ct-registry.app.workbuddy.host/`. Never `createNewApp`. Before deploy:
> 1. `python workbench/publish-kit/build_publish.py` — rebuild `workbench/publish-dist/` from the skill tree (whitelist + prune, no bulk delete).
> 2. `python workbench/publish-kit/install_genie.py` — install the `.wbapp_*.genie` marker + `applications.yaml` into the **current workspace root** so `workbuddy_sites_deploy` can claim the appId (the marker's `localDir` is re-pinned to this machine's `publish-dist` on every run).
> 3. Deploy with the existing `appId` (overwrite). After deploy, assert the returned `shareLink` equals the expected URL (§13.5 dirty-binding red line).
> Last republished 2026-09-26 (feedback two-stage fix); scheme B publish infrastructure migrated 2026-09-27.

> Safe by default: preview, not execute.

## Purpose

Search global clinical-trial registries in one pass, normalize heterogeneous records into a unified schema, and aggregate them into an actionable landscape (phase / status / sponsor / timeline / competitor map) to support trial planning, de-duplication, control-design benchmarking, and competitive intelligence.

## Architecture

**Principle: the skill does not use a headless browser to scrape WAF-blocked registries over the network.** Chinese registries (CDE, ChiCTR) and WebForms portals (e.g. old ICTRP portal) block automated browsers via WAF fingerprint checks — a verified platform limitation, not a tooling gap. Where a registry has no clean HTTP API, retrieval is delegated to an external workflow (Tier 2) instead of the caller scraping: any needed browser automation runs **server-side inside the unified endpoint**, and a local **paste-mode** (`parse_cde.py`) parses user-pasted pages with **no egress**. The skill therefore uses two safe paths:

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

## External Open-Source Integrations (v0.13.0 · 外部开源资产引用)

| Tool | Source | Purpose | Integration |
|---|---|---|---|
| **pytrials** | `pip install pytrials` | CT.gov 批量检索客户端：`ClinicalTrials().get_study_fields()` 批量拉取字段，适配不同端点返回结构 | 可选 API 客户端，与现有 CT.gov v2 REST API 路径并列 |
| **Docling** | `pip install docling` | 法规文档结构化解析：`DocumentConverter().convert('protocol.pdf')` 输出带层级结构的 Markdown/JSON，保住表格结构和章节层级 | PDF 解析增强层，供 ct-protocol / ct-literature 共用 |

> WHO ICTRP is the meta-aggregator: when `--with-ictrp` is set it is PRIMARY and the national registries it covers (CT.gov, EU-CTR, ISRCTN, DRKS, ChiCTR) become FALLBACK-ONLY (skipped on WHO success). **CDE is ALWAYS independent** (`--with-cde` never skipped) because WHO's English-title matching misses Chinese trials.

## Features

- Search by disease / intervention / sponsor across sources → de-duplicate similar trials, find control designs.
- Unified normalization → heterogeneous cross-registry records into one schema.
- Aggregation analysis → phase / status distribution, top sponsors, timeline, competitor landscape.
- Drug → target mapping (PubChem) → mechanism & competitor target comparison.
- Structured output → JSON / Markdown / optional PNG; chained to `ct-pipeline` and `ct-protocol`.
- **Status track / diff (P0-A, local-only):** `--track` writes normalized results to `registry_snapshot.json`; `--diff <snapshotA> <snapshotB>` compares two `normalized.json` by NCT set and outputs `status_delta` (added / removed / status-changed / synonym-spelling-changed). Diff uses `STATUS_EIV` synonym normalization (RECRUITING≈ACTIVE_NOT_RECRUITING≈ONGOING in the same bucket, no false positives). Zero network.
- **pytrials 增强模式 (v0.13.0, opt-in):** 使用 pytrials 作为官方 API 客户端批量拉取 CT.gov 字段，新增：① 适应症在研试验分布热力图；② 同适应症终点设计对比；③ 目标中心历史项目检索。与现有 Tier 1 直连模式互补，pytrials 提供更友好的 Python 封装。
- **Tier-2 graceful fallback (P0-B, network only with --run):** WHO timeout/error auto-falls back to CDE + ClinicalTrials.gov for the report and sets `who_status=failed` (not hidden); CDE returning 0 records triggers one auto-retry (`--cde-retry` default 1, rate-limited by `--cde-retry-delay` default 2s); if still 0, marks `zero_hit_unverified`; all fallback paths disclose data flow in `report.md` (also writes `run_status.json`).
- **WHO Chinese-English keyword auto-translation (P0-C, 2026-09-07):** WHO ICTRP endpoint only accepts English (Chinese keywords reliably return 0; English hits normally). For any `source=who` search (including the ChiCTR→WHO fallback path where the keyword is Chinese), keyword / multi_keywords are auto-translated to English: curated term_map (`references/term_map.json`, bidirectional authoritative) first; dictionary-miss long-tail terms fall back to online translation (`kw_localize.online_translate`, MyMemory keyless); envelope labels `source=term_map/online` truthfully. Disable with `--no-kw-localize`. ⚠️ Online translation is unreliable for medical terms (tested `光生物调节`→`Photobioregulation`, WHO hit 0; correct term `photobiomodulation` hit 974) — **new domain terms MUST enter term_map (ct-base single source), do not rely on online fallback**.
- **ChiCTR WAF pure-Python crack (server-side node, 2026-09-07):** ChiCTR's Alibaba Cloud WAF `acw_sc__v2` can be cracked deterministically — challenge page inlines `var arg1='<40 hex>'`, algorithm = 40-bit position permutation table + fixed XOR key, solvable in pure Python (no Node/Playwright needed). Coze-side `chictr_search_node` rewritten to **HTTP-first** (`searchproj.html?title=<kw>&page=N` new param; old `searchContent=` is dead), Playwright as fallback only. ⚠️ This change is in Coze server-side source — **must be re-packaged and deployed to Coze console to take effect**; local `--source chictr` goes through the unified endpoint and auto-benefits from the node update.
- **WHO-COVERED 5-source auto WHO fallback (P0-D, 2026-09-07):** When a WHO-covered source is queried directly but that source's site is unreachable, auto-fallback to WHO ICTRP to retrieve that source's trials — no interruption, no empty hand. Layered: ① Unified-endpoint sources (ChiCTR/ISRCTN/DRKS, `search_ictrp.py`) detect `source_likely_down` then in-process switch to WHO, filter that source's records by `_SOURCE_ID_RE` and backfill (envelope `fallback_used=who_ictrp` / `<src>_records_via_who=N`); ② Tier-1 direct sources (CT.gov/EU-CTR, `ct_registry.py` orchestration) site-unreachable → `_tier1_who_backfill` auto-sends WHO search and merges into normalization — if WHO primary path already succeeded, the mirror already covers it, no duplicate request. CLI: `--no-fallback-who` disables auto-WHO-switch for unified-endpoint sources; Tier-1 fallback is on by default.

## Requirements

- Python 3.10+ (Anaconda `C:\Tools\anaconda3\python.exe` recommended).
- Required: `requests`, `pandas`, `beautifulsoup4`, `lxml`.
- Optional: `matplotlib` (PNG); `playwright` (CDE local scrape — last resort only, WAF-blocked).
- Network: read-only public data. **CDE / WHO / ChiCTR / ISRCTN / DRKS require a Bearer token** (unified endpoint).

## Coze key (unified-endpoint credential)

All Tier-2 retrieval (CDE, WHO ICTRP, ChiCTR, ISRCTN, DRKS) is served by one unified endpoint `https://ct-search.coze.site/run`, which requires a Bearer token. That token is a **shared public credential** — a Coze workload-identity issued by the author, bound to the endpoint (not to any individual user), not a personal secret.

- **Where it lives:** embedded in `adapters/endpoint_token.py` as an XOR+base64 obfuscated blob (`EMBEDDED_SECRETS["coze_unified"]`). `.py` is on every publishing platform's allow-list, so it ships with the package and works out-of-the-box. (The blob used to live in `config/ictrp.dat`, but platforms like SkillHub silently strip `*.dat`, which broke the shipped skill — hence the move to `adapters/endpoint_token.py`.)
- **Resolution order (ct-base §5.236):** `CLI --token` > env `CT_REGISTRY_COZE_TOKEN` (legacy `ICTRP_WORKFLOW_TOKEN`; CDE standalone `CDE_WORKFLOW_TOKEN`) > embedded blob > legacy `.dat`. The embedded blob is the default; you normally never touch it.
- **Keep it as-is — do not replace it with your own token** unless the author issues a new one. To override (e.g. after a re-issue), pass `--token <JWT>` on the CLI or export `CT_REGISTRY_COZE_TOKEN`; never paste tokens into chat.
- **Obfuscated, not encrypted (ct-base §5.234):** the XOR+base64 encoding only hides the string from casual directory-listing / grep, not from a determined reader. Public shared credentials are allowed to ship with the package (§5.239/§5.243); private tokens must come from CLI/env only and are not persisted to disk.

## ⚠️ Safety

- Default SAFE PREVIEW: scripts only generate / display; network runs only with explicit `--run`.
- Reads public registry data ONLY — **zero confidential data or information input** (B-tier: ordinary input + public retrieval).
- CDE automatable path is the unified endpoint (one long-lived token shared with WHO ICTRP via `adapters/endpoint_token.py`); the legacy standalone `search_cde_workflow.py` is archived locally under `CDE/` (NOT shipped with the package — **RETIRED 2026-08-12**; `--cde-legacy` is now a no-op warning that auto-routes to the unified endpoint `search_ictrp.py --source chinadrugtrials`). Only public query terms are sent; Bearer token REQUIRED (verified: HTTP 401 without it); still disclose "data via third party". CDE paste-mode (Playwright / `parse_cde.py`) remains a no-egress fallback.
- **Unified-endpoint token** — all Tier-2 sources share one long-lived Bearer token, embedded in `adapters/endpoint_token.py` as a public shared credential (XOR+base64 obfuscated, not a personal secret). Full resolution order, override, and history → **Coze key** above. Never paste tokens into chat — provide via CLI(`--token`) / env `CT_REGISTRY_COZE_TOKEN` only.
- Output is for reference only, not a regulatory submission (CSR / filing must be generated per GCP separately).
- **Concurrency constraint (P1-7):** the quota counter `config/usage.json` and the output directory are shared files inside the skill directory; `usage_guard.py` serializes read/write via an advisory file lock. Run **one skill per session**; if multiple AI sessions call the same skill directory in parallel, they must rely on that lock to avoid shared-state races that could corrupt the counter or outputs.

## Search procedure

Execute in **forced order** (scope → translate → search). Full three-step procedure + the mandatory Keyword-System Confirmation Gate → **`references/search_procedure.md`**.

1. **Scope** — pick registries. WHO+CDE already covers CT.gov/EU-CTR/ChiCTR/ISRCTN/DRKS (two endpoints only); WHO and CDE are **separate calls** (shared `demand_id`), never one request.
2. **Keywords** — translate per source (English for CT.gov/WHO/PubChem; CDE needs Chinese, strip "类" suffix, e.g. use `drugs_name=列汀` not `DPP-4抑制剂`).
3. **Execute** — direct sources free & unmetered; external-workflow sources counted once per `demand_id` (currently free, daily cap). Then `normalize → aggregate → report` (Excel final artifact; PDFs never auto-downloaded).

> **⏱️ Retrieval time & data-volume guide** → **`docs/retrieval_guide.md`** (typical 10s–5min; partial-result-on-timeout; empirical record-throughput by keyword breadth).

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

Entry script: `ct_registry.py` (cross-source orchestration, auto keyword-localization, parallel batch retrieval, quota guard) lives in `scripts/`. Outbound-calling per-source wrappers live in `adapters/` (the dedicated outbound directory per §16.9): `search_ctgov.py`, `search_eu_ctr.py`, `search_ictrp.py`, `search_chictr.py`, `search_isrctn.py`, `search_drks.py`, `search_cde.py`, `extsvc_client.py`, `enrich_pubchem.py`, `download_docs.py`, `fetch_eu_ctr_docs.py`. Pure-local compute stays in `scripts/`: `normalize.py`, `aggregate.py`, `report.py`, `export_xlsx.py`, `parse_cde.py` (no-egress paste-mode), `usage_guard.py`, `i18n.py`. The retired standalone CDE workflow is archived locally under `CDE/` (NOT shipped; **RETIRED 2026-08-12 — `--cde-legacy` is a no-op warning**).

- CDE external-workflow modes, payload contract, decision flow, parameter mapping → **`CDE/cde_workflow.md`** (archived, local reference only).
- Search procedure, scope rules, keyword gate → **`references/search_procedure.md`**.
- All CLI recipes, advanced-field inventory (WHO/CDE), detail/doc enrichment, resource-usage policy → **`references/cli_reference.md`**.

One-shot example:

```bash
# agent / non-interactive calls MUST add --no-expand (or --kw-en/--kw-zh / --kw-adopt),
# otherwise the Keyword-System Confirmation Gate stops unconditionally (sys.exit) with no output
python scripts/ct_registry.py --cond "NSCLC" --status RECRUITING --with-cde --no-expand --out-dir ./out --run
```

## Pipeline

- `ct-registry` → `ct-pipeline`: `normalized.json` consumed by the intelligence layer for competitor discovery & landscape.
- `ct-registry` → `ct-protocol`: similar-trial design benchmarking, aiding protocol writing.

See `references/units.md` for the atomic-task unit index.

## Bug Reporting (ct-base §20.3, adapter: `adapters/bug_report.py`)

Trigger (explicit request → two-stage confirmation; strong signal + retry ≥1 → ≤1 unsolicited proposal/session), two-stage confirmation, post-send history receipt, 11-key sanitization whitelist, client-only scope → **`docs/bug_reporting.md`**. Invoke: `python adapters/bug_report.py --error-type <t> --description "<free text>" [--send]` (add `--send` only after the user confirms).

## Publishing (ct-base §16)

Shared assets are single-source in `ct-base` (§16.8) — never edit a shared file locally and ship it. Mandatory pre-publish gate `scripts/publish_preflight.py` (shared-sync check → secret scan → ClawHub audit → inject dry-run) + `publish_inject.py` self-contained packaging → GitHub → SkillHub → ClawHub. Full procedure → **`docs/publishing.md`**.
