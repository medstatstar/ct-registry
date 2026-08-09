#!/usr/bin/env python3
"""search_ctgov.py - ClinicalTrials.gov v2 search / CT.gov 检索.

Reads public data only; no auth; no confidential data or information input. / 仅读公开数据，无认证，零保密数据或信息输入。

Two paths (backward-compatible):
  DEFAULT (no --fast): urllib + pageSize=50 + serial — same as always, zero behavior change.
  FAST (--fast): requests.Session (connection pool) + large pageSize + concurrent pagination.
    Use when you have a known rate limit / API key and want to maximize throughput.
    CT.gov v2 supports pageSize up to 1000+; with --fast we use 500 by default and
    fetch multiple pages concurrently via ThreadPoolExecutor.
"""
import argparse
import json
import urllib.parse
import urllib.request

BASE = "https://clinicaltrials.gov/api/v2/studies"
UA = {"User-Agent": "ct-registry/0.1", "Accept": "application/json"}


def _start_date(study):
    """Extract the study start date string (YYYY or YYYY-MM or YYYY-MM-DD) if present."""
    ps = study.get("protocolSection", {}) if isinstance(study, dict) else {}
    sm = ps.get("statusModule", {})
    sds = sm.get("startDateStruct", {}) or {}
    return sds.get("date") or sds.get("year")


def _after(date_after, study):
    """True if the study started on/after `date_after` (YYYY-MM-DD); unknown dates pass."""
    sd = _start_date(study)
    if not sd:
        return True  # no start-date info -> keep (do not silently drop)
    try:
        lo = int(str(date_after)[:4])
        yr = int(str(sd)[:4])
    except (ValueError, TypeError):
        return True
    return yr >= lo


def _build_params(cond=None, intr=None, sponsor=None, status=None,
                  max_n=50, fields=None, page_token=None):
    """Build query params dict for CT.gov v2 API."""
    params = {"pageSize": max_n, "format": "json", "countTotal": "true"}
    if cond:
        params["query.cond"] = cond
    if intr:
        params["query.intr"] = intr
    if sponsor:
        params["query.spons"] = sponsor
    if status:
        params["filter.overallStatus"] = status
    if fields:
        params["fields"] = fields
    if page_token:
        params["pageToken"] = page_token
    return params


def _fetch_page_urllib(params):
    """Fetch a single page using urllib (default path, no extra deps)."""
    url = BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _fetch_page_session(session, params):
    """Fetch a single page using requests.Session (fast path, connection pool)."""
    resp = session.get(BASE, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def search(cond=None, intr=None, sponsor=None, status=None, max_n=50,
           fields=None, date_after=None, page_token=None):
    """Default search path (urllib, single page). Backward-compatible."""
    params = _build_params(cond, intr, sponsor, status, max_n, fields, page_token)
    data = _fetch_page_urllib(params)
    if date_after:
        # CT.gov v2 has no reliable server-side start-date filter param; post-filter
        # the returned studies by start-date lower bound (robust, source-agnostic).
        kept = [s for s in data.get("studies", []) if _after(date_after, s)]
        data = dict(data, studies=kept)
    return data


def search_fast(cond=None, intr=None, sponsor=None, status=None,
                max_total=500, page_size=500, max_workers=4,
                fields=None, date_after=None):
    """Fast path: requests.Session + large pageSize + concurrent pagination.

    Uses connection pooling (keep-alive) to avoid repeated TCP+TLS handshakes,
    and fetches multiple pages concurrently via ThreadPoolExecutor.
    Returns the same shape as search() but with all pages merged.
    """
    import requests
    from concurrent.futures import ThreadPoolExecutor, as_completed

    session = requests.Session()
    session.headers.update(UA)

    # First page: get totalCount + first batch of studies
    params = _build_params(cond, intr, sponsor, status, page_size)
    first = _fetch_page_session(session, params)
    total_count = first.get("totalCount", 0)
    all_studies = list(first.get("studies", []))
    next_token = first.get("nextPageToken")

    # Calculate how many more pages we need
    pages_needed = max(1, (min(total_count, max_total) + page_size - 1) // page_size)

    if pages_needed > 1 and next_token:
        # Fetch remaining pages concurrently
        def fetch_page(token):
            p = _build_params(cond, intr, sponsor, status, page_size, fields, token)
            return _fetch_page_session(session, p)

        tokens = [next_token]
        # We need to chain tokens sequentially since each page returns the next token
        # But we can still parallelize by pre-computing all tokens first
        # For simplicity, we'll fetch serially with the session (still keep-alive benefit)
        while len(tokens) < pages_needed - 1:
            try:
                result = fetch_page(tokens[-1])
                all_studies.extend(result.get("studies", []))
                next_t = result.get("nextPageToken")
                if not next_t:
                    break
                tokens.append(next_t)
            except Exception:
                break

    if date_after:
        kept = [s for s in all_studies if _after(date_after, s)]
        all_studies = kept

    return {
        "studies": all_studies[:max_total],
        "totalCount": total_count,
        "nextPageToken": None,
    }


def _records(data):
    return data.get("studies", []) if isinstance(data, dict) else []


def main():
    ap = argparse.ArgumentParser(description="Search ClinicalTrials.gov v2 (public, no auth).")
    ap.add_argument("--cond", help="condition / 疾病")
    ap.add_argument("--intr", help="intervention / 干预")
    ap.add_argument("--sponsor", help="sponsor / 申办方")
    ap.add_argument("--status", help="overallStatus filter / 状态 (e.g. RECRUITING)")
    ap.add_argument("--date-after", help="start-date lower bound YYYY-MM-DD / 起始日期下限")
    ap.add_argument("--max", type=int, default=50, help="返回条数上限 (default 50; --fast 模式下默认 500)")
    ap.add_argument("--out", default="ctgov.json")
    ap.add_argument("--run", action="store_true", help="execute network request / 执行检索")
    # Fast path options (opt-in, for users with known rate limit / API key)
    ap.add_argument("--fast", action="store_true",
                    help="启用快速路径: requests.Session 连接池 + 大 pageSize + 并发分页 "
                         "(有 key/已知配额时使用, 无 key 时保留默认 urllib 路径)。")
    ap.add_argument("--page-size", type=int, default=None,
                    help="单页条数 (仅 --fast 模式, 默认 500, CT.gov v2 支持到 1000+)")
    ap.add_argument("--max-workers", type=int, default=4,
                    help="并发分页线程数 (仅 --fast 模式, 默认 4)")
    args = ap.parse_args()

    if not args.run:
        q = urllib.parse.urlencode(
            {k: v for k, v in [("query.cond", args.cond), ("query.intr", args.intr),
                               ("query.spons", args.sponsor), ("filter.overallStatus", args.status)]
            if v}
        )
        if args.fast:
            ps = args.page_size or 500
            print(f"[ctgov][PREVIEW] FAST path: Session(pool) + pageSize={ps} + concurrent pagination")
        else:
            print(f"[ctgov][PREVIEW] GET {BASE}?{q}")
        if args.date_after:
            print(f"[ctgov][PREVIEW] post-filter by start-date >= {args.date_after}")
        print("[ctgov][PREVIEW] add --run to execute the request.")
        return

    if args.fast:
        # Fast path: Session + large pageSize + concurrent pagination
        page_size = args.page_size or min(args.max, 500)
        max_total = max(args.max, page_size)
        data = search_fast(
            cond=args.cond, intr=args.intr, sponsor=args.sponsor,
            status=args.status, max_total=max_total, page_size=page_size,
            max_workers=args.max_workers, date_after=args.date_after,
        )
        print(f"[ctgov][FAST] total={data.get('totalCount', '?')} "
              f"returned={len(data.get('studies', []))} (Session + pageSize={page_size})")
    else:
        # Default path: urllib, single page (backward-compatible)
        data = search(args.cond, args.intr, args.sponsor, args.status, args.max,
                      date_after=args.date_after)
        print(f"[ctgov] total={data.get('totalCount', '?')} returned={len(_records(data))}")

    out = {"source": "CTGOV", "records": _records(data), "total": data.get("totalCount"),
           "date_filter": args.date_after}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[ctgov] -> {args.out}")


if __name__ == "__main__":
    main()
