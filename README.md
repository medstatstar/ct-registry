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

**Is the result a regulatory submission?**
No. Output is for reference / planning only. CSR / filing documents must be produced separately per GCP.

## Before You Run — Time & Data Limits

When you mirror 14+ registries through WHO ICTRP in one call, the backend literally crawls those registries — **it is not instant**. Here's what to expect:

- **How long:** a live retrieval typically takes **1–5 minutes** to come back. The skill first hands you a "submitted, running" receipt, then polls automatically and delivers the result when ready — you don't have to babysit it.
- **Why it can hug the 5-minute ceiling:** the unified third-party endpoint sits behind a hard **5-minute gateway cap**. Broad queries like `cancer`, or "global + no country filter", can run right up against that wall and, rarely, time out. If it does, the skill tells you explicitly instead of silently dropping data.
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

WHO ICTRP and China CDE **share one long-lived token** on the unified endpoint. It is a PUBLIC shared credential, embedded as an XOR+base64 blob in `config/keys.py` (shipped with the package) so it works out-of-the-box. Resolution order: CLI(`--token`) > env(`CT_REGISTRY_COZE_TOKEN`, legacy `ICTRP_WORKFLOW_TOKEN`) > embedded blob (ct-base §5.236). No confidential data ever reaches any of these endpoints.

### Coze key (unified-endpoint credential)

The unified Coze endpoint `https://ct-search.coze.site/run` (used by CDE, WHO ICTRP, ChiCTR, ISRCTN, DRKS) needs a Bearer token. It is a **shared public credential** — issued by the author, bound to the endpoint, not your personal secret.

- **It just works:** the token is embedded in `config/keys.py` (an obfuscated XOR+base64 blob) and ships with the skill, so retrieval runs out-of-the-box with no setup.
- **To override it** (e.g. the author re-issues the token): pass `--token <JWT>` on the command line, or set the `CT_REGISTRY_COZE_TOKEN` environment variable. Do not paste tokens into chat.
- **Obfuscated, not encrypted:** the encoding hides the string from casual viewing, not from a determined reader. Treat it as a credential, not a secret to protect at all costs.
- **Security scanners:** some automated scanners flag `extsvc_client.py` (HTTP/Bearer usage). The blob is a public shared credential, not a private key — there is no private secret in the repo. Override via CLI/env only.

## Advanced Reference

> The commands below are for developers / power users. In normal conversation you do **not** type these — the assistant builds and runs them for you behind the safe-preview gate.

### Requirements
- Python 3.10+ (Anaconda recommended).
- Required: `requests`, `pandas`, `beautifulsoup4`, `lxml`.
- Optional: `matplotlib` (PNG charts); `playwright` + `playwright install chromium` (CDE local scrape, kept only as last resort).

### One-shot orchestration (CT.gov + PubChem + aggregate + report)
```bash
python scripts/ct_registry.py --cond "NSCLC" --status RECRUITING --with-pubchem --out-dir ./out
```

### Cross-source orchestration (CT.gov + CDE merged into the SAME landscape)
```bash
# English primary term: CT.gov uses it as-is; CDE keyword auto-derived to Chinese
python scripts/ct_registry.py --cond "NSCLC" --status RECRUITING --with-cde --out-dir ./out --run
# Chinese primary term: CT.gov auto-translated to English; CDE uses it as-is (bilingual zh+en)
python scripts/ct_registry.py --cond "非小细胞肺癌" --status RECRUITING --with-cde --out-dir ./out --run
# explicit CDE keyword override (still bilingual)
python scripts/ct_registry.py --cond "NSCLC" --status RECRUITING --with-cde --cde-keyword "高血压" --out-dir ./out --run
# advanced filter on CDE (drug + indication + status), merged
python scripts/ct_registry.py --cond "NSCLC" --with-cde --cde-mode combined --cde-keyword "678" --cde-trial-status "已完成" --run
# multi-keyword AND on CDE, merged
python scripts/ct_registry.py --cond "NSCLC" --with-cde --cde-multi-keywords "高血压 糖尿病" --run
```

### Full landscape (Tier-1 + Tier-2 external services)
```bash
python scripts/ct_registry.py --cond "NSCLC" --status RECRUITING \
    --with-euctr --with-cde --with-chictr --with-isrctn --with-drks --with-ictrp \
    --out-dir ./out --run
```

### Per-source direct scripts
```bash
# CT.gov (required, official API)
python scripts/search_ctgov.py --cond "non-small cell lung cancer" --status RECRUITING --max 50 --out ctgov.json
# EU-CTR (pure-HTTP HTML parse, no token)
python scripts/search_eu_ctr.py --q "cancer" --run --out euctr.json
# PubChem drug -> target
python scripts/enrich_pubchem.py --drug "osimertinib" --targets --out pubchem.json
```

### Unified endpoint (WHO ICTRP + China CDE + ChiCTR / ISRCTN / DRKS)
```bash
# Recommended: unified Coze /run endpoint (WHO + CDE share one token embedded in config/keys.py)
python scripts/search_ictrp.py --source who --q "osimertinib" --run --out ictrp.json
python scripts/search_ictrp.py --source chinadrugtrials --q "高血压" --run --out cde_list.json
python scripts/search_ictrp.py --source chinadrugtrials --q "678" --drugs-name "帕博利珠单抗" --trial-status "进行中" --run --out cde_list.json
python scripts/search_ictrp.py --source chinadrugtrials --q "高血压 糖尿病" --run --out cde_list.json
python scripts/search_ictrp.py --source chictr --q "肺癌" --run --out chictr.json
python scripts/search_ictrp.py --source isrctn --q "cancer" --run --out isrctn.json
python scripts/search_ictrp.py --source drks --q "diabetes" --run --out drks.json
# Legacy standalone CDE endpoint (archived locally under CDE/, NOT shipped; FALLBACK reference only)
python CDE/search_cde_workflow.py --keyword "奥希替尼" --run --out cde_list.json
# Token is embedded in config/keys.py (shipped) — no manual step needed.
# To override on a rare 403, set CT_REGISTRY_COZE_TOKEN env or pass --token.
```

### CDE four calling modes (auto-judged; flags shown for reference)
```bash
# Mode search (default keyword OR advanced filters)
python CDE/search_cde_workflow.py --drugs-name "帕博利珠单抗" --indication "非小细胞肺癌" --drugs-type "化学药物" --appliers "默沙东" --trial-status "进行中" --run
# Mode combined (keyword + advanced filter)
python CDE/search_cde_workflow.py --mode combined --keyword "678" --trial-status "已完成" --run
# Mode multi_keyword (space-separated AND)
python CDE/search_cde_workflow.py --mode multi_keyword --multi-keywords "高血压 糖尿病" --run
# Mode detail (project list -> parallel 65-field fetch; auto-run if <=100, confirm if >100)
python CDE/search_cde_workflow.py --project-list cde_list.json --run --out cde_detail.json
# Preview only (default, no network)
python CDE/search_cde_workflow.py --keyword "奥希替尼"
```

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
```bash
python scripts/ct_registry.py --cond "NSCLC" --status RECRUITING \
    --with-cde --with-euctr --with-detail --out-dir ./out --run
# Actually download the listed EU-CTR PDFs (explicit confirmation gate)
python scripts/ct_registry.py --cond "NSCLC" --status RECRUITING \
    --with-cde --with-euctr --with-detail --download-docs --out-dir ./out --run
python scripts/download_docs.py --in ./out/normalized.json --out-dir ./out/docs --yes
```

### WHO ICTRP advanced fields (subset → CLI)
`--who-title` (+ operator), `--who-condition`, `--who-intervention` (alias `--intr`), `--who-recruitment-status` (alias `--status`), `--who-sponsor`, `--who-country`, `--who-phase` (comma-separated), `--who-date-start` / `--who-date-end` (DD/MM/YYYY), `--who-with-results`, `--who-secondary-id`. Any structured field auto-selects `mode=combined`.

### CDE advanced fields (subset → CLI)
`--reg-no`, `--indication`, `--case-no`, `--drugs-name`, `--drugs-type` (enum: 中药/天然药物/化学药物/生物制品), `--appliers`, `--communities`, `--researchers`, `--agencies`, `--trial-status` (11-value enum: 进行中/尚未招募/招募中/招募完成/已完成/主动暂停/主动终止/IEC·IRB暂停/IEC·IRB终止/责令暂停/责令终止). Note: CDE advanced UI has **no phase filter** — phase is post-filtered from detail.

### Interaction contract (two gates)
- **Gate 1 — Pre-search brief (before `--run`):** the assistant prints keywords (EN+ZH per source), scope, any time/status filter, the `demand_id` grouping + quota impact, and the "free, 100 demands/day" note. It asks only when there is a real choice.
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

**Version**: v0.3.78 | **License**: MIT | **Authors**: medstatstar, phoe-zip

For feature requests, bug reports, or other feedback, please contact the author directly at medstatstar@gmail.com (Wintone Zhang / 张文彤).

## Confidentiality Notice

> The CT series consists of 16+ specialized domain skills, organized into four tiers — A, B, C, D — by "confidential-data-exfiltration risk + whether external retrieval is needed", providing full coverage of the entire new-drug clinical trial (Clinical Trial) lifecycle.
>
> - **Tier A / B (non-confidential)**: run fully locally using only ordinary data; Tier B may need external public retrieval but involves no confidential information. These skills are published openly on GitHub.
> - **Tier C / D (confidential)**: involve strictly confidential clinical-trial data and internal information from pharma sponsors (e.g., ct-analysis, ct-sdtm); Tier C is processed locally and never leaves the boundary, while Tier D additionally requires policy approval. These skills are designated for internal enterprise use only and are not publicly released at present.
>
> If you do have a genuine need for these confidential skills, please contact the author to request custom installation.
>
> 📧 Contact: medstatstar@gmail.com (Wintone Zhang / 张文彤)
