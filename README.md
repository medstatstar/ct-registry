# Clinical Trial Registry Search (ct-registry)

[🇨🇳 中文](./README_zh-CN.md) / [🇺🇸 English](#)

<div align="center">
  <img src="assets/icon.svg" width="240" height="240" alt="ct-registry logo"/>
</div>

> Cross-source search of global clinical-trial registries (ClinicalTrials.gov, China CDE, WHO ICTRP, EU-CTR, ChiCTR, ISRCTN, DRKS, PubChem), normalized and aggregated into one actionable landscape — for trial planning, de-duplication, control-design benchmarking, and competitive intelligence. B-tier: ordinary input + public retrieval, quickly-adoptable.

## Who This Is For

The `ct-*` clinical-trial skill family covers the entire clinical-trial lifecycle. It serves three groups:

- **Clinical-trial practitioners at pharmaceutical companies** — sponsors, CROs, and medical / statistical / regulatory roles;
- **Clinicians and nurses who design, manage, or run clinical-trial projects**;
- **Medical students who want to learn clinical-trial methodology in a structured way**.

## How to Use (in conversation)

Just describe what you need in plain language. The assistant auto-decides which registries, which keywords (it localizes CN/EN for you), and which retrieval mode — you never pick flags yourself. Below are real examples from simple to complex.

### Example 1 · Quick registry search
**You say:**
> Search Pfizer's phase 3 oncology trials registered since 2022.

**Assistant replies (sketch):**
> Queries ClinicalTrials.gov v2 directly, normalizes phase / status / sponsor, and returns a ranked table (count, scope, sample rows) plus a homepage link per trial.

**How to trigger real computation:**
> Safe preview prints the plan only; say "run it" / "请直接计算" to execute the live retrieval.

### Example 2 · Cross-source (CT.gov + China CDE)
**You say:**
> Find trials on 奥希替尼 (osimertinib) in non-small-cell lung cancer, both globally and in China.

**Assistant replies (sketch):**
> Proposes a scope of ClinicalTrials.gov v2 + China CDE, auto-translates the keyword to English for CT.gov and to Chinese (奥希替尼) for CDE, runs both, then merges them into one unified landscape (e.g. CT.gov 20 + CDE 2057 → 2077 records) with a phase / status / sponsor breakdown.

**How to trigger real computation:**
> Safe preview prints the keyword map + scope; say "run it" to execute. CDE uses the unified Coze endpoint (token required); CT.gov is free and direct.

### Example 3 · Complex — multi-parameter CDE routing menu
**You say:**
> Search CDE for 化学药物 (chemical drug) 帕博利珠单抗 in 非小细胞肺癌, status 进行中, applicant 默沙东.

**Assistant replies (sketch):**
> Recognizes this as a CDE advanced (structured) search. Instead of guessing, it pops a routing menu so you confirm each dimension before the query is built:

> ┌─ CDE search scope ──────────────────────────┐
> │ 1) Keyword / drug name : 帕博利珠单抗        │
> │ 2) Indication          : 非小细胞肺癌        │
> │ 3) Drug type           : 化学药物            │
> │ 4) Applicant (申办方)   : 默沙东              │
> │ 5) Trial status        : 进行中              │
> │ 6) Confirm & run                               │
> │ 7) 还拿不准 → 详细解释差异 (explain differences) │
> └─────────────────────────────────────────────┘

> Selecting **7) 还拿不准 → 详细解释差异** opens a sub-explanation of what each field filters, why `trial_status` must use the exact enum value (进行中, not "正在进行"), and that CDE has no phase filter (phase comes from detail mode later). You adjust any item, then confirm.

**How to trigger real computation:**
> The menu is a safe preview. After you confirm (item 6), say "run it" to send the payload to the CDE unified endpoint.

### Example 4 · Vague — grill-me clarification
**You say:**
> I'm not sure what I want yet — I just heard about a competitor's new drug.

**Assistant replies (sketch):**
> Asks branch by branch to pin down your need, e.g.:
> - "Do you know the drug name, or just the disease area / mechanism?"
> - "Are you comparing globally, or specifically in China (CDE)?"
> - "Is this for competitive landscaping, control-design benchmarking, or de-duplication before your own trial?"
> - "Any phase / status / time window you care about?"

> Once clarified (e.g. "a GLP-1 class drug, global + China, phase 3, last 3 years"), it proposes a scope and keywords, then previews the plan.

**How to trigger real computation:**
> Safe preview throughout clarification; say "run it" once the scope is confirmed to execute.

### Example 5 · Structured detail + document links
**You say:**
> Pull the detailed records (sponsor, phase, endpoints) for the NSCLC CDE hits, and list any downloadable PDFs.

**Assistant replies (sketch):**
> Runs CDE `detail` mode (65 fields per record) so sponsor / phase are populated (list mode shows them as `Unknown`). It renders a homepage link for every record and **lists** (but does not auto-download) any EU-CTR PDFs. PDFs download only after you explicitly confirm.

**How to trigger real computation:**
> Detail fetch auto-runs if ≤100 items; if >100 it confirms the list first. Say "download the PDFs" to trigger the explicit download gate.

### Example 6 · Broad global coverage via WHO ICTRP
**You say:**
> Give me the global landscape of DPP-4 inhibitor trials for type 2 diabetes since 2023.

**Assistant replies (sketch):**
> Uses WHO ICTRP (one call mirrors 14+ primary registries: CT.gov, EU-CTR, ISRCTN, DRKS, ChiCTR, jRCT, ANZCTR, CTRI …) plus China CDE (always searched independently, since WHO's English-title matching misses Chinese-registered trials), aggregates into one landscape with a competitor map.

**How to trigger real computation:**
> Safe preview shows scope (WHO + CDE = two endpoints); say "run it" to execute. Counted as one demand against the shared quota.

## What It Can Do — Scenarios

| Capability | Source(s) | Try saying |
|---|---|---|
| Search by disease / intervention / sponsor | CT.gov (direct); CDE / ChiCTR (user-paste or workflow) | "Find phase 3 oncology trials by Pfizer since 2022" |
| Unified cross-registry normalization | All sources | "Merge CT.gov and CDE NSCLC trials into one table" |
| Aggregation: phase / status / sponsor / timeline / competitor landscape | All sources | "Show the competitor landscape for osimertinib in NSCLC" |
| China CDE advanced & multi-keyword search | China CDE (unified endpoint) | "CDE: 沙坦 + 进行中, chemical drug, since 2023" |
| Global mirror via WHO ICTRP (14+ registries) | WHO ICTRP (unified endpoint) | "Global DPP-4 inhibitor T2D trials since 2023" |
| Drug → target / property mapping | PubChem (direct) | "Map osimertinib to its target via PubChem" |
| Structured detail (sponsor / phase / endpoints) | CDE detail (65 fields), EU-CTR docs | "Pull full details for these CDE registration numbers" |
| Structured output: JSON / Markdown / PNG / Excel | — | "Export the landscape as an Excel workbook" |
| Chained downstream analysis | → `ct-pipeline` / `ct-protocol` | "Feed the normalized results to ct-pipeline for intel" |

## FAQ

**Can I search with only some parameters?**
Yes. You never choose a mode or flag — the assistant auto-decides the CDE calling mode (`search` / `combined` / `multi_keyword` / `detail`) from your words. Leave any field blank; unused fields are simply omitted (empty fields would otherwise poison the query).

**Are the counts per group or total?**
Totals are aggregated into one landscape. A cross-source run reports the grand total **and** the per-source breakdown (e.g. CT.gov 20 + CDE 2057 → 2077 records). The status distribution shows both `RECRUITING` and `已完成/进行中` in the same table.

**How do I actually retrieve the data?**
By default you get a **safe preview** (the plan / payload only). Say "run it" / "请直接计算" to execute the live retrieval.

**Is the output in Chinese when I'm on a Chinese system?**
Yes. The scripts auto-detect locale: all user-facing prompts switch to Chinese on a `zh-*` locale and to English otherwise. Raw data values (CDE Chinese status / indication, etc.) are always kept verbatim — never translated.

**Why do some rows show phase / sponsor as `Unknown`?**
List-mode search returns only summary fields. `sponsor` and `phase` are populated only by CDE `detail` mode (65 fields) or by WHO detail. Request detail when you need sponsor / phase breakdowns.

**Is it free, and is there a quota?**
Currently free. The shared third-party endpoint is metered by **demand** (one user request = 1 demand; WHO + CDE + keyword tweaks within it collapse to 1). Daily cap is 100 demands; direct Tier-1 sources (CT.gov v2, EU-CTR, PubChem) and preview are not counted.

**Concurrency / parallel sessions (P1-7)?** The quota counter `config/usage.json` and the output dir are shared files inside the skill directory. `usage_guard.py` serialises their read-modify-write with an advisory file lock, so parallel calls won't corrupt the counter. Best practice is still **one skill per session**; if multiple AI sessions drive the same skill directory at once, rely on that lock and avoid sharing an `out_dir`.

**CDE standalone endpoint status?** The original standalone CDE endpoint `ct-searchcde.coze.site/run` (`CDE/search_cde_workflow.py`) was **RETIRED on 2026-08-12**; `--cde-legacy` now only prints a deprecation warning and auto-routes to the unified endpoint `search_ictrp.py --source chinadrugtrials`. CDE/ is local-archive only and not shipped.

**Is the result a regulatory submission?**
No. Output is for reference / planning only. CSR / filing documents must be produced separately per GCP.

**Is the retrieval compliant, and does it hit rate limits?**
All queries go through official public APIs / public search interfaces (CT.gov v2, EU-CTR, PubChem, WHO ICTRP, China CDE unified endpoint) — no scraping of non-public pages, no bypassing of site protections. The backend calls third-party endpoints **serially with exponential backoff**, honouring their rate limits; on 429 / timeout it retries with backoff rather than hammering them. The 5-minute gateway cap on global mirrors (14+ registries) is a compliant wait, not a throttling penalty.

## Before You Run — Time & Data Limits

When you mirror 14+ registries through WHO ICTRP in one call, the backend literally crawls those registries — **it is not instant**. Here's what to expect:

- **How long:** a live retrieval typically takes **1–5 minutes** to come back. The skill first hands you a "submitted, running" receipt, then polls automatically and delivers the result when ready — you don't have to babysit it.
- **Why it can hug the 5-minute ceiling:** the unified third-party endpoint sits behind a hard **5-minute gateway cap**. The workflow uses **P4 async fire-and-forget** (`/run` returns immediately with a `run_id`, then polls `/run/status/{run_id}` with exponential backoff) to bypass this wall. Broad queries like `cancer`, or "global + no country filter", can run right up against that wall and, rarely, time out. If it does, the skill tells you explicitly instead of silently dropping data.
- **What happens after 5 minutes:** if the retrieval volume exceeds the 5-minute cap and still isn't complete, the system **returns whatever partial results have been collected so far** (rather than erroring out), and marks the output with `is_timeout: true`. You can trade off between wait time and data completeness: wait longer for full results, or accept partial results for a quick preview.
- **Roughly how many records in 5 minutes:** it depends on how broad the query is:

  | Keyword type | Typical hit count | Can 5 min finish? | Empirical throughput |
  |-------------|------------------|-------------------|---------------------|
  | Narrow (e.g. `osimertinib`) | 20-200 | ✅ Easily | WHO ~100-150 pages/min, CDE ~200-300 pages/min |
  | Medium (e.g. `diabetes`) | 5,000-50,000 | ❌ Partial only | 5 min ≈ 1000-1500 records |
  | Broad (e.g. `cancer`) | 100,000+ | ❌ Only a small fraction | First page ~30s, ~2-3s/page thereafter (WHO) |

  What to do when you can't get everything: ① Accept partial results (enough for trend analysis); ② Narrow the scope (add intervention / sponsor / country filters); ③ Split into multiple queries (by dimension).
- **How to keep the data volume sane:** WHO global results can be huge. If a query returns too few rows or times out, it's usually **too broad** — narrow the keyword (e.g. `osimertinib` instead of `cancer`), or use **advanced search** (just say "advanced search" in conversation; the code auto-builds precise `drug AND condition` filters, returning a smaller, faster set). There's also a **daily cap of 100 demands** (see FAQ above) — normal use won't get near it.

## Safety (safe preview)

**Safe preview by default.** Scripts only generate and display a plan / payload. Network requests run **only** when you explicitly say so ("run it" / "请直接计算"). Nothing is sent or fetched until then.

**Public data only — zero confidential input.** The skill reads public registry data; you never supply subject / protocol / CRF data, and none is ever transmitted.

**Outbound data disclosure (egress).** When you run a live retrieval, only **public query terms** (drug name, indication, registration number) leave your environment, sent to these public endpoints:

- **ClinicalTrials.gov v2** — official REST API (direct, no token).
- **PubChem** — PUG-REST (drug → CID / properties / targets; direct, no token).
- **China CDE** — via the unified Coze `/run` endpoint `ct-search.coze.site/run` (third-party, Bearer token required — verified HTTP 401 without it).
- **EU-CTR** — pure-HTTP HTML parse of legacy EudraCT results (direct, no token, no browser).
- **WHO ICTRP** — unified Coze `/run` endpoint (third-party, Bearer token required); one call mirrors 14+ registries.
- **ChiCTR / ISRCTN / DRKS** — served by the **same** unified Coze `/run` endpoint via `source=chictr|isrctn|drks` (third-party, shared token).
- **Bug reports (optional, opt-in only):** if a likely skill defect is detected, the assistant may ask to send a **sanitized** bug report to the unified report endpoint `https://ct-bugreport.coze.site/run` (skill name/version/error type plus a problem description you review and approve — never your raw data). Nothing is sent without your confirmation; you can always decline.

**First-outbound confirmation.** The first time a search sends your terms to the unified endpoint, you'll see a one-time confirmation prompt (target server + what is sent = your public search terms, no personal info). After you approve, the endpoint is whitelisted and you won't be asked again this session. This follows the ct-base §5 library-wide outbound-authorization norm. Nothing is sent until you approve or say "run it".

WHO ICTRP and China CDE **share one long-lived token** on the unified endpoint. It is a PUBLIC shared credential, embedded as an XOR+base64 blob in `config/keys.py` (shipped with the package) so it works out-of-the-box. Resolution order: CLI(`--token`) > env(`CT_REGISTRY_COZE_TOKEN`, legacy `ICTRP_WORKFLOW_TOKEN`) > embedded blob (ct-base §5.236). No confidential data ever reaches any of these endpoints.

### Coze key (unified-endpoint credential)

The unified Coze endpoint `https://ct-search.coze.site/run` (used by CDE, WHO ICTRP, ChiCTR, ISRCTN, DRKS) needs a Bearer token. It is a **shared public credential** — issued by the author, bound to the endpoint, not your personal secret.

- **It just works:** the token is embedded in `config/keys.py` (an obfuscated XOR+base64 blob) and ships with the skill, so retrieval runs out-of-the-box with no setup.
- **To override it** (e.g. the author re-issues the token): pass `--token <JWT>` on the command line, or set the `CT_REGISTRY_COZE_TOKEN` environment variable. Do not paste tokens into chat.
- **Obfuscated, not encrypted:** the encoding hides the string from casual viewing, not from a determined reader. Treat it as a credential, not a secret to protect at all costs.
- **Security scanners:** some automated scanners flag `extsvc_client.py` (HTTP/Bearer usage). The blob is a public shared credential, not a private key — there is no private secret in the repo. Override via CLI/env only.

## Why You Can Trust the Results (anti-hallucination)

Every row in the output is **retrieved, not invented**:

- **Source-authoritative.** Records come straight from the registries' own APIs / endpoints (ClinicalTrials.gov v2, PubChem PUG-REST, EU-CTR HTML, and the unified Coze endpoint for CDE / WHO / ChiCTR / ISRCTN / DRKS). No LLM generation sits between you and the source data.
- **Rule-based normalization.** Merging / field mapping (phase, status, sponsor…) is deterministic code, not free-text rewriting. Raw values (CDE Chinese status, indication, etc.) are kept **verbatim** — never translated or altered.
- **Counts are echoed, not estimated.** Totals and per-source breakdowns are taken directly from each source's response; the skill does not round, guess, or extrapolate counts.
- **Known limits are labelled, not hidden.** A broad query that hits the 5-minute gateway returns **partial** results marked `is_timeout: true` (see *Before You Run — Time & Data Limits*); list-mode rows show `Unknown` for sponsor / phase (populated only by detail mode). These caveats are printed, not silently dropped.

Caveat: registries update on their own cadence and may have gaps or lags; always cross-check against the source before any regulatory / submission use.

## Advanced Reference

> The commands below are for developers / power users. In normal conversation you do **not** type these — the assistant builds and runs them for you behind the safe-preview gate.
>
> ⚠️ Commands that include `--run` perform **live network retrieval** (public query terms egress to the endpoints above). Omit `--run` — or stay in the conversation safe-preview — for the default **no-network plan** that prints only the intended call.

### Requirements
- Python 3.10+ (Anaconda recommended).
- Required: `requests`, `pandas`, `beautifulsoup4`, `lxml`.
- Optional: `matplotlib` (PNG charts); `playwright` + `playwright install chromium` (CDE local scrape, kept only as last resort).

### One-shot orchestration (CT.gov + PubChem + aggregate + report)
```bash
python scripts/ct_registry.py --cond "NSCLC" --status RECRUITING --with-pubchem --out-dir ./out
```

### Cross-source orchestration (CT.gov + CDE merged into the SAME landscape)
Merge CT.gov + CDE in one run: English / Chinese primary terms with auto keyword localization, explicit CDE keyword override, advanced filters (`--cde-mode combined`), and multi-keyword AND (`--cde-multi-keywords`). Full CLI examples: `references/cli_reference.md`.

### Full landscape (Tier-1 + Tier-2 external services)
One invocation covering CT.gov + EU-CTR + CDE + ChiCTR + ISRCTN + DRKS + WHO ICTRP, merged and aggregated into one report. Full CLI example: `references/cli_reference.md`.

### Per-source direct scripts
```bash
# CT.gov (required, official API)
python scripts/search_ctgov.py --cond "non-small cell lung cancer" --status RECRUITING --max 50 --out ctgov.json
# CT.gov advanced search (full v2 query.* / filter.* coverage, v0.3.84+)
python scripts/search_ctgov.py \
  --cond "non-small cell lung cancer" \
  --phase PHASE1,PHASE3 --study-type INTERVENTIONAL \
  --status RECRUITING,COMPLETED \
  --start-date-since 2023-01-01 --last-update-until 2026-08-01 \
  --sort LastUpdatePostDate:desc --has-results --fields NCTId,BriefTitle --max 10
# CT.gov raw Expert Search expression passthrough (paste from website advanced search)
python scripts/search_ctgov.py --adv 'AREA[StudyType]OBSERVATIONAL AND AREA[LocationCountry]China' --max 5
# PubChem drug -> target
python scripts/enrich_pubchem.py --drug "osimertinib" --targets --out pubchem.json
```

> **CT.gov advanced flags** (v0.3.85+, full list via `--help`): `--query` (query.term, AREA[] ok),
> `--titles` `--outc` `--lead` `--id` `--locn` `--patient` (other query.*),
> `--adv` (raw filter.advanced), `--phase` `--study-type` `--age-group` `--sex` `--has-results`
> (assembled into `filter.advanced` AREA[] expressions, AND-combined with `--adv`),
> `--sort` (max 2; `field[:asc|:desc]` or `@relevance`), `--ids` (NCT batch), `--geo`
> (`distance(lat,lon,dist)` or bare `lat,lon,dist`; 1-500 mi / 1-805 km enforced), `--fields`,
> server-side date ranges `--first-post-since/--until`, `--last-update-*`,
> `--start-date-*`, `--primary-completion-*`, `--completion-*`, multi-value `--status`,
> and `--post-status/--post-ids/--post-geo/--post-adv` (postFilter.* — same semantics but
> does NOT affect relevance ranking).
> NOTE: v2 has no flat phase/studyType/date params — they all go through `filter.advanced`;
> `query.rmtln` is a **v1 legacy param removed in v2** (HTTP 400, verified against the live
> API 2026-08-13) — use `--query`/`--adv` for remote-trial search;
> `--date-after` keeps the legacy local post-filter (start-year lower bound).

### Unified endpoint (WHO ICTRP + China CDE + ChiCTR / ISRCTN / DRKS)
WHO + CDE + ChiCTR / ISRCTN / DRKS share one Coze endpoint; the token is embedded in `config/keys.py` (shipped) — no manual step needed. To override on a rare 403, set `CT_REGISTRY_COZE_TOKEN` env or pass `--token`. Per-source CLI examples: `references/cli_reference.md`.

### CDE four calling modes (RETIRED 2026-08-12; local archive reference only; production uses the unified endpoint)
Production CDE retrieval goes through the unified endpoint above; the retired standalone workflow is archived locally under `CDE/` (NOT shipped).

### Normalize → aggregate → report → Excel
```bash
python scripts/normalize.py --ctgov ctgov.json --cde cde.json --chictr chictr.json \
    --euctr euctr.json --isrctn isrctn.json --drks drks.json --out normalized.json
python scripts/aggregate.py --in normalized.json --out agg.json
python scripts/report.py --in agg.json --out report.md --png report.png
# Clinical-friendly 4-sheet Excel (auto-generated by the orchestrator; --no-excel to disable)
python scripts/export_xlsx.py --in normalized.json --out report.xlsx --title "Asciminib 2023-2026"
```

### Structured detail + confirm-gated PDF download
Detail fetch (≤100 items auto, >100 confirm) and PDF download are gated by explicit confirmation; PDFs are never auto-downloaded. Direct doc download is resumable (skips existing files). CLI examples: `references/cli_reference.md`.

> ⚠️ **Document-download duration & volume warning (measured 2026-08-12)**
> `download_docs.py` downloads **sequentially** (one file at a time, no concurrency) and has **no built-in quantity cap** — it pulls every `documents[].url` in the input JSON. Only **EU-CTR** yields real downloadable links (CDE / WHO / CT.gov expose no protocol-PDF API), so a broad EU-CTR search (e.g. 40 records × ~3 docs each) can mean **100+ sequential downloads**.
>
> **Measured behavior (sandbox, 2026-08-12):**
> - Per-file hard timeout `--timeout` default **60s**; on failure it prints `FAILED` and moves on — there is **no retry loop** (the docstring says "per-file retries" but the code only tries once).
> - Round-trip latency to `euclinicaltrials.eu` ≈ **1–3 s/request**.
> - This sandbox's egress is throttled to ~20–30 KB/s, so a 3 MB PDF would hit the 60s timeout and be **skipped** — i.e. in a throttled network, large docs fail. Production (Coze) bandwidth is normally far higher, but **don't assume** a doc will finish.
>
> **Planning rule of thumb:** total wall-clock ≈ `N_files × per_file_time`, with a **worst-case ceiling of `N_files × 60s`** (a hung file burns the full timeout before skipping). For 100 files that is up to ~100 min in the worst case. EU-CTR protocol / IB / CSR PDFs are commonly 0.5–15 MB, so real per-file time varies with doc size and deployment bandwidth.
>
> **Mitigations:**
> - Cap how many docs are gathered: `fetch_eu_ctr_docs.py --max N` and/or download only a subset of records.
> - Download in small confirmed batches; re-run is safe — files already in `--out-dir` are **skipped** (resumable).
> - If you see many `FAILED … timed out`, raise `--timeout` (e.g. `--timeout 180`) or run from a faster network.

### WHO ICTRP advanced fields (subset → CLI)
`--who-title` (+ operator), `--who-condition`, `--who-intervention` (alias `--intr`), `--who-recruitment-status` (alias `--status`), `--who-sponsor`, `--who-country`, `--who-phase` (comma-separated), `--who-date-start` / `--who-date-end` (DD/MM/YYYY), `--who-with-results`, `--who-secondary-id`. Any structured field auto-selects `mode=combined`.

### CDE advanced fields (subset → CLI)
`--reg-no`, `--indication`, `--case-no`, `--drugs-name`, `--drugs-type` (enum: 中药/天然药物/化学药物/生物制品), `--appliers`, `--communities`, `--researchers`, `--agencies`, `--trial-status` (11-value enum: 进行中/尚未招募/招募中/招募完成/已完成/主动暂停/主动终止/IEC·IRB暂停/IEC·IRB终止/责令暂停/责令终止). Note: CDE advanced UI has **no phase filter** — phase is post-filtered from detail.

### Interaction contract (two gates)
- **Gate 1 — Pre-search brief (before any live-network call):** the assistant prints keywords (EN+ZH per source), scope, any time/status filter, the `demand_id` grouping + quota impact, and the "free, 100 demands/day" note. It asks only when there is a real choice.
- **Gate 2 — Post-list confirmation:** it presents the list (count, scope, sample rows, `Unknown` phase/sponsor caveat). Detail fetch: ≤100 items auto-runs; >100 items confirm first. PDFs are never auto-downloaded.

### Errors (quick reference)
| Error | Cause | Fix |
|---|---|---|
| CT.gov `URLError` | No network / proxy | Confirm clinicaltrials.gov reachable; set proxy |
| CDE empty / "access blocked" | SafeDog WAF blocks browsers | Use unified endpoint workflow (preferred); or assisted paste → `parse_cde.py` (no egress) |
| WHO / CDE HTTP 401 | Missing `Authorization: Bearer <token>` | Token is embedded in `config/keys.py` (shipped); if a 401 persists, set `CT_REGISTRY_COZE_TOKEN` or pass `--token` |
| WHO / CDE HTTP 403 (rare) | Corrupted / revoked token blob | Re-issue via env `CT_REGISTRY_COZE_TOKEN` / `--token` (token is long-lived; 403 is not expiry) |
| CDE HTTP 500 `字段类型错误` | Field sent as `{"value":x}` or `project_list` as array | Use plain strings; `project_list` must be a JSON **string** |
| ISRCTN 404 | Public API dead (2026-07-20) | Use unified endpoint `source=isrctn` |
| CDE read timed out | Large result / transient gateway (capped ~300 s/run) | Retry with default 300 s; transient, not a payload error |

### Pipeline
`ct-registry` → `ct-pipeline` (consumes `normalized.json` for competitor intel) / `ct-protocol` (design benchmarking).

---

**Version**: v0.3.81 | **License**: MIT | **Authors**: medstatstar, phoe-zip

For feature requests, bug reports, or other feedback, please contact the author directly at medstatstar@gmail.com (Wintone Zhang / 张文彤).

## Confidentiality Notice

> The CT series consists of 20+ specialized domain skills, organized into two tiers — A, B — by "confidential-data-exfiltration risk + whether external retrieval is needed", providing full coverage of the entire new-drug clinical trial (Clinical Trial) lifecycle.
>
> - **Tier A (non-confidential · public)**: takes only ordinary (non-confidential) input; runs fully locally (`network=off`) or performs public retrieval (`network=public-retrieval`, e.g. ct-registry / ct-advisor) — never involves confidential information. Tier A skills are published openly on GitHub.
> - **Tier B (confidential · internal)**: involve strictly confidential clinical-trial data and internal information from pharma sponsors (e.g., ct-analysis, ct-sdtm, ct-eligibility); Tier B is processed locally (`egress=none`, data never leaves the machine) or requires approved egress (`egress=approval-req`, e.g. ct-eligibility). These skills are designated for internal enterprise use only and are not publicly released at present.
>
> If you do have a genuine need for these confidential skills, please contact the author to request custom installation.
>
> 📧 Contact: medstatstar@gmail.com (Wintone Zhang / 张文彤)
