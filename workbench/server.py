#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ct-registry 检索工作台 · 本地后端 (stdlib http.server, 零外部依赖)
==================================================================
标准 Chrome 前端 (index.html) + 本地 /api/* 端点。检索走子进程编排:
    POST /api/search  -> 线程内 Popen(ct_registry.py ...), 立即返回 {task_id}
    GET  /api/task/<id> -> {state, log, summary, rows, report_md, excelUrl}  状态流轮询
    GET  /api/download?task=<id> -> report.xlsx
设计依据: ct-base/references/workbench_ui.md §7 后端契约 (端点前缀 /api/,
mock 开关命名 CT_<SKILL大写>_MOCK, 端口预检, 改后必重启+强刷)。
运行: python server.py   (默认端口 8790; 环境变量 WB_PORT 可覆盖)
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUNS_DIR = os.path.join(BASE_DIR, "runs")


def _resolve_skill_dir(base_dir):
    """相对解析 ct-registry 技能根目录 (scripts/ct_registry.py 所在目录):
       1) CT_REGISTRY_SKILL 环境变量覆盖 (CI/特殊部署/开发布局)
       2) 默认取本文件所在目录的父目录 —— 落地于 ct-registry/workbench/server.py
          时, 父目录即 ct-registry 技能根, 含 scripts/ct_registry.py
       3) 若该父目录不含脚本, 则从 base_dir 向上回溯查找 (兜底)
    不再硬编码任何用户家目录路径, 拷贝进技能目录/上架后亦可运行。"""
    cand = os.path.dirname(base_dir)
    if os.path.isfile(os.path.join(cand, "scripts", "ct_registry.py")):
        return cand
    env = os.environ.get("CT_REGISTRY_SKILL")
    if env and os.path.isfile(os.path.join(env, "scripts", "ct_registry.py")):
        return env
    cur = base_dir
    for _ in range(5):
        if os.path.isfile(os.path.join(cur, "scripts", "ct_registry.py")):
            return cur
        nxt = os.path.dirname(cur)
        if nxt == cur:
            break
        cur = nxt
    return cand


SKILL_DIR = _resolve_skill_dir(BASE_DIR)     # ct_registry.py 所在技能目录 (相对解析)
PY = os.environ.get("CTWB_PY", sys.executable)   # 默认使用运行 server.py 的解释器
PORT = int(os.environ.get("WB_PORT", "8790"))
MOCK = os.environ.get("CT_REGISTRY_MOCK", "").lower() in ("1", "true", "yes")

os.makedirs(RUNS_DIR, exist_ok=True)

TASKS = {}          # task_id -> dict(state/log...)
TASKS_LOCK = threading.Lock()

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".md": "text/plain; charset=utf-8",
}


def _tail(path, n=12000):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - n))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def _last_summary(log_text):
    """ct_registry.py _print_summary 在 stdout 尾部打印 {"tool":"ct-registry",...} JSON"""
    for line in reversed(log_text.splitlines()):
        line = line.strip()
        if line.startswith('{"tool": "ct-registry"'):
            try:
                return json.loads(line)
            except Exception:
                return None
    return None


RID_KEYS = ["nct_id", "registry_id", "primary_id", "utn", "trn", "registry_number",
            "registration_number", "trial_id", "identifier", "number"]
TITLE_KEYS = ["title", "official_title", "scientific_title", "public_title", "study_title"]
STATUS_KEYS = ["status", "recruitment_status", "overall_status", "trial_status"]
PHASE_KEYS = ["phase"]
COUNTRY_KEYS = ["countries", "country"]
SPONSOR_KEYS = ["sponsor", "primary_sponsor", "sponsors", "organization"]
SOURCE_KEYS = ["source", "registry", "datasource", "data_source"]
URL_KEYS = ["url", "full_url", "link", "registry_url"]


def _first(d, keys):
    for k in keys:
        v = d.get(k)
        if v not in (None, "", [], {}):
            if isinstance(v, list):
                return ", ".join(str(x) for x in v)
            return str(v)
    return ""


def _canon(row):
    reg_no = _first(row, RID_KEYS)
    url = _first(row, URL_KEYS)
    source = _first(row, SOURCE_KEYS)
    if not reg_no:
        m = re.search(r"(NCT\d+|CTR\d+|EUCTR[\w-]+|ISRCTN\d+|DRKS\d+|ChiCTR[\w-]+)", url or "")
        reg_no = m.group(1) if m else ""
    if not reg_no:
        base = source or "reg"
        reg_no = base + "-" + str(row.get("id") or row.get("index") or "")
    return {
        "regNo": reg_no,
        "title": _first(row, TITLE_KEYS) or "(untitled)",
        "phase": _first(row, PHASE_KEYS) or "",
        "status": _first(row, STATUS_KEYS) or "",
        "countries": _first(row, COUNTRY_KEYS),
        "sponsor": _first(row, SPONSOR_KEYS) or "",
        "source": source,
        "url": url,
    }


def _build_cmd(params):
    """前端检索表单 -> ct_registry.py CLI。非交互调用必须 --no-expand 旁路关键词确认门。"""
    args = ["scripts/ct_registry.py", "--run", "--print-summary", "--no-expand",
            "--auto-confirm", "--allow-broad", "--keep-meta"]

    def add(name, val, default=""):
        if val in (None, ""):
            return
        if str(val) == str(default):
            return
        args.append(name)
        args.append(str(val))

    add("--cond", params.get("cond"))
    add("--intr", params.get("intr"))
    add("--sponsor", params.get("sponsor"))
    add("--status", params.get("status"))
    add("--max", params.get("max"), 50)
    add("--since-years", params.get("since_years"), 0)

    regs = params.get("registries") or []
    # ClinicalTrials.gov 由 ct_registry 恒开, 无需 flag; WHO 聚合 14 源
    if "who" in regs:
        args.append("--with-ictrp")
    if "cde" in regs:
        args.append("--with-cde")
        # CDE 需要中文关键字; cond 若为中文直接作 CDE keyword, 否则回退 cde_keyword 字段
        cde_kw = (params.get("cde_keyword") or "").strip() or (params.get("cond") or "").strip()
        if cde_kw:
            args += ["--cde-keyword", cde_kw]
    if "euctr" in regs:
        args.append("--with-euctr")
    if "chictr" in regs:
        args.append("--with-chictr")
    if "isrctn" in regs:
        args.append("--with-isrctn")
    if "drks" in regs:
        args.append("--with-drks")
    if "pubchem" in regs:
        args.append("--with-pubchem")
    return args


def _run_task(task_id, params):
    """后台线程: 子进程跑 ct_registry.py, 状态/日志写入 TASKS 与磁盘。"""
    out_dir = os.path.join(RUNS_DIR, task_id)
    os.makedirs(out_dir, exist_ok=True)
    log_path = os.path.join(out_dir, "log.txt")
    meta = {"id": task_id, "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "params": {k: params.get(k) for k in
                       ("cond", "intr", "sponsor", "status", "max", "since_years",
                        "registries", "cde_keyword")},
            "state": "running", "sources": ",".join(params.get("registries") or [])}
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    cmd = [PY] + _build_cmd(params) + ["--out-dir", out_dir]
    with TASKS_LOCK:
        TASKS[task_id] = {"id": task_id, "state": "running", "started": time.time(),
                          "out": out_dir, "log": log_path}
    log = open(log_path, "a", encoding="utf-8", buffering=1)
    try:
        log.write("$ " + " ".join(cmd) + "\n\n")
        proc = subprocess.Popen(cmd, cwd=SKILL_DIR, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                errors="replace")
        for line in proc.stdout:
            log.write(line)
        rc = proc.wait()
        log.write("\n[exit code] %s\n" % rc)
        log.flush()
        result = {"exit": rc, "summary": None, "rows": [], "report_md": None,
                  "excel": os.path.exists(os.path.join(out_dir, "report.xlsx")),
                  "excelUrl": "/api/download?task=%s" % task_id}
        txt = _tail(log_path, 200000)
        if rc == 0:
            result["summary"] = _last_summary(txt)
            norm = os.path.join(out_dir, "normalized.json")
            if os.path.exists(norm):
                try:
                    with open(norm, encoding="utf-8") as f:
                        data = json.load(f)
                    rows = data if isinstance(data, list) else (data.get("records") or data.get("trials") or [])
                    result["rows"] = [_canon(r) for r in rows[:300]]
                except Exception as e:
                    result["rows_note"] = "normalized.json 解析失败: %s" % e
            md = os.path.join(out_dir, "report.md")
            if os.path.exists(md):
                result["report_md"] = _tail(md, 60000)
        else:
            result["error"] = txt[-3000:]
        state = "done" if rc == 0 else "error"
        meta["state"] = state
        meta["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
        meta["exit"] = rc
        with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        state = "error"
        meta["state"] = "error"
        with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
        result = {"error": str(e)}
    finally:
        log.close()
        with TASKS_LOCK:
            TASKS[task_id]["state"] = state
            TASKS[task_id]["finished"] = time.time()
            TASKS[task_id]["result"] = result


def _task_view(task_id):
    with TASKS_LOCK:
        t = TASKS.get(task_id)
    if not t:
        return {"state": "unknown"}
    view = {"id": task_id, "state": t["state"],
            "log": _tail(t["log"], 12000),
            "out": os.path.basename(t["out"])}
    if t.get("result") is not None:
        r = t["result"]
        view["exit"] = r.get("exit")
        view["summary"] = r.get("summary")
        view["rows"] = r.get("rows", [])
        view["report_md"] = r.get("report_md")
        view["excelUrl"] = r.get("excelUrl")
        if r.get("error"):
            view["error"] = r["error"]
    return view


def _runs_view():
    out = []
    if os.path.isdir(RUNS_DIR):
        for name in sorted(os.listdir(RUNS_DIR), reverse=True):
            meta_path = os.path.join(RUNS_DIR, name, "meta.json")
            if not os.path.exists(meta_path):
                continue
            try:
                with open(meta_path, encoding="utf-8") as f:
                    m = json.load(f)
            except Exception:
                continue
            m["excel"] = os.path.exists(os.path.join(RUNS_DIR, name, "report.xlsx"))
            out.append(m)
    return out[:50]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        """CORS 预检（预览 iframe / 托管副本跨源 POST application/json 需要）"""
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self._cors()
        self.end_headers()

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def _static(self, rel):
        root = BASE_DIR
        p = os.path.abspath(os.path.join(root, rel))
        if not p.startswith(os.path.abspath(root)):
            return self._json({"error": "bad path"}, 400)
        if not os.path.isfile(p):
            return self._json({"error": "not found"}, 404)
        ext = os.path.splitext(p)[1].lower()
        with open(p, "rb") as f:
            self._send(200, f.read(), MIME.get(ext, "application/octet-stream"))

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        path = u.path
        if path in ("/", "/index.html"):
            return self._static("index.html")
        if path == "/api/config":
            try:
                with open(os.path.join(BASE_DIR, "workbench.config.json"), encoding="utf-8") as f:
                    cfg = json.load(f)
            except Exception:
                cfg = {"skill": "ct-registry"}
            cfg["backend"] = dict(cfg.get("backend", {}), mockEnv="CT_REGISTRY_MOCK")
            return self._json(cfg)
        if path == "/api/health":
            return self._json({"ok": True, "skill": "ct-registry", "mock": MOCK,
                               "time": time.strftime("%Y-%m-%d %H:%M:%S")})
        if path == "/api/runs":
            return self._json({"runs": _runs_view()})
        if path.startswith("/api/task/"):
            tid = path.split("/")[-1]
            return self._json(_task_view(tid))
        if path == "/api/download":
            tid = (q.get("task") or [""])[0]
            fpath = os.path.join(RUNS_DIR, tid, "report.xlsx")
            if not os.path.isfile(fpath):
                return self._json({"error": "report.xlsx 不存在 (可能未产出)"}, 404)
            self.send_response(200)
            self.send_header("Content-Type", MIME[".xlsx"])
            self.send_header("Content-Disposition",
                             "attachment; filename=ct-registry-report-%s.xlsx" % tid)
            self.send_header("Content-Length", str(os.path.getsize(fpath)))
            self._cors()
            self.end_headers()
            with open(fpath, "rb") as f:
                shutil.copyfileobj(f, self.wfile)
            return None
        # 其余静态资源 (tokens.css / icon.svg 等, 供直连引用)
        return self._static(path.lstrip("/"))

    def do_POST(self):
        u = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8")) if raw.strip() else {}
        except Exception:
            return self._json({"error": "invalid json"}, 400)
        if u.path == "/api/search":
            task_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
            th = threading.Thread(target=_run_task, args=(task_id, body), daemon=True)
            th.start()
            return self._json({"task_id": task_id, "mock": MOCK})
        if u.path == "/api/bug-report":
            # ct-base §20.3 风格：仅收问题描述（无检索数据），本地落盘（runs/_bugreports/）
            desc = str(body.get("description") or "").strip()
            if not desc:
                return self._json({"ok": False, "error": "description required"}, 400)
            if len(desc) > 5000:
                desc = desc[:5000]
            d = os.path.join(RUNS_DIR, "_bugreports")
            os.makedirs(d, exist_ok=True)
            bid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
            with open(os.path.join(d, bid + ".json"), "w", encoding="utf-8") as f:
                json.dump({"id": bid, "ts": time.time(), "description": desc}, f,
                          ensure_ascii=False, indent=1)
            return self._json({"ok": True, "id": bid})
        if u.path == "/api/run-delete":
            tid = body.get("id") or ""
            target = os.path.join(RUNS_DIR, tid)
            if tid and os.path.isdir(target):
                shutil.rmtree(target, ignore_errors=True)
                with TASKS_LOCK:
                    TASKS.pop(tid, None)
            return self._json({"ok": True})
        return self._json({"error": "unknown endpoint"}, 404)


def _port_free(port):
    import socket
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


if __name__ == "__main__":
    if not os.path.isfile(os.path.join(SKILL_DIR, "scripts", "ct_registry.py")):
        print("[ct-registry-wb] 找不到技能脚本: %s" % SKILL_DIR, file=os.sys.stderr)
        raise SystemExit(1)
    if not os.path.isfile(PY):
        print("[ct-registry-wb] 找不到 Python: %s (可用 CTWB_PY 覆盖)" % PY, file=os.sys.stderr)
        raise SystemExit(1)
    if not _port_free(PORT):
        print("[ct-registry-wb] 端口 %d 已被占用 —— 先杀掉旧进程再重启 (改后必重启+强刷)" % PORT,
              file=os.sys.stderr)
        raise SystemExit(1)
    print("[ct-registry-wb] http://127.0.0.1:%d  (mock=%s, py=%s)" % (PORT, MOCK, PY))
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
