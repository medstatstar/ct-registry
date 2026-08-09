#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scenario10.py - ct-registry 真实联网 10 案例（从简单到复杂，覆盖各种场景）。

与 regression_real.py 的区别：
  regression_real.py 绕过主编排、直连底层 search_*.py，验证的是「每个数据源单独能取到数」。
  本套件全部走顶层编排 ct_registry.py 的 CLI，验证的是「主编排各分支在真实联网下的行为」：
  keyword 门 / confirm 门 / 覆盖注入 / WHO primary + covered-skip / CDE 双语合并 /
  PubChem 富集 / 多源聚合去重 / fallback-covered 全源桥接 / detail / 过宽保护。

10 个案例（简单 -> 复杂）：
  C1  CT.gov 最小冒烟（仅 cond）                      [Tier-1, 纯 HTTP]
  C2  CT.gov 多过滤（cond+intr+status+sponsor）        [Tier-1]
  C3  CT.gov 时间窗（--min-year）                      [Tier-1]
  C4  CT.gov + PubChem 富集（drug intent）             [Tier-1 + enrich]
  C5  EU-CTR 直连（HTML 解析）                         [Tier-1]
  C6  WHO ICTRP primary（covered-skip CT.gov）         [Tier-2 Coze]
  C7  CDE 双语自动合并（zh 关键字 -> zh+en 两次检索）    [Tier-2 Coze]
  C8  多源聚合去重（CT.gov+EU-CTR+CDE+ChiCTR，无 WHO）  [混合]
  C9  6 源独立检索桥接（+ISRCTN/DRKS，无 WHO）           [混合全源]
  C10 高级组合：keyword 门停止(控制流) + CDE 过宽中止(控制流)
      + --kw-en/--kw-zh 覆盖注入 + --with-detail 联网    [控制流 + Tier-2]

注1：主编排 ct_registry.py 默认把中间 .md/.json 移入 out_dir/_unsaved/，仅保留 .xlsx。
     本驱动通过 find_artifact() 在 out_dir 与 _unsaved/ 双路径定位中间产物。
注2：WHO primary 时 covered 源（CT.gov/EU-CTR/ISRCTN/DRKS/ChiCTR）被跳过是**设计行为**
     （fallback 策略），在 C6 验证；C9 因此不带 --with-ictrp，改为 6 源全部独立检索。

配额：CT_USAGE_CONFIG 指向隔离计数文件（真实联网照常，但不污染真实 usage.json）。
用法：  C:/Tools/anaconda3/python.exe tests/scenario10.py [--cases 1,3,10]
结果：  tests/results/scenario10_<date>.json  +  每 case 日志 scenario10_<date>_cN.log
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))          # tests/
SKILL = os.path.dirname(HERE)                               # ct-registry/
SCRIPTS = os.path.join(SKILL, "scripts")
RESULTS = os.path.join(HERE, "results")
RUNS = os.path.join(HERE, "scenario10_run")                 # case 产物目录
DATE = datetime.date.today().isoformat()
DEMAND_BASE = f"scenario10-{DATE}"
PY = "C:/Tools/anaconda3/python.exe"
# 隔离配额计数（真实联网不受影响；DAILY_LIMIT 发布值为 100）
os.environ["CT_USAGE_CONFIG"] = os.path.join(RESULTS, "scenario10_usage.json")
os.makedirs(RESULTS, exist_ok=True)
os.makedirs(RUNS, exist_ok=True)

BASE = ["--no-expand", "--auto-confirm"]   # C1-C9：绕过 keyword/confirm 门，保证真实联网


def run_case(out_dir, *args, timeout=420):
    """调用主编排 ct_registry.py；返回 (rc, stdout, stderr)。"""
    os.makedirs(out_dir, exist_ok=True)
    cmd = [PY, os.path.join(SCRIPTS, "ct_registry.py"), *args,
           "--out-dir", out_dir, "--run"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           cwd=SCRIPTS, env=dict(os.environ))
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        return 124, (e.stdout or ""), (e.stderr or "") + "\n[TIMEOUT]"


def find_artifact(out_dir, fn):
    """主编排把中间产物移入 _unsaved/；优先 out_dir，其次 _unsaved/。"""
    for base in (out_dir, os.path.join(out_dir, "_unsaved")):
        p = os.path.join(base, fn)
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return p
    return None


def load_json(path):
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def norm_count(out_dir):
    d = load_json(find_artifact(out_dir, "normalized.json"))
    return len(d) if isinstance(d, list) else 0


def agg_sources(out_dir):
    """从 agg_full.json 统计各 source 归一化记录数（无该文件返回 {}）。"""
    a = load_json(find_artifact(out_dir, "agg_full.json"))
    if not isinstance(a, dict):
        return {}
    from collections import Counter
    return dict(Counter(r.get("source") for r in (a.get("records") or [])))


def std_assert(out_dir, rc, se, label, expect_sources=()):
    """公共断言：rc==0 + normalized/agg/report/xlsx 产物齐全。返回 (ok, detail)。"""
    if rc != 0:
        return False, f"rc={rc}\nSTDERR:\n{se[-1200:]}"
    n = norm_count(out_dir)
    if n <= 0:
        return False, "normalized.json 为空（0 记录）"
    missing = [f for f in ("report.xlsx", "agg.json", "report.md")
               if not find_artifact(out_dir, f)]
    if missing:
        return False, f"产物缺失: {missing}"
    srcs = agg_sources(out_dir)
    detail = f"normalized={n} sources={srcs}"
    if expect_sources:
        absent = [s for s in expect_sources if srcs.get(s, 0) == 0]
        if absent:
            return False, f"期望来源缺失: {absent} | {detail}"
    return True, detail


# ---------------------------------------------------------------- 案例定义 ---
def c01_ctgov_min(out):
    rc, so, se = run_case(out, "--cond", "lung cancer", "--max", "10", *BASE)
    ok, det = std_assert(out, rc, se, "C1", expect_sources=("CTGOV",))
    return ok, det


def c02_ctgov_multi(out):
    rc, so, se = run_case(out, "--cond", "breast cancer", "--intr", "trastuzumab",
                          "--status", "RECRUITING", "--sponsor", "Roche",
                          "--max", "10", *BASE)
    ok, det = std_assert(out, rc, se, "C2", expect_sources=("CTGOV",))
    extra = ""
    a = load_json(find_artifact(out, "agg_full.json"))
    recs = (a or {}).get("records") or []
    if recs:
        bad_status = [r for r in recs
                      if r.get("status") and "recruit" not in str(r.get("status")).lower()]
        # CT.gov --sponsor 过滤是「任一申办方含 Roche」，但记录只显示 lead sponsor
        # （协作组/机构主导试验的 lead 可能不是 Roche）——仅报告，不判 FAIL。
        bad_sponsor = [r for r in recs
                       if r.get("sponsor") and "roche" not in str(r.get("sponsor")).lower()]
        extra = (f" | status_mismatch={len(bad_status)} "
                 f"lead_sponsor_not_roche={len(bad_sponsor)}(正常)")
        if len(bad_status) > len(recs) // 2:
            ok = False
    return ok, det + extra


def _yr(r):
    """简化 _reg_year：从 start_date 提取年份（normalize 后字段）。"""
    import re as _re
    m = _re.search(r"(19|20)\d{2}", str(r.get("start_date") or ""))
    return int(m.group()) if m else 0


def c03_ctgov_year(out):
    rc, so, se = run_case(out, "--cond", "chimeric antigen receptor",
                          "--min-year", "2023", "--max", "20", *BASE)
    ok, det = std_assert(out, rc, se, "C3", expect_sources=("CTGOV",))
    # --min-year 走 normalized_filtered.json 过滤产物（normalized.json 是未过滤全集）
    fp = find_artifact(out, "normalized_filtered.json")
    if not fp:
        return False, "normalized_filtered.json 缺失（--min-year 未生效）"
    kept = load_json(fp) or []
    bad = [r for r in kept if _yr(r) < 2023]
    extra = (f" | filtered={len(kept)} pre_2023_in_filtered={len(bad)}")
    if len(kept) == 0:
        return False, "过滤后 0 条（查询词在 2023+ 无结果）" + extra
    if bad:
        ok = False
    return ok, det + extra


def c04_pubchem(out):
    rc, so, se = run_case(out, "--drug", "osimertinib", "--with-pubchem",
                          "--max", "10", *BASE)
    ok, det = std_assert(out, rc, se, "C4", expect_sources=("CTGOV",))
    extra = ""
    if not find_artifact(out, "pubchem.json"):
        ok, extra = False, " | pubchem.json 缺失"
    return ok, det + extra


def c05_euctr(out):
    rc, so, se = run_case(out, "--with-euctr", "--euctr-keyword", "diabetes",
                          "--cond", "diabetes", "--max", "10", *BASE)
    ok, det = std_assert(out, rc, se, "C5", expect_sources=("EUCTR",))
    return ok, det


def c06_who(out):
    rc, so, se = run_case(out, "--with-ictrp", "--ictrp-keyword", "lung cancer",
                          "--cond", "lung cancer", "--max", "10", *BASE)
    ok, det = std_assert(out, rc, se, "C6", expect_sources=("ICTRP",))
    return ok, det


def c07_cde_bilingual(out):
    rc, so, se = run_case(out, "--with-cde", "--cde-keyword", "奥希替尼",
                          "--cond", "lung cancer", "--max", "10", *BASE)
    ok, det = std_assert(out, rc, se, "C7", expect_sources=("CDE",))
    zh = find_artifact(out, "cde_zh.json") is not None
    en = find_artifact(out, "cde_en.json") is not None
    extra = f" | cde_zh={zh} cde_en={en}"
    if not (zh and en):
        ok = False
    return ok, det + extra


def c08_multisource(out):
    rc, so, se = run_case(out, "--with-euctr", "--with-cde", "--with-chictr",
                          "--cde-keyword", "肺癌", "--chictr-keyword", "肺癌",
                          "--cond", "lung cancer", "--intr", "osimertinib",
                          "--max", "10", *BASE)
    ok, det = std_assert(out, rc, se, "C8",
                         expect_sources=("CTGOV", "EUCTR", "CDE", "CHICTR"))
    return ok, det


def c09_full_fallback(out):
    # 6 源独立检索 + 聚合桥接（不含 WHO：WHO primary 时 covered 源被 skip 是设计行为，
    # 已在 C6 验证；此处验证 ISRCTN/DRKS/ChiCTR 等 national registries 全部能独立取数并桥接）
    rc, so, se = run_case(out, "--with-euctr", "--with-cde", "--with-chictr",
                          "--with-isrctn", "--with-drks",
                          "--cde-keyword", "哮喘", "--chictr-keyword", "哮喘",
                          "--isrctn-keyword", "asthma", "--drks-keyword", "asthma",
                          "--cond", "asthma", "--max", "8", *BASE)
    ok, det = std_assert(out, rc, se, "C9",
                         expect_sources=("CTGOV", "EUCTR", "CDE", "CHICTR",
                                         "ISRCTN", "DRKS"))
    return ok, det


def c10_advanced(out):
    """三个子检查：keyword 门停止 / CDE 过宽中止 / 覆盖注入+detail。"""
    notes = []
    # 10a: keyword 门（无 --no-expand、无 --kw-*）-> 应 STOP(rc=0) 且输出菜单，不联网
    outa = os.path.join(out, "10a_gate")
    rc_a, so_a, se_a = run_case(outa, "--cond", "肺癌", "--intr", "奥希替尼",
                                "--max", "5", timeout=120)
    gate_hit = rc_a == 0 and ("kw_gate" in so_a or "确认关键字" in so_a
                              or "关键字体系" in so_a)
    notes.append(f"10a gate rc={rc_a} stop={gate_hit}")
    if rc_a != 0 or not gate_hit:
        return False, "10a keyword 门未按预期停止 | " + notes[-1] + "\n" + so_a[-800:] + se_a[-400:]

    # 10b: CDE 单关键词过宽 -> 应中止 rc=2（不联网，保护共享端点）
    outb = os.path.join(out, "10b_broad")
    rc_b, so_b, se_b = run_case(outb, "--with-cde", "--cde-keyword", "癌症",
                                "--max", "5", *BASE, timeout=120)
    notes.append(f"10b broad rc={rc_b}")
    if rc_b != 2:
        return False, f"10b CDE 过宽应中止(rc=2) 实际 rc={rc_b}\n{so_b[-600:]}{se_b[-600:]}"

    # 10c: --kw-en/--kw-zh 覆盖注入（不走 --no-expand，验证 gate 覆盖路径）
    #     + --with-cde --with-ictrp --with-detail（真实联网 + detail 拉取）
    outc = os.path.join(out, "10c_override_detail")
    rc_c, so_c, se_c = run_case(outc, "--kw-en", "osimertinib", "--kw-zh", "奥希替尼",
                                "--with-cde", "--with-ictrp", "--with-detail",
                                "--cond", "lung cancer", "--max", "5", timeout=480)
    n = norm_count(outc)
    detail_ok = (find_artifact(outc, "cde_detail.json") is not None
                 or find_artifact(outc, "ictrp.json") is not None)
    notes.append(f"10c override+detail rc={rc_c} normalized={n} detail={detail_ok}")
    if rc_c != 0 or n <= 0:
        return False, f"10c 覆盖注入+detail 失败 rc={rc_c}\n{so_c[-1200:]}{se_c[-1200:]}"
    return True, " | ".join(notes)


CASES = [
    (1,  "CT.gov 最小冒烟（仅 cond）", c01_ctgov_min),
    (2,  "CT.gov 多过滤（cond+intr+status+sponsor）", c02_ctgov_multi),
    (3,  "CT.gov 时间窗（--min-year）", c03_ctgov_year),
    (4,  "CT.gov + PubChem 富集（drug intent）", c04_pubchem),
    (5,  "EU-CTR 直连（HTML 解析）", c05_euctr),
    (6,  "WHO ICTRP primary（covered-skip）", c06_who),
    (7,  "CDE 双语自动合并（zh+en）", c07_cde_bilingual),
    (8,  "多源聚合去重（CT.gov+EU-CTR+CDE+ChiCTR）", c08_multisource),
    (9,  "6 源独立检索桥接（CT.gov+EU-CTR+CDE+ChiCTR+ISRCTN+DRKS）", c09_full_fallback),
    (10, "高级组合（keyword 门 + 过宽中止 + 覆盖注入 + detail）", c10_advanced),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", help="comma-separated case numbers")
    args = ap.parse_args()
    sel = {int(x) for x in args.cases.split(",") if x.strip()} if args.cases else None

    results = []
    for num, name, fn in CASES:
        if sel and num not in sel:
            continue
        rec = {"case": num, "name": name, "status": None, "detail": None}
        out = os.path.join(RUNS, f"c{num:02d}")
        os.makedirs(out, exist_ok=True)
        log = os.path.join(RESULTS, f"scenario10_{DATE}_c{num:02d}.log")
        try:
            ok, det = fn(out)
            rec["status"] = "PASS" if ok else "FAIL"
            rec["detail"] = det
        except Exception as e:
            rec["status"] = "FAIL"
            rec["detail"] = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1000:]}"
        print(f"[case{num:02d}] {rec['status']:4s} {name} :: {rec['detail']}")
        results.append(rec)

    n_pass = sum(1 for r in results if r["status"] == "PASS")
    n_fail = sum(1 for r in results if r["status"] == "FAIL")
    summary = {"date": DATE, "suite": "scenario10",
               "demand_base": DEMAND_BASE, "total": len(results),
               "PASS": n_pass, "FAIL": n_fail, "cases": results}
    out_path = os.path.join(RESULTS, f"scenario10_{DATE}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n=== SCENARIO10 {DATE}: PASS={n_pass} FAIL={n_fail} ===")
    print(f"results -> {out_path}")
    if n_fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
