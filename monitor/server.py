#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CheepSeek Radar — 本地 HTTP 服务（Python 标准库，零依赖）

启动：  python server.py [--port 8765] [--open] [--idle-exit 分钟]
面板：  http://127.0.0.1:8765/
API：
  GET    /api/snapshots?platform=&model=&plan=   快照列表（按抓取日倒序）
  POST   /api/snapshots                          新增（JSON body，字段同 snapshots 表）
  PUT    /api/snapshots/<id>                     修改（JSON body）
  DELETE /api/snapshots/<id>                     删除
  GET    /api/meta                               平台/模型/套餐去重值（筛选用）
  GET    /api/ping                               心跳（面板每 30 秒一次，用于保活判定；不查库）
  POST   /api/shutdown                           停止服务（面板「停止服务」按钮）

空闲自动退出：--idle-exit N 表示 N 分钟无任何请求则自动停止（0=禁用）。
配合「打开监控台.vbs」与面板心跳使用，实际效果为：
  · 面板页面开着（哪怕切到别的标签页/最小化）→ 每 30 秒心跳，服务**不会**退出；
  · 关闭面板页面（或整个浏览器）→ 心跳停止 → N 分钟后服务自动退出。
"""
import argparse
import json
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    if sys.stdout is None:            # pythonw（无控制台）下 stdout 为 None
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    else:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 最后活动时间（monotonic），由每个请求刷新；供空闲自动退出判定
LAST_SEEN = time.monotonic()
_last_lock = threading.Lock()


def touch():
    """记录一次活动（任何 HTTP 请求都会调用）"""
    global LAST_SEEN
    with _last_lock:
        LAST_SEEN = time.monotonic()

BASE = Path(__file__).resolve().parent
# 品牌图标静态资源（只放行这三个固定路径，避免把 BASE 下任意文件暴露出去）
ASSETS = {
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
    "/favicon.ico": ("favicon.ico", "image/x-icon"),
    "/apple-touch-icon.png": ("apple-touch-icon.png", "image/png"),
}
FIELDS = ["captured_at", "platform", "plan", "model", "fee", "fee_currency",
          "quota", "quota_currency", "window", "in_v", "cache_v", "out_v",
          "in_p", "cache_p", "out_p", "currency", "promo", "source_url", "note"]
NUMERIC = {"fee", "quota", "in_v", "cache_v", "out_v", "in_p", "cache_p", "out_p"}

REPORTS_DIR = BASE.parent / "reports"
REPORTS_DIST = REPORTS_DIR / "dist"
_REPORT_LOCK = threading.Lock()
_REPORT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
}


def build_reports_preview():
    """重建报告预览产物（包含草稿）。报告页本身是静态 HTML，不依赖本服务运行。"""
    script = REPORTS_DIR / "build.py"
    if not script.is_file():
        return False, "reports/build.py 不存在"
    with _REPORT_LOCK:
        try:
            result = subprocess.run(
                [sys.executable, str(script), "--preview", "--out", str(REPORTS_DIST)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=30, creationflags=0x08000000 if os.name == "nt" else 0,
            )
        except Exception as exc:
            return False, str(exc)
        if result.returncode != 0:
            return False, (result.stderr or result.stdout or "构建失败").strip()
        return True, (result.stdout or "").strip()


def conn(db):
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    c.executescript("""
      CREATE TABLE IF NOT EXISTS snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        captured_at TEXT NOT NULL,
        platform TEXT NOT NULL,
        plan TEXT NOT NULL DEFAULT '按量',
        model TEXT NOT NULL,
        fee REAL, fee_currency TEXT DEFAULT 'USD',
        quota REAL, quota_currency TEXT DEFAULT 'USD',
        window TEXT,
        in_v REAL, cache_v REAL, out_v REAL,
        in_p REAL, cache_p REAL, out_p REAL,
        currency TEXT DEFAULT 'USD',
        promo TEXT,
        source_url TEXT,
        note TEXT
      );
      CREATE INDEX IF NOT EXISTS idx_key ON snapshots(platform, model, plan, captured_at);
      CREATE TABLE IF NOT EXISTS templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        cache_rate REAL NOT NULL,
        peak_pct REAL NOT NULL,
        input_share REAL NOT NULL,
        input_pct REAL,
        output_pct REAL
      );
    """)
    cols = {row["name"] for row in c.execute("PRAGMA table_info(templates)")}
    if "input_pct" not in cols:
        c.execute("ALTER TABLE templates ADD COLUMN input_pct REAL")
    if "output_pct" not in cols:
        c.execute("ALTER TABLE templates ADD COLUMN output_pct REAL")
    # 旧模板只有「非缓存部分的输入占比」，补出全量 token 中的输入/输出占比
    for row in c.execute("SELECT id, cache_rate, input_share, input_pct, output_pct FROM templates").fetchall():
        if row["input_pct"] is None or row["output_pct"] is None:
            cache = clamp_pct(row["cache_rate"], 0)
            share = clamp_pct(row["input_share"], 80)
            rest = max(0.0, 100 - cache)
            inp = rest * share / 100
            c.execute("UPDATE templates SET input_pct=?, output_pct=? WHERE id=?",
                      (round(inp, 6), round(rest - inp, 6), row["id"]))
    c.commit()
    return c


def clamp_pct(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(0.0, min(100.0, number))


def normalize_composition(cache, inp, outp):
    """保证缓存/输入/输出三项合计 100%，并保留小数比例。"""
    cache = clamp_pct(cache, 0)
    inp = clamp_pct(inp, 0)
    outp = clamp_pct(outp, 0)
    rest = max(0.0, 100 - cache)
    total = inp + outp
    if total <= 0:
        inp, outp = rest, 0.0
    else:
        scale = rest / total
        inp = round(inp * scale, 6)
        outp = round(rest - inp, 6)
    return cache, inp, outp


def template_composition(data):
    """读取模板参数；兼容旧的 input_share 字段。"""
    cache = clamp_pct(data.get("cache_rate"), 0)
    peak = clamp_pct(data.get("peak_pct"), 60)
    if data.get("input_pct") is not None or data.get("output_pct") is not None:
        inp = clamp_pct(data.get("input_pct"), 0)
        outp = clamp_pct(data.get("output_pct"), 0)
    else:
        share = clamp_pct(data.get("input_share"), 80)
        rest = max(0.0, 100 - cache)
        inp, outp = rest * share / 100, rest - rest * share / 100
    cache, inp, outp = normalize_composition(cache, inp, outp)
    total = inp + outp
    input_share = (inp / total * 100) if total > 0 else 80.0
    return cache, peak, round(input_share, 6), round(inp, 6), round(outp, 6)


def clean(data):
    out = {}
    for f in FIELDS:
        v = data.get(f)
        if v is None or v == "":
            out[f] = None
        elif f in NUMERIC:
            try:
                out[f] = float(v)
            except (TypeError, ValueError):
                out[f] = None
        else:
            out[f] = str(v).strip()
    # 币种兜底：费用/额度/价格币种缺省一律 USD（官方直售等特殊情况显式传 CNY）
    for f in ("fee_currency", "quota_currency", "currency"):
        if not out[f]:
            out[f] = "USD"
    return out


def make_handler(db_path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # 静默访问日志
            pass

        def _send(self, code, payload, ctype="application/json; charset=utf-8"):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if not isinstance(payload, bytes) else payload
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        # 任何请求都算一次活动（空闲自动退出据此判定）
        def handle_one_request(self):
            touch()
            BaseHTTPRequestHandler.handle_one_request(self)

        def _read_json(self):
            n = int(self.headers.get("Content-Length") or 0)
            if not n:
                return {}
            raw = self.rfile.read(n)
            try:
                return json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                # 兼容 GBK 终端（如 Windows curl）误发的编码，尝试二次解码
                try:
                    return json.loads(raw.decode("gbk"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self._send(400, {"error": "请求体不是合法 JSON"})
                    return None

        def _serve_report(self, path):
            """报告页：静态产物 + 本地预览构建（含草稿）。"""
            if path == "/reports":
                self.send_response(302)
                self.send_header("Location", "/reports/")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            if path == "/reports/":
                ok, msg = build_reports_preview()
                if not ok:
                    self._send(500, f"报告生成失败：{msg}".encode("utf-8"), "text/plain; charset=utf-8")
                    return
                target = REPORTS_DIST / "index.html"
            else:
                rel = path[len("/reports/"):]
                if not rel or rel.endswith("/"):
                    rel += "index.html"
                if rel.endswith(".html"):
                    ok, msg = build_reports_preview()
                    if not ok:
                        self._send(500, f"报告生成失败：{msg}".encode("utf-8"), "text/plain; charset=utf-8")
                        return
                target = (REPORTS_DIST / rel).resolve()
                dist = REPORTS_DIST.resolve()
                if target != dist and dist not in target.parents:
                    self._send(404, {"error": "not found"})
                    return

            ctype = _REPORT_TYPES.get(target.suffix.lower())
            if not ctype or not target.is_file():
                self._send(404, {"error": "not found"})
                return
            self._send(200, target.read_bytes(), ctype)

        # ---------- GET ----------
        def do_GET(self):
            parsed = urlparse(self.path)
            path, qs = parsed.path, parsed.query
            if path == "/" or path == "/panel.html":
                html = (BASE / "panel.html").read_bytes()
                self._send(200, html, "text/html; charset=utf-8")
                return
            # 品牌图标（favicon / iOS 主屏）
            if path in ASSETS:
                name, ctype = ASSETS[path]
                f = BASE / name
                if f.is_file():
                    self._send(200, f.read_bytes(), ctype)
                    return
                self._send(404, {"error": "not found"})
                return
            # 研究报告：本地预览与未来静态部署共用 reports/dist 产物
            if path == "/reports" or path.startswith("/reports/"):
                self._serve_report(path)
                return
            # 本地静态 HTML（测试页/未来附加页面；file:// 下 fetch 会跨域，故走本服务）
            if path.startswith("/") and not path.startswith("/api/"):
                f = BASE / path.lstrip("/")
                if f.is_file() and f.suffix.lower() == ".html":
                    self._send(200, f.read_bytes(), "text/html; charset=utf-8")
                    return
                self._send(404, {"error": "not found"})
                return
            # 心跳：面板页面每 30 秒 ping 一次，用于「页面开着就不退出」的保活判定
            # 极轻量（不碰数据库）——请求本身已由 handle_one_request 记为活动
            if path == "/api/ping":
                self._send(200, {"ok": True})
                return
            if path == "/api/meta":
                c = conn(db_path)
                def distinct(col):
                    return [r[0] for r in c.execute(
                        f"SELECT DISTINCT {col} FROM snapshots WHERE {col} IS NOT NULL AND {col} != '' ORDER BY {col}")]
                # 平台 → 套餐 映射（套餐是平台的二级选项）
                plans_by_platform = {}
                for r in c.execute("SELECT DISTINCT platform, plan FROM snapshots WHERE plan IS NOT NULL AND plan != ''"):
                    plans_by_platform.setdefault(r[0], []).append(r[1])
                for k in plans_by_platform:
                    plans_by_platform[k].sort()
                self._send(200, {"platforms": distinct("platform"), "models": distinct("model"),
                                 "plans": distinct("plan"), "plans_by_platform": plans_by_platform})
                return
            if path == "/api/templates":
                c = conn(db_path)
                rows = c.execute("SELECT * FROM templates ORDER BY id").fetchall()
                self._send(200, [dict(r) for r in rows])
                return
            if path == "/api/snapshots":
                q = parse_qs(qs)
                where, args = [], []
                for col in ("platform", "model", "plan"):
                    if q.get(col):
                        where.append(f"{col} = ?"); args.append(q[col][0])
                w = ("WHERE " + " AND ".join(where)) if where else ""
                c = conn(db_path)
                rows = c.execute(f"SELECT * FROM snapshots {w} ORDER BY captured_at DESC, id DESC", args).fetchall()
                self._send(200, [dict(r) for r in rows])
                return
            self._send(404, {"error": "not found"})

        # ---------- POST ----------
        def do_POST(self):
            if self.path == "/api/shutdown":
                # 面板「停止服务」按钮：先回包，再在独立线程里关服务（避免自己阻塞自己）
                self._send(200, {"ok": True, "message": "服务正在停止"})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if self.path == "/api/templates":
                data = self._read_json()
                if data is None:
                    return
                name = str(data.get("name") or "").strip()
                try:
                    float(data["cache_rate"]); float(data["peak_pct"])
                except (KeyError, TypeError, ValueError):
                    self._send(400, {"error": "cache_rate/peak_pct 必须为数字"})
                    return
                if not name:
                    self._send(400, {"error": "模板名不能为空"})
                    return
                cr, pp, ins, inp, outp = template_composition(data)
                c = conn(db_path)
                cur = c.execute(
                    "INSERT INTO templates (name, cache_rate, peak_pct, input_share, input_pct, output_pct) VALUES (?,?,?,?,?,?)",
                    (name, cr, pp, ins, inp, outp))
                c.commit()
                self._send(201, {"id": cur.lastrowid})
                return
            if self.path == "/api/snapshots":
                data = self._read_json()
                if data is None:
                    return
                data = clean(data)
                if not data.get("captured_at") or not data.get("platform") or not data.get("model"):
                    self._send(400, {"error": "captured_at/platform/model 必填"})
                    return
                cols = ", ".join(FIELDS)
                marks = ", ".join("?" * len(FIELDS))
                c = conn(db_path)
                cur = c.execute(f"INSERT INTO snapshots ({cols}) VALUES ({marks})",
                                [data.get(f) for f in FIELDS])
                c.commit()
                self._send(201, {"id": cur.lastrowid})
                return
            self._send(404, {"error": "not found"})

        # ---------- PUT / DELETE ----------
        def _match_id(self, path):
            # /api/<res>/<id>
            parts = path.split("/")
            if len(parts) == 4 and parts[1] == "api" and parts[2] in ("snapshots", "templates"):
                try:
                    return parts[2], int(parts[3])
                except ValueError:
                    return parts[2], None
            return None, None

        def do_PUT(self):
            res, rid = self._match_id(self.path)
            if res is None or rid is None:
                self._send(404, {"error": "not found"}); return
            data = self._read_json()
            if data is None:
                return
            c = conn(db_path)
            if res == "templates":
                try:
                    float(data["cache_rate"]); float(data["peak_pct"])
                except (KeyError, TypeError, ValueError):
                    self._send(400, {"error": "cache_rate/peak_pct 必须为数字"}); return
                name = str(data.get("name") or "").strip() or "未命名模板"
                cr, pp, ins, inp, outp = template_composition(data)
                cur = c.execute(
                    "UPDATE templates SET name=?, cache_rate=?, peak_pct=?, input_share=?, input_pct=?, output_pct=? WHERE id=?",
                    (name, cr, pp, ins, inp, outp, rid))
            else:
                data = clean(data)
                sets = ", ".join(f"{f} = ?" for f in FIELDS)
                cur = c.execute(f"UPDATE snapshots SET {sets} WHERE id = ?",
                                [data.get(f) for f in FIELDS] + [rid])
            c.commit()
            self._send(200, {"ok": cur.rowcount > 0})

        def do_DELETE(self):
            res, rid = self._match_id(self.path)
            if res is None or rid is None:
                self._send(404, {"error": "not found"}); return
            c = conn(db_path)
            table = "templates" if res == "templates" else "snapshots"
            cur = c.execute(f"DELETE FROM {table} WHERE id = ?", (rid,))
            c.commit()
            self._send(200, {"ok": cur.rowcount > 0})

    return Handler


def main():
    ap = argparse.ArgumentParser(description="CheepSeek Radar 本地服务")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--db", default=str(BASE / "plans.db"))
    ap.add_argument("--open", action="store_true", help="服务启动成功后自动打开浏览器")
    ap.add_argument("--idle-exit", type=float, default=0, metavar="分钟",
                    help="空闲多少分钟后自动停止（0=不自动停止）")
    a = ap.parse_args()

    url = f"http://{a.host}:{a.port}/"
    # 端口预检：Windows 允许 SO_REUSEADDR 重复绑定，防多实例叠加（旧代码进程轮询导致数据不一致）
    probe = socket.socket()
    try:
        probe.bind((a.host, a.port))
        probe.close()
    except OSError:
        print(f"端口 {a.port} 已被占用——监控台可能已在运行，直接打开 {url} 即可", file=sys.stderr)
        sys.exit(2)   # 2 = 已在运行（VBS 据此判断直接开浏览器）
    try:
        httpd = ThreadingHTTPServer((a.host, a.port), make_handler(a.db))
    except OSError as e:
        print(f"启动失败：端口 {a.port} 被占用（{e}）", file=sys.stderr)
        print(f"可能监控台已在运行 → 浏览器直接打开 {url}", file=sys.stderr)
        sys.exit(1)
    print(f"CheepSeek Radar 已启动：{url}")
    ok, msg = build_reports_preview()
    if not ok:
        print(f"报告预览构建失败：{msg}", file=sys.stderr)
    if a.open:
        try:
            webbrowser.open(url)
        except Exception:
            pass  # 无默认浏览器等环境下静默

    # 空闲看门狗：超过 --idle-exit 分钟无任何请求则自动停止（关闭浏览器后服务自行退出）
    # 启动后前 2 分钟为宽限期，避免浏览器尚未连上就被判空闲
    if a.idle_exit and a.idle_exit > 0:
        def watchdog():
            time.sleep(120)
            while True:
                with _last_lock:
                    idle = time.monotonic() - LAST_SEEN
                if idle >= a.idle_exit * 60:
                    print(f"空闲 {a.idle_exit:g} 分钟，自动停止服务", file=sys.stderr)
                    httpd.shutdown()
                    return
                time.sleep(min(30, max(5, a.idle_exit * 60 - idle)))
        threading.Thread(target=watchdog, daemon=True).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
