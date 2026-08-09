#!/usr/bin/env python3
"""download_docs.py - Confirm-gated download of trial document PDFs / 确认门控下载.

Why (ct-registry 2026-07-28, v0.3.0)
-------------------------------------
The user wants downloadable documents surfaced as links, and downloaded ONLY after
explicit confirmation. This module:
  * reads normalized records (normalized.json) or aggregated records (agg.json),
  * collects every non-empty `documents` entry ({title, type, url}),
  * PRINTS them (always), and
  * downloads them ONLY when --yes is passed (otherwise preview-only).
Sequential with per-file retries; skips files that already exist.

Note: CDE's workflow detail carries NO attachment URLs (verified), so CDE records
have empty `documents`; real downloadable links come mainly from EU-CTR (populated
by fetch_eu_ctr_docs.py). CT.gov / WHO generally expose no protocol-PDF API either.

Safety: default PREVIEW (lists links, downloads nothing). --yes required to fetch.
"""
import argparse
import json
import os
import re
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}


def _safe_name(s):
    s = re.sub(r"[^\w\-\. ]+", "_", s or "doc")
    return (s.strip().replace(" ", "_")[:120]) or "doc"


def collect(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    # Accept both shapes:
    #   * top-level list of records (normalize.py output: list[dict]), or
    #   * dict wrapping records under `records` / `records_all` (legacy agg.json)
    if isinstance(data, list):
        recs = data
    elif isinstance(data, dict):
        recs = data.get("records") or data.get("records_all") or []
    else:
        recs = []
    out = []
    for r in recs:
        for d in (r.get("documents") or []):
            url = d.get("url")
            if not url:
                continue
            out.append({
                "registry_id": r.get("registry_id"),
                "source": r.get("source"),
                "title": d.get("title"),
                "type": d.get("type"),
                "url": url,
            })
    return out


def main():
    ap = argparse.ArgumentParser(description="Confirm-gated trial-document downloader.")
    ap.add_argument("--in", dest="inp", required=True, help="normalized.json or agg.json")
    ap.add_argument("--out-dir", default="./docs")
    ap.add_argument("--yes", action="store_true",
                    help="actually download (default = preview only, lists links)")
    ap.add_argument("--timeout", type=int, default=60)
    args = ap.parse_args()

    docs = collect(args.inp)
    if not docs:
        print("[download_docs] no downloadable documents found in %s" % args.inp)
        return

    print("[download_docs] %d document link(s) found:" % len(docs))
    for i, d in enumerate(docs, 1):
        print("  %d. [%s] %s | %s (%s)\n     %s"
              % (i, d["source"], d["registry_id"], d["title"], d["type"], d["url"]))

    if not args.yes:
        print("[download_docs][PREVIEW] 默认仅列出链接，不下载（PDF 默认不自动下载，"
              "确认门控）。加 --yes 才真正下载。")
        return

    os.makedirs(args.out_dir, exist_ok=True)
    for i, d in enumerate(docs, 1):
        url = d["url"]
        fn = "%03d_%s_%s_%s.pdf" % (i, d["source"], d["registry_id"] or "na",
                                    _safe_name(d["title"]))
        fp = os.path.join(args.out_dir, fn)
        if os.path.exists(fp):
            print("[download_docs] skip existing %s" % fn)
            continue
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=args.timeout) as r:
                blob = r.read()
            with open(fp, "wb") as f:
                f.write(blob)
            print("[download_docs] saved %s (%d bytes)" % (fn, len(blob)))
        except Exception as e:  # noqa: BLE001 - per-file retry/skip
            print("[download_docs] FAILED %s: %s" % (fn, e))
    print("[download_docs] done -> %s" % args.out_dir)


if __name__ == "__main__":
    main()
