import io, json, os, re, subprocess, sys, zipfile, tempfile
SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(SKILL, "scripts")
PY = "C:/Tools/anaconda3/python.exe"

# Plausibly-malformed UNIFIED records (fields shaped slightly wrong but
# realistic): strings where lists expected, int where str expected, None/empty.
recs = [
    # conditions/countries as STRINGS (some adapters/legacy data)
    {"source": "CTGOV", "registry_id": "NCT0001", "title": "Trial string-fields",
     "conditions": "Lung Cancer", "phase": "PHASE 3", "enrollment": "350",
     "status": "RECRUITING", "sponsor": "Acme", "countries": "United States",
     "start_date": "2024-01-01", "interventions": "Osimertinib",
     "url": "https://clinicaltrials.gov/study/NCT0001"},
    # start_date as INT, title None, url empty string
    {"source": "CDE", "registry_id": "CTR20240701", "title": None,
     "conditions": ["非小细胞肺癌"], "phase": "III期", "enrollment": 350,
     "status": "进行中（招募中）", "sponsor": "恒瑞", "countries": ["China"],
     "start_date": 20240101, "interventions": None, "url": ""},
    # enrollment as float, phase weird-case, conditions list mixed
    {"source": "EUCTR", "registry_id": "EUCTR2024-1", "title": "EU study",
     "conditions": ["Diabetes", "Obesity"], "phase": "phase 2", "enrollment": 120.0,
     "status": "Ongoing", "sponsor": "EU Pharma", "countries": ["Germany"],
     "start_date": "2023-02-01", "interventions": ["DrugX"], "url": None},
    # totally minimal (only id)
    {"source": "ISRCTN", "registry_id": "ISRCTN111", "title": "Min",
     "conditions": None, "phase": None, "enrollment": None, "status": None,
     "sponsor": None, "countries": None, "start_date": None,
     "interventions": None, "url": None},
]

tmp = tempfile.mkdtemp()
inp = os.path.join(tmp, "norm.json")
json.dump(recs, open(inp, "w", encoding="utf-8"))
out = os.path.join(tmp, "r.xlsx")
p = subprocess.run([PY, os.path.join(SCRIPTS, "export_xlsx.py"),
                    "--in", inp, "--out", out, "--lang", "zh"],
                   cwd=SCRIPTS, capture_output=True, text=True)
print("export_xlsx rc=", p.returncode)
print("STDOUT:", p.stdout[-400:])
print("STDERR:", p.stderr[-800:])
print("xlsx exists:", os.path.exists(out), "size:", os.path.getsize(out) if os.path.exists(out) else 0)
