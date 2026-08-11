#!/usr/bin/env python3
"""report.py - Report export / 报告产出 (Markdown + optional JSON/PNG)."""
import argparse
import json
import os
import sys

# Shared ct-base source_guard is resolved from this skill's own scripts/ dir.
# IMPORTANT (2026-08-11): ct-base is NEVER published. Every ct- skill must carry
# its own complete copy. We ONLY resolve from this skill's own `scripts/` dir —
# never fall back to a ct-base sibling.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

try:
    from source_guard import require_source  # BASE.md §17.1 溯源红线
except Exception:  # noqa: BLE001  (vendored copy guaranteed in publish package)
    require_source = None


def md(agg):
    L = []
    L.append("## 📊 Clinical Trial Registry Report / 临床试验注册库检索报告\n")
    L.append(f"- **Total trials / 试验总数**: {agg['total']}\n")
    L.append("### Phase distribution / 分期分布")
    for k, v in agg["phase_dist"].items():
        L.append(f"- {k}: {v}")
    L.append("\n### Status distribution / 状态分布")
    for k, v in agg["status_dist"].items():
        L.append(f"- {k}: {v}")
    L.append("\n### Top sponsors / 主要申办方")
    for k, v in agg["top_sponsors"].items():
        L.append(f"- {k}: {v}")
    L.append("\n### Timeline (start year) / 时间线")
    for k, v in agg["timeline"].items():
        L.append(f"- {k}: {v}")
    L.append("\n### Competitor landscape / 竞品格局 (适应症 → 申办方数)")
    for k, v in agg["competitor_map"].items():
        L.append(f"- {k}: {v} sponsors")
    # De-duplication summary (跨库去重)
    ds = agg.get("dedup_summary")
    if ds:
        L.append("\n### De-duplication / 跨库去重 (自建桥接：UTN/TRN 注册号归一 + 模糊匹配)")
        L.append(f"- 原始记录 / raw records: {ds['raw_total']}")
        L.append(f"- 去重后唯一试验 / unique trials: {ds['deduped_total']}")
        L.append(f"- 移除重复 / removed duplicates: {ds['removed']}")
        L.append(f"- 跨库重复组 / cross-source groups: {ds['cross_source_groups']}")
    L.append("\n> 数据来源：公开注册库（CT.gov / CDE / ChiCTR / EU CTR / ISRCTN / DRKS / WHO ICTRP）。输出仅供参考，非监管提交文件。")
    # --- Per-record section: homepage links + downloadable documents ---
    recs = agg.get("records") or []
    # Anti-hallucination (BASE.md §17.1): every emitted record must carry a
    # traceable source. The canonical registry homepage `url` is mapped to
    # `source_quote` so registry-origin records auto-verify; only records with
    # NO url are flagged "⚠️ 待核实". We deliberately use require_source ONLY
    # (not guard_records' assert_no_fabrication): retrieval legitimately returns
    # drugs/targets outside the input whitelist (e.g. search NSCLC -> Osimertinib),
    # so the fabrication hard-gate would false-kill valid results.
    if recs and require_source is not None:
        for r in recs:
            if not r.get("source_quote") and r.get("url"):
                r["source_quote"] = r["url"]
        recs, n_unverified = require_source(recs, quote_key="source_quote",
                                            status_key="verification")
        if n_unverified:
            L.append(f"\n> ⚠️ {n_unverified} 条记录缺少可溯源的首页链接，已标记「待核实」，请人工复核其来源后再引用。")
    if recs:
        L.append("\n### Records / 逐条记录（含首页链接与可下载文档）")
        L.append(f"- 共 {len(recs)} 条 primary 记录；下表给出每条的注册库首页链接，"
                 "以及可下载的详细文档（PDF 等）链接。")
        for r in recs:
            rid = r.get("registry_id") or r.get("title") or "?"
            src = r.get("source") or "?"
            title = (r.get("title") or "")[:80]
            status = r.get("status") or ""
            phase = r.get("phase") or ""
            url = r.get("url")
            link = f"[首页]({url})" if url else "首页: (无)"
            docs = r.get("documents") or []
            doc_line = ""
            if docs:
                doc_line = "；下载: " + ", ".join(
                    f"[{d.get('title') or 'doc'}]({d.get('url')})" for d in docs)
            else:
                if src == "CDE":
                    doc_line = "；附件: CDE 公示平台详情页可手动下载（自动化受 WAF 限制，无直链）"
            flag = " ⚠️ 待核实" if r.get("needs_verification") else ""
            L.append(f"- **{rid}** [{src}] {title} — {status}/{phase} — {link}{doc_line}{flag}")
        # Document manifest summary (where downloadable links exist)
        with_docs = [r for r in recs if r.get("documents")]
        if with_docs:
            L.append(f"\n> 可下载文档来源：{len(with_docs)} 条记录含下载链接"
                     f"（主要来自 EU-CTR）。用 `--download-docs` 确认后批量下载。")
        else:
            L.append("\n> 本次结果无可自动下载的文档直链（CDE 工作流不返回附件 URL；"
                     "CT.gov/WHO 亦无协议 PDF API）。如需 CDE 原文，请到其公示平台手动下载。")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", default="report.md")
    ap.add_argument("--json-out")
    ap.add_argument("--png")
    args = ap.parse_args()
    with open(args.inp, encoding="utf-8") as f:
        agg = json.load(f)
    text = md(agg)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"[report] wrote {args.out}")
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(agg, f, ensure_ascii=False, indent=2)
    if args.png:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            keys = list(agg["phase_dist"].keys())
            vals = list(agg["phase_dist"].values())
            plt.figure(figsize=(6, 4))
            plt.bar([str(k) for k in keys], vals)
            plt.title("Phase distribution")
            plt.xticks(rotation=45, ha="right")
            plt.tight_layout()
            plt.savefig(args.png, dpi=120)
            print(f"[report] wrote {args.png}")
        except Exception as e:
            print(f"[report] PNG skipped: {e}")


if __name__ == "__main__":
    main()
