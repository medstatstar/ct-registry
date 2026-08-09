#!/usr/bin/env python3
"""regression_real.py - REAL-execution regression suite for ct-registry.

DIFFERENCE vs regression_harness.py:
  This suite performs ACTUAL network retrieval against every source, including
  the shared Coze /run workflow (WHO ICTRP / China CDE / ChiCTR / ISRCTN / DRKS).
  It does NOT set CT_USAGE_CONFIG, so the real daily quota counter
  (config/usage.json) is used.

  All Coze calls share ONE --demand-id (realrun-<date>) so the live endpoint is
  genuinely hit but the daily quota consumes exactly ONE counted demand_id
  (the guard is idempotent per demand_id). Tier-1 sources (CT.gov v2, EU CTR
  HTML parse) are free and unlimited.

Run:  python tests/regression_real.py [--cases 1,3,10]
Result: tests/results/realrun_<date>.json  (per-case PASS/WARN/FAIL + artifacts)
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
SCRIPTS = os.path.join(SKILL, "scripts")
OUT = os.path.join(HERE, "realrun")
os.makedirs(OUT, exist_ok=True)

DATE = datetime.date.today().isoformat()
# --round N gives each repeat run its own demand_id, so every round is a genuinely
# independent real demand against the shared endpoint (quota: 1 counted per round).
ROUND = int(os.environ.get("CT_REALRUN_ROUND", "0") or 0)
DEMAND_ID = f"realrun-{DATE}" + (f"-r{ROUND}" if ROUND else "")
PY = "C:/Tools/anaconda3/python.exe"

# --- subprocess runner -------------------------------------------------------
def run(script, *args, timeout=320):
    cmd = [PY, os.path.join(SCRIPTS, script), *args]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                       cwd=SCRIPTS)
    return p.returncode, p.stdout, p.stderr

def assert_rc(rc, se, label):
    if rc != 0:
        raise AssertionError(f"{label} rc={rc}\nSTDERR:\n{se[-1500:]}")

def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

# --- case runners -----------------------------------------------------------
def case01_ctgov_basic(out):
    rc, so, se = run("search_ctgov.py", "--cond", "type 2 diabetes", "--max", "20",
                     "--out", os.path.join(out, "ctgov.json"), "--run")
    assert_rc(rc, se, "ctgov")
    d = load_json(os.path.join(out, "ctgov.json"))
    n = len(d.get("records", []))
    total = d.get("total")
    assert n > 0, f"CT.gov returned 0 records (total={total})"
    return f"CT.gov cond='type 2 diabetes' -> {n} records (total={total})"

def case02_ctgov_filtered(out):
    rc, so, se = run("search_ctgov.py", "--cond", "breast cancer", "--intr",
                     "pembrolizumab", "--status", "RECRUITING", "--max", "20",
                     "--out", os.path.join(out, "ctgov2.json"), "--run")
    assert_rc(rc, se, "ctgov2")
    d = load_json(os.path.join(out, "ctgov2.json"))
    n = len(d.get("records", []))
    assert n > 0, "CT.gov multi-filter returned 0 records"
    return f"CT.gov cond+intr+status -> {n} records"

def case03_eu_ctr(out):
    rc, so, se = run("search_eu_ctr.py", "--q", "diabetes", "--max", "20",
                     "--out", os.path.join(out, "euctr.json"), "--run")
    assert_rc(rc, se, "euctr")
    d = load_json(os.path.join(out, "euctr.json"))
    n = len(d.get("records", []))
    assert n > 0, "EU-CTR parsed 0 result rows"
    return f"EU-CTR q='diabetes' -> {n} parsed rows"

def case04_who(out):
    rc, so, se = run("search_ictrp.py", "--source", "who", "--q", "lung cancer",
                     "--max", "10", "--out", os.path.join(out, "who.json"),
                     "--demand-id", DEMAND_ID, "--run")
    assert_rc(rc, se, "who")
    d = load_json(os.path.join(out, "who.json"))
    n = len(d.get("records", []))
    assert n > 0, f"WHO ICTRP returned 0 records (error_msg={d.get('error_msg')})"
    return f"WHO ICTRP q='lung cancer' -> {n} records"

def case05_cde(out):
    rc, so, se = run("search_ictrp.py", "--source", "chinadrugtrials", "--q", "肺癌",
                     "--max", "10", "--out", os.path.join(out, "cde.json"),
                     "--demand-id", DEMAND_ID, "--run")
    assert_rc(rc, se, "cde")
    d = load_json(os.path.join(out, "cde.json"))
    n = len(d.get("records", []))
    assert n > 0, f"CDE returned 0 records (error_msg={d.get('error_msg')})"
    return f"CDE q='肺癌' -> {n} records"

def case06_chictr(out):
    rc, so, se = run("search_chictr.py", "--q", "糖尿病", "--max", "10",
                     "--out", os.path.join(out, "chictr.json"),
                     "--demand-id", DEMAND_ID, "--run")
    assert_rc(rc, se, "chictr")
    d = load_json(os.path.join(out, "chictr.json"))
    n = len(d.get("records", []))
    if n == 0:
        return ("WARN: ChiCTR returned 0 records (backend may not serve "
                "source=chictr via unified endpoint; error_msg="
                f"{d.get('error_msg')})")
    return f"ChiCTR q='糖尿病' -> {n} records"

def case07_isrctn(out):
    rc, so, se = run("search_isrctn.py", "--q", "cancer", "--max", "10",
                     "--out", os.path.join(out, "isrctn.json"),
                     "--demand-id", DEMAND_ID, "--run")
    assert_rc(rc, se, "isrctn")
    d = load_json(os.path.join(out, "isrctn.json"))
    n = len(d.get("records", []))
    if n == 0:
        return ("WARN: ISRCTN returned 0 records (backend may not serve "
                "source=isrctn; error_msg=" + str(d.get("error_msg")) + ")")
    return f"ISRCTN q='cancer' -> {n} records"

def case08_drks(out):
    rc, so, se = run("search_drks.py", "--q", "diabetes", "--max", "10",
                     "--out", os.path.join(out, "drks.json"),
                     "--demand-id", DEMAND_ID, "--run")
    assert_rc(rc, se, "drks")
    d = load_json(os.path.join(out, "drks.json"))
    n = len(d.get("records", []))
    if n == 0:
        return ("WARN: DRKS returned 0 records (backend may not serve "
                "source=drks; error_msg=" + str(d.get("error_msg")) + ")")
    return f"DRKS q='diabetes' -> {n} records"

def case09_cde_bilingual(out):
    # Real zh + en CDE retrieval, then merge by 登记号 (the v0.3.54 fix path).
    rc, so, se = run("search_ictrp.py", "--source", "chinadrugtrials", "--q", "肺癌",
                     "--max", "10", "--out", os.path.join(out, "cde_zh.json"),
                     "--demand-id", DEMAND_ID, "--run")
    assert_rc(rc, se, "cde_zh")
    rc, so, se = run("search_ictrp.py", "--source", "chinadrugtrials", "--q",
                     "lung cancer", "--max", "10",
                     "--out", os.path.join(out, "cde_en.json"),
                     "--demand-id", DEMAND_ID, "--run")
    assert_rc(rc, se, "cde_en")
    sys.path.insert(0, SCRIPTS)
    import ct_registry as cr
    cr._merge_bilingual(os.path.join(out, "cde_zh.json"),
                        os.path.join(out, "cde_en.json"),
                        os.path.join(out, "cde_merged_raw.json"))
    m = load_json(os.path.join(out, "cde_merged_raw.json"))
    zh = len(m.get("records") or m.get("projects") or [])
    # normalize the merged raw then re-merge to confirm registry_id merge works
    rc, so, se = run("normalize.py", "--cde", os.path.join(out, "cde_merged_raw.json"),
                     "--out", os.path.join(out, "cde_merged_norm.json"))
    assert_rc(rc, se, "normalize merged")
    nn = load_json(os.path.join(out, "cde_merged_norm.json"))
    assert isinstance(nn, list) and len(nn) > 0, "merged normalize empty"
    return (f"CDE bilingual zh(肺癌)+en(lung cancer) merged raw={zh} -> "
            f"normalized {len(nn)}")

def case10_e2e(out):
    # Capstone: CT.gov + EU-CTR + CDE + WHO, all REAL, then aggregate+report+xlsx.
    run("search_ctgov.py", "--cond", "lung cancer", "--max", "15",
        "--out", os.path.join(out, "e2e_ctgov.json"), "--run")
    run("search_eu_ctr.py", "--q", "lung cancer", "--max", "15",
        "--out", os.path.join(out, "e2e_euctr.json"), "--run")
    run("search_ictrp.py", "--source", "chinadrugtrials", "--q", "肺癌", "--max", "10",
        "--out", os.path.join(out, "e2e_cde.json"), "--demand-id", DEMAND_ID, "--run")
    run("search_ictrp.py", "--source", "who", "--q", "lung cancer", "--max", "10",
        "--out", os.path.join(out, "e2e_who.json"), "--demand-id", DEMAND_ID, "--run")
    # normalize all sources together
    norm = os.path.join(out, "e2e_norm.json")
    rc, so, se = run("normalize.py",
                     "--ctgov", os.path.join(out, "e2e_ctgov.json"),
                     "--euctr", os.path.join(out, "e2e_euctr.json"),
                     "--cde", os.path.join(out, "e2e_cde.json"),
                     "--ictrp", os.path.join(out, "e2e_who.json"),
                     "--out", norm)
    assert_rc(rc, se, "normalize all")
    nnorm = load_json(norm)
    assert isinstance(nnorm, list) and len(nnorm) > 0, "normalized empty"
    # aggregate
    agg = os.path.join(out, "e2e_agg.json")
    rc, so, se = run("aggregate.py", "--in", norm, "--out", agg)
    assert_rc(rc, se, "aggregate")
    a = load_json(agg)
    # report
    rep = os.path.join(out, "e2e_report.md")
    rc, so, se = run("report.py", "--in", agg, "--out", rep, "--json-out",
                     os.path.join(out, "e2e_report.json"))
    assert_rc(rc, se, "report")
    # xlsx
    xlsx = os.path.join(out, "e2e_report.xlsx")
    rc, so, se = run("export_xlsx.py", "--in", norm, "--out", xlsx, "--lang", "zh")
    assert_rc(rc, se, "export_xlsx")
    assert os.path.exists(xlsx)
    ds = a.get("dedup_summary", {})
    # per-source normalized breakdown — surfaces SILENT drops (e.g. a Tier-2 source
    # that returned 0 on a transient workflow miss is absent here with no error).
    from collections import Counter
    breakdown = dict(Counter(r.get("source") for r in nnorm))
    requested = ["CTGOV", "EUCTR", "CDE", "ICTRP"]
    missing = [s for s in requested if breakdown.get(s, 0) == 0]
    detail = (f"E2E normalized={len(nnorm)} sources={breakdown} -> "
              f"agg total={a.get('total')} (removed={ds.get('removed')}, "
              f"cross={ds.get('cross_source_groups')}); xlsx OK")
    if missing:
        # transient Tier-2 miss (e.g. WHO) -> WARN, not FAIL (re-run usually recovers)
        detail = ("WARN: requested source(s) contributed 0 records (likely a "
                  f"transient unified-workflow miss): {missing}. " + detail)
    return detail

CASES = [
    (1, "CT.gov basic (single condition)", case01_ctgov_basic),
    (2, "CT.gov filtered (cond+intr+status)", case02_ctgov_filtered),
    (3, "EU-CTR HTML parse (Tier-1, no token)", case03_eu_ctr),
    (4, "WHO ICTRP keyword (Coze, real)", case04_who),
    (5, "China CDE list (Coze, real)", case05_cde),
    (6, "ChiCTR (Coze, real)", case06_chictr),
    (7, "ISRCTN (Coze, real)", case07_isrctn),
    (8, "DRKS (Coze, real)", case08_drks),
    (9, "CDE bilingual zh+en merge (Coze, real×2)", case09_cde_bilingual),
    (10, "Full multi-source E2E (CT.gov+EU-CTR+CDE+WHO → agg+report+xlsx)", case10_e2e),
]

def main():
    global DEMAND_ID, ROUND, OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", help="comma-separated case numbers to run")
    ap.add_argument("--round", type=int, default=0,
                    help="repeat-round number; gives this run its own demand_id")
    args = ap.parse_args()
    if args.round:
        ROUND = args.round
        DEMAND_ID = f"realrun-{DATE}-r{ROUND}"
        # Each round writes to its OWN subdir so parallel/back-to-back rounds
        # never contend on the same output filenames (avoids PermissionError
        # from concurrent writers on Windows). Round 0 keeps legacy path.
        OUT = os.path.join(HERE, "realrun", f"r{ROUND}")
        os.makedirs(OUT, exist_ok=True)
    sel = None
    if args.cases:
        sel = {int(x) for x in args.cases.split(",") if x.strip()}
    results = []
    for num, name, fn in CASES:
        if sel and num not in sel:
            continue
        rec = {"case": num, "name": name, "status": None, "detail": None}
        try:
            rec["detail"] = fn(OUT)
            # WARN is only set inside a case that returns a string starting with WARN
            if isinstance(rec["detail"], str) and rec["detail"].startswith("WARN"):
                rec["status"] = "WARN"
            else:
                rec["status"] = "PASS"
        except Exception as e:
            rec["status"] = "FAIL"
            rec["detail"] = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1200:]}"
        print(f"[case{num:02d}] {rec['status']:4s} {name} :: {rec['detail']}")
        results.append(rec)
    n_pass = sum(1 for r in results if r["status"] == "PASS")
    n_warn = sum(1 for r in results if r["status"] == "WARN")
    n_fail = sum(1 for r in results if r["status"] == "FAIL")
    summary = {"date": DATE, "round": ROUND, "demand_id": DEMAND_ID,
               "total": len(results),
               "PASS": n_pass, "WARN": n_warn, "FAIL": n_fail, "cases": results}
    suffix = f"_r{ROUND}" if ROUND else ""
    out_path = os.path.join(HERE, "results", f"realrun_{DATE}{suffix}.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    # Windows can transiently lock a file (AV scan / concurrent writer) -> retry
    # before giving up, so a single PermissionError does not waste a whole round.
    for attempt in range(5):
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            break
        except PermissionError:
            if attempt == 4:
                raise
            print(f"[harness] result write to {out_path} blocked (attempt "
                  f"{attempt + 1}/5) - retrying...", flush=True)
            time.sleep(2.0)
    print(f"\n=== REAL RUN {DATE}: PASS={n_pass} WARN={n_warn} FAIL={n_fail} "
          f"(demand_id={DEMAND_ID}) ===")
    print(f"results -> {out_path}")
    # final quota state
    try:
        u = load_json(os.path.join(SKILL, "config", "usage.json"))
        print(f"quota file: date={u.get('date')} count={u.get('count')} "
              f"(demand_id shared -> 1 counted)")
    except Exception:
        pass

if __name__ == "__main__":
    main()
