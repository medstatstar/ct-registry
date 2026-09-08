---
slug: ct-registry
displayName: Clinical Trial Registry Search / 临床试验注册检索专家
name: ct-registry
cn_name: 临床试验注册检索专家
version: 0.10.0
invocable: true
required_commands: [python]
summary: "跨源检索全球临床试验注册库（ClinicalTrials.gov、CDE/ChiCTR/ISRCTN/DRKS/WHO ICTRP、PubChem），归一化聚合分期/状态/申办方/时间线/竞品格局，产出 JSON / Markdown，用于立项查重、对照设计与竞品格局分析。"
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

> WHO ICTRP is the meta-aggregator: when `--with-ictrp` is set it is PRIMARY and the national registries it covers (CT.gov, EU-CTR, ISRCTN, DRKS, ChiCTR) become FALLBACK-ONLY (skipped on WHO success). **CDE is ALWAYS independent** (`--with-cde` never skipped) because WHO's English-title matching misses Chinese trials.

## Features

- Search by disease / intervention / sponsor across sources → de-duplicate similar trials, find control designs.
- Unified normalization → heterogeneous cross-registry records into one schema.
- Aggregation analysis → phase / status distribution, top sponsors, timeline, competitor landscape.
- Drug → target mapping (PubChem) → mechanism & competitor target comparison.
- Structured output → JSON / Markdown / optional PNG; chained to `ct-pipeline` and `ct-protocol`.
- **Status track / diff (P0-A, local-only):** `--track` writes normalized results to `registry_snapshot.json`; `--diff <snapshotA> <snapshotB>` compares two `normalized.json` by NCT set and outputs `status_delta` (added / removed / status-changed / synonym-spelling-changed). Diff uses `STATUS_EIV` synonym normalization (RECRUITING≈ACTIVE_NOT_RECRUITING≈ONGOING in the same bucket, no false positives). Zero network.
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

> **⏱️ Retrieval time & data-volume guide**
>
> - A search typically takes **10 seconds ~ 3 minutes**; large result sets (broad keywords, deep pagination) can run up to **5 minutes**.
> - If a search exceeds 5 minutes without finishing, the system **returns the partial results already retrieved** (instead of erroring) and marks the output with `is_timeout: true`.
> - You may trade off wait-time vs. completeness: wait for full results, or accept a partial set for a quick preview.
>
> **📊 How many records fit in ~5 minutes?**
>
> Depends on query breadth; empirical ranges:
>
> | Keyword type | Typical hit count | Fully retrievable in 5 min? | Empirical throughput |
> |---|---|---|---|
> | Narrow (e.g. `osimertinib`) | 20-200 | ✅ easily | WHO ~100-150 pages/min, CDE ~200-300 pages/min |
> | Medium (e.g. `diabetes`) | 5,000-50,000 | ❌ partial only | 5 min ≈ 1,000-1,500 records |
> | Broad (e.g. `cancer`) | 100,000+ | ❌ tiny fraction | first page ~30s, ~2-3s/page (WHO) |
>
> - **If results are incomplete**: ① accept the partial set (sufficient for trend analysis); ② narrow the query (add intervention / sponsor / country filters); ③ split into multiple searches (by dimension).

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

- **Trigger:** two paths — (A) **explicit user request** ("report a bug" / "反馈问题" / "提交错误报告"): go straight to two-stage confirmation, no strong signal needed, unlimited per session; (B) **strong signal** (CLI non-zero exit / engine or compute error / user explicitly questions the result) **and** the same operation was retried ≥1 → at most 1 unsolicited proposal/session. Weak signal (just repeated tuning) never triggers.
- **Two-stage confirmation (2026-08-21, from three-stage):** ① propose-with-preview — show the bilingual `confirm_prompt` **together with** the full report (`render_report_text`, state "sanitized, no input data", invite a problem description; if the user adds one, re-render and re-show before consent) → ② on explicit consent, `send_to_endpoint` (auto action=report, endpoint `https://ct-bugreport.coze.site/run`, token = embedded §5 public credential). If the user declines, never re-propose this session.
- **Post-send history receipt (2026-08-22):** after a successful send, the endpoint returns `history` (last submission for the same `query_origin`, or `""`). Compose the reply from `confirm_thanks(locale)` + `build_followup(history, locale)` — bilingual, auto-switched by `locale`: empty `history` → end; `history.resultstr == "done"` → also show the fix note from `history.memo`; otherwise show "not yet fixed". All user-facing strings are bilingual via `_MSGS` and `_current_locale()` auto-detection.
- **Sanitization is hard:** the report carries only the 11-key whitelist (skill / version / error_type / error_code / engine_status / description / locale / query_origin / session_hash / attempts / test) — never raw data or subject records. `description` is the single free-text field for debugging, **user-reviewed**: write the symptom / reproduction / expected vs actual / algorithm or function used / error message; values and study design are OK. Hard boundary: no identifiable person/institution/subject info. The user reviews it in stage ① before consent; empty description omits the key. If the session had **no** cloud call, `save_local_report()` writes a local md + author email (data never leaves the machine).
- **Client-only:** this adapter sends `report` only. Governance actions (get/update/download/delete — pull pending, mark done, download all, clean up) are reserved for the `ct-update` skill (author side); never call them from here.

Invoke: `python adapters/bug_report.py --error-type <t> --description "<free text>" [--send]` (add `--send` only after the user confirms).

## Publishing (ct-base §16)

Shared assets (`i18n.py`, `kw_localize.py`, `keyword_breadth.py`, `excel_style.py`,
`drug_name_resolver.py`, `source_guard.py`, `r_libs.py`, `office_to_md.py`, `merge_spec.py`,
and the JSON lexicons/maps) are **single-source in `ct-base`** (§16.8). `ct-registry` only
vendors synced copies; never edit a shared file locally and ship it — publish will silently
overwrite local edits with the `ct-base` version, losing your change. Fix in `ct-base` first,
then sync down.

**Mandatory pre-publish gate (run from the dev workspace where `ct-base` is a sibling):**

```bash
python scripts/publish_preflight.py            # resolves ct-base as ../ct-base
# or explicit:
python scripts/publish_preflight.py --base-dir ../ct-base
```

`publish_preflight.py` runs, in order:
1. `shared_sync_check.py` — blocks (exit 1) on any JSON or **Python** shared-module drift
   vs `ct-base` (§16.8 invariant; Python modules added 2026-08-27 — previously only JSON was
   checked, so `.py` forks went undetected).
2. `publish_secret_scan.py` — blocks on committed secrets / tokens.
3. `clawhub_security_audit.py --warn-only` — informational ClawHub term-audit (network; never blocks).
4. `publish_inject.py --dry-run` — previews which `ct-base` assets would be injected.

Only when `publish_preflight.py` exits 0 may you proceed:

```bash
python ../ct-base/scripts/publish_inject.py .          # inject shared assets (makes package self-contained)
# ... package & publish to GitHub → SkillHub → ClawHub (ClawHub: no --version) ...
python ../ct-base/scripts/publish_inject.py . --clean  # remove injected copies (auto-generated artifacts)
```

The `scripts/publish_preflight.py` orchestrator is **dev-only** (references the `ct-base`
sibling) and is excluded from the published package via `.clawhubignore`.
