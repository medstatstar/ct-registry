#!/usr/bin/env python3
"""track_diff.py - Local-only trial status change / snapshot diff for ct-registry.

Pure-local: reads two ``normalized.json`` snapshots (each a list of records with
``registry_id`` + canonical ``status``), diffs by NCT / registry_id set, and emits
a ``status_delta`` list. No network is touched.

``track`` writes the current normalized result to ``registry_snapshot.json`` so the
next run can diff against it.

Only the *status* field is compared. Fine wording drift that maps to the same
lifecycle bucket is surfaced as ``spelling_change`` rather than ``status_change``
so legitimate source-spelling churn does not create false-positive deltas.
"""
import argparse
import json
import os
import shutil
import sys

# --- Status equivalence map (coarse lifecycle buckets) -------------------
# Used ONLY for diff comparison: synonymous canonical statuses that should NOT
# be reported as a "real" change. This is intentionally coarser than
# ``normalize.canon_status`` — its sole purpose is to suppress false-positive
# deltas from wording drift across registries.
#
# Grouping rationale (ct-registry P0-A):
#   * RECRUITING / ACTIVE_NOT_RECRUITING / ONGOING / NOT_YET_RECRUITING
#     all mean "the trial is alive / not closed"  -> bucket "ACTIVE".
#     (RECRUITING ≈ ACTIVE 一类: recruiting and active-not-recruiting are both
#      ongoing programmes; a wording flip between them is not a status change.)
#   * COMPLETED stands alone.
#   * TERMINATED / SUSPENDED / WITHDRAWN all mean "closed / no longer enrolling"
#     -> bucket "CLOSED".
#   * UNKNOWN stays its own bucket.
STATUS_EQUIV = {
    "NOT_YET_RECRUITING": "ACTIVE",
    "RECRUITING": "ACTIVE",
    "ACTIVE_NOT_RECRUITING": "ACTIVE",
    "ONGOING": "ACTIVE",
    "COMPLETED": "COMPLETED",
    "TERMINATED": "CLOSED",
    "SUSPENDED": "CLOSED",
    "WITHDRAWN": "CLOSED",
    "UNKNOWN": "UNKNOWN",
}


def _bucket(status):
    """Map a canonical status onto its coarse lifecycle bucket (uppercased)."""
    if status is None:
        return None
    return STATUS_EQUIV.get(str(status).upper(), str(status).upper())


def load_record_status(path):
    """Return ``{registry_id: {"status": canonical, "status_raw": ...}}``.

    Accepts a normalized.json that is either a bare list of records or an object
    carrying a ``records`` list (both shapes exist in this skill's pipelines).
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    recs = data if isinstance(data, list) else data.get("records", [])
    out = {}
    for r in recs:
        rid = r.get("registry_id")
        if not rid:
            continue
        st = r.get("status")
        out[str(rid)] = {
            "status": st,
            "status_raw": r.get("status_raw") or st,
        }
    return out


def diff_snapshots(a_path, b_path):
    """Diff two normalized.json snapshots; return a status_delta report dict."""
    a = load_record_status(a_path)
    b = load_record_status(b_path)
    ka, kb = set(a), set(b)
    added = sorted(kb - ka)
    removed = sorted(ka - kb)
    common = sorted(ka & kb)
    deltas = []
    for rid in added:
        deltas.append({
            "nct": rid, "old_status": None, "new_status": b[rid]["status"],
            "change_type": "added",
        })
    for rid in removed:
        deltas.append({
            "nct": rid, "old_status": a[rid]["status"], "new_status": None,
            "change_type": "removed",
        })
    for rid in common:
        os_ = a[rid]["status"]
        ns_ = b[rid]["status"]
        if os_ == ns_:
            continue
        if _bucket(os_) == _bucket(ns_):
            ct = "spelling_change"
        else:
            ct = "status_change"
        deltas.append({
            "nct": rid, "old_status": os_, "new_status": ns_,
            "change_type": ct,
            "old_bucket": _bucket(os_), "new_bucket": _bucket(ns_),
        })
    return {
        "snapshot_a": a_path,
        "snapshot_b": b_path,
        "n_a": len(ka),
        "n_b": len(kb),
        "added": len(added),
        "removed": len(removed),
        "status_change": sum(1 for d in deltas if d["change_type"] == "status_change"),
        "spelling_change": sum(1 for d in deltas if d["change_type"] == "spelling_change"),
        "status_delta": deltas,
    }


def cmd_diff(a, b, out=None):
    res = diff_snapshots(a, b)
    print(f"[track_diff] A={res['n_a']} NCTs, B={res['n_b']} NCTs")
    print(f"[track_diff] added={res['added']} removed={res['removed']} "
          f"status_change={res['status_change']} spelling_change={res['spelling_change']}")
    for d in res["status_delta"]:
        print(f"  {d['change_type']:<14} {d['nct']}: "
              f"{d['old_status']} -> {d['new_status']}")
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        print(f"[track_diff] wrote {out}")
    return res


def cmd_track(normalized_path, snapshot_path):
    shutil.copy(normalized_path, snapshot_path)
    print(f"[track_diff] snapshot written -> {snapshot_path} "
          f"(copied from {normalized_path})")


def main():
    ap = argparse.ArgumentParser(
        description="Local status diff / snapshot track for ct-registry (no network)")
    ap.add_argument("--diff", nargs=2, metavar=("SNAP_A", "SNAP_B"),
                    help="diff two normalized.json snapshots by NCT set -> status_delta")
    ap.add_argument("--diff-out", help="write the status_delta JSON here")
    ap.add_argument("--track", help="normalized.json path to snapshot as registry_snapshot.json")
    ap.add_argument("--snapshot-out", default="registry_snapshot.json",
                    help="target snapshot path for --track (default registry_snapshot.json)")
    args = ap.parse_args()
    if args.diff:
        cmd_diff(args.diff[0], args.diff[1], args.diff_out)
    elif args.track:
        cmd_track(args.track, args.snapshot_out)
    else:
        ap.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
