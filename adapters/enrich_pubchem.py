#!/usr/bin/env python3
"""enrich_pubchem.py - PubChem PUG-REST drug->CID/props/targets / 药物->靶点映射.

Reads public data only. / 仅读公开数据。
"""
import argparse
import json
import urllib.parse
import urllib.request

PUB = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ct-registry/0.1", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def cid_of(name):
    d = _get(f"{PUB}/compound/name/{urllib.parse.quote(name)}/cids/JSON")
    return d["IdentifierList"]["CID"][0]


def props_of(name):
    d = _get(f"{PUB}/compound/name/{urllib.parse.quote(name)}/property/MolecularWeight,IUPACName,IsomericSMILES/JSON")
    return d["PropertyTable"]["Properties"][0]


def targets_of(cid):
    try:
        d = _get(f"{PUB}/compound/cid/{cid}/assaysummary/JSON")
        genes = set()
        for row in d.get("Table", {}).get("Rows", []):
            g = row.get("GeneSymbol")
            if g:
                genes.add(g)
        return sorted(genes)
    except Exception:
        return []


def main():
    ap = argparse.ArgumentParser(description="PubChem drug->target (public).")
    ap.add_argument("--drug", required=True)
    ap.add_argument("--targets", action="store_true", help="include gene targets / 含靶点基因")
    ap.add_argument("--out", default="pubchem.json")
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args()

    if not args.run:
        print(f"[pubchem][PREVIEW] would enrich drug='{args.drug}' (add --run to execute)")
        return

    cid = cid_of(args.drug)
    rec = {"drug": args.drug, "cid": cid, "props": props_of(args.drug)}
    if args.targets:
        rec["targets"] = targets_of(cid)
    out = {"source": "PUBCHEM", "records": [rec]}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[pubchem] {args.drug} -> CID {cid} -> {args.out}")


if __name__ == "__main__":
    main()
