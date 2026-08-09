# AGENTS.md — ct-registry v0.3.78

## Overview

`ct-registry`: Cross-source search of global clinical-trial registries (ClinicalTrials.gov /
China CDE / China ChiCTR / EU CTR / ISRCTN / DRKS / WHO ICTRP) and normalized aggregation,
for trial planning, de-duplication, control-design benchmarking and competitive intelligence.
PubChem provides drug→target mapping. **WHO ICTRP is a Tier-2 external service (re-added
2026-07-27)** via `search_ictrp.py` (`source="who"`); one call mirrors 14+ registries
(jRCT / DRKS / ANZCTR / ISRCTN / CTRI / …), expanding coverage — its bridge/de-dup value is
reinforced (not merely replaced) by `aggregate.py`. **The SAME unified endpoint also serves China
CDE** via `source="chinadrugtrials"` (`search_ictrp.py --source chinadrugtrials`; `ct_registry.py --with-cde` defaults there, `--cde-legacy` falls back to the standalone `ct-searchcde.coze.site/run` endpoint) — **one token (`config/ictrp.dat`) covers both WHO and CDE**.
**WHO-coverage fallback policy (2026-07-28, revised 2026-07-28):** when `ct_registry.py --with-ictrp` is set, WHO ICTRP is the PRIMARY aggregator and the national registries it covers (CT.gov, EU-CTR, ISRCTN, DRKS, ChiCTR) become FALLBACK-ONLY — skipped on WHO success, retrieved independently + aggregated ONLY if WHO cannot retrieve (prompt via `[ct_registry][FALLBACK-PROMPT]`, then re-run with `--fallback-covered`). **EXCEPTION — CDE is always independent:** China CDE (`--with-cde`) is never skipped on WHO success and never a fallback, because WHO's English-title matching misses Chinese-registered trials; CDE is searched on its own whenever `--with-cde` is set. PubChem enrichment is unaffected. Without `--with-ictrp`, legacy behavior is preserved. Sources split into Tier 1 (direct, pure
HTTP: CT.gov + EU CTR + PubChem) and Tier 2 (external workflow, Bearer token, no browser:
CDE / ChiCTR / ISRCTN / DRKS / WHO ICTRP). Reads public registry data via public retrieval;
ordinary input + public retrieval; B-tier quickly-adoptable. Natural-language parameter
confirmation follows `references/search_menu.md` (ct-base §6.1).

### Search procedure (mandatory order, v0.3.2)
1. **Scope first** — decide which registries to cover. If scope = {WHO ICTRP, CDE}, those TWO
   endpoints already cover CT.gov / EU-CTR / ChiCTR / ISRCTN / DRKS (WHO mirrors them) + China CDE
   (independent), so do NOT separately hit CT.gov/EU-CTR/ChiCTR/ISRCTN/DRKS. Only fall back to
   direct Tier-1 sources if WHO is unreachable (no token / 403) — via FALLBACK-PROMPT, no auto fan-out.
2. **Keywords + translation** — derive per-source terms and translate: EN for CT.gov/WHO/PubChem
   (`Type 2 Diabetes` + `DPP-4 inhibitor`); ZH for CDE (`II型糖尿病`/`2型糖尿病` + `DPP-4抑制剂`,
   strip the `类` suffix; never `DPP-4抑制剂类`). Category terms → use acronym/full-name or enumerate
   members, not a bare class suffix.
2b. **Prefer advanced search when the prompt has a parameter combo (v0.3.14)** — WHO AdvSearch
   exposes **Phases** + condition/intervention/sponsor/country/date fields; CDE AdvSearch exposes
   登记号/适应症/药物名称/药物类型/申请人/试验状态 (NO phase filter). When the user's prompt
   contains a combination (drug + phase, disease + sponsor + country + year, …), build a **structured
   payload** instead of bare keyword: WHO → `--who-condition/--who-intervention/--who-sponsor/
   --who-country/--who-phase` (auto `mode=combined`); CDE → `--reg-no/--indication/--drugs-name/
   --drugs-type/--appliers/--trial-status` (auto `is_advanced_search`). ⚠️ `--who-phase` server-side
   filtering **under-captures combined/numeric phases** (verified: Olverembatinib +I/II → 2 of ~19
   true I/II); use it only as a coarse narrowing, and always re-validate phase on detail-normalized
   `phase` (authoritative). Full field→CLI map in SKILL.md "Advanced search (高级检索)".
3. **Execute + return** — direct sources run free (`--run`, no quota); external-workflow sources
   ride the shared endpoint (**1 count PER DEMAND** via `usage_guard`: WHO+CDE / keyword tweaks /
  repeats sharing one `demand_id` collapse to a single count; daily cap = 100 demands; **local long-lived token, no refresh needed**).
   Then `normalize → aggregate → report`; PDFs never auto-download (only `--download-docs` on
   explicit user request). Full text in SKILL.md "Search procedure" section.

### Resource-usage policy (v0.3.1, enforced in code)
- WHO / CDE retrieval is **free** but rides a **shared** third-party endpoint (Coze /run); follow
  **minimal shared-resource occupation**. Bulk retrieval needs → direct the user to **contact the
  author (Wintone) for coordination**.
- **Hard daily cap = 100 demands** (a demand = one `ct_registry.py --run`, or one agent task of
  step-by-step retrievals sharing a `demand_id`). WHO+CDE / keyword tweaks / repeats inside the SAME
  demand all collapse to **1 count** — charged per `demand_id`, not per raw HTTP call. Counts only
  real `--run` network calls (WHO/CDE/ChiCTR/ISRCTN/DRKS); preview / `--store-token` / direct sources
  CT.gov/EU-CTR/PubChem are NOT counted. Rolls over at local midnight. **Each call prints the
  remaining quota** (a repeat of an already-counted demand prints "already counted, not re-charged");
  at 100 demands the call is BLOCKED with "come back tomorrow". Counter: `config/usage.json` (fail-open on IO error).
- **PDFs are NEVER auto-downloaded**: `download_docs.py` lists links by default and downloads only
  with `--yes`; the orchestrator downloads only when `--download-docs` (explicit user request) is set.
- Enforcement: `scripts/usage_guard.py` (`check()`), called from `search_ictrp.py`,
  `CDE/search_cde_workflow.py` (archived standalone), and `extsvc_client.dispatch()`; `ct_registry.py` also prints the policy
  in preview mode.

---

## Core Rules (inherited from ct-base, applies library-wide)

### 1. R / Python Environment Detection
- Python via Anaconda (`C:\Tools\anaconda3\python.exe`); do not hardcode paths.

### 2. Code Execution
- **Default: SAFE PREVIEW (dry-run).** Scripts show the planned call; execute only with `--run`.
- Temp files written to system temp, auto-cleaned.

### 3. Language Detection (see references/language_policy.md)
- Default English; auto-switch to Chinese on Chinese-OS.
- Common modules prepare EN+ZH; code output always English.

### 4. Security Red Line (inherited from ct-base, highest priority)
- **Read public registry data via public retrieval; zero confidential data or information input.** This skill is B-tier quickly-adoptable.
- CDE primary automatable path is the **unified endpoint** (`search_ictrp.py --source chinadrugtrials` → third-party endpoint `ct-search.coze.site/run`), shared with WHO ICTRP. It sends only public query terms and REQUIRES a Bearer token. The legacy **standalone** CDE workflow (`CDE/search_cde_workflow.py` → `ct-searchcde.coze.site/run`, archived under `CDE/`, NOT shipped) is retired and only reachable via `ct_registry.py --cde-legacy` as a local fallback. Paste-mode Playwright / `parse_cde.py` local parse stays a no-egress fallback. Always disclose "data passes through a third party" for any workflow path.
- All user strings whitelist-validated to prevent injection / RCE.
- `permissions` block explicitly declared at top level of SKILL.md.
- **Tokens (`config/*.dat`) are obfuscated PUBLIC shared Coze/ICTRP credentials** (not personal). Classified as public per ct-base §5; excluded from the published package by design (installers supply their own via `--store-token` / env, or a deploy populates the blob). Never paste tokens in chat.

### 5. Reuse from base
- Copied from `ct-base`: `i18n.py`, `r_libs.py`, `language_policy.md`, `report_template.md`, `icon.svg`. Business scripts live in `scripts/`.

---

## Menu / Navigation Design (ct-base §6)

### 6. Menu / Navigation Design — Non-Exclusive / 交互菜单 / 导航设计：互不互斥
- 全库通用 UX 基线。ct-registry 的注册库 / 场景入口**不得设计成互斥树**：同一注册库可出现在多个入口下。 / Library-wide UX baseline. The registry / scenario entries MUST NOT be a mutually-exclusive tree; the same source can appear under multiple top-level entries.
- 例：「德国试验」既可从「区域」入口勾 DRKS，也可从「全球全部源」入口勾 DRKS；「中国试验」既可从「区域」入口勾 CDE+ChiCTR，也可从「中国全覆盖」预设进入。 / Example: "German trials" is reachable BOTH from a **Region** entry (DRKS) AND from an **All global sources** entry (DRKS); "China trials" from both **Region** (CDE+ChiCTR) and an **China coverage** preset.
- 菜单是「引导」而非「严格分类」。 / The menu is a *navigation aid*, not a taxonomy.

### 6.1 Natural Language Dialogue / 自然语言对话参数确认
- 当用户通过自然语言触发检索时，遵循本技能 `references/search_menu.md` 定义的对话流程（ct-base §6.1 的定制实现）。 / When triggered via natural language, follow the dialogue flow defined in `references/search_menu.md` (the ct-registry customization of ct-base §6.1).
- 核心流程（2026-07-30 更新）：识别意图 → 收集参数 → **Gate1 检索前简报**（关键字/范围/时间窗/demand_id/免费10次每日）→ 执行 → **Gate2 列表确认**（先给列表，确认正确后再确认是否抓详情/下载）。参数缺失时最多追问 2 轮，然后使用默认值。 / Core flow (updated 2026-07-30): parse intent → collect params → **Gate1 pre-search brief** (keywords/scope/time-window/demand_id/free-10-per-day) → execute → **Gate2 list confirmation** (show list first, then confirm details/download after user approves the list). Max 2 rounds of follow-up for missing params, then use defaults.
- 定制要点：检索主题（cond/intr/drug）必填；数据源默认 CT.gov+EU CTR（Tier 1 直连）；国外源术语未命中触发确认门（§6.4）；详情抓取按条目数分档——≤100 条直接自动抓取，>100 条先确认列表再抓取；文档（PDF）始终需显式确认，不自动下载。 / Customization: search term required; default sources CT.gov+EU CTR; foreign-source term miss triggers a confirm gate (§6.4); detail fetching is tiered by count — ≤100 auto-fetch directly, >100 confirm list first; documents (PDF) always require explicit confirmation, never auto-download.

---

## Dependencies

### Python (shared + business)
```
requests>=2.28
pandas>=1.5
beautifulsoup4>=4.12
lxml>=4.9
# optional
matplotlib>=3.6     # PNG charts
playwright>=1.40    # CDE local scraping (requires playwright install chromium)
```
