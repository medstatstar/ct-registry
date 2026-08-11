#!/usr/bin/env python3
"""ct_registry.py - Orchestrator / 顶层编排.

CT.gov (required) + optional direct-connect sources (EU-CTR pure HTTP) +
optional external-service sources (CDE / ChiCTR / ISRCTN / DRKS, each via a
Coze /run workflow that bypasses WAF/JS) + optional PubChem enrich +
normalize + aggregate (self-controlled bridge/dedup) + report.

ARCHITECTURE DECISION 2026-07-27 (reverses 2026-07-24): WHO ICTRP IS now a
Tier-2 data source, via a clean external service (Coze /run, source="who") that
mirrors 14+ primary registries in one call. We still PARALLEL-DIRECT-CONNECT the
registries we can and do our own bridge/dedup (registration-number normalization
+ fuzzy match, CT.gov primary) in aggregate.py; ICTRP's full-record `raw` is
bridged on embedded registry numbers (NCT/JPRN/CTRI/...).
- Tier 1 (pure HTTP, no browser): CT.gov (REST v2), EU-CTR (legacy EudraCT HTML parse).
- Tier 2 (no clean API -> external service, all via the UNIFIED Coze endpoint
  ct-search.coze.site/run sharing ONE ICTRP token): CDE (source=chinadrugtrials),
  WHO ICTRP (source=who), and the WHO-covered national registries ISRCTN
  (source=isrctn) / DRKS (source=drks) / ChiCTR (source=chictr) used as fallback
  when WHO ICTRP (source="who") cannot retrieve.
- WHO-COVERED FALLBACK POLICY (2026-07-28, revised 2026-07-28): when --with-ictrp is
  set, WHO ICTRP is the PRIMARY aggregator; the national registries it covers
  (CT.gov, EU-CTR, ISRCTN, DRKS, ChiCTR) become FALLBACK-ONLY. They are SKIPPED on
  WHO success and run independently + aggregated ONLY if WHO cannot retrieve (we
  PROMPT the user; pass --fallback-covered to execute). PubChem enrich is unaffected.
  EXCEPTION: CDE is ALWAYS retrieved independently (never skipped on WHO success,
  never a fallback) because WHO's English-title matching misses Chinese trials.
  WHO and CDE are retrieved concurrently in Batch-1 (see _who_cmd / _run_parallel).
- NO local Playwright/headless browser anywhere (owner rule).

CDE is opt-in via --with-cde; the other external sources via --with-<src>. Each
needs a Bearer token (config/env). The external workflow is the automatable path
that bypasses WAF/JS walls. All results normalize into the SAME schema.

Keyword localization policy (ct-registry optimization 2026-07-24)
---------------------------------------------------------------
- Foreign registries (CT.gov, PubChem) expect ENGLISH keywords.
- Domestic CDE expects CHINESE but also accepts ENGLISH (bilingual-friendly).
- Resolution is TWO-PHASE:
  1. TERMINOLOGY FIRST: consult ct-base/references/term_map.json.
  2. CONFIRM-ON-MISS: if a foreign-source keyword is NOT in the map, we STOP and
     ask the user to confirm a proposed translation (via --confirm-* or by
     rewriting the argument) before any network call -- so we never silently
     search CT.gov with a wrong-language term. CDE, being bilingual, still runs
     (and bilingual mode additionally tries the other language).
- CDE BILINGUAL (default ON): when a CDE keyword has a known (zh, en) pair, we
  search CDE once with the Chinese keyword and once with the English keyword,
  then merge the two result sets (dedup by registry_id). This captures trials
  registered in either language on CDE. Disable with --no-cde-bilingual.

Safety: network requests run only with --run (default = preview).
"""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import time
import concurrent.futures
import usage_guard
import track_diff  # P0-A: local status diff / snapshot track (no network)

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

# --- P0-B run-status manifest (graceful-degradation disclosure) ----------
# Surfaced to the user via run_status.json + a disclosure line appended to
# report.md. Only mutated during a networked (--run) retrieval.
_RUN_STATUS = {
    "who_status": "ok",                 # "ok" | "failed" (WHO timed out / errored)
    "cde_zero_hit_unverified": False,   # CDE returned 0 after retry
    "cde_retried": 0,                   # number of CDE auto-reruns performed
}

# Shared ct-base assets (i18n + the keyword-expansion engine `kw_localize`) are
# vendored into this skill directory (see ct-base/scripts/publish_inject.py).
# IMPORTANT (2026-08-11): ct-base is NEVER published. Every ct- skill must carry
# its own complete copy of shared assets. At runtime we ONLY resolve from this
# skill's own `scripts/` directory — never fall back to a ct-base sibling.
for _p in (HERE,):
    if os.path.isdir(_p):
        sys.path.insert(0, _p)

import kw_localize as kl

# keyword_breadth is also a ct-base shared asset (vendored into this skill).
try:
    from keyword_breadth import (is_broad_keyword, choose_primary_keyword,
                                 plan_coze_keywords)
except Exception:  # noqa: BLE001  (vendored copy guaranteed in publish package)
    is_broad_keyword = choose_primary_keyword = plan_coze_keywords = None

# Bilingual runtime prompts delegate to ct-base's shared i18n (EN default, ZH on
# a zh-* OS). Only framework labels are localized; raw data values are not.
try:
    from i18n import t as _t  # noqa: F401
except Exception:  # noqa: BLE001  (vendored copy guaranteed in publish package)
    def _t(key, **kw):
        return kw.get("_default", key)

# Excel export is now built-in (no hand-written post-processing script needed).
sys.path.insert(0, HERE)
try:
    from export_xlsx import export_workbook as _export_xlsx
except Exception as _xlsx_err:  # pragma: no cover - defensive
    _export_xlsx = None
    print(f"[ct_registry][WARN] export_xlsx 不可用 ({_xlsx_err}); 将跳过 Excel 生成。")


def _load_recs(path):
    """Load normalized records from a .json that may be a list or a dict."""
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return []
    if isinstance(d, list):
        return d
    if isinstance(d, dict):
        return d.get("records") or d.get("records_all") or d.get("projects") or []
    return []


def _reg_year(r):
    """Registration year: start_date year, else year embedded in registry_id."""
    import re as _re
    sd = r.get("start_date") or ""
    m = _re.search(r"(19|20)\d{2}", str(sd))
    if m:
        return int(m.group())
    rid = r.get("registry_id") or r.get("登记号") or r.get("project_id") or ""
    m = _re.search(r"(19|20)\d{2}", str(rid))
    return int(m.group()) if m else 0


def _is_timeout(reason):
    """Detect a shared-endpoint timeout / network failure from an error string.

    Accepts either ``str`` or ``bytes`` (subprocess stderr is bytes) — a bytes
    value is decoded before matching. This guards every timeout check site
    (including the parallel CDE/WHO result interpreters) against a TypeError
    when the captured stderr is bytes.
    """
    if isinstance(reason, bytes):
        reason = reason.decode("utf-8", "replace")
    r = (reason or "").lower()
    return any(k in r for k in ("timed out", "timeout", "request failed",
                                "readtimeout", "connectionerror", "connectionreset"))


def _cp_stderr(e):
    """Extract stderr text from a CalledProcessError (bytes -> str)."""
    s = getattr(e, "stderr", "") or ""
    if isinstance(s, bytes):
        s = s.decode("utf-8", "replace")
    return s


def _print_timeout_advice(source):
    """User-facing advice when a shared-endpoint retrieval times out."""
    print("  ── 后续建议 ──")
    print(f"  1. 稍后重试：共享端点(ct-search.coze.site)多为临时网络抖动，通常数分钟内恢复，"
          f"重跑同一条命令即可。")
    print("  2. 网络检查：确认本机可访问外网；若处于公司代理/防火墙环境，可能需要放行该域名。")
    print("  3. 单源重试：若仅需某一源，可单独重跑（如仅 WHO 用 --with-ictrp；仅 CDE 用 --with-cde），"
          "避免长时间等待无关源。")
    print("  4. 持续/批量超时：联系技能作者 Wintone 协调共享端点资源或获取备用端点。")


def _cover_title(args):
    """Build a short cover title from the supplied query arguments."""
    parts = []
    for v in (args.cond, args.intr, args.drug, args.ictrp_keyword,
              args.cde_keyword, args.cde_indication):
        if v:
            parts.append(str(v))
    kw = " / ".join(parts) or "临床试验检索"
    win = f" (≥{args.min_year})" if args.min_year else ""
    return f"{kw}{win}"


def _cleanup_meta(out_dir):
    """Remove intermediate .md/.json files, keeping only .xlsx deliverables.

    In sandboxed environments where unlink is blocked (recycle-bin
    unavailable), move files aside into an `_unsaved/` subdir so the
    deliverable directory still stays clean of intermediate artifacts.
    """
    if not os.path.isdir(out_dir):
        return
    trash = os.path.join(out_dir, "_unsaved")
    for fn in os.listdir(out_dir):
        if fn.lower().endswith((".md", ".json")):
            p = os.path.join(out_dir, fn)
            try:
                os.remove(p)
            except OSError:
                # unlink blocked (sandbox recycle-bin unavailable): move aside
                try:
                    os.makedirs(trash, exist_ok=True)
                    os.replace(p, os.path.join(trash, fn))
                except OSError:
                    pass


def run(cmd):
    print("+ " + " ".join(cmd))
    subprocess.run(cmd, check=True)


def _resolve(raw, target, confirm_val):
    """Resolve a keyword to its target-language value.

    Returns (value, status). status in {confirmed, empty, same, term_map, miss}.
      - confirm_val given        -> (confirm_val, 'confirmed')  (user-supplied)
      - no raw                   -> (None, 'empty')
      - kw_localize result       -> (value, source) where source in
                                    {same, term_map, miss}
    """
    if confirm_val:
        return confirm_val, "confirmed"
    if not raw:
        return None, "empty"
    return kl.localize(raw, target)


def _derive_kw(args, lang):
    """Derive a search keyword for an opt-in source from the primary term.

    Uses kw_localize to switch language; falls back to the raw term if the map
    misses (external sources are bilingual-friendly, so no abort gate here).
    """
    base = args.cond or args.drug
    if not base:
        return None
    v, st = kl.localize(base, lang)
    if st in ("term_map", "same"):
        if st == "term_map":
            print(f"[ct_registry][i18n] {lang.upper()} keyword: {base!r} -> {v!r}")
        return v
    print(f"[ct_registry][i18n] {lang.upper()} keyword: 未命中术语表, 直接使用原文 {base!r}")
    return base


# --- Keyword-System Confirmation Gate (ct-registry v0.4) ---
def _kw_inject_manifests(args, manifests):
    """Derive per-source keyword injection from confirmed manifests and mutate args.

    Uses the design's per_source recommendations:
      - EN exact engines (CT.gov --intr/--cond, WHO, PubChem): the class/primary EN
        token (manifest["en"][0]) — robust single-term match.
      - ZH substring engines (CDE, ChiCTR): the optimized ZH set (class suffix for
        drug_class; e.g. "列汀"), injected via the existing override flags so the
        downstream command builders pick them up unchanged.
    """
    cond_en = intr_en = who_en = None
    cde_parts, chi_parts = [], []
    for axis, base, m in manifests:
        en0 = m["en"][0] if m.get("en") else base
        ps = m.get("per_source", {})
        cde_kw = (ps.get("cde") or {}).get("keywords") or m.get("zh", [])[:1]
        chi_kw = (ps.get("chictr") or {}).get("keywords") or cde_kw
        if axis == "condition":
            cond_en = en0
        else:
            intr_en = en0
            who_en = en0
        cde_parts.extend(cde_kw)
        chi_parts.extend(chi_kw)
    if intr_en:
        args.confirm_intr = intr_en
        args.confirm_drug = intr_en
    if cond_en:
        args.confirm_cond = cond_en
    if who_en:
        args.ictrp_keyword = who_en
    if cde_parts:
        args.cde_keyword = " ".join(dict.fromkeys(cde_parts))
    if chi_parts:
        args.chictr_keyword = " ".join(dict.fromkeys(chi_parts))
    print(f"[ct_registry][KW] 采用关键字体系 → EN={intr_en or cond_en} | "
          f"ZH(CDE/ChiCTR)={args.cde_keyword}")


def _kw_apply_override(args):
    """Direct override injection from the agent after an edited confirmation.

    Used when the user deleted/added words: the agent passes the final EN/ZH sets
    via --kw-en / --kw-zh (comma-separated) instead of adopting the proposed set.
    """
    en = [w.strip() for w in (args.kw_en or "").split(",") if w.strip()]
    zh = [w.strip() for w in (args.kw_zh or "").split(",") if w.strip()]
    if en:
        en_term = en[0]
        if args.intr or args.drug:
            args.confirm_intr = en_term
            args.confirm_drug = en_term
        if args.cond:
            args.confirm_cond = en_term
        args.ictrp_keyword = en_term
    if zh:
        zh_term = zh[0]
        args.cde_keyword = zh_term
        args.chictr_keyword = zh_term
    print(f"[ct_registry][KW] 直接注入覆盖 → EN={en} | ZH={zh}")


def _kw_system_gate(args):
    """Keyword-System Confirmation Gate: expand + bilingual match, force-confirm.

    Inserted before Gate 1. Triggered whenever a parseable keyword exists, unless
    --no-expand. Flow:
      1) build Manifest(s) for the provided axes (intervention/drug + condition);
      2) --kw-en/--kw-zh given -> direct(edited) injection, proceed;
      3) --kw-adopt -> cache + inject + proceed (user confirmed via menu);
      4) all axes cached this session -> reuse, no menu (avoids re-confirm);
      5) else render menu and STOP (sys.exit) until the user confirms.
    """
    if args.no_expand:
        print("[ct_registry][KW] --no-expand: 跳过关键字体系确认门。")
        return
    if args.kw_en or args.kw_zh:
        _kw_apply_override(args)
        return
    bases = []
    if args.intr or args.drug:
        bases.append(("intervention", args.intr or args.drug))
    if args.cond:
        bases.append(("condition", args.cond))
    if not bases:
        return
    intent = args.expand_intent or "auto"
    manifests, all_cached = [], True
    for axis, base in bases:
        m = kl.get_cached_manifest(base, intent)
        if m is None:
            all_cached = False
            m = kl.expand_keyword(base, intent)
        if m:
            manifests.append((axis, base, m))
    if args.kw_adopt:
        for _, _, m in manifests:
            kl.cache_manifest(m, intent)
        _kw_inject_manifests(args, manifests)
        return
    if all_cached and manifests:
        print("[ct_registry][KW] 命中会话缓存, 直接采用已确认关键字体系。")
        _kw_inject_manifests(args, manifests)
        return
    # not confirmed -> show menu and STOP (no --run issued until user confirms)
    print(kl.render_kw_system_menu_multi(manifests))
    print("")
    print(_t("kw_gate.stopped"))
    sys.exit(0)


def _merge_bilingual(zh_path, en_path, out_path, label="bilingual"):
    """Merge two normalized outputs (dicts carrying 'records') by registry_id.

    Generic for any bilingual source (CDE / ChiCTR). The merged dict keeps zh-run
    metadata and replaces records/projects with the de-duplicated union.
    normalize.py reads `data.get("records", [])`, so this stays compatible.

    Robust to BOTH input shapes: a dict with a `records`/`projects` key (raw
    CDE output) OR a bare JSON list (e.g. the output of normalize.py, which is a
    plain list). Previously a bare list raised ``'list' object has no attribute
    'get'`` when the orchestrator merged normalized outputs — now handled.
    """
    def _load(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    def _records_of(obj):
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            return obj.get("records") or obj.get("projects") or []
        return []
    a = _load(zh_path)
    b = _load(en_path)
    ra = _records_of(a)
    rb = _records_of(b)
    if not isinstance(ra, list):
        ra = []
    if not isinstance(rb, list):
        rb = []
    seen = {}
    for rec in ra + rb:
        if not isinstance(rec, dict):
            continue
        # Match by the trial's registry number across raw + normalized shapes:
        # normalized uses registry_id/nctId/id; RAW CDE uses 登记号; WHO uses
        # Main ID / TrialID. Without this, a zh (登记号) and en (登记号) record
        # for the SAME trial would NOT collapse (they'd only share title, which
        # differs by language) -> bilingual dedup silently fails.
        rid = None
        for f in ("registry_id", "nctId", "id", "登记号", "Main ID", "TrialID", "trial_id"):
            if rec.get(f):
                rid = rec.get(f)
                break
        key = rid or (rec.get("title"), rec.get("url"))
        seen[key] = rec
    merged = list(seen.values())
    # If `a` was a bare list (no metadata), start from an empty dict so we don't
    # try to call dict() on a list.
    out = dict(a) if isinstance(a, dict) else {}
    out["records"] = merged
    out["projects"] = merged
    out["total_count"] = len(merged)
    out["bilingual_merge"] = {"zh": len(ra), "en": len(rb), "merged": len(merged)}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[ct_registry][{label}] 中英双检合并: zh {len(ra)} + en {len(rb)} "
          f"-> {len(merged)} 条 (去重)")


# back-compat alias
_bilingual_cde_merge = _merge_bilingual


def _emit_run_status(args):
    """P0-B: write the run-status manifest and append a data-flow disclosure.

    Only meaningful after a networked (--run) retrieval — the manifest flags
    (``who_status``, ``cde_zero_hit_unverified``) are only ever set during a
    real pull. Emits ``run_status.json`` and, when a degradation happened, a
    disclosure paragraph appended to ``report.md`` so the user is never left
    with a silently-incomplete report.
    """
    if not getattr(args, "run", False):
        return
    out_dir = args.out_dir
    try:
        with open(os.path.join(out_dir, "run_status.json"), "w", encoding="utf-8") as f:
            json.dump(_RUN_STATUS, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ct_registry][run_status] skip write: {e}")

    who_failed = _RUN_STATUS.get("who_status") == "failed"
    cde_zero = _RUN_STATUS.get("cde_zero_hit_unverified")
    if not (who_failed or cde_zero):
        return
    lines = ["", "> ⚠️ 数据流向披露（降级兜底 / degradation fallback）："]
    if who_failed:
        lines.append("> - WHO ICTRP 端点检索超时/失败，已自动降级为 CDE + ClinicalTrials.gov "
                     "独立出报告（who_status=failed；未隐藏、未假装完整，覆盖源可能不全）。")
    if cde_zero:
        lines.append("> - CDE 返回 0 条且自动重跑仍 0 条，标记 zero_hit_unverified"
                     "（未经第三方复核，该部分结果仅供参考）。")
    lines.append("> 其余数据仍通过公开注册库 / 第三方统一端点（Coze）检索，仅公开查询词出域；"
                 "详见 SKILL.md 数据流向说明。")
    try:
        with open(os.path.join(out_dir, "report.md"), "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print("[ct_registry][run_status] disclosure appended to report.md "
              f"(who_status={_RUN_STATUS['who_status']}, "
              f"zero_hit_unverified={cde_zero}, cde_retried={_RUN_STATUS['cde_retried']})")
    except Exception as e:
        print(f"[ct_registry][run_status] disclosure append skipped: {e}")


def main():
    ap = argparse.ArgumentParser(
        description="Cross-source trial-registry search -> normalize -> aggregate -> report")
    # CT.gov (required source)
    ap.add_argument("--cond")
    ap.add_argument("--intr")
    ap.add_argument("--sponsor")
    ap.add_argument("--status")
    ap.add_argument("--max", type=int, default=50, help="CT.gov 返回条数上限 (default 50)")
    ap.add_argument("--ctgov-api-key", help="CT.gov API key (opt-in; 启用快速路径: Session 连接池 + 大 pageSize)。"
                         "有 key 时走 search_ctgov.py --fast，无 key 时保留默认 urllib 路径。")
    # PubChem enrich
    ap.add_argument("--with-pubchem", action="store_true")
    ap.add_argument("--drug")
    # CDE cross-source (opt-in)
    ap.add_argument("--with-cde", action="store_true",
                    help="also retrieve China CDE and merge into the landscape. PRIMARY path = "
                         "unified endpoint (search_ictrp.py --source chinadrugtrials -> "
                         "ct-search.coze.site/run). Add --cde-legacy to use the standalone "
                         "ct-searchcde.coze.site/run fallback instead.")
    ap.add_argument("--cde-keyword", help="CDE free keyword (or first term); required when --with-cde without --cde-multi-keywords")
    ap.add_argument("--cde-multi-keywords", help="CDE multi_keyword mode (space-separated AND terms)")
    ap.add_argument("--cde-mode", choices=["search", "combined", "multi_keyword"], default="search",
                    help="CDE mode when --cde-keyword is given (default search; 'combined' = keyword + filters)")
    ap.add_argument("--cde-indication")
    ap.add_argument("--cde-drugs-name")
    ap.add_argument("--cde-drugs-type", help="enum: 中药/天然药物/化学药物/生物制品")
    ap.add_argument("--cde-appliers")
    ap.add_argument("--cde-trial-status", help="enum (11 values), e.g. 进行中/已完成")
    ap.add_argument("--cde-legacy", action="store_true",
                    help="CDE 改用独立端点 ct-searchcde.coze.site/run（CDE/search_cde_workflow.py，本地归档、不随包发布）兜底，"
                         "而非默认的统一端点 ct-search.coze.site/run（source=chinadrugtrials）。"
                         "仅当统一端点异常时启用。")
    ap.add_argument("--cde-api-key", help="CDE 商业 API key (opt-in; 走丁香园直连 ~1-3s, 无需 Coze token)。"
                         "有 key 时优先走快速路径，无 key 时保留现有 Coze workflow 路径。")
    # keyword localization control
    ap.add_argument("--confirm-cond", help="已确认英文译文(CT.gov --cond): 跳过术语确认门")
    ap.add_argument("--confirm-intr", help="已确认英文译文(CT.gov --intr/--drug): 跳过术语确认门")
    ap.add_argument("--confirm-drug", help="已确认英文译文(PubChem --drug): 跳过术语确认门")
    ap.add_argument("--confirm-cde-keyword", help="已确认中文译文(CDE 关键字): 跳过派生/确认")
    # keyword-system confirmation gate (v0.4)
    ap.add_argument("--no-expand", action="store_true",
                    help="跳过「关键字体系确认门」(直接进 Gate 1, 保留旧行为)")
    ap.add_argument("--expand-intent", choices=["disease", "intervention", "drug", "drug_class"],
                    help="显式指定关键字体系意图, 规避 auto 误判(仅影响扩展枚举)")
    ap.add_argument("--kw-adopt", action="store_true",
                    help="用户已在确认门选「采用」→ 采用并缓存已扩展关键字体系, 直接检索")
    ap.add_argument("--kw-en", help="确认门编辑后注入: 逗号分隔的英文关键字集(覆盖 auto-localize)")
    ap.add_argument("--kw-zh", help="确认门编辑后注入: 逗号分隔的中文关键字集(CDE/ChiCTR 子串)")
    # Direct-connect Tier 1 / external-service Tier 2 opt-in sources
    ap.add_argument("--with-euctr", action="store_true",
                    help="also retrieve EU Clinical Trials Register (legacy EudraCT), pure HTTP")
    ap.add_argument("--with-isrctn", action="store_true",
                    help="also retrieve ISRCTN via external workflow (no clean search API)")
    ap.add_argument("--with-drks", action="store_true",
                    help="also retrieve DRKS (German register) via external workflow")
    ap.add_argument("--with-chictr", action="store_true",
                    help="also retrieve ChiCTR (China academic trials) via external workflow")
    ap.add_argument("--euctr-keyword", help="EU-CTR keyword override (else derived, EN)")
    ap.add_argument("--isrctn-keyword", help="ISRCTN keyword override (else derived, EN)")
    ap.add_argument("--drks-keyword", help="DRKS keyword override (else derived, EN)")
    ap.add_argument("--chictr-keyword", help="ChiCTR keyword override (else derived, ZH)")
    ap.add_argument("--with-ictrp", action="store_true",
                    help="include WHO ICTRP (Tier-2 external service, source='who'); "
                         "mirrors 14+ registries -- jRCT, DRKS, ANZCTR, ISRCTN, CTRI, ... -- "
                         "in one call")
    ap.add_argument("--ictrp-keyword", help="WHO ICTRP keyword override (else derived, EN)")
    ap.add_argument("--who-phase", help="WHO 高级检索 Phases 参数(逗号分隔, 如 'Phase 1,Phase 2,"
                         "Phase 1/Phase 2,Early Phase 1'); 透传给 search_ictrp.py --who-phase。"
                         "注意: 服务端 Phases 归一化字段较窄, 会漏掉部分联合期/数字期, "
                         "因此仅作粗筛降量, 最终分期以 detail 后归一化 phase 为准(详见 SKILL.md 高级检索)。")
    # WHO 高级检索（combined 模式）—— 由代码实现，用户无需手动操作字段。
    # 超时兜底时由代理（agent）通过 --who-mode combined 重新发起：复合关键字按
    # 药物→who_intervention / 疾病→who_condition / 申办方→who_sponsor 拆分，服务端 AND 过滤。
    ap.add_argument("--who-mode", choices=["search", "combined"],
                    help="WHO 检索模式：默认 search（自由文本）；combined = 高级检索（who_* 字段级 AND 过滤，"
                         "返回量更小、通常更快，适合超时兜底）。未显式指定但给了任一 --who-* 字段时自动转 combined。")
    ap.add_argument("--who-condition", help="WHO 高级检索：疾病/健康状况（对应 --cond）")
    ap.add_argument("--who-intervention", help="WHO 高级检索：干预/药物（对应 --drug/--intr）")
    ap.add_argument("--who-sponsor", help="WHO 高级检索：申办方")
    ap.add_argument("--who-country", help="WHO 高级检索：招募国家（逗号分隔）")
    ap.add_argument("--auto-confirm", action="store_true",
                    help="术语缺失时不中止, 直接用原文检索(可能漏检) -- 仅用于已知安全的自动化")
    ap.add_argument("--no-cde-bilingual", action="store_true",
                    help="关闭 CDE 中英双检(默认开启: 同时用中文与英文关键字检索并合并)")
    ap.add_argument("--with-detail", action="store_true",
                    help="检索后自动补结构化详情: CDE 跑 detail 模式拉 65 字段(合并 sponsor/phase/"
                         "入排/终点); EU-CTR 调 CTIS 文档端点抽取可下载文档链接。默认关。")
    ap.add_argument("--download-docs", action="store_true",
                    help="确认门控: 真正下载报告中列出的可下载 PDF(默认仅列出链接, 不下载)。"
                         "显式传此旗即代表用户确认下载。")
    ap.add_argument("--fallback-covered", action="store_true",
                    help="WHO 主路径失败时的兜底执行开关: 对 WHO 已覆盖、除 CDE 外的全部试验注册库"
                         "(CT.gov/EU-CTR/ISRCTN/DRKS/ChiCTR) 分别独立检索并聚合。"
                         "注意: CDE(中国药物临床试验)始终独立检索, 不属此回落集合。"
                         "仅在 --with-ictrp 且 WHO 检索失败时生效。")
    ap.add_argument("--since-years", type=int, default=0,
                    help="仅取近 N 年注册的试验(按 WHO 注册日期区间过滤); "
                         "仅当 --with-ictrp 时生效, 透传给 WHO 主调用 "
                         "(--who-date-start/--who-date-end, DD/MM/YYYY)。")
    # output shaping
    ap.add_argument("--min-year", type=int, default=0,
                    help="注册年份精确下限(>=); 按 start_date 年份筛选(缺失时 CDE 用登记号年份兜底)。0=不筛选。")
    ap.add_argument("--no-excel", dest="excel", action="store_false",
                    help="关闭内置 Excel 生成(默认生成 .xlsx)。")
    ap.add_argument("--keep-meta", action="store_true",
                    help="保留中间 md/json(默认删除, 仅留 .xlsx)。")
    ap.add_argument("--lang", choices=["auto", "zh", "en"], default="auto",
                    help="Excel 界面语言(默认 auto=OS locale)。")
    # io
    ap.add_argument("--out-dir", default="./out")
    ap.add_argument("--run", action="store_true",
                    help="actually run network requests (default = preview only)")
    # --- P0-A: local snapshot track / diff (no network) ---
    ap.add_argument("--diff", nargs=2, metavar=("SNAP_A", "SNAP_B"),
                    help="本地比对两快照 normalized.json（按 NCT 集合 diff）-> status_delta"
                         "（纯本地、零联网，不触发任何网络请求）")
    ap.add_argument("--diff-out", help="--diff 结果写出 JSON 路径（默认仅打印）")
    ap.add_argument("--track", action="store_true",
                    help="--run 后将归一化结果写入 registry_snapshot.json，供下次 --diff 比对"
                         "（增量兼容，不破坏原 normalized.json 输出）")
    # --- P0-B: Tier-2 graceful-degradation knobs (only active on --run / network) ---
    ap.add_argument("--cde-retry", type=int, default=1,
                    help="CDE 返回 0 条时的自动重跑次数（默认 1，限频）；仅 --run 联网时触发")
    ap.add_argument("--cde-retry-delay", type=float, default=2.0,
                    help="CDE 重跑之间的限频间隔秒数（默认 2.0，避免放大端点负载）")
    args = ap.parse_args()

    # P0-A: pure-local diff is handled standalone (no network, no gates) and exits.
    if args.diff:
        track_diff.cmd_diff(args.diff[0], args.diff[1], args.diff_out)
        return
    # One ct_registry --run = ONE retrieval demand. Inject a unique demand_id into the
    # environment so every child process (WHO + CDE + detail + tweaks within this run)
    # shares it and collapses to a SINGLE counted call against the shared endpoint.
    import os as _os
    import datetime as _dt
    _os.environ["CT_DEMAND_ID"] = f"ctreg-{_dt.datetime.now():%Y%m%d%H%M%S%f}"

    # Reset the P0-B run-status manifest for this run (fresh process in normal
    # use; reset defensively in case the module is reused across calls).
    for _k in _RUN_STATUS:
        if _k == "who_status":
            _RUN_STATUS[_k] = "ok"
        else:
            _RUN_STATUS[_k] = (0 if _k == "cde_retried" else False)

    # 关键词广度守卫（检索前拦截，preview 与 --run 均生效，无网络）：
    # Coze 完整翻页源单关键词过宽 -> 中止；多关键词自动重排主词。
    _guard_keyword_breadth(args)

    if not args.run:
        print("[ct_registry][PREVIEW] add --run to execute network requests.")
        if args.with_cde:
            if args.cde_api_key:
                print("[ct_registry][PREVIEW]   CDE source WILL be included (commercial API fast path, ~1-3s).")
            else:
                print("[ct_registry][PREVIEW]   CDE source WILL be included (needs Bearer token).")
        # Policy reminder (shared-resource minimal occupation + bulk coordination).
        print("[ct_registry][POLICY] WHO/CDE 等共享端点检索遵循「共享资源最小占用」原则："
              "每日上限 100 次，达上限请次日再用；"
              "大批量检索需求请直接联系技能作者 Wintone 协调。")
        print("[ct_registry][POLICY] PDF 文档默认不自动下载；仅在您明确要求下载时才会执行。")
        return

    os.makedirs(args.out_dir, exist_ok=True)

    # --- Keyword-System Confirmation Gate (NEW, forced before Gate 1) ---
    # Expand + bilingual-match the user's keyword(s); STOP and show a confirmation
    # menu until the user adopts (--kw-adopt) or opts out (--no-expand).
    _kw_system_gate(args)

    norm_inputs = []

    # --- CT.gov (required source, expects ENGLISH keywords) ---
    # `--drug` doubles as the CT.gov intervention term when neither --cond/--intr
    # is given, so `ct_registry.py --drug X` yields real trial results (not a
    # blank unfiltered pull). `--drug` still drives PubChem enrichment below.
    intr = args.intr or args.drug
    cond_v, cond_st = _resolve(args.cond, "en", args.confirm_cond)
    intr_v, intr_st = _resolve(intr, "en", args.confirm_intr)

    # === Batch 1: WHO (if --with-ictrp) + CDE (if --with-cde) — run concurrently ===
    # WHO aggregates 14+ primary registries in ONE call, COVERING most national
    # registries we otherwise reach individually (CT.gov, EU-CTR, ISRCTN, DRKS,
    # ChiCTR). Policy (2026-07-28): covered sources are FALLBACK-ONLY. EXCEPTION:
    # CDE (中国药物临床试验) is ALWAYS searched independently because WHO's
    # English-title matching misses Chinese-registered trials.
    #
    # WHO and CDE are fully independent sources, so we launch them in PARALLEL
    # (ThreadPoolExecutor). This roughly halves the wall-clock retrieval time vs
    # the old serial order. A single usage_guard.check() is performed here
    # (orchestrator parent side) and child endpoint subprocesses skip their own
    # check via CT_DEMAND_CHECKED=1, so the daily quota is charged exactly once
    # per demand even under concurrency (no cross-process double-count).
    who_primary = args.with_ictrp
    who_ok = False
    # --- prepare WHO date window + Batch-1 tasks (local, no network) ---
    who_date_start, who_date_end = _build_who_date_window(args)
    cde_script, cde_src_args, cde_kw_flag, cde_path_type = _cde_script_and_flag(args)
    cde_out = os.path.join(args.out_dir, "cde.json")
    cde = cde_out  # alias used by the CDE detail step below
    who_out = os.path.join(args.out_dir, "ictrp.json")
    batch1, cde_zh, cde_en, cde_kw, wcmd = _build_batch1(
        args, who_date_start, who_date_end, args.who_phase,
        cde_script, cde_src_args, cde_kw_flag, cde_path_type, who_out, cde_out)
    who_ok, stop = _run_batch1(args, batch1, who_primary, wcmd, who_out, cde_out,
                               cde_zh, cde_en, cde_kw, cde_script, cde_src_args,
                               cde_kw_flag, cde_path_type, norm_inputs)
    if stop:
        return

    skip_covered = who_primary and who_ok
    force_all = who_primary and (not who_ok) and args.fallback_covered

    # --- CDE fallback (WHO failed + --fallback-covered + CDE not already run) ---
    # Built as a task and merged into the parallel tier-2 batch below (no longer
    # serial), so it overlaps with EU-CTR/ISRCTN/DRKS/ChiCTR when WHO fails.
    cde_fb = _build_cde_fallback_task(args, force_all, cde_script, cde_src_args,
                                      cde_kw_flag, cde_out)


    # Confirm gate (foreign/CT.gov keywords not in term map); skipped if WHO covered.
    _confirm_foreign_gate(args, args.cond, intr, cond_st, intr_st, skip_covered)

    if not skip_covered:
        _run_ctgov(args, cond_v, intr_v, intr, cond_st, intr_st, args.out_dir, norm_inputs)
    else:
        print("[ct_registry][i] CT.gov 跳过 (已由 WHO 主路径覆盖, 转备用)。")

    # --- CDE retrieval now runs inside the parallel Batch-1 block (above) ---
    # (kept here only as a structural marker; CDE is always independent of WHO)

    # --- CDE auto-detail (--with-detail): fetch full 65-field records & swap in ---
    # 注意：CDE 走 api_key（商业接口）时，接口本身返回的就是完整的结构化数据
    # （含 sponsor/phase/终点等字段），无需再跑 detail 模式
    _cde_detail_skip = (cde_path_type == "api_key")
    if (args.with_cde or force_all) and args.with_detail and os.path.exists(cde) \
            and not _cde_detail_skip:
        cde_detail = os.path.join(args.out_dir, "cde_detail.json")
        det = _run_cde_detail(cde, cde_detail, cde_script, cde_src_args, HERE, run, args)
        if det:
            for i, v in enumerate(norm_inputs):
                if v == "--cde" and i + 1 < len(norm_inputs):
                    norm_inputs[i + 1] = det

    # --- Covered national registries: independent retrieval (parallel) ---
    # EU-CTR (Tier-1 pure HTTP, no token) + ISRCTN / DRKS / ChiCTR (Tier-2, via the
    # UNIFIED Coze endpoint, source=isrctn/drks/chictr, sharing the ICTRP token).
    # WHO-COVERED: skipped when WHO succeeded (skip_covered); run when opted in
    # (--with-<src>) or when WHO failed + --fallback-covered (force_all). Launched in
    # ONE parallel batch (same ThreadPoolExecutor pattern as Batch-1); the parent
    # quota check is idempotent and sets CT_DEMAND_CHECKED=1 so the shared endpoint
    # is charged exactly once per demand even under concurrency.
    _run_tier2_fallback(args, skip_covered, force_all, norm_inputs,
                        extra_tasks=([cde_fb] if cde_fb else None))

    # --- EU-CTR document enrichment (--with-detail): pull download URLs from CTIS ---
    euctr = os.path.join(args.out_dir, "euctr.json")
    if (args.with_euctr or force_all) and args.with_detail and os.path.exists(euctr):
        euctr_docs = os.path.join(args.out_dir, "euctr_docs.json")
        try:
            run([PY, os.path.join(HERE, "fetch_eu_ctr_docs.py"), "--run",
                 "--in", euctr, "--out", euctr_docs])
            if os.path.exists(euctr_docs):
                for i, v in enumerate(norm_inputs):
                    if v == "--euctr" and i + 1 < len(norm_inputs):
                        norm_inputs[i + 1] = euctr_docs
        except subprocess.CalledProcessError as e:
            print(f"[ct_registry][WARN] EU-CTR doc enrichment failed ({e}); using list-only.")

    # --- WHO ICTRP (Tier-2, source="who") ---
    # Handled EARLIER as the PRIMARY aggregator when --with-ictrp is set (see the
    # WHO PRIMARY block above). The national registries above are its FALLBACK
    # (covered sources) and only run if WHO cannot retrieve.

    # --- normalize (multi-source -> unified schema) ---
    normalized = os.path.join(args.out_dir, "normalized.json")
    run([PY, os.path.join(HERE, "normalize.py"), *norm_inputs, "--out", normalized])

    # --- P0-A: --track snapshots the current normalized result for future diff ---
    if args.track:
        _snap = os.path.join(args.out_dir, "registry_snapshot.json")
        shutil.copy(normalized, _snap)
        print(f"[ct_registry][track] snapshot -> {_snap}")

    # --- aggregate + report ---
    agg = os.path.join(args.out_dir, "agg.json")
    run([PY, os.path.join(HERE, "aggregate.py"), "--in", normalized, "--out", agg])

    report = os.path.join(args.out_dir, "report.md")
    run([PY, os.path.join(HERE, "report.py"), "--in", agg, "--out", report,
         "--json-out", os.path.join(args.out_dir, "agg_full.json")])

    # --- confirm-gated document download (--download-docs = explicit user confirmation) ---
    if args.download_docs:
        docs_out = os.path.join(args.out_dir, "docs")
        run([PY, os.path.join(HERE, "download_docs.py"), "--in", normalized,
             "--out-dir", docs_out, "--yes"])

    # --- optional PubChem enrich (needs ENGLISH drug name) ---
    if args.with_pubchem and args.drug:
        drug_v, drug_st = _resolve(args.drug, "en", args.confirm_drug)
        if drug_st == "term_map":
            print(f"[ct_registry][i18n] PubChem (en): {args.drug!r} -> {drug_v!r}")
        elif drug_st == "miss":
            sug = kl.suggest(args.drug, "en")
            print(f"[ct_registry][CONFIRM][PubChem] --drug {args.drug!r} 未命中术语表; "
                  f"建议英文译文: {sug or '<请提供>'}。"
                  f" 用 --confirm-drug 传入确认译文后重跑。")
        pc = os.path.join(args.out_dir, "pubchem.json")
        run([PY, os.path.join(HERE, "enrich_pubchem.py"), "--run", "--drug", drug_v,
             "--targets", "--out", pc])

    # --- optional year filter (--min-year, built-in) ---
    recs_for_excel, norm_in = _apply_min_year(args, normalized, args.out_dir)
    if norm_in:
        agg = os.path.join(args.out_dir, "agg.json")
        run([PY, os.path.join(HERE, "aggregate.py"), "--in", norm_in, "--out", agg])
        report = os.path.join(args.out_dir, "report.md")
        run([PY, os.path.join(HERE, "report.py"), "--in", agg, "--out", report,
             "--json-out", os.path.join(args.out_dir, "agg_full.json")])

    # --- P0-B: emit run-status manifest + disclosure (graceful-degradation) ---
    _emit_run_status(args)

    # --- build Excel (built-in) ---
    if args.excel and _export_xlsx is not None:
        xlsx_out = os.path.join(args.out_dir, "report.xlsx")
        _export_xlsx(recs_for_excel, xlsx_out, title=_cover_title(args), lang=args.lang)
        print(f"[ct_registry][excel] 已生成 -> {xlsx_out}")

    # --- cleanup intermediate md/json (default; keep only .xlsx) ---
    if args.excel and not args.keep_meta:
        _cleanup_meta(args.out_dir)
        print("[ct_registry][cleanup] 已清理中间 md/json, 仅保留 .xlsx。")

    print(f"[ct_registry] done -> {args.out_dir}")


def _run_tier2_fallback(args, skip_covered, force_all, norm_inputs, extra_tasks=None):
    """Retrieve the WHO-covered national registries independently (parallel).

    Sources: EU-CTR (pure HTTP, no token) + ISRCTN / DRKS / ChiCTR (unified Coze
    endpoint, source=isrctn/drks/chictr, sharing the ICTRP token). These are
    WHO-COVERED: skipped when WHO succeeded (``skip_covered``); run when opted in
    via ``--with-<src>`` OR when WHO failed and ``--fallback-covered`` is set
    (``force_all``). Launched in ONE parallel batch (``_run_parallel``) so the
    fallback wall-clock stays low. On success the matching ``--<src>`` flag +
    output path is appended to ``norm_inputs``; timeout / failure is reported and
    the source is skipped (other sources may still yield a report).

    Returns the list of source names actually launched.
    """
    _specs = [
        # (SRC, src_lower, kw_lang, is_endpoint, api_source)
        ("EUCTR", "euctr", "en", False, None),
        ("ISRCTN", "isrctn", "en", True, "isrctn"),
        ("DRKS", "drks", "en", True, "drks"),
        ("CHICTR", "chictr", "zh", True, "chictr"),
    ]
    tasks = []
    if extra_tasks:
        tasks += extra_tasks
    for _SRC, _sl, _kl, _ep, _api in _specs:
        _with = getattr(args, f"with_{_sl}", False)
        if skip_covered or (not _with and not force_all):
            continue
        _kw = getattr(args, f"{_sl}_keyword", None) or _derive_kw(args, _kl)
        if not _kw:
            print(f"[ct_registry][ERROR] --with-{_sl} needs "
                  f"--{_sl}-keyword or a base term; skipping.")
            continue
        _out = os.path.join(args.out_dir, f"{_sl}.json")
        if _ep:
            _cmd = [PY, os.path.join(HERE, "search_ictrp.py"), "--run",
                    "--source", _api, "--q", _kw, "--out", _out]
        else:
            _cmd = [PY, os.path.join(HERE, "search_eu_ctr.py"), "--run",
                    "--q", _kw, "--out", _out]
        tasks.append({"name": _SRC, "cmd": _cmd, "out": _out,
                      "src_l": _sl, "is_ep": _ep})
    if not tasks:
        return []
    _has_ep = any(t["is_ep"] for t in tasks)
    if _has_ep and not _ensure_quota_checked(os.environ.get("CT_DEMAND_ID")):
        print("[ct_registry][QUOTA] 已达每日共享检索上限, 跳过备用源(含统一端点)检索。")
        return []
    print(f"[ct_registry][i] 并行检索备用源: "
          f"{', '.join(t['name'] for t in tasks)} "
          f"(WHO 覆盖源独立检索, 并发执行以缩短等待)...")
    _res = _run_parallel(tasks)
    for _t in tasks:
        _SRC, _sl, _out = _t["name"], _t["src_l"], _t["out"]
        _rc, _sd, _exists = _res.get(_SRC, (1, b"", False))
        if _rc == 0 and _exists:
            # 超时退出的占位输出（is_timeout=True）不应当作成功并入
            try:
                with open(_out, encoding="utf-8") as f:
                    _od = json.load(f)
            except Exception:
                _od = {}
            if _od.get("is_timeout"):
                print(f"[ct_registry][TIMEOUT] ⚠️ {_SRC} 检索超时（is_timeout=True，数据可能不全）。")
                _print_timeout_advice(_SRC)
                print(f"[ct_registry][TIMEOUT] 已跳过 {_SRC}，继续后续流程"
                      f"（若其他源有数据仍可出报告）。")
            else:
                norm_inputs += [f"--{_sl}", _out]
                print(f"[ct_registry][i] {_SRC} 检索完成 -> {_out}")
        elif _is_timeout(_sd):
            print(f"[ct_registry][TIMEOUT] ⚠️ {_SRC} 检索超时（外部网络故障）。")
            _print_timeout_advice(_SRC)
            print(f"[ct_registry][TIMEOUT] 已跳过 {_SRC}，继续后续流程"
                  f"（若其他源有数据仍可出报告）。")
        else:
            print(f"[ct_registry][WARN] {_SRC} retrieval failed (exit {_rc}); skipping.")
    return [_t["name"] for _t in tasks]


def _run_cde_detail(cde_list, cde_detail, cde_script, cde_src_args, here, run, args):
    """Fetch full CDE detail records (65 fields) and return the detail path.

    Runs mode=detail against the SAME CDE script used for the list search (unified
    endpoint by default, standalone fallback with --cde-legacy). Respects the
    skill's >100-items confirmation rule: a large list would be a slow 8-thread
    parallel fetch, so we skip auto-detail unless --auto-confirm is set.

    Returns the detail output path on success (caller swaps it into norm_inputs),
    or None to fall back to the list-only file.
    """
    try:
        with open(cde_list, encoding="utf-8") as f:
            lst = json.load(f)
        recs = lst.get("records") or lst.get("projects") or []
        n = len(recs)
    except Exception:
        n = 0
    if n > 100 and not args.auto_confirm:
        print(f"[ct_registry][DETAIL-SKIP] CDE 列表 {n} 条 >100, detail 拉取耗时长, "
              f"跳过自动补详情(可加 --auto-confirm 强制, 或单独跑 detail 模式)。")
        return None
    try:
        run([PY, cde_script, "--run", *cde_src_args, "--out", cde_detail,
             "--mode", "detail", "--project-list", cde_list])
    except subprocess.CalledProcessError as e:
        print(f"[ct_registry][WARN] CDE detail fetch failed ({e}); using list-only.")
        return None
    if not os.path.exists(cde_detail):
        return None
    print(f"[ct_registry][DETAIL] CDE 详情已合并到归一化({cde_detail})。")
    return cde_detail


def _cde_script_and_flag(args):
    """Resolve the CDE search script + source args + keyword flag.

    FAST PATH (--cde-api-key given) = direct commercial API (search_cde.py --api-key, ~1-3s).
    PRIMARY = unified endpoint (search_ictrp.py --source chinadrugtrials, ~15-60s).
    FALLBACK = standalone endpoint (search_cde_workflow.py, archived under CDE/) when --cde-legacy.
    """
    if args.cde_api_key:
        # 快速路径：商业接口直连，不走 Coze workflow
        return os.path.join(HERE, "search_cde.py"), [], "--q", "api_key"
    if args.cde_legacy:
        return os.path.join(HERE, "..", "CDE", "search_cde_workflow.py"), [], "--keyword", "workflow"
    return os.path.join(HERE, "search_ictrp.py"), ["--source", "chinadrugtrials"], "--q", "workflow"


def _cde_single_cmd(args, out, cde_kw, cde_script, cde_src_args, cde_kw_flag):
    """Build a single CDE search command (search or combined mode)."""
    cmd = [PY, cde_script, "--run", *cde_src_args, "--out", out]
    if args.cde_mode == "combined" and cde_kw:
        cmd += ["--mode", "combined", cde_kw_flag, cde_kw]
    else:
        cmd += ["--mode", "search", cde_kw_flag, cde_kw]
    for cli, val in [("--indication", args.cde_indication),
                     ("--drugs-name", args.cde_drugs_name),
                     ("--drugs-type", args.cde_drugs_type),
                     ("--appliers", args.cde_appliers),
                     ("--trial-status", args.cde_trial_status)]:
        if val:
            cmd += [cli, val]
    return cmd


def _cde_api_key_cmd(args, out, cde_kw, cde_mk):
    """Build a CDE search command for the commercial API fast path.

    Uses search_cde.py --api-key (丁香园商业接口, ~1-3s). Returns None if no
    valid keyword available. No Coze token/endpoint needed; no usage_guard count.
    """
    if not args.cde_api_key:
        return None
    cmd = [PY, os.path.join(HERE, "search_cde.py"), "--run",
           "--api-key", args.cde_api_key, "--out", out,
           "--max", str(args.max)]
    if cde_mk:
        # multi_keyword 模式：拆成多个关键词参数传递
        for kw in cde_mk.split():
            cmd += ["--q", kw]
    elif cde_kw:
        cmd += ["--q", cde_kw]
    elif args.cde_indication:
        cmd += ["--indication", args.cde_indication]
    elif args.cde_drugs_name:
        cmd += ["--drug", args.cde_drugs_name]
    else:
        # 无任何有效关键词，返回 None 让调用方走 workflow 路径
        return None
    return cmd


def _derive_cde_kw(args):
    """Derive the (Chinese) CDE keyword from the base term; enforce the 'miss'
    confirm gate (prints a menu and may sys.exit). Returns (cde_kw, cde_mk, cde_st).
    """
    cde_kw = args.cde_keyword
    cde_mk = args.cde_multi_keywords
    cde_st = "confirmed" if cde_kw else None
    if not (cde_kw or cde_mk):
        base = args.confirm_cde_keyword or args.cond or args.drug
        if base:
            cde_kw, cde_st = kl.localize(base, "zh")
            if cde_st == "miss":
                cands = kl.kw_match_candidates(base, "cde")
                print(kl.render_kw_menu(base, cands))
                if not args.auto_confirm:
                    print("[ct_registry][ABORT] 未确认 CDE 关键字解释, 已停止 CDE 检索"
                          "(可加 --auto-confirm 自动采用最佳译文, 或用 --confirm-cde-keyword / "
                          "--cde-keyword 显式指定中文检索词后重跑)。")
                    sys.exit(2)
                pick = next((c for c in cands
                             if c["strategy"] in ("translate", "class_suffix")),
                            cands[0])
                cde_kw = pick["value"] if isinstance(pick["value"], str) else base
                print(f"[ct_registry][WARN] --auto-confirm: 自动采用 "
                      f"{pick['strategy']} -> {cde_kw!r} 检索 CDE (可能漏检)。")
            elif cde_st == "term_map":
                print(f"[ct_registry][i18n] CDE (zh): {base!r} -> {cde_kw!r}")
        else:
            print("[ct_registry][ERROR] --with-cde 需要 --cde-keyword / "
                  "--cde-multi-keywords, 或从主检索词 (--cond/--drug) 派生; 跳过 CDE。")
            cde_kw = None
    return cde_kw, cde_mk, cde_st


# --- Keyword breadth guard (防 Coze 端点 1000+ 页爆炸) ---
def _guard_keyword_breadth(args):
    """在发起任何网络检索前，校验主关键词广度。

    规则（源自 BASE.md §11.x，ct- 全库统一约定）：
      - **多关键词组合检索**：主词（首次完整检索的词）不能是最宽泛的；
        若 CDE 多关键词里主词过宽，自动把最具体的词重排到最前。
      - **只有一个关键词且过宽**（Coze 完整翻页源：CDE/WHO/ChiCTR/ISRCTN/DRKS）：
        直接停止检索，要求用户缩小关键词范围。
      - **CT.gov**（受 --max 上限约束、不会全量翻千页）：仅 WARN，不中止。

    Coze 检索源命中「单关键词过宽」时 sys.exit(2)；CT.gov 仅打印 WARN。
    """
    if is_broad_keyword is None:  # 底座未就绪时跳过（不应发生）
        return

    abort_sources = []  # [(源名, 过宽主词), ...]
    warns = []

    # ---- CDE（中国药物临床试验，Coze 统一端点，会完整翻页） ----
    if args.with_cde:
        mk = getattr(args, "cde_multi_keywords", None)
        if mk:
            # CLI 传入的是空格分隔的单个字符串（非 nargs="*"），先拆词。
            words = mk.split() if isinstance(mk, str) else list(mk)
            plan = plan_coze_keywords(words)
            if plan["ordered"] != words:
                args.cde_multi_keywords = " ".join(plan["ordered"])
                print(f"[ct_registry][BREADTH] CDE 多关键词已重排为主词优先"
                      f"(具体词在前): {plan['ordered']}")
            if plan["action"] == "abort":
                abort_sources.append(("CDE(中国药物临床试验)", plan["primary"]))
        else:
            kw = args.cde_keyword or args.confirm_cde_keyword or args.cond or args.drug
            if kw and is_broad_keyword(kw):
                abort_sources.append(("CDE(中国药物临床试验)", kw))

    # ---- WHO ICTRP（Coze 统一端点，会完整翻页） ----
    if args.with_ictrp:
        kw = args.ictrp_keyword or _derive_kw(args, "en")
        if kw and is_broad_keyword(kw):
            abort_sources.append(("WHO ICTRP", kw))

    # ---- 国家级 Coze 端点（ISRCTN / DRKS / ChiCTR） ----
    for _sl, _lang in (("isrctn", "en"), ("drks", "en"), ("chictr", "zh")):
        if getattr(args, f"with_{_sl}", False):
            kw = getattr(args, f"{_sl}_keyword", None) or _derive_kw(args, _lang)
            if kw and is_broad_keyword(kw):
                abort_sources.append((_sl.upper(), kw))

    # ---- CT.gov（受 --max 上限约束，仅 WARN） ----
    ctgov_kw = _derive_kw(args, "en")
    if ctgov_kw and is_broad_keyword(ctgov_kw):
        warns.append(ctgov_kw)

    for w in warns:
        print(f"[ct_registry][WARN] CT.gov 关键词 {w!r} 可能过宽（结果量大）；"
              f"CT.gov 受 --max 上限约束不会全量抓取，但建议加限定词缩小范围。")

    if abort_sources:
        print("[ct_registry][ABORT] 以下 Coze 检索源的主关键词过于宽泛，"
              "结果可能超过千页、无法完整抓取：")
        for _name, _kw in abort_sources:
            print(f"  - {_name}: 主词 {_kw!r}")
        print("请缩小关键词范围后再检索：① 用更具体的疾病/药物/分期限定词；"
              "② 多关键词组合检索时把具体词放在最前（作主词）；"
              "③ 或用 --confirm-* / --*-keyword 显式指定具体检索词后重跑。")
        sys.exit(2)


def _run_one(task):
    """Run one subprocess task, returning (name, rc, stderr_bytes, out_exists).

    Worker for :func:`_run_parallel` — never raises, so a failing task cannot
    kill its sibling threads.
    """
    name, cmd, out = task["name"], task["cmd"], task.get("out")
    try:
        p = subprocess.run(cmd, capture_output=True)
        exists = os.path.exists(out) if out else True
        return name, p.returncode, p.stderr, exists
    except Exception as e:  # defensive: never raise from a worker thread
        return name, -1, str(e).encode(), False


def _run_parallel(tasks):
    """Run independent subprocess tasks concurrently.

    Returns ``{name: (rc, stderr_bytes, out_exists)}``. Non-raising — callers
    interpret outcomes. Used for the WHO + CDE retrieval phase so their
    independent network calls overlap instead of stacking serially.
    """
    if not tasks:
        return {}
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(tasks), 8)) as ex:
        futs = {ex.submit(_run_one, t): t["name"] for t in tasks}
        for f in concurrent.futures.as_completed(futs):
            name, rc, sd, exists = f.result()
            results[name] = (rc, sd, exists)
    return results


_quota_checked = {"done": False}


def _ensure_quota_checked(demand_id):
    """Perform the per-demand quota check ONCE (orchestrator parent side).

    Sets ``CT_DEMAND_CHECKED=1`` so child endpoint subprocesses skip their own
    :func:`usage_guard.check` — this keeps the daily count at exactly ONE per
    demand even when WHO + CDE are launched concurrently (a cross-process race
    would otherwise double-count). Returns True if allowed (or already checked),
    False if the daily cap is reached.
    """
    if _quota_checked["done"]:
        return True
    allowed, _remaining, guard_msg = usage_guard.check(
        demand_id=demand_id, source_label="WHO/CDE")
    print(guard_msg)
    if not allowed:
        return False
    os.environ["CT_DEMAND_CHECKED"] = "1"
    _quota_checked["done"] = True
    return True


def _who_cmd(args, out, who_date_start, who_date_end, who_phase):
    """Build the WHO ICTRP search command, or None if no keyword can be derived.

    Default = free-text search (--q). When --who-mode combined is set, or any
    --who-* field is supplied, builds the ADVANCED (combined) command: the
    composite keyword is split into structured who_* fields (drug -> who_intervention,
    disease -> who_condition, sponsor -> who_sponsor) so the endpoint does a
    server-side AND filter (smaller payload, usually faster) instead of pulling a
    huge free-text result set that then times out. This is code-driven; the user
    does not operate the fields manually.
    """
    ictrp_kw = args.ictrp_keyword or _derive_kw(args, "en")
    if not ictrp_kw:
        return None
    # 高级检索触发条件：显式 --who-mode combined，或给了任一 --who-* 字段
    use_advanced = (getattr(args, "who_mode", None) == "combined") or any(
        getattr(args, a, None) for a in ("who_condition", "who_intervention",
                                         "who_sponsor", "who_country"))
    cmd = [PY, os.path.join(HERE, "search_ictrp.py"), "--run", "--out", out]
    if use_advanced:
        cmd += ["--mode", "combined"]
        cond = getattr(args, "who_condition", None) or getattr(args, "cond", None)
        intr = getattr(args, "who_intervention", None) or getattr(args, "drug", None) \
            or getattr(args, "intr", None)
        if cond:
            cmd += ["--who-condition", cond]
        if intr:
            cmd += ["--who-intervention", intr]
        if getattr(args, "who_sponsor", None):
            cmd += ["--who-sponsor", args.who_sponsor]
        if getattr(args, "who_country", None):
            cmd += ["--who-country", args.who_country]
    else:
        max_pages = max(1, (args.max + 9) // 10)
        cmd += ["--q", ictrp_kw, "--max-pages", str(max_pages)]
    if who_date_start:
        cmd += ["--who-date-start", who_date_start]
    if who_date_end:
        cmd += ["--who-date-end", who_date_end]
    if who_phase:
        cmd += ["--who-phase", who_phase]
    return cmd


def _interpret_who(res, out):
    """Interpret a WHO task result -> (ok, reason)."""
    rc, sd, exists = res
    if rc != 0:
        # P0-B: WHO failed -> flag it so the report can disclose the degradation
        # (we auto-fall back to CDE + CT.gov rather than aborting).
        _RUN_STATUS["who_status"] = "failed"
        if _is_timeout(sd) or _is_timeout(str(sd)):
            return False, f"TIMEOUT: {(sd.strip()[-240:]) or 'read timeout'}"
        return False, f"retrieval failed (exit {rc})"
    if not exists:
        _RUN_STATUS["who_status"] = "failed"
        return False, "no output written (likely HTTP != 200)"
    try:
        with open(out, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        _RUN_STATUS["who_status"] = "failed"
        return False, "output unreadable"
    if data.get("is_timeout"):
        _RUN_STATUS["who_status"] = "failed"
        return False, f"TIMEOUT(is_timeout=True): Coze 检索超过等待上限，数据可能不全"
    if data.get("error_msg"):
        _RUN_STATUS["who_status"] = "failed"
        return False, f"error_msg: {data.get('error_msg')}"
    return True, None


def _who_failed(who_reason, args):
    """Handle a WHO failure.

    P0-B graceful degradation: WHO is the meta-aggregator. When it times out or
    errors we no longer abort the whole run — we auto-degrade to a CDE +
    ClinicalTrials.gov report (those sources are already in ``norm_inputs`` /
    always retrieved independently) and mark ``who_status=failed`` for disclosure.
    Returns 'fallback' (caller continues building the report) instead of 'stop'.
    """
    if _is_timeout(who_reason):
        print("[ct_registry][TIMEOUT] ⚠️ WHO ICTRP 共享端点检索超时（外部网络故障，非技能问题）。")
        print("[ct_registry][TIMEOUT] P0-B 优雅降级：跳过 WHO，改用 CDE + ClinicalTrials.gov 独立出报告"
              "（已在结果中置 who_status=failed，不隐藏、不假装完整）。")
        print("[ct_registry][TIMEOUT] 亦可选：① --who-mode combined 重新发起（服务端 AND 过滤，更快）；"
              "② 缩小/更换关键字重试。")
        _print_timeout_advice("WHO ICTRP（全球 14+ 一级注册库聚合）")
        return "fallback"
    print(f"[ct_registry][FALLBACK-PROMPT] WHO ICTRP 检索失败（{who_reason}）。")
    print("[ct_registry][FALLBACK-PROMPT] P0-B 优雅降级：已自动改用 CDE + ClinicalTrials.gov 出报告"
          "（who_status=failed）。")
    print("[ct_registry][FALLBACK-PROMPT] WHO 已覆盖以下数据源, 如需对其分别独立检索并聚合可加 --fallback-covered 重跑:")
    for _lbl in ["CT.gov (ClinicalTrials.gov)", "EU-CTR (欧盟临床试验)",
                 "ISRCTN", "DRKS (德国)",
                 "ChiCTR (中国临床试验注册中心)"]:
        print(f"[ct_registry][FALLBACK-PROMPT]   - {_lbl}")
    if args.fallback_covered:
        print("[ct_registry] --fallback-covered 已设置: 对以上数据源分别独立检索并聚合。")
    print("[ct_registry] P0-B 已自动用 CDE + ClinicalTrials.gov 出报告（who_status=failed）；"
          "如需额外覆盖源请加 --fallback-covered 重跑。")
    return "fallback"


def _cde_count(out_path):
    """Return # of records in a raw CDE / Coze output file, or None if unreadable."""
    try:
        with open(out_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    if isinstance(data, list):
        return len(data)
    recs = data.get("records")
    if recs is None:
        recs = data.get("project_list")
    if recs is None:
        tc = data.get("total_count")
        if isinstance(tc, int):
            return tc
        return 0
    if isinstance(recs, str):
        try:
            recs = json.loads(recs)
        except Exception:
            return 0
    return len(recs) if hasattr(recs, "__len__") else 0


def _interpret_cde(results, cde_tasks, cde_out, cde_zh, cde_en, cde_kw,
                   cde_script, cde_src_args, cde_kw_flag, args, norm_inputs,
                   cde_path_type="workflow"):
    """Interpret parallel CDE task results; append --cde to ``norm_inputs`` on success.

    cde_path_type: "api_key" → commercial API path (fast, no Coze); "workflow" → Coze.
    Handles bilingual (CDE-zh / CDE-en) merge and single-run fallback.

    P0-B graceful degradation: if CDE returns 0 records (a *successful but empty*
    pull — exit 0, file written), auto-rerun ``--cde-retry`` times, rate-limited
    by ``--cde-retry-delay`` to avoid放大端点负载. If it is STILL 0 after the
    retries, mark ``cde_zero_hit_unverified`` (the trial set could not be verified
    via the third-party endpoint) but keep going so a report can still be built
    from the other sources. A hard timeout / failure is NOT retried here (original
    skip behaviour preserved). Only triggered on a real networked (--run) pull.
    """
    retry = max(0, int(getattr(args, "cde_retry", 0) or 0))
    delay = max(0.0, float(getattr(args, "cde_retry_delay", 2.0) or 2.0))
    cmd_by_name = {t["name"]: t["cmd"] for t in cde_tasks}

    def _retry(names_to_rerun):
        for _ in range(retry):
            time.sleep(delay)  # rate-limit: avoid放大端点负载
            for nm in names_to_rerun:
                _cmd = cmd_by_name.get(nm)
                if not _cmd:
                    continue
                try:
                    run(_cmd)
                    _RUN_STATUS["cde_retried"] += 1
                except Exception:
                    pass

    def _flag_zero():
        _RUN_STATUS["cde_zero_hit_unverified"] = True
        print("[ct_registry][CDE-ZERO] ⚠️ CDE 重跑后仍 0 条，标记 zero_hit_unverified"
              "（未经第三方复核，结果仅供参考）。")

    names = {t["name"] for t in cde_tasks}
    if "CDE-zh" in names and "CDE-en" not in names:
        # 静默降级：只发了 zh 主查询；zh=0 时自动补发 en
        zh = results.get("CDE-zh", (1, b"", False))
        zh_ok = zh[0] == 0 and zh[2]
        if zh_ok:
            if _cde_count(cde_zh) > 0:
                # zh 有结果，直接采用
                if os.path.exists(cde_zh):
                    shutil.copy2(cde_zh, cde_out)
                norm_inputs += ["--cde", cde_out]
                print("[ct_registry][i] CDE 中文检索完成。")
            else:
                # zh=0，静默降级：补发 en
                print("[ct_registry][CDE-FALLBACK] 中文检索 0 条，静默补发英文检索。")
                cde_en = os.path.join(args.out_dir, "cde_en.json")
                try:
                    run(_cde_single_cmd(args, cde_en, cde_kw, cde_script,
                                        cde_src_args, cde_kw_flag))
                except subprocess.CalledProcessError as e:
                    _sd = _cp_stderr(e)
                    if _is_timeout(_sd):
                        print("[ct_registry][TIMEOUT] ⚠️ CDE 英文降级检索超时。")
                        _flag_zero()
                    else:
                        print(f"[ct_registry][WARN] CDE 英文降级检索失败: {e}")
                        _flag_zero()
                except Exception:
                    pass
                # 合并 zh + en
                if os.path.exists(cde_en):
                    _bilingual_cde_merge(cde_zh, cde_en, cde_out)
                if _cde_count(cde_out) > 0:
                    norm_inputs += ["--cde", cde_out]
                    print("[ct_registry][i] CDE 静默降级完成 (zh+en 已合并)。")
                else:
                    _flag_zero()
        else:
            print("[ct_registry][WARN] CDE 中文检索失败; 跳过。")
    elif "CDE-zh" in names and "CDE-en" in names:
        # 兼容旧路径：双检同时跑（保留备用）
        zh = results.get("CDE-zh", (1, b"", False))
        en = results.get("CDE-en", (1, b"", False))
        zh_ok = zh[0] == 0 and zh[2]
        en_ok = en[0] == 0 and en[2]
        if zh_ok and en_ok:
            _bilingual_cde_merge(cde_zh, cde_en, cde_out)
            if _cde_count(cde_out) == 0 and retry > 0:
                _retry(["CDE-zh", "CDE-en"])
                _bilingual_cde_merge(cde_zh, cde_en, cde_out)
            if _cde_count(cde_out) > 0:
                norm_inputs += ["--cde", cde_out]
                print("[ct_registry][i] CDE 中英双检完成 (zh+en 已合并)。")
            else:
                _flag_zero()
        else:
            print("[ct_registry][WARN] CDE 双语检索部分失败; 回退单语检索。")
            single_out = cde_zh if zh_ok else (cde_en if en_ok else cde_out)
            if os.path.exists(single_out):
                if single_out != cde_out:
                    shutil.copy2(single_out, cde_out)
                if _cde_count(cde_out) > 0:
                    norm_inputs += ["--cde", cde_out]
                else:
                    _flag_zero()
    else:
        r = results.get("CDE", (1, b"", False))
        if r[0] == 0 and r[2]:
            # P0-B: zero-hit retry on the single CDE output
            if _cde_count(cde_out) == 0 and retry > 0:
                _retry(["CDE"])
                # fall back to a direct rerun if no stored cmd (api_key path)
                if _cde_count(cde_out) == 0 and "CDE" not in cmd_by_name:
                    try:
                        run(_cde_single_cmd(args, cde_out, cde_kw, cde_script,
                                            cde_src_args, cde_kw_flag))
                        _RUN_STATUS["cde_retried"] += 1
                    except Exception:
                        pass
            if _cde_count(cde_out) > 0:
                norm_inputs += ["--cde", cde_out]
                if cde_path_type == "api_key":
                    print("[ct_registry][i] CDE 商业 API 快速路径检索完成 (~1-3s)。")
                else:
                    print("[ct_registry][i] CDE 检索完成。")
            else:
                _flag_zero()
        else:
            if cde_path_type == "api_key":
                # 商业接口直连失败（非共享端点问题），提示用户检查 key/网络
                print(f"[ct_registry][WARN] CDE 商业 API 检索失败 (exit {r[0]}); "
                      f"可去掉 --cde-api-key 走 Coze workflow 兜底。")
            else:
                if _is_timeout(r[1]):
                    print("[ct_registry][TIMEOUT] ⚠️ CDE 共享端点检索超时（外部网络故障，非技能问题）。")
                    _print_timeout_advice("CDE（中国药物临床试验）")
                    print("[ct_registry][TIMEOUT] 已跳过 CDE，继续后续流程（若其他源有数据仍可出报告）。")
                else:
                    print("[ct_registry][WARN] CDE retrieval failed; continuing.")


def _build_who_date_window(args):
    """Return (start, end) DD/MM/YYYY for --since-years, or (None, None).

    Pure / local (no network) — prepared before any concurrent launch so the
    pre-network prep phase is a single deterministic pass (shorter, testable).
    """
    if not (args.with_ictrp and args.since_years and args.since_years > 0):
        return None, None
    today = datetime.date.today()
    start = today.replace(year=today.year - args.since_years)
    s, e = start.strftime("%d/%m/%Y"), today.strftime("%d/%m/%Y")
    print(f"[ct_registry][i] WHO 日期窗口: {s} ~ {e} (过去 {args.since_years} 年)。")
    return s, e


def _build_batch1(args, who_date_start, who_date_end, who_phase,
                  cde_script, cde_src_args, cde_kw_flag, cde_path_type,
                  who_out, cde_out):
    """Build Batch-1 task specs (WHO + CDE variants) as PURE data — no network.

    cde_path_type: "api_key" (search_cde.py --api-key, ~1-3s) or
                   "workflow" (search_ictrp.py / search_cde_workflow.py, ~15-60s).
    Returns (batch1, cde_zh, cde_en, cde_kw, wcmd).
    """
    batch1 = []
    cde_zh = cde_en = cde_kw = None
    wcmd = None
    if args.with_ictrp:
        wcmd = _who_cmd(args, who_out, who_date_start, who_date_end, who_phase)
        if wcmd:
            batch1.append({"name": "WHO", "cmd": wcmd, "out": who_out})
        else:
            print("[ct_registry][WARN] WHO 无关键字, 跳过 WHO 主路径。")
    if args.with_cde:
        cde_kw, cde_mk, cde_st = _derive_cde_kw(args)
        if cde_path_type == "api_key":
            # 快速路径：CDE 商业接口直连（search_cde.py --api-key），不走 Coze workflow
            cde_api_cmd = _cde_api_key_cmd(args, cde_out, cde_kw, cde_mk)
            if cde_api_cmd:
                batch1.append({"name": "CDE", "cmd": cde_api_cmd, "out": cde_out})
                print("[ct_registry][CDE-FAST] 使用商业 API 快速路径 (~1-3s)。")
        elif cde_mk:
            batch1.append({"name": "CDE", "cmd": [PY, cde_script, "--run",
                         *cde_src_args, "--out", cde_out, "--mode", "multi_keyword",
                         "--multi-keywords", cde_mk], "out": cde_out})
        elif cde_kw:
            zh_kw, en_kw = kl.bilingual_pair(cde_kw)
            has_filters = any([args.cde_indication, args.cde_drugs_name,
                               args.cde_drugs_type, args.cde_appliers,
                               args.cde_trial_status])
            # 静默降级：只发 zh 主查询；保留 en_kw 供 _interpret_cde 在 zh=0 时降级使用
            if (not args.no_cde_bilingual) and bool(zh_kw) and bool(en_kw) \
                and zh_kw != en_kw and args.cde_mode == "search" and not has_filters:
                cde_zh = os.path.join(args.out_dir, "cde_zh.json")
                batch1.append({"name": "CDE-zh", "cmd": _cde_single_cmd(
                    args, cde_zh, zh_kw, cde_script, cde_src_args, cde_kw_flag),
                    "out": cde_zh})
            else:
                batch1.append({"name": "CDE", "cmd": _cde_single_cmd(
                    args, cde_out, cde_kw, cde_script, cde_src_args, cde_kw_flag),
                    "out": cde_out})
    return batch1, cde_zh, cde_en, cde_kw, wcmd


def _run_batch1(args, batch1, who_primary, wcmd, who_out, cde_out, cde_zh,
                cde_en, cde_kw, cde_script, cde_src_args, cde_kw_flag,
                cde_path_type, norm_inputs):
    """Launch Batch-1 (WHO + CDE concurrent) and interpret. Returns (who_ok, stop).

    cde_path_type: "api_key" → CDE 走商业接口（无 quota 计数）；"workflow" → 走 Coze。
    ``stop`` is truthy when the whole retrieval should abort (quota cap reached,
    or WHO failed and policy says stop). The caller should ``return`` on stop.
    """
    if not batch1:
        if who_primary and not wcmd:
            if _who_failed("no WHO keyword (need --ictrp-keyword or base term)", args) == "stop":
                return False, True
        return False, False
    print(f"[ct_registry][i] 并行检索: {', '.join(t['name'] for t in batch1)} "
          f"(WHO 与 CDE 为独立源, 并发执行以缩短等待)...")
    # 配额检查：
    # - CDE 走 api_key（商业接口）时不消耗共享端点配额，但 WHO 仍走 workflow 需要检查
    # - CDE 走 workflow 时需检查配额
    # - 只要 batch1 里有非 api_key 的 workflow 任务（含 WHO/CDE），就检查配额
    _has_workflow_task = cde_path_type == "workflow" or who_primary
    if _has_workflow_task and not _ensure_quota_checked(os.environ.get("CT_DEMAND_ID")):
        print("[ct_registry][QUOTA] 已达每日共享检索上限, 停止本次检索。")
        return False, True
    res = _run_parallel(batch1)
    who_ok, who_reason = False, None
    if who_primary and wcmd:
        who_ok, who_reason = _interpret_who(res["WHO"], who_out)
        if who_ok:
            norm_inputs += ["--ictrp", who_out]
        if not who_ok and _who_failed(who_reason, args) == "stop":
            return who_ok, True
    elif who_primary and not wcmd:
        if _who_failed("no WHO keyword (need --ictrp-keyword or base term)", args) == "stop":
            return False, True
    if any(t["name"].startswith("CDE") for t in batch1):
        _interpret_cde(res, [t for t in batch1 if t["name"].startswith("CDE")],
                       cde_out, cde_zh, cde_en, cde_kw,
                       cde_script, cde_src_args, cde_kw_flag, args, norm_inputs,
                       cde_path_type=cde_path_type)
    return who_ok, False


def _build_cde_fallback_task(args, force_all, cde_script, cde_src_args,
                             cde_kw_flag, cde_out):
    """Build the CDE fallback task (WHO failed + --fallback-covered + CDE not run).

    Pure / no network. Returns a task dict (with src_l/is_ep so it merges into the
    tier-2 parallel batch) or None. Merged into the concurrent fallback batch so
    CDE no longer runs serially after WHO fails — cutting fallback wall-clock.
    """
    if not (force_all and not args.with_cde):
        return None
    fk, fm, fst = _derive_cde_kw(args)
    if args.cde_api_key:
        # 快速路径：CDE 商业接口直连
        cmd = _cde_api_key_cmd(args, cde_out, fk, fm)
        if cmd:
            return {"name": "CDE", "cmd": cmd, "out": cde_out, "src_l": "cde", "is_ep": False}
        # 无法构建 api_key 命令（无关键词），回退 workflow
    if fm:
        return {"name": "CDE", "cmd": [PY, cde_script, "--run", *cde_src_args,
                "--out", cde_out, "--mode", "multi_keyword", "--multi-keywords", fm],
                "out": cde_out, "src_l": "cde", "is_ep": True}
    if fk:
        return {"name": "CDE", "cmd": _cde_single_cmd(args, cde_out, fk, cde_script,
                cde_src_args, cde_kw_flag), "out": cde_out, "src_l": "cde", "is_ep": True}
    return None


def _confirm_foreign_gate(args, cond, intr, cond_st, intr_st, skip_covered):
    """Confirm-gate for foreign (CT.gov) keywords not in the term map.

    Only relevant when CT.gov will actually run (not covered by a successful WHO).
    May sys.exit(2) if a miss is unconfirmed. No network.
    """
    if skip_covered:
        print("[ct_registry][i] CT.gov 确认门跳过 (已由 WHO 主路径覆盖, 转备用)。")
        return
    foreign_miss = []
    if args.cond and cond_st == "miss":
        foreign_miss.append(("CT.gov --cond", args.cond, kl.suggest(args.cond, "en")))
    if intr and intr_st == "miss":
        foreign_miss.append(("CT.gov --intr/--drug", intr, kl.suggest(intr, "en")))
    if not foreign_miss:
        return
    print("[ct_registry][CONFIRM] 以下检索词未命中术语表, 需确认英文译文后再检索"
          "(避免 CT.gov 漏检):")
    for label, orig, sug in foreign_miss:
        print(f"  - {label}: {orig!r}  ->  建议英文译文: {sug or '<请提供>'}")
        cands = kl.kw_match_candidates(orig, "ctgov")
        print(kl.render_kw_menu(orig, cands))
    print("  处理: ① 以英文重写该参数; 或 ② 用 --confirm-cond / --confirm-intr "
          "传入确认译文后重跑。")
    if not args.auto_confirm:
        print("[ct_registry][ABORT] 未确认, 已停止检索"
              "(加 --auto-confirm 可跳过确认直接用原文)。")
        sys.exit(2)
    else:
        print("[ct_registry][WARN] --auto-confirm: 未确认, 直接用原文检索 CT.gov (可能漏检)。")


def _run_ctgov(args, cond_v, intr_v, intr, cond_st, intr_st, out_dir, norm_inputs):
    """Retrieve ClinicalTrials.gov (required source, ENGLISH keywords).

    Also emits the i18n term_map notices (moved here so the CT.gov call + its
    pre-print are one cohesive, testable unit).

    When --ctgov-api-key is given, uses search_ctgov.py --fast (Session pool +
    large pageSize + concurrent pagination). Otherwise uses the default urllib
    path (backward-compatible).
    """
    if args.cond and cond_st == "term_map":
        print(f"[ct_registry][i18n] CT.gov (en): {args.cond!r} -> {cond_v!r}")
    if intr and intr_st == "term_map":
        print(f"[ct_registry][i18n] CT.gov (en): {intr!r} -> {intr_v!r}")
    ctgov = os.path.join(out_dir, "ctgov.json")
    cmd = [PY, os.path.join(HERE, "search_ctgov.py"), "--run"]
    if args.ctgov_api_key:
        # 快速路径：Session 连接池 + 大 pageSize + 并发分页
        cmd += ["--fast", "--page-size", str(max(args.max, 500))]
        print("[ct_registry][CTGOV-FAST] 使用 Session 连接池快速路径 (大 pageSize + 并发分页)。")
    cmd += [
        *(["--cond", cond_v] if cond_v else []),
        *(["--intr", intr_v] if intr_v else []),
        *(["--sponsor", args.sponsor] if args.sponsor else []),
        *(["--status", args.status] if args.status else []),
        "--max", str(args.max), "--out", ctgov,
    ]
    run(cmd)
    norm_inputs += ["--ctgov", ctgov]


def _apply_min_year(args, normalized, out_dir):
    """Apply --min-year filter. Returns (recs_for_excel, norm_in_or_None).

    Writes normalized_filtered.json when filtering is active (norm_in set),
    else returns all normalized records (norm_in None -> aggregate uses original).
    """
    recs_all = _load_recs(normalized)
    if args.min_year and args.min_year > 0:
        kept = [r for r in recs_all if _reg_year(r) >= args.min_year]
        dropped = len(recs_all) - len(kept)
        print(f"[ct_registry][filter] --min-year {args.min_year}: "
              f"保留 {len(kept)} 条, 剔除 {dropped} 条。")
        norm_in = os.path.join(out_dir, "normalized_filtered.json")
        with open(norm_in, "w", encoding="utf-8") as f:
            json.dump(kept, f, ensure_ascii=False, indent=2)
        return kept, norm_in
    return recs_all, None


if __name__ == "__main__":
    main()
