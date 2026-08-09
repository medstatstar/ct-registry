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
  CDE/) -> ct-searchcde.coze.site/run is retained as a FALLBACK reference only.

Modes (`mode` field, required):
  search        - free-text `keyword` query (structured WHO fields not used)
  combined      - structured `who_*` filters (+ optional `keyword`)
  multi_keyword - multi_keywords (space separated, intersect)
  detail        - fetch project details from a project_list JSON string

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

# Reuse the shared external-service token machinery (config/keys.py, XOR+base64 embedded; no .dat).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extsvc_client import (get_token, _status_guidance, _check_outbound_authorization)
import usage_guard  # daily shared-resource call cap (100/day)

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
# archived under CDE/) -> ct-searchcde.coze.site/run is a FALLBACK kept for reference only.
TOKEN_SOURCE = "ICTRP"


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
                if isinstance(d, list):
                    pl = d  # top-level array of records -> use directly
                elif isinstance(d, dict):
                    # Prefer project_list_raw (wrapped {projects:[{project_id}]} string
                    # preserved by a prior LIST call) so the endpoint can resolve details;
                    # fall back to project_list / records (6-field summary) if absent.
                    pl = d.get("project_list_raw") or d.get("project_list") or d.get("records") or pl
                else:
                    pl = d
            except Exception:
                pass
        if isinstance(pl, (list, dict)):
            pl = json.dumps(pl, ensure_ascii=False)
        return {"mode": "detail", "source": api_source, "project_list": pl}

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

    # mode selection
    structured = [k for k in fields if k != "keyword"]
    if args.mode == "multi_keyword" or args.multi_keywords:
        mode = "multi_keyword"
        fields["multi_keywords"] = args.multi_keywords or args.q
    elif args.mode:
        mode = args.mode
    elif structured:
        mode = "combined"
    else:
        mode = "search"

    payload = {"mode": mode, "source": api_source}
    payload.update(fields)
    if args.max_pages:
        payload["max_pages"] = args.max_pages
    elif args.max:
        payload["max_pages"] = max(1, (args.max + 9) // 10)
    return payload


def _build_cde_payload(args, api_source):
    # ---- search / combined / multi_keyword (China CDE via unified endpoint,
    #      source="chinadrugtrials") ----
    # Mirrors the VERIFIED CDE workflow contract (search_cde_workflow.py) but routed
    # through the unified endpoint. Plain STRING fields; OMIT unused (do NOT send "").
    fields = {}
    if args.q:
        fields["keyword"] = args.q
    for cli, field in [("reg_no", "reg_no"), ("indication", "indication"),
                       ("case_no", "case_no"), ("drugs_name", "drugs_name"),
                       ("drugs_type", "drugs_type"), ("appliers", "appliers"),
                       ("communities", "communities"), ("researchers", "researchers"),
                       ("agencies", "agencies"), ("trial_status", "trial_status")]:
        v = getattr(args, cli, None)
        if v:
            fields[field] = v
    adv_fields = [f for f in fields if f != "keyword"]
    if args.mode == "multi_keyword" or args.multi_keywords:
        mode = "multi_keyword"
        fields["multi_keywords"] = args.multi_keywords or args.q
    elif args.mode:
        mode = args.mode
    else:
        mode = "search"
    # Mirror the VERIFIED standalone CDE contract: in `search` mode, advanced filter
    # fields are sent as an advanced (field-filtered) search via is_advanced_search.
    # `combined` mode is only used when the caller explicitly passes --mode combined
    # (ct_registry.py --cde-mode combined) and ignores is_advanced_search.
    if mode == "search" and (getattr(args, "is_advanced_search", False) or adv_fields):
        fields["is_advanced_search"] = True
    payload = {"mode": mode, "source": api_source}
    payload.update(fields)
    if args.max_pages:
        payload["max_pages"] = args.max_pages
    elif args.max:
        payload["max_pages"] = max(1, (args.max + 9) // 10)
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
    }
    if not _write_out_json(out, out_obj):
        return None
    print(f"[ictrp-extsvc] {len(records)} records -> {out} "
          f"(total_count={out_obj['total']})")
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
            r = requests.get(status_url, headers=headers, timeout=10)
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


def run(payload, token, out, timeout, endpoint, source_label):
    out = _resolve_out_path(out)
    import requests  # lazy import; only needed when actually running
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        print("[ictrp-extsvc][WARN] no token -> endpoint returns 401 (Bearer required)")

    # ===== 阶段 1：提交（应毫秒级返回 run_id；用短超时，避免卡在网关）=====
    try:
        submit_resp = requests.post(endpoint, headers=headers, json=payload, timeout=30)
    except requests.exceptions.Timeout:
        # 提交本身超时极罕见（异步 /run 只做 fire-and-forget）；按原超时逻辑降级
        _write_timeout_ictrp(out, source_label, timeout, "submit")
        return
    except requests.RequestException as e:
        sys.exit(f"[ictrp-extsvc][ERROR] request failed: {e}")

    # 探测响应形态：异步协议返回 {status:accepted, run_id} → 轮询；否则按同步协议
    try:
        submit_data = submit_resp.json()
    except Exception:
        submit_data = {}

    if submit_data.get("status") == "accepted" and submit_data.get("run_id"):
        _run_async_poll_ictrp(source_label, endpoint, token, submit_data["run_id"], out, timeout, payload)
        return

    # ===== 同步协议分支（Coze 端未部署 P4 时走这里，逻辑同原版）=====
    print(f"[ictrp-extsvc] HTTP {submit_resp.status_code}")
    guide = _status_guidance(submit_resp.status_code)
    if guide:
        print(f"[ictrp-extsvc][GUIDE] {guide}")
    if submit_resp.status_code != 200:
        print(f"[ictrp-extsvc] body: {submit_resp.text[:600]}")
        print("[ictrp-extsvc] no successful response -> output NOT written.")
        return
    try:
        data = submit_resp.json()
    except Exception:
        data = {"raw": submit_resp.text}
    if data.get("error_msg"):
        print(f"[ictrp-extsvc][ERROR-MSG] {data['error_msg']}")
    _parse_response(data, source_label, payload, out, http_status=submit_resp.status_code)


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
    ap.add_argument("--max", type=int, help="max records (converted to max_pages)")
    ap.add_argument("--max-pages", type=int, help="WHO max_pages (default 50)")
    ap.add_argument("--token", help="Bearer token (else env CT_REGISTRY_COZE_TOKEN / embedded blob in config/keys.py)")
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    ap.add_argument("--out", default="ictrp_extsvc.json")
    ap.add_argument("--demand-id",
                    help="检索需求标识：同一 demand_id 当日只计 1 次配额（WHO+CDE 合并、"
                         "关键词微调/重复检索均不重复计数）。省略则每次调用各计 1 次。")
    ap.add_argument("--run", action="store_true",
                    help="actually POST (default = preview only, no network)")
    ap.add_argument("--timeout", type=int, default=600,
                    help="Coze 检索等待超时上限（秒），默认 600 = 10 分钟；超时退出时返回值 is_timeout=True")
    args = ap.parse_args()

    payload = build_payload(args)
    token = get_token(args.token)
    endpoint = args.endpoint or DEFAULT_ENDPOINT
    source_label = RECORD_SOURCE.get(args.source, "ICTRP")
    if not args.run:
        print_preview(payload, token, args.out, endpoint)
        return
    # §5.212 outbound authorization gate (before quota check + network I/O).
    if not _check_outbound_authorization(endpoint):
        return
    # Daily shared-resource guard: caps WHO/CDE (all shared-endpoint) retrieval at 100/day,
    # charged ONCE per demand_id (WHO+CDE merged; tweaks/repeats within a demand are free).
    allowed, _remaining, guard_msg = usage_guard.check(
        demand_id=args.demand_id or os.environ.get("CT_DEMAND_ID"), source_label=source_label)
    print(guard_msg)
    if not allowed:
        return
    run(payload, token, args.out, args.timeout, endpoint, source_label)


if __name__ == "__main__":
    main()
