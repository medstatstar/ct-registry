#!/usr/bin/env python3
"""search_ictrp.py - Unified Coze external-service caller (Tier-2): WHO ICTRP (source="who")

WHY (architecture decision 2026-07-27):
  WHO ICTRP was previously NOT a data source because its public portal (ASP.NET
  WebForms) had no clean API and required fragile browser scraping. A dedicated
  external workflow now exposes a clean JSON API for WHO ICTRP (source="who") and
  also for China drug trials (source="chinadrugtrials"). This revives WHO ICTRP as
  a Tier-2 external service. It is valuable because ICTRP mirrors 14+ primary
  registries (jRCT, DRKS, ANZCTR, ISRCTN, CTRI, TCTR, PACTR, IRCT, SLCTR, ...) in
  ONE call -- materially expanding ct-registry coverage beyond the registries we
  directly connect to. The bridging/de-dup value that ICTRP provides is preserved
  by feeding its records into aggregate.py, which re-derives cross-registry links
  (UTN/TRN + fuzzy match + embedded-registration-number scan on the `raw` field).

Endpoint: https://ct-search.coze.site/run  (POST; Bearer token REQUIRED)
  This is the UNIFIED Coze workflow endpoint. It serves:
    - source="who"            -> WHO ICTRP (registry aggregator, mirrors 14+ registries)
    - source="chinadrugtrials" -> China CDE (drug trials registry)
    - source="isrctn"         -> ISRCTN (UK registry; no clean public search API)
    - source="drks"           -> DRKS (German registry; JS/redirect-only search)
    - source="chictr"         -> ChiCTR (China academic trials; no public API)
  The last three are WHO-COVERED national registries that ct-registry retrieves
  INDEPENDENTLY as a fallback when WHO ICTRP (source="who") cannot retrieve. They
  share the single ICTRP Bearer token (embedded in config/keys.py; no .dat file dependency). Drive via --source
  (default who). The standalone CDE endpoint search_cde_workflow.py (archived under
  CDE/) -> ct-searchcde.coze.site/run is RETIRED (2026-08-12) -- local reference only;
  production CDE uses source="chinadrugtrials" on the unified endpoint.

Modes (`mode` field, required):
  search        - free-text `keyword` query (structured WHO fields not used)
  combined      - structured `who_*` filters (+ optional `keyword`)
  multi_keyword - multi_keywords (space separated, intersect)
  detail        - fetch project details from a project_list JSON string

Fetch strategy (`--fetch-mode`, optional; default = legacy auto-detect):
  list   - run a search ONLY (1 Coze call). (Legacy default when no --project-list.)
  detail - run detail ONLY (requires --project-list; 1 Coze call).
           (Legacy when --mode detail or --project-list is set.)
  both   - run the search, then AUTOMATICALLY fetch details from the returned
           project_list in the SAME invocation (2 Coze calls, but 1 demand_id
           charge thanks to DEMAND-BASED DEDUP). Symmetric across who /
           chinadrugtrials / isrctn / drks / chictr. Lists with >100 records skip
           auto-detail unless --auto-confirm (cost / timeout guard, mirrors the
           CDE _run_cde_detail skip logic in ct_registry.py).

Payload contract (mirrors CDE / Coze convention, verified for that family):
  - Send PLAIN STRINGS for who_* fields; OMIT unused fields entirely (do NOT send
    "" -- the endpoint rejects/poisons the query when empty fields are present).
  - who_*_operator: "AND" / "OR" / "NOT". who_*_no_synonyms: boolean.
  - max_pages: int (default 50 -> ~500 results; ~10 records per page).
  - Booleans: who_covid19 / who_with_results / who_rare_diseases / who_gene_editing.

Response schema:
  {"source":"who", "project_list":"<JSON string of records>", "total_count":N,
   "error_msg":"...", "scraped_data_json":"..." (detail mode)}
  `project_list` is a JSON STRING -> parsed here into a list of record dicts.
  Each record carries fields such as 登记号/Main ID, 药物名称/公共标题,
  适应症/健康状况, 试验状态/招募状态, 项目ID. norm_ictrp (normalize.py) probes
  candidate keys and stashes the FULL record in `raw` so aggregate.py can bridge
  on embedded registry numbers (NCT / JPRN / CTRI / ...).

Egress: only PUBLIC query terms leave. No confidential subject / protocol data ->
compliant with the ct-base confidentiality red line.

Safety model (ct-base §0.2): default SAFE PREVIEW. The script prints the exact
payload and the request it WOULD make, and performs NO network I/O unless --run.
"""
import argparse
import base64
import json
import os
import sys
import time          # 异步轮询指数退避用
import re            # 升级反馈环 keyword 粗粒度拆分用
import hashlib       # ct-base §8.6：query_origin = sha256(本机 hostname)，须由技能安装设备生成
import socket        # ct-base §8.6：禁止由 Coze 服务器生成（容器 hostname 漂移）

# Reuse the shared external-service token machinery (config/keys.py, XOR+base64 embedded; no .dat).
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "scripts"))  # shared pure-local utils (usage_guard, keyword_breadth)
from extsvc_client import (get_token, _status_guidance, _check_outbound_authorization,
                            _request, _sanitize_payload)
import usage_guard  # daily shared-resource call cap (100/day)
try:
    from keyword_breadth import is_soft_broad
except Exception:  # 底座未就绪时降级（不影响硬逻辑）
    def is_soft_broad(kw):
        return False

DEFAULT_ENDPOINT = "https://ct-search.coze.site/run"

# API `source` field values for the unified endpoint.
# who = WHO ICTRP (registry aggregator); chinadrugtrials = China CDE (drug trials).
# isrctn / drks / chictr = the national registries WHO covers but which have no
#   clean public search API of their own — they are served by the SAME unified
#   workflow (extended to these sources) so ct-registry can fall back to them
#   independently when WHO ICTRP (source="who") cannot retrieve.
API_SOURCE = {"who": "who", "chinadrugtrials": "chinadrugtrials",
              "isrctn": "isrctn", "drks": "drks", "chictr": "chictr"}
# Internal record-source label (used by normalize.py adapter routing).
RECORD_SOURCE = {"who": "ICTRP", "chinadrugtrials": "CDE",
                 "isrctn": "ISRCTN", "drks": "DRKS", "chictr": "CHICTR"}
# Token config is SHARED: both sources hit the SAME unified endpoint and use the
# SAME Coze token (config/keys.py embedded blob). The standalone CDE endpoint (search_cde_workflow.py,
# archived under CDE/) -> ct-searchcde.coze.site/run is RETIRED (2026-08-12), kept for local reference only.
TOKEN_SOURCE = "ICTRP"


def _compute_query_origin():
    """ct-base §8.6：query_origin = sha256(本机 hostname)，标识调用来源机器。

    必须由技能安装设备（本机）生成并随请求携带；禁止由 Coze 服务器生成
    （Coze 容器 hostname 是实例标识，重建即漂移，且标识的是服务器而非来源机器）。
    SHA256 单向不可逆，不含明文主机名 / IP / 任何 PII。
    """
    return "sha256:" + hashlib.sha256(socket.gethostname().encode("utf-8")).hexdigest()


def _map_status(status):
    """Map a ct_registry --status value to a WHO recruitment status if possible.

    WHO's recruitment_status enum is only Recruiting / All; other Chinese statuses
    (进行中 / 已完成 / ...) have no clean WHO equivalent, so we leave them generic.
    """
    if not status:
        return None
    s = status.strip()
    if s in ("招募中", "Recruiting"):
        return "Recruiting"
    return None


def build_payload(args):
    api_source = API_SOURCE.get(args.source, "who")
    if args.mode == "detail" or args.project_list:
        # ---- detail fetch. project_list may be a JSON string OR a file path. ----
        pl = args.project_list
        if os.path.isfile(pl):
            try:
                d = json.load(open(pl, encoding="utf-8"))
            except Exception as e:
                sys.exit(f"[ictrp-extsvc][ERROR] --project-list 文件不是合法 JSON: {pl} ({e})")
            if isinstance(d, list):
                pl = d  # top-level array of records -> use directly
            elif isinstance(d, dict):
                # Prefer project_list_raw (wrapped {projects:[{project_id}]} string
                # preserved by a prior LIST call) so the endpoint can resolve details;
                # fall back to project_list / records (6-field summary) if absent.
                pl = (d.get("project_list_raw") or d.get("project_list") or d.get("records"))
                if pl is None:
                    sys.exit("[ictrp-extsvc][ERROR] --project-list 文件缺少 project_list_raw / project_list / records 字段，"
                              "无法用作 detail 输入。应指向 list 输出文件（含 project_list_raw）或 `{\"records\": [...]}` 格式。")
            else:
                pl = d
        if isinstance(pl, (list, dict)):
            pl = json.dumps(pl, ensure_ascii=False)
        payload = {"mode": "detail", "source": api_source, "project_list": pl}
        if getattr(args, "query_origin", None):
            payload["query_origin"] = args.query_origin
        return payload

    if args.source == "chinadrugtrials":
        return _build_cde_payload(args, api_source)
    if args.source in ("isrctn", "drks", "chictr"):
        return _build_simple_payload(args, api_source)
    return _build_who_payload(args, api_source)


def _build_who_payload(args, api_source):
    # ---- search / combined / multi_keyword (WHO ICTRP, source="who") ----
    fields = {}
    if args.q:
        fields["keyword"] = args.q
    if args.who_title:
        fields["who_title"] = args.who_title
        if args.who_title_operator:
            fields["who_title_operator"] = args.who_title_operator
    if args.who_condition:
        fields["who_condition"] = args.who_condition
    iv = args.who_intervention or args.intr
    if iv:
        fields["who_intervention"] = iv
        if args.who_intervention_operator:
            fields["who_intervention_operator"] = args.who_intervention_operator
    sp = args.who_sponsor or args.sponsor
    if sp:
        fields["who_sponsor"] = sp
    if args.who_country:
        fields["who_country"] = args.who_country
    if args.who_phase:
        fields["who_phase"] = args.who_phase
    rs = args.who_recruitment_status or _map_status(args.status)
    if rs:
        fields["who_recruitment_status"] = rs
    if args.who_secondary_id:
        fields["who_secondary_id"] = args.who_secondary_id
    if args.who_date_start:
        fields["who_date_start"] = args.who_date_start
    if args.who_date_end:
        fields["who_date_end"] = args.who_date_end
    for b in ("who_covid19", "who_with_results", "who_rare_diseases", "who_gene_editing"):
        v = getattr(args, b, None)
        if v is not None:
            fields[b] = v

    # ---- mode selection (2026-08-14 rev: multi_keyword is the default anti-ban START point;
    #      "advanced" == combined, there is NO separate advanced mode) ----
    # Text query terms (q/title/condition/intervention/sponsor) can be folded into a single
    # multi_keyword AND. Structured filters (country/phase/date/recruitment/secondary-id/
    # booleans) ONLY take effect in combined mode.
    _q_words = args.q.split() if args.q else []
    text_terms = [v for v in (_q_words + [args.who_title, args.who_condition,
                              args.who_intervention or args.intr,
                              args.who_sponsor or args.sponsor]) if v]
    struct_filters = [v for v in (args.who_country, args.who_phase, args.who_date_start,
                                   args.who_date_end, rs, args.who_secondary_id) if v]
    if args.mode == "multi_keyword" or args.multi_keywords:
        mode = "multi_keyword"
        fields["multi_keywords"] = args.multi_keywords or args.q or " ".join(text_terms)
    elif args.mode:
        mode = args.mode
    elif struct_filters:
        mode = "combined"
    elif len(text_terms) >= 2:
        mode = "multi_keyword"
        fields["multi_keywords"] = " ".join(text_terms)
    else:
        mode = "search"

    # multi_keyword mode honors ONLY `multi_keywords`; drop the individual who_* TEXT fields
    # so the unified endpoint does NOT treat them as combined structured filters.
    if mode == "multi_keyword":
        for k in ("who_title", "who_title_operator", "who_condition", "who_intervention",
                  "who_intervention_operator", "who_sponsor", "keyword"):
            fields.pop(k, None)

    payload = {"mode": mode, "source": api_source}
    payload.update(fields)
    if args.max_pages:
        payload["max_pages"] = args.max_pages
    elif args.max:
        payload["max_pages"] = max(1, (args.max + 9) // 10)
    if getattr(args, "query_origin", None):
        payload["query_origin"] = args.query_origin
    return payload


def _build_cde_payload(args, api_source):
    # ---- CDE search via unified endpoint (source="chinadrugtrials") ----
    # VERIFIED 2026-08-14 (3 variants, raw POST A/B): the unified CDE node ONLY honors
    # free-text `keyword`. Sending structured fields (drugs_name / indication /
    # appliers / trial_status / ...) makes the node build
    # `searchlist.dhtml?<field>=...` GET URLs that the LIVE CDE site's advanced-search
    # FORM ignores -> 0 records (returns 0 even when `keyword` is also present).
    # coze's own self-test uses `keyword` only, hence "normal". This is the root cause
    # of `ct_registry.py --cde --cde-drugs-name ...` always returning 0 (calling-method
    # bug, NOT upstream). FIX: fold every supplied CDE field into the free-text
    # `keyword` (space-joined) and emit ONLY `keyword` (+ mode). Do NOT emit
    # is_advanced_search or the individual structured fields for the unified endpoint.
    # Field-level AND precision is approximated by CDE's substring match across
    # 药物名称 / 适应症 / 题目 fields. multi_keyword mode keeps wide queries small.
    terms = []
    if args.q:
        terms.append(args.q)
    for cli in ["reg_no", "indication", "case_no", "drugs_name", "drugs_type",
                "appliers", "communities", "researchers", "agencies", "trial_status"]:
        v = getattr(args, cli, None)
        if v:
            terms.append(v)
    keyword = " ".join(terms).strip()
    fields = {}
    if keyword:
        fields["keyword"] = keyword
    if args.multi_keywords:
        # explicit multi-keyword AND (space-separated); fold CLI fields in too
        fields["multi_keywords"] = (keyword + " " + args.multi_keywords).strip() if keyword else args.multi_keywords
        mode = "multi_keyword"
    elif len(terms) > 1 and args.mode != "combined":
        # several structured terms -> multi_keyword AND keeps the result set small
        mode = "multi_keyword"
        fields["multi_keywords"] = keyword
    elif args.mode:
        mode = args.mode
    else:
        mode = "search"
    payload = {"mode": mode, "source": api_source}
    payload.update(fields)
    # 静默降级参数（CDE 中文检索 0 条时自动补发英文）
    if getattr(args, "silent_fallback", False):
        payload["silent_fallback"] = True
    if getattr(args, "fallback_keyword", None):
        payload["fallback_keyword"] = args.fallback_keyword
    if args.max_pages:
        payload["max_pages"] = args.max_pages
    elif args.max:
        payload["max_pages"] = max(1, (args.max + 9) // 10)
    if getattr(args, "query_origin", None):
        payload["query_origin"] = args.query_origin
    return payload


def _build_simple_payload(args, api_source):
    # ---- search / multi_keyword (ISRCTN / DRKS / ChiCTR via unified endpoint) ----
    # These national registries have NO clean public search API of their own
    # (ISRCTN query API 404 + JS page; DRKS JS/redirect; ChiCTR no API). The unified
    # Coze workflow serves them with a simple free-text `keyword` search (optionally
    # multi_keyword AND). No structured WHO/CDE fields are used. The backend returns
    # records shaped for the matching normalize adapter (ISRCTN -> isrctn/title/...;
    # DRKS -> drks_id/title/...; CHICTR -> registry_id/title/url).
    fields = {}
    if args.q:
        fields["keyword"] = args.q
    if args.multi_keywords:
        fields["multi_keywords"] = args.multi_keywords
    mode = "multi_keyword" if args.multi_keywords else "search"
    payload = {"mode": mode, "source": api_source}
    payload.update(fields)
    if args.max_pages:
        payload["max_pages"] = args.max_pages
    elif args.max:
        payload["max_pages"] = max(1, (args.max + 9) // 10)
    if getattr(args, "query_origin", None):
        payload["query_origin"] = args.query_origin
    return payload


def print_preview(payload, token, out, endpoint):
    print("[ictrp-extsvc][PREVIEW] No network request will be made. Add --run to execute.")
    print(f"[ictrp-extsvc][PREVIEW] Endpoint : {endpoint}")
    print("[ictrp-extsvc][PREVIEW] Auth     :",
          "Bearer <token set>" if token else "none (endpoint returns 401)")
    print(f"[ictrp-extsvc][PREVIEW] Payload:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"[ictrp-extsvc][PREVIEW] Output   : {out}")


def _resolve_out_path(out):
    """Normalize the --out path and ensure its parent directory exists.

    Robustness fix (2026-08-09): when the caller passes a POSIX-style path
    produced by Git Bash (e.g. `/tmp/ct_retest/A.json`), native Windows Python
    resolves it to `C:\\tmp\\ct_retest\\A.json`. If that directory does not
    exist the write fails with a raw traceback. We abspath + expanduser and
    create the parent dir up front so the write always lands somewhere
    predictable (and on Windows the POSIX path is anchored to the CWD drive).
    """
    p = os.path.expanduser(out)
    p = os.path.abspath(p)
    parent = os.path.dirname(p)
    if parent:
        try:
            os.makedirs(parent, exist_ok=True)
        except OSError:
            pass  # best-effort; the open() below will surface a clear error
    return p


# --fetch-mode both (2026-08-12): list-then-detail in ONE invocation.
# Lists with more than this many records skip auto-detail (cost / timeout guard),
# matching the CDE _run_cde_detail skip logic in ct_registry.py.
BOTH_DETAIL_LIMIT = 100


def _detail_out_path(out):
    """For --fetch-mode both: derive the detail-output path from the list-output path."""
    base, ext = os.path.splitext(out)
    return base + "_detail" + ext


def _read_project_list_raw(out):
    """Read a prior list output JSON and return its project_list_raw (wrapped string),
    or fall back to re-serializing its `records` list. None if unreadable / empty."""
    try:
        with open(out, encoding="utf-8") as f:
            obj = json.load(f)
    except Exception:
        return None
    raw = obj.get("project_list_raw")
    if isinstance(raw, str) and raw.strip():
        return raw
    recs = obj.get("records")
    if isinstance(recs, list) and recs:
        return json.dumps(recs, ensure_ascii=False)
    return None


def _read_record_count(out):
    """Read `total` (record count) from a prior list output JSON. None if unreadable."""
    try:
        with open(out, encoding="utf-8") as f:
            obj = json.load(f)
        return obj.get("total")
    except Exception:
        return None


def _resolve_fetch_mode(args):
    """Map CLI to one of list/detail/both.

    Legacy (no --fetch-mode): detail when --mode detail or --project-list is set,
    else list. --fetch-mode always wins when supplied.
    """
    if args.fetch_mode:
        return args.fetch_mode
    if args.mode == "detail" or args.project_list:
        return "detail"
    return "list"


def _write_out_json(out, obj):
    """Write the result dict as JSON; surface a clear error instead of a raw traceback."""
    try:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        return True
    except OSError as e:
        print(f"[ictrp-extsvc][ERROR] 无法写入输出文件 {out}: {e}")
        print(f"[ictrp-extsvc][ERROR] 请检查路径/父目录是否存在、是否有写权限；"
              f"建议改用绝对路径（如 C:/Users/you/out.json）。")
        return False


def _write_timeout_ictrp(out, source_label, timeout, phase):
    """统一写 is_timeout=True 占位输出（提交/轮询阶段超时共用），含高级检索建议菜单。"""
    out_obj = {
        "source": source_label,
        "records": [],
        "total": 0,
        "total_available": None,
        "total_count_reported": None,
        "error_msg": f"timeout after {timeout}s (Coze search exceeded wait limit)",
        "project_list_raw": None,
        "is_timeout": True,
        # 结构化建议：供代理（agent）转达为交互菜单。高级检索由代码实现，
        # 用户无需手动操作字段——代理把复合关键字按 药物→who_intervention /
        # 疾病→who_condition / 申办方→who_sponsor 拆分后，以 combined 模式发起，
        # 服务端做字段级 AND 过滤，返回量更小、通常更快。
        "suggestion": "advanced_combined_search",
        "suggestion_detail": (
            "可改用 WHO 高级检索（combined 模式，由代码实现）：把复合关键字按 "
            "药物→who_intervention、疾病→who_condition、申办方→who_sponsor 拆分，"
            "服务端做字段级 AND 过滤，返回量更小、通常更快。用户无需手动操作字段，"
            "由代理（agent）通过 ct_registry.py --who-mode combined 或 "
            "search_ictrp.py --mode combined 发起。注意：WHO 站点设定可能导致高级检索"
            "漏掉部分记录，若需最全覆盖可再用普通检索交叉验证。"),
    }
    if not _write_out_json(out, out_obj):
        return
    print(f"[ictrp-extsvc][TIMEOUT] Coze 检索超过 {timeout}s 仍未返回，已超时退出（is_timeout=True）。")
    print(f"[ictrp-extsvc][GUIDE] 数据可能不全。可选项（由代理转达为菜单，二选一/跳过）：")
    print(f"[ictrp-extsvc][GUIDE]   ① 改用 WHO 高级检索（combined 模式，代码自动拆分关键字做服务端 AND 过滤，返回量更小更快）")
    print(f"[ictrp-extsvc][GUIDE]   ② 缩小 / 更换关键字后重试")
    print(f"[ictrp-extsvc][GUIDE]   ③ 跳过 WHO，用其他已检索源（CT.gov / EU-CTR / CDE 等）出报告")


def _parse_response(data, source_label, payload, out, http_status=200, is_timeout=False):
    """把 Coze 响应解析为输出对象并落盘；同步分支与异步 completed 分支共用。"""
    # project_list shape:
    #   search/combined/multi_keyword -> a JSON STRING whose inner object holds
    #     {"total_count":N, "total_records":M, "projects":[...]}  (projects = records)
    #   detail                        -> a list of records (already JSON)
    pl = data.get("project_list")
    records = []
    total_available = None
    inner = None  # may stay None when project_list is dict-wrapped (detail mode)
    if isinstance(pl, str):
        try:
            inner = json.loads(pl)
        except Exception:
            inner = None
            print("[ictrp-extsvc][WARN] project_list not valid JSON; storing empty records.")
        if isinstance(inner, dict):
            total_available = inner.get("total_records")  # grand total available (e.g. 28933)
            pl = inner.get("projects") or inner.get("records")
        elif isinstance(inner, list):
            pl = inner
    elif isinstance(pl, dict):
        # detail mode may return a dict-wrapped project_list directly
        inner = pl
        total_available = pl.get("total_records") or pl.get("total_count")
        pl = pl.get("projects") or pl.get("records")
    if isinstance(pl, list):
        records = pl
    # fallback: records / projects at top level (some detail responses)
    if not records:
        fb = data.get("records") or data.get("projects")
        if isinstance(fb, list):
            records = fb
    # ---- detail-mode enrichment: prefer scraped_data_json (65-field detail) ----
    sdj = data.get("scraped_data_json")
    if sdj:
        try:
            parsed = json.loads(sdj) if isinstance(sdj, str) else sdj
            det = (parsed.get("projects") or parsed.get("records") or parsed
                   if isinstance(parsed, dict) else parsed) if not isinstance(parsed, list) else parsed
            if isinstance(det, list) and det:
                records = det
        except Exception:
            pass
    project_list_raw = data.get("project_list") if isinstance(data.get("project_list"), str) else None
    if not records and http_status == 200 and not data.get("error_msg"):
        print(f"[ictrp-extsvc][WARN] 0 records returned for source={source_label} "
              f"despite HTTP 200 and no error_msg. This is usually a TRANSIENT "
              f"scrape miss by the unified workflow (same query often recovers on "
              f"re-run), NOT a genuine zero-result. Downstream will simply lack "
              f"this source — consider re-running the query.")
    req_pages = payload.get("max_pages") if isinstance(payload, dict) else None
    if req_pages and records:
        approx_cap = req_pages * 10
        if len(records) > approx_cap:
            print(f"[ictrp-extsvc][WARN] returned {len(records)} records but "
                  f"max_pages={req_pages} was requested (~{approx_cap} expected). "
                  f"The unified endpoint IGNORES max_pages and returns the full "
                  f"match — `--max` is NOT enforced for Coze sources "
                  f"(CDE/WHO/ChiCTR/ISRCTN/DRKS). Narrow the keyword to reduce volume.")
    out_obj = {
        "source": source_label,
        "records": records,
        "total": len(records),
        "total_available": total_available,
        "total_count_reported": data.get("total_count"),
        "error_msg": data.get("error_msg"),
        "project_list_raw": project_list_raw,
        "is_timeout": is_timeout,
        "escalate_to_combined": inner.get("escalate_to_combined") if isinstance(inner, dict) else None,
        "large_result_set": inner.get("large_result_set") if isinstance(inner, dict) else None,
        "is_partial": (inner.get("is_partial", False) if isinstance(inner, dict) else False),
        "log": data.get("log", ""),
        "query_origin": data.get("query_origin", ""),
    }
    # P1-followup (2026-08-12): surface partial-result gaps so the user knows they did
    # NOT get the full result set (unified gateway may return only part of a wide query).
    if out_obj.get("large_result_set"):
        out_obj["error_msg"] = out_obj.get("error_msg") or (
            "结果集过大（>WHO_RESULT_CEILING），已停止检索并避免翻页封禁。"
            "请加窄筛选字段（--who-condition/--who-country/--who-phase/--who-recruitment-status）后重试。")
        print(f"[ictrp-extsvc][LARGE-RESULT-SET] ⚠️ coze 回 large_result_set："
              f"combined 仍超阈值，已停止。{out_obj['error_msg']}")
    if total_available and isinstance(total_available, int) and len(records) < total_available:
        _gap = total_available - len(records)
        print(f"[ictrp-extsvc][PARTIAL] ⚠️ 仅取回 {len(records)} 条 / 共 {total_available} 条"
              f"（缺口 {_gap} 条）。统一网关对宽检索可能只返回部分结果；"
              f"建议缩小关键词或改用 --mode combined 字段过滤后重跑。")
    if not _write_out_json(out, out_obj):
        return None
    print(f"[ictrp-extsvc] {len(records)} records -> {out} "
          f"(total_count={out_obj['total']})")
    if data.get("log"):
        print(f"[ictrp-extsvc][LOG] {data['log']}")
    return out_obj


def _finalize_async_ictrp(source_label, endpoint_base, data, out, timeout, run_id, payload):
    """解析 /run/status 的最终结果（兼容两种返回形态）。"""
    if data.get("status") == "failed":
        sys.exit(f"[ictrp-extsvc][ERROR] remote run failed: {data.get('error')}")
    if data.get("status") == "cancelled":
        _write_timeout_ictrp(out, source_label, timeout, "cancelled")
        return
    # completed：data 可能是 {status, result} 或直接是 result dict
    result = data.get("result", data)
    is_timeout = bool(result.get("is_timeout"))
    _parse_response(result, source_label, payload, out, http_status=200, is_timeout=is_timeout)


def _run_async_poll_ictrp(source_label, endpoint, token, run_id, out, timeout, payload):
    """异步模式：轮询 /run/status/{run_id}，指数退避，总上限 timeout 秒。"""
    import requests
    endpoint_base = endpoint.rsplit("/run", 1)[0]
    status_url = f"{endpoint_base.rstrip('/')}/run/status/{run_id}"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    deadline = time.time() + timeout
    wait = 5.0
    while time.time() < deadline:
        try:
                # ct-base §5.49：代理残留自动重试（ProxyError/ConnectionError → 绕代理直连）
            r = _request("GET", status_url, headers=headers, timeout=10)
        except requests.exceptions.Timeout:
            time.sleep(min(wait, max(1, deadline - time.time())))
            wait = min(wait * 2, 30)
            continue
        except requests.RequestException as e:
            sys.exit(f"[ictrp-extsvc][ERROR] poll request failed: {e}")
        try:
            data = r.json()
        except Exception:
            data = {}
        status = data.get("status")
        if status == "running":
            time.sleep(min(wait, max(1, deadline - time.time())))
            wait = min(wait * 2, 30)
            continue
        _finalize_async_ictrp(source_label, endpoint_base, data, out, timeout, run_id, payload)
        return
    _write_timeout_ictrp(out, source_label, timeout, "poll")


def run(payload, token, out, timeout, endpoint, source_label, use_stream=False):
    """检索（含升级反馈环）：multi_keyword→combined 逐级收敛大结果集，combined 仍超限即报错。

    收到 coze 端 escalate_to_combined 信号时，自动构造 combined payload 重发；收到
    large_result_set 信号时停止并报错。最多 MAX_WHO_ESCALATION 次。目的：避免单次超宽
    检索硬翻数十页触发 WHO 限流/封禁（详见 coze/WHO_SEARCH_OPTIMIZATION.md §0.6）。
    """
    out = _resolve_out_path(out)
    last_out = None
    cur_payload = payload
    for depth in range(MAX_WHO_ESCALATION + 1):
        last_out = _run_once(cur_payload, token, out, timeout, endpoint, source_label, use_stream)
        if last_out is None:
            return None
        if depth >= MAX_WHO_ESCALATION:
            break
        if last_out.get("escalate_to_combined"):
            np = _escalate_payload(cur_payload, "combined")
            if np is None:
                break
            cur_payload = np
            print(f"[ictrp-extsvc][ESCALATE] multi_keyword/search 超限 → 升级 combined 重发（depth {depth + 1}）")
            continue
        # combined 仍超限（coze 回 large_result_set）-> 循环自然结束，最后 out_obj 带报错标记
        break
    return last_out


# ===== WHO 升级反馈环辅助函数（2026-08-14）=====
MAX_WHO_ESCALATION = 2          # multi_keyword→combined 最多 1 次升级重发（值留 2 作余量）

def _read_out_json(out):
    """读回已落盘的输出 JSON（异步轮询分支升级重发前取结果）。"""
    try:
        with open(out, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

# ===== 流式调用（/stream_run, SSE）=====
# 2026-08-14 实测结论（决定解析位置，已用真实 SSE 探测验证）：coze 对该 vibeflow 的流行为——
#   * 普通流式（不带 debug 头）：仅 workflow_start + workflow_end(output:{})，结果完全不进流 → 不可用。
#   * debug 流式（header x-workflow-stream-mode: debug）：发出 node_start/node_end；
#     主检索节点 search_node（detail 模式为 scrape_details_node）的 node_end.output
#     携带 {project_list, total_count, log}（即真正的回传参数）；workflow_end.output 恒为 {}。
# 因此流式【必须带 debug 头】，并从「主节点的 node_end.output」取结果；workflow_end 忽略。
# 取不到结果（非 debug / 流异常 / HTTP≠200）一律回退同步 /run，保证零回归。
_STREAM_DEBUG_HEADER = "x-workflow-stream-mode"
_PRIMARY_NODES = ("search_node", "scrape_details_node")


def _parse_sse(resp):
    """解析 /stream_run 的 SSE 流，取出主节点的回传参数。

    返回 (result_dict_or_None, stream_dropped, error_msg)：
      - result_dict: 主节点 node_end.output（含 project_list/total_count/log），可直接喂 _parse_response
      - stream_dropped: True 表示流中未取到任何可用结果（需回退 /run 同步）
      - error_msg: 流中 error 帧的错误文案（可能为 None）
    """
    result = None
    error_msg = None
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        chunk = line[len("data:"):].strip()
        if not chunk:
            continue
        try:
            evt = json.loads(chunk)
        except Exception:
            continue
        etype = evt.get("type")
        if etype == "node_end":
            out = evt.get("output")
            nm = evt.get("node_name", "")
            if isinstance(out, dict) and (nm in _PRIMARY_NODES or "project_list" in out):
                # 主检索节点输出即最终回传参数；detail 模式下 scrape_details_node 覆盖 search_node
                result = out
        elif etype == "error":
            error_msg = evt.get("msg") or evt.get("error_message") or json.dumps(evt, ensure_ascii=False)
        # workflow_end.output 恒为 {}，忽略
    if result is None and error_msg is None:
        return None, True, None
    return result, False, error_msg


def _try_stream(payload, token, out, timeout, endpoint, source_label):
    """尝试 /stream_run（debug 模式）。成功取到结果返回 out_obj；否则返回 None（交由调用方回退 /run）。"""
    import requests
    stream_endpoint = endpoint.rsplit("/run", 1)[0] + "/stream_run"
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream",
               _STREAM_DEBUG_HEADER: "debug"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    print(f"[ictrp-extsvc][STREAM] POST {stream_endpoint} (debug)")
    try:
        # ct-base §5.50：出站 payload 发送前脱敏；§5.49：代理残留自动重试
        resp = _request("POST", stream_endpoint, headers=headers,
                        json=_sanitize_payload(payload), stream=True, timeout=timeout)
    except requests.exceptions.Timeout:
        _write_timeout_ictrp(out, source_label, timeout, "submit-stream")
        return None
    except requests.RequestException as e:
        print(f"[ictrp-extsvc][STREAM][WARN] 流式请求异常 {e}，回退同步 /run")
        return None
    if resp.status_code != 200:
        print(f"[ictrp-extsvc][STREAM][WARN] /stream_run HTTP {resp.status_code}，回退同步 /run")
        return None
    result, dropped, err = _parse_sse(resp)
    if dropped:
        print("[ictrp-extsvc][STREAM][WARN] 流中无可用结果（确认 debug 头已带 / 端点支持流式），回退同步 /run")
        return None
    if err and result is None:
        print(f"[ictrp-extsvc][STREAM][ERROR-MSG] {err}")
        return None
    print("[ictrp-extsvc][STREAM] 已从主节点 node_end 取到回传参数，落盘")
    return _parse_response(result, source_label, payload, out, http_status=200)


def _run_once(payload, token, out, timeout, endpoint, source_label, use_stream=False):
    """单次提交+等待+解析（流式 /stream_run 优先，失败自动回退同步 /run），落盘并返回 out_obj；失败返回 None。"""
    # ---- 审计日志字段：把本次请求参数（不含 querystr 自身）序列化，供 coze 端飞书 querystr 列记录 ----
    # token 在 HTTP header（Authorization），从不进 payload；此处仅序列化检索参数，无凭据。
    if "querystr" not in payload:
        payload["querystr"] = json.dumps(
            {k: v for k, v in payload.items() if k != "querystr"},
            ensure_ascii=False, sort_keys=True)
    # ---- 流式优先（debug 模式，从主节点 node_end.output 取回传参数）----
    if use_stream:
        so = _try_stream(payload, token, out, timeout, endpoint, source_label)
        if so is not None:
            return so
        print("[ictrp-extsvc][STREAM] 回退同步 /run")
    import requests
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        print("[ictrp-extsvc][WARN] no token -> endpoint returns 401 (Bearer required)")
    # 阶段1：提交（应毫秒级返回 run_id；短超时避免卡网关）
    # ct-base §5.50：出站 payload 发送前脱敏；§5.49：代理残留自动重试
    try:
        submit_resp = _request("POST", endpoint, headers=headers,
                               json=_sanitize_payload(payload), timeout=30)
    except requests.exceptions.Timeout:
        _write_timeout_ictrp(out, source_label, timeout, "submit")
        return None
    except requests.RequestException as e:
        sys.exit(f"[ictrp-extsvc][ERROR] request failed: {e}")
    try:
        submit_data = submit_resp.json()
    except Exception:
        submit_data = {}
    if submit_data.get("status") == "accepted" and submit_data.get("run_id"):
        _run_async_poll_ictrp(source_label, endpoint, token, submit_data["run_id"], out, timeout, payload)
        return _read_out_json(out)
    # 同步协议分支
    print(f"[ictrp-extsvc] HTTP {submit_resp.status_code}")
    guide = _status_guidance(submit_resp.status_code)
    if guide:
        print(f"[ictrp-extsvc][GUIDE] {guide}")
    if submit_resp.status_code != 200:
        print(f"[ictrp-extsvc] body: {submit_resp.text[:600]}")
        print("[ictrp-extsvc] no successful response -> output NOT written.")
        return None
    try:
        data = submit_resp.json()
    except Exception:
        data = {"raw": submit_resp.text}
    if data.get("error_msg"):
        print(f"[ictrp-extsvc][ERROR-MSG] {data['error_msg']}")
    return _parse_response(data, source_label, payload, out, http_status=submit_resp.status_code)

def _escalate_payload(base, level):
    """构造升级重发 payload（仅 level="combined"）。无法升级时返回 None。

    multi_keyword/search 超限 -> combined：
      - 已有 who_* 结构化字段 -> 直接 mode=combined 复用。
      - 来自 multi_keyword（有 multi_keywords 自由文本）或单 keyword ->
        把自由文本词拆成 who_condition / who_intervention（前半/后半，含分隔符时），
        并加 who_recruitment_status=Recruiting 尽力收敛，mode=combined。
      精准拆分仍应由上层 ct_registry.py 用 --who-condition/--who-intervention 完成。
    """
    if level != "combined":
        return None
    p = dict(base)
    p.pop("multi_keywords", None)          # combined 模式不认 multi_keywords
    # 关键：不要把 keyword 直接丢弃——coze 端 combined 模式只认 who_* 字段、不认裸
    # keyword，若丢弃关键词会变成「仅 who_recruitment_status=Recruiting」的全库查询
    # （实测 283167 条）。必须把自由文本关键词映射成 who_condition/who_intervention
    # 才能保留过滤语义。
    if p.get("who_condition") or p.get("who_intervention") or p.get("who_country") \
            or p.get("who_phase") or p.get("who_sponsor"):
        p["mode"] = "combined"
        return p
    # 自由文本 -> 尽力拆成 who_* 字段 + Recruiting 收敛（始终保留关键词过滤）
    text = (p.get("keyword") or base.get("keyword")
            or p.get("multi_keywords") or base.get("multi_keywords") or "").strip()
    p.pop("keyword", None)                 # 已转为 who_* 字段，combined 不再发裸 keyword
    if text:
        if re.search(r"[\s,;]+", text):
            parts = [x.strip() for x in re.split(r"[\s,;]+", text, maxsplit=1)]
            if len(parts) == 2 and all(parts):
                p["who_condition"] = parts[0]
                p["who_intervention"] = parts[1]
                print(f"[ictrp-extsvc][ESCALATE] 粗粒度拆分 {text!r} → "
                      f"who_condition={parts[0]!r} / who_intervention={parts[1]!r}"
                      f"（启发式；精准拆分见 ct_registry.py）")
        else:
            # 单关键词：整词作 who_condition，保留过滤语义（避免升 combined 后变全库）
            p["who_condition"] = text
            print(f"[ictrp-extsvc][ESCALATE] 单关键词 {text!r} → who_condition={text!r}"
                  f"（启发式；精准字段拆分见 ct_registry.py）")
    if not p.get("who_recruitment_status"):
        p["who_recruitment_status"] = "Recruiting"   # 满足 coze combined 强制筛选校验
    p["mode"] = "combined"
    return p

def main():
    ap = argparse.ArgumentParser(
        description="WHO ICTRP search via external Coze workflow (Tier-2, no local browser)")
    ap.add_argument("--q", help="free-text query -> keyword (search mode)")
    ap.add_argument("--cond", dest="q", help="alias of --q (condition)")
    ap.add_argument("--intr", help="intervention -> who_intervention")
    ap.add_argument("--sponsor", help="sponsor -> who_sponsor")
    ap.add_argument("--status", help="status; mapped to who_recruitment_status when Recruiting")
    ap.add_argument("--mode", choices=["search", "combined", "multi_keyword", "detail"])
    ap.add_argument("--who-title", help="WHO title keyword")
    ap.add_argument("--who-title-operator", choices=["None", "NOT"])
    ap.add_argument("--who-condition", help="WHO health condition (override --q)")
    ap.add_argument("--who-intervention", help="WHO intervention (override --intr)")
    ap.add_argument("--who-intervention-operator", choices=["AND", "OR", "NOT"])
    ap.add_argument("--who-sponsor", help="WHO sponsor (override --sponsor)")
    ap.add_argument("--who-country", help="WHO recruiting country (comma-separated)")
    ap.add_argument("--who-phase", help="WHO phase (e.g. 'Phase 2,Phase 3')")
    ap.add_argument("--who-recruitment-status", help="WHO recruitment status (Recruiting/All)")
    ap.add_argument("--who-secondary-id", help="WHO secondary ID (e.g. an ISRCTN number)")
    ap.add_argument("--who-date-start", help="WHO reg date start (DD/MM/YYYY)")
    ap.add_argument("--who-date-end", help="WHO reg date end (DD/MM/YYYY)")
    ap.add_argument("--who-covid19", type=lambda x: str(x).lower() == "true",
                    help="boolean: COVID-19 studies only")
    ap.add_argument("--who-with-results", type=lambda x: str(x).lower() == "true",
                    help="boolean: studies with results only")
    ap.add_argument("--who-rare-diseases", type=lambda x: str(x).lower() == "true",
                    help="boolean: rare-disease / orphan-drug studies only")
    ap.add_argument("--who-gene-editing", type=lambda x: str(x).lower() == "true",
                    help="boolean: gene-editing studies only")
    ap.add_argument("--multi-keywords", help="multi_keyword mode: space-separated AND terms")
    ap.add_argument("--keyword", dest="q", help="alias of --q (free-text keyword)")
    ap.add_argument("--source", choices=["who", "chinadrugtrials", "isrctn", "drks", "chictr"],
                    default="who",
                    help="unified endpoint source selector: 'who' (WHO ICTRP, default), "
                         "'chinadrugtrials' (China CDE), or 'isrctn'/'drks'/'chictr' "
                         "(national registries WHO covers, retrievable independently when "
                         "WHO cannot — used by the ct_registry fallback). "
                         "All hit ct-search.coze.site/run, sharing one ICTRP token.")
    # CDE (chinadrugtrials) search fields -- plain strings, mirroring search_cde_workflow.py.
    ap.add_argument("--reg-no", help="CDE registration number (reg_no)")
    ap.add_argument("--indication", help="CDE indication (适应症)")
    ap.add_argument("--case-no", help="CDE case number (case_no)")
    ap.add_argument("--drugs-name", help="CDE drug name (drugs_name)")
    ap.add_argument("--drugs-type", help="CDE drug type enum: 中药/天然药物/化学药物/生物制品")
    ap.add_argument("--appliers", help="CDE applicant / sponsor (appliers)")
    ap.add_argument("--communities", help="CDE communities")
    ap.add_argument("--researchers", help="CDE researchers")
    ap.add_argument("--agencies", help="CDE agencies")
    ap.add_argument("--trial-status", help="CDE trial status enum (11 values)")
    ap.add_argument("--is-advanced-search", action="store_true",
                    help="CDE search mode: treat supplied structured filters as advanced search")
    ap.add_argument("--project-list", help="detail mode: project_list JSON string or path")
    ap.add_argument("--fetch-mode", choices=["list", "detail", "both"],
                    help="(可选) 取数策略：list=仅检索列表(1次调用)；detail=仅下载详情(需 --project-list)；"
                         "both=检索列表后自动下载详情(同一次调用内2次Coze调用、计1次配额)。"
                         "省略时沿用旧逻辑(--mode detail 或 --project-list 触发 detail，否则 search)。")
    ap.add_argument("--auto-confirm", action="store_true",
                    help="--fetch-mode both 且列表 >100 条时，跳过成本护栏、强制拉取详情")
    ap.add_argument("--max", type=int, help="max records (converted to max_pages)")
    ap.add_argument("--max-pages", type=int, help="WHO max_pages (default 50)")
    ap.add_argument("--token", help="Bearer token (else env CT_REGISTRY_COZE_TOKEN / embedded blob in config/keys.py)")
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    ap.add_argument("--out", default="ictrp_extsvc.json")
    ap.add_argument("--demand-id",
                    help="检索需求标识：同一 demand_id 当日只计 1 次配额（WHO+CDE 合并、"
                         "关键词微调/重复检索均不重复计数）。省略则每次调用各计 1 次。")
    # CDE 静默降级参数（中文检索 0 条时自动补发英文检索，由 Coze workflow 处理）
    ap.add_argument("--silent-fallback", action="store_true",
                    help="CDE 静默降级：中文检索 0 条时自动补发英文检索（需配合 --fallback-keyword）")
    ap.add_argument("--fallback-keyword",
                    help="CDE 静默降级关键字（通常为中译英），由 Coze workflow 在中文 0 条时自动补发")
    ap.add_argument("--run", action="store_true",
                    help="actually POST (default = preview only, no network)")
    ap.add_argument("--no-stream", dest="stream", action="store_false", default=True,
                    help="强制同步 /run（默认走 /stream_run 流式；流式取不到结果会自动回退同步，此开关用于完全跳过流式）")
    ap.add_argument("--query-origin",
                    help="调用发起来源标识（sha256:<64 hex>），用于审计/限流；由技能安装设备（本机）"
                         "生成并携带，禁止由 Coze 服务器生成（ct-base §8.6）。未显式传参时自动计算注入")
    ap.add_argument("--timeout", type=int, default=600,
                    help="Coze 检索等待超时上限（秒），默认 600 = 10 分钟；超时退出时返回值 is_timeout=True")
    args = ap.parse_args()

    # ct-base §8.6：query_origin 必须由技能安装设备（本机）生成并携带，
    # 禁止由 Coze 服务器兜底生成（容器 hostname 漂移，且标识非来源机器）。
    if not args.query_origin:
        args.query_origin = _compute_query_origin()

    api_source = API_SOURCE.get(args.source, "who")
    fetch_mode = _resolve_fetch_mode(args)
    token = get_token(args.token)
    endpoint = args.endpoint or DEFAULT_ENDPOINT
    source_label = RECORD_SOURCE.get(args.source, "ICTRP")

    # ---- resolve payload(s) per fetch strategy ----
    list_payload = None
    detail_payload = None
    if fetch_mode == "detail":
        if not args.project_list:
            sys.exit("[ictrp-extsvc][ERROR] --fetch-mode detail 需要 --project-list"
                     "（列表输出文件或 project_list JSON 字符串）。")
        detail_payload = build_payload(args)   # builds mode=detail from --project-list
    else:
        list_payload = build_payload(args)     # search/combined/multi_keyword
        if fetch_mode == "both":
            detail_payload = {"mode": "detail", "source": api_source, "project_list": None}

    # P1-4 (2026-08-12, extended 2026-08-12): breadth advisory for ANY bare-keyword
    # search (no structured filters) on the unified Coze gateway — not just WHO. A bare
    # wide keyword may hit the ~5-min wall and return only part of the results. Tier-2
    # broad disease classes (diabetes/hypertension/...) also warn here but do NOT abort.
    _no_struct = (args.mode in (None, "search") and not args.multi_keywords
                  and not any(getattr(args, f, None) for f in
                              ("who_title", "who_condition", "who_intervention", "who_sponsor",
                               "who_country", "who_phase", "who_secondary_id"))
                  and " " not in (args.q or ""))   # 多词 q 会走 multi_keyword，不告警
    if fetch_mode in ("list", "both") and _no_struct:
        reasons = []
        if args.q and is_soft_broad(args.q):
            reasons.append(f"关键词 {args.q!r} 属宽病类（如糖尿病/高血压），单独检索可能仅取回部分结果")
        if args.source == "who":
            reasons.append("WHO 纯关键词检索可能命中统一网关 ~5 分钟硬墙")
        if reasons:
            print("[ictrp-extsvc][BREADTH] " + "；".join(reasons)
                  + "。建议改用 --mode multi_keyword（多词 AND 缩窄，最快）或 --mode combined "
                    "（who_* 字段级 AND 过滤，更准），或收窄/组合关键词。"
                    "详见 README 「数据量与超时」一节。")
    if not args.run:
        preview_payload = list_payload or detail_payload
        print_preview(preview_payload, token, args.out, endpoint)
        if fetch_mode == "both":
            print(f"[ictrp-extsvc][PREVIEW] --fetch-mode both：列表返回后将自动拉取详情到 "
                  f"{_detail_out_path(args.out)}（同一次调用内、计 1 次配额）。")
        return
    # §5.212 outbound authorization gate (before quota check + network I/O).
    if not _check_outbound_authorization(endpoint):
        return
    # Daily shared-resource guard: caps WHO/CDE (all shared-endpoint) retrieval at 100/day,
    # charged ONCE per demand_id (WHO+CDE merged; tweaks/repeats within a demand are free).
    # For --fetch-mode both, list+detail share the SAME demand_id -> counted as 1 call.
    allowed, _remaining, guard_msg = usage_guard.check(
        demand_id=args.demand_id or os.environ.get("CT_DEMAND_ID"), source_label=source_label)
    print(guard_msg)
    if not allowed:
        return

    if fetch_mode == "detail":
        run(detail_payload, token, args.out, args.timeout, endpoint, source_label, args.stream)
    elif fetch_mode == "list":
        run(list_payload, token, args.out, args.timeout, endpoint, source_label, args.stream)
    else:  # both: search, then auto-detail from the returned project_list
        run(list_payload, token, args.out, args.timeout, endpoint, source_label, args.stream)
        pl_raw = _read_project_list_raw(args.out)
        if not pl_raw:
            print("[ictrp-extsvc][BOTH] 列表未返回可用的 project_list，跳过自动详情。")
        else:
            n = _read_record_count(args.out)
            if isinstance(n, int) and n > BOTH_DETAIL_LIMIT and not args.auto_confirm:
                print(f"[ictrp-extsvc][BOTH-SKIP] 列表 {n} 条 > {BOTH_DETAIL_LIMIT}，"
                      f"自动详情耗时长/易超时，默认跳过（加 --auto-confirm 强制拉取）。")
            else:
                detail_payload["project_list"] = pl_raw
                dout = _detail_out_path(args.out)
                run(detail_payload, token, dout, args.timeout, endpoint, source_label, args.stream)
                print(f"[ictrp-extsvc][BOTH] 列表+详情完成：列表 {args.out}；详情 {dout}。")


if __name__ == "__main__":
    main()
