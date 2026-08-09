#!/usr/bin/env python3
"""search_eu_ctr.py - EU Clinical Trials Register (legacy EudraCT) search / EU-CTR 检索.

Why this approach (verified 2026-07-24):
  The legacy EU Clinical Trials Register (clinicaltrialsregister.eu) has NO clean REST
  API. The search page (ctr-search/search?query=...) returns server-rendered HTML whose
  results live in `<table class="result">` blocks, each carrying the EudraCT number
  (checkbox value `YYYY-NNNNNN-NN`), title (link), and status. We parse that HTML with
  BeautifulSoup -> no browser, no API key, fully pure-HTTP. This is the "Tier 1 direct
  connect" path: avoid the ICTRP portal, take the freshest fields ourselves.

  NOTE: the NEW CTIS (euclinicaltrials.eu, post-2022 trials) requires OAuth2 and is NOT
  covered here; it would be a separate external-service source. This module covers the
  legacy EudraCT register (2004-2022+ pharma trials), which is the bulk of EU drug trials.

Reads public data only; no auth; no confidential data or information input.
"""
import argparse
import json
import re
import urllib.parse
import urllib.request

BASE = "https://www.clinicaltrialsregister.eu/ctr-search/search"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}

EUCTR_RE = re.compile(r"\b(\d{4}-\d{6}-\d{2})\b")


def _fetch_html(query, max_n):
    params = {"query": query, "numberResults": max_n}
    url = BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        return url, r.read().decode("utf-8", "replace")


def _parse(html):
    """Extract result rows from the server-rendered search HTML.

    Each `<table class="result">` block carries labelled fields, e.g.
      EudraCT Number: 2010-023457-11
      Sponsor Protocol Number: S52798
      Start Date * : 2011-02-15
      Sponsor Name: UZ Leuven
      Full Title: Immune regulation and timing of chemotherapy ...
      Medical condition: advanced/recurrent ovarian and endometrial cancer
    We pull the fields we need with labelled regexes (tolerant of missing ones).
    """
    records = []
    for block in re.findall(r"<table class=\"result\">(.*?)</table>", html, re.S):
        txt = re.sub(r"<[^>]+>", " ", block)
        txt = re.sub(r"\s+", " ", txt)
        m = re.search(r"EudraCT Number:\s*(\d{4}-\d{6}-\d{2})", txt)
        ct_number = m.group(1) if m else None
        if not ct_number:
            continue
        title = None
        mt = re.search(r"Full Title:\s*(.+?)(?=\s*Medical condition:|\s*Disease:|\s*Sponsor Name:|\s*Record|\s*Study design|$)", txt)
        if mt:
            title = mt.group(1).strip()
        sponsor = None
        ms = re.search(r"Sponsor Name:\s*(.+?)(?=\s*Full Title:|\s*Medical condition:|\s*Disease:|\s*Record|$)", txt)
        if ms:
            sponsor = ms.group(1).strip().rstrip(".")
        start = None
        mst = re.search(r"Start Date\s*[*]?\s*:\s*(\d{4}-\d{2}-\d{2})", txt)
        if mst:
            start = mst.group(1)
        cond = None
        mc = re.search(r"Medical condition:\s*(.+?)(?=\s*Disease:|\s*Version SOC|$)", txt)
        if mc:
            cond = mc.group(1).strip()
        status = None
        mstt = re.search(r"(Authorised|Completed|Ongoing|Recruiting|Not Authorised|"
                         r"Terminated|Suspended|Closed|Otherwise)", txt)
        if mstt:
            status = mstt.group(1)
        records.append({
            "ctNumber": ct_number,
            "title": title,
            "ctStatus": status,
            "phase": None,
            "conditions": [cond] if cond else [],
            "interventions": [],
            "sponsor": sponsor,
            "startDateEU": start,
            "endDateEU": None,
            "countries": [],
        })
    return records


def main():
    ap = argparse.ArgumentParser(description="Search EU Clinical Trials Register (legacy EudraCT), pure HTTP.")
    ap.add_argument("--q", help="free-text query / 检索词")
    ap.add_argument("--max", type=int, default=50)
    ap.add_argument("--out", default="eu_ctr.json")
    ap.add_argument("--run", action="store_true", help="execute network request / 执行检索")
    args = ap.parse_args()

    if not args.run:
        url = BASE + "?" + urllib.parse.urlencode({"query": args.q or "", "numberResults": args.max})
        print(f"[eu_ctr][PREVIEW] GET {url}")
        print("[eu_ctr][PREVIEW] add --run to execute the request.")
        return

    if not args.q:
        print("[eu_ctr][ERROR] --q is required when --run.")
        return

    url, html = _fetch_html(args.q, args.max)
    records = _parse(html)
    out = {"source": "EUCTR", "records": records, "total": len(records), "query_url": url}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[eu_ctr] parsed {len(records)} result rows -> {args.out}")


if __name__ == "__main__":
    main()
