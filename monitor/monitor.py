#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CheepSeek Radar — SQLite 快照库 CLI（Python 标准库，零依赖）

用法：
  python monitor.py add    --date 2026-11-02 --platform Ollama --plan Pro \
        --model deepseek-v4.1-flash-1017 --fee 20 --quota 60 --window "月重置" \
        --in 0.15 --cache 0.003 --out 0.6 --in-p 0.3 --cache-p 0.006 --out-p 1.2 \
        --url https://ollama.com/pricing
  python monitor.py latest                 # 各平台×模型×套餐最新状态
  python monitor.py diff                   # 全部：对比最近两轮快照
  python monitor.py diff --platform ollama --model deepseek-v4.1-flash-1017
  python monitor.py history --platform opencode
  python monitor.py dump [-o out.csv]      # 导出全量 CSV

约定：
  - 一行 = 一次抓取的「平台 × 模型 × 套餐」价格快照
  - 价格为每百万 token，峰谷分列（--in/--cache/--out 为谷价，--in-p/--cache-p/--out-p 为峰价）
  - --fee/--quota 为月费/月额度（--fee-ccy/--quota-ccy 默认 USD）
  - 半自动监控：Agent 抓页面 → add 录入 → diff 报变化；脚本只管存储与对比
"""
import argparse
import csv
import json
import os
import re
import sqlite3
import sys
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DB = Path(os.environ.get("MONITOR_DB", Path(__file__).resolve().parent / "plans.db"))
SCHEMA = """
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
"""


def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


# ---------------- add ----------------
def cmd_add(a):
    if not a.date or not a.platform or not a.model:
        sys.exit("add 需要 --date --platform --model")
    c = conn()
    c.execute(
        """INSERT INTO snapshots
           (captured_at, platform, plan, model, fee, fee_currency, quota, quota_currency,
            window, in_v, cache_v, out_v, in_p, cache_p, out_p, currency, promo, source_url, note)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (a.date, a.platform, a.plan, a.model,
         a.fee, a.fee_ccy, a.quota, a.quota_ccy, a.window,
         a.inv, a.cachev, a.outv, a.inp, a.cachep, a.outp,
         a.currency, a.promo, a.url, a.note),
    )
    c.commit()
    rid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    print(f"已录入 #{rid}: {a.date} {a.platform}·{a.plan}·{a.model}")


# ---------------- 展示工具 ----------------
def fmt_price(v):
    return "-" if v is None else f"{v:g}"


def fmt_money(v, ccy):
    return "-" if v is None else f"{v:g} {ccy or 'USD'}"


def latest_rows(c, platform=None, model=None, plan=None):
    """每个 (platform, model, plan) 取最新一条（captured_at 最新，同日取后插入的）"""
    where, args = [], []
    if platform:
        where.append("platform = ?"); args.append(platform)
    if model:
        where.append("model = ?"); args.append(model)
    if plan:
        where.append("plan = ?"); args.append(plan)
    w = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"""
      SELECT * FROM (
        SELECT s.*, ROW_NUMBER() OVER (
          PARTITION BY platform, model, plan ORDER BY captured_at DESC, id DESC) rn
        FROM snapshots s) t
      WHERE rn = 1 {w} ORDER BY platform, model, plan"""
    return c.execute(sql, args).fetchall()


# ---------------- latest ----------------
def cmd_latest(a):
    c = conn()
    rows = latest_rows(c, a.platform, a.model, a.plan)
    if not rows:
        print("（空）尚无快照")
        return
    hdr = f"{'平台':<10}{'套餐':<8}{'模型':<26}{'月费':<10}{'月额度':<10}{'谷 in/cache/out':<22}{'峰 in/cache/out':<22}{'促销':<10}{'抓取日'}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        p = f"{r['in_v'] if r['in_v'] is not None else '-'}/{r['cache_v'] if r['cache_v'] is not None else '-'}/{r['out_v'] if r['out_v'] is not None else '-'}"
        pk = f"{r['in_p'] if r['in_p'] is not None else '-'}/{r['cache_p'] if r['cache_p'] is not None else '-'}/{r['out_p'] if r['out_p'] is not None else '-'}"
        print(f"{r['platform']:<10}{r['plan']:<8}{r['model']:<26}"
              f"{fmt_money(r['fee'], r['fee_currency']):<10}{fmt_money(r['quota'], r['quota_currency']):<10}"
              f"{p:<22}{pk:<22}{str(r['promo'] or ''):<10}{r['captured_at']}")


# ---------------- diff ----------------
def pct(new, old):
    if old in (None, 0) or new is None:
        return ""
    d = (new - old) / old * 100
    s = "+" if d > 0 else ""
    return f"({s}{d:.1f}%)"


def cell_diff(name, new, old):
    if new == old:
        return None
    if isinstance(new, (int, float)) or isinstance(old, (int, float)):
        return f"{name}: {fmt_price(old)} → {fmt_price(new)} {pct(new, old)}".strip()
    return f"{name}: {old} → {new}"


def cmd_diff(a):
    c = conn()
    cur = latest_rows(c, a.platform, a.model, a.plan)
    if not cur:
        print("（空）尚无快照")
        return
    print(f"{'平台·套餐·模型':<42}{'变化（最近两轮）':<70}")
    print("-" * 112)
    n_changed = 0
    for r in cur:
        prev = c.execute(
            """SELECT * FROM snapshots WHERE platform=? AND model=? AND plan=?
               AND (captured_at < ? OR (captured_at = ? AND id < ?))
               ORDER BY captured_at DESC, id DESC LIMIT 1""",
            (r["platform"], r["model"], r["plan"], r["captured_at"], r["captured_at"], r["id"]),
        ).fetchone()
        key = f"{r['platform']}·{r['plan']}·{r['model']}"
        if not prev:
            print(f"{key:<42}{'首次快照（无对比）':<70}")
            continue
        diffs = [d for d in [
            cell_diff("谷输入", r["in_v"], prev["in_v"]),
            cell_diff("谷缓存", r["cache_v"], prev["cache_v"]),
            cell_diff("谷输出", r["out_v"], prev["out_v"]),
            cell_diff("峰输入", r["in_p"], prev["in_p"]),
            cell_diff("峰缓存", r["cache_p"], prev["cache_p"]),
            cell_diff("峰输出", r["out_p"], prev["out_p"]),
            cell_diff("月费", r["fee"], prev["fee"]),
            cell_diff("月额度", r["quota"], prev["quota"]),
            cell_diff("促销", r["promo"], prev["promo"]),
        ] if d]
        if not diffs:
            print(f"{key:<42}{'无变化（' + r['captured_at'] + '）':<70}")
        else:
            n_changed += 1
            print(f"{key:<42}{'; '.join(diffs):<70}")
    print("-" * 112)
    print(f"共 {len(cur)} 个监测项，{n_changed} 项发生变化")


# ---------------- history ----------------
def cmd_history(a):
    c = conn()
    rows = c.execute(
        """SELECT * FROM snapshots WHERE (? IS NULL OR platform=?) AND (? IS NULL OR model=?)
           ORDER BY platform, model, plan, captured_at, id""",
        (a.platform, a.platform, a.model, a.model),
    ).fetchall()
    if not rows:
        print("（空）")
        return
    for r in rows:
        p = f"{r['in_v'] if r['in_v'] is not None else '-'}/{r['cache_v'] if r['cache_v'] is not None else '-'}/{r['out_v'] if r['out_v'] is not None else '-'}"
        print(f"{r['captured_at']}  {r['platform']:<10}{r['plan']:<8}{r['model']:<26} 谷[{p}]"
              f"{' 促销:' + r['promo'] if r['promo'] else ''}")


# ---------------- dump ----------------
# ---------------- fetch：自动抓取 + 多维核验（对话内使用；只输出草稿，不写库） ----------------
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def fetch_ollama(html):
    """Ollama 价表：同一模型可能出现两行——
    `NAME`（峰价）与 `NAME (Off-Peak)`（谷价）；无 Off-Peak 行的模型 = 单一价、无峰谷。
    兼容旧版页面：若同一模型出现两行且都无 Off-Peak 标签，按「第一行谷、第二行峰」处理。"""
    rows = {}
    for m in re.finditer(r'<a href="/library/([a-z0-9.-]+)"[^>]*>([^<]+)</a></td>\s*<td[^>]*>\$?([\d.]+)</td>\s*<td[^>]*>(?:-|\$?([\d.]+))</td>\s*<td[^>]*>\$?([\d.]+)</td>', html):
        name, label, inp, cache, outp = m.groups()
        rows.setdefault(name, []).append({
            "label": label.strip(),
            "off": "off-peak" in label.lower(),
            "p": {"in": float(inp), "cache": float(cache) if cache else None, "out": float(outp)},
        })
    out = []
    for name, entries in rows.items():
        off = [e for e in entries if e["off"]]
        reg = [e for e in entries if not e["off"]]
        if off:
            valley = off[0]["p"]
            peak = reg[0]["p"] if reg else None
        elif len(reg) >= 2:
            valley, peak = reg[0]["p"], reg[1]["p"]
        elif reg:
            valley, peak = reg[0]["p"], None
        else:
            continue
        out.append({"model": name, "valley": valley, "peak": peak})
    return out


def fetch_opencode(html):
    """opencode.ai/docs/go 价表：<tr><td>NAME (Off-Peak|Peak)</td><td>$in</td><td>$out</td><td>$cache</td>...
    按上下文长度分档的行不纳入（当前产品只跟踪统一计价模型）。"""
    out = {}
    for m in re.finditer(r'<tr><td>([^<]+?)\s*(?:\((Off-Peak|Peak)\))?</td><td>\$([\d.]+)</td><td>\$([\d.]+)</td><td>\$([\d.]+)</td>', html):
        name, mode, inp, outp, cache = m.groups()
        name = name.strip()
        if "272K" in name:
            continue
        v = {"in": float(inp), "out": float(outp), "cache": float(cache)}
        d = out.setdefault(name, {"model": name, "valley": None, "peak": None})
        if mode == "Peak":
            d["peak"] = v
        else:
            d["valley"] = v
    return [v for v in out.values() if v["valley"]]


def fetch_commandcode(html):
    """commandcode.ai/docs/plans/goat 模型目录：tr 内 href=/models/xxx。
    谷价单元格结构为 <span...>$X<button（峰价只出现在 title/aria-label 提示里，不在此结构中）；
    峰 in/out 从提示 'peak $a / $b' 提取，缓存峰按官方结构 = 谷×2。"""
    out = []
    for tr in re.findall(r'<tr[\s\S]*?</tr>', html):
        m = re.search(r'href="/models/([a-z0-9-]+)"', tr)
        if not m:
            continue
        cells = re.findall(r'<span[^>]*>\$([\d.]+)<button', tr)
        if len(cells) < 3:
            continue
        valley = {"in": float(cells[0]), "out": float(cells[1]), "cache": float(cells[2])}
        peak = None
        tm = re.search(r'peak \$([\d.]+) / \$([\d.]+)', tr)
        if tm:
            peak = {"in": float(tm.group(1)), "out": float(tm.group(2)),
                    "cache": valley["cache"] * 2}
        out.append({"model": m.group(1), "valley": valley, "peak": peak})
    return out


def sanity_check(p):
    """合理性核验：价格为正、峰≥谷、字段完整。返回 (ok, 问题列表)。"""
    probs = []
    for k, v in p["valley"].items():
        if v is None or v <= 0:
            probs.append(f"谷价 {k} 非法: {v}")
    if p["peak"]:
        for k in ("in", "cache", "out"):
            v, b = p["valley"][k], p["peak"][k]
            if v is None or b is None or b < v - 1e-9:
                probs.append(f"峰价 {k} ({b}) < 谷价 ({v})")
    return (not probs, probs)


def diff_check(p, prev):
    """与库内最近快照偏差告警（>±30% 提示待核）+ 促销变化提示。"""
    warns = []
    if not prev:
        return ["首次快照（无历史对比）"]
    for k in ("in", "cache", "out"):
        nv = p["valley"].get(k)
        ov = prev.get("in_v" if k == "in" else ("cache_v" if k == "cache" else "out_v"))
        if nv is None or ov is None:
            continue
        d = (nv - ov) / ov * 100
        if abs(d) > 30:
            warns.append(f"谷{k} 变动 {d:+.0f}% (上次 {ov})")
    # 促销归一化（页面常带 "New · " 前缀等装饰词，与库内简写比较前先清洗）
    def norm_promo(s):
        s = (s or "").strip()
        for p in ("New · ", "NEW · "):
            if s.startswith(p):
                s = s[len(p):]
        return s
    if norm_promo(p.get("promo")) != norm_promo(prev.get("promo")):
        warns.append(f"促销: {prev.get('promo') or '无'} → {p.get('promo') or '无'}")
    return warns


# 抓取页面模型名 → 库内规范名
# 注意：官方已把旧名 deepseek-v4-flash 路由到 V4.1-Flash-1017，故页面上的旧名按 1017 归一；
# 历史 0731 线仍保留在库内，但不再由 fetch 自动映射（避免把新价写进旧模型线）。
MODEL_ALIASES = {
    "deepseek-v4.1-flash-1017": "deepseek-v4.1-flash-1017",
    "deepseek-v4.1-flash": "deepseek-v4.1-flash-1017",
    "deepseek-v4-1-flash": "deepseek-v4.1-flash-1017",
    "DeepSeek V4.1 Flash": "deepseek-v4.1-flash-1017",
    "DeepSeek V4.1 Flash (latest)": "deepseek-v4.1-flash-1017",
    "deepseek-v4-flash": "deepseek-v4.1-flash-1017",
    "DeepSeek V4 Flash": "deepseek-v4.1-flash-1017",
    "deepseek-v4-flash-0731": "deepseek-v4-flash-0731",
}


def alias_model(name):
    """精确匹配优先，其次前缀匹配（如 'DeepSeek V4.1 Flash (latest)'）。"""
    if name in MODEL_ALIASES:
        return MODEL_ALIASES[name]
    for k, v in MODEL_ALIASES.items():
        if name.startswith(k):
            return v
    return name


# 抓取平台参数 → 库内平台名（库内 Command Code 带空格、OpenCode 首字母大写）
PLATFORM_NAMES = {"commandcode": "Command Code", "opencode": "OpenCode", "ollama": "Ollama"}


def cmd_fetch(a):
    fetchers = {"ollama": ("https://ollama.com/pricing", fetch_ollama),
                "opencode": ("https://opencode.ai/docs/go", fetch_opencode),
                "commandcode": ("https://commandcode.ai/docs/plans/goat", fetch_commandcode)}
    if a.platform not in fetchers:
        sys.exit(f"未知平台：{a.platform}（可用：{'/'.join(fetchers)}）")
    url, parser = fetchers[a.platform]
    print(f"[1/3] 抓取 {url} …")
    html = http_get(url)
    print(f"[2/3] 解析 + 核验（{a.platform}）…")
    items = parser(html)
    if not items:
        print("[结果] 解析失败：页面结构可能已变化，请人工核对该平台页面")
        sys.exit(1)
    c = conn()
    for it in items:
        ok, probs = sanity_check(it)
        prev = None
        if a.with_prev:
            mkey = alias_model(it["model"])
            pname = PLATFORM_NAMES.get(a.platform, a.platform)
            r = c.execute("""SELECT * FROM snapshots WHERE platform=? AND model=? COLLATE NOCASE
                             ORDER BY captured_at DESC, id DESC LIMIT 1""", (pname, mkey)).fetchone()
            prev = dict(r) if r else None
        warns = diff_check(it, prev) if a.with_prev else []
        status = "PASS" if (ok and not [w for w in warns if "变动" in w]) else ("WARN" if ok else "FAIL")
        print(f"  [{status}] {it['model']}  谷 {it['valley']['in']}/{it['valley']['cache']}/{it['valley']['out']}"
              + (f"  峰 {it['peak']['in']}/{it['peak']['cache']}/{it['peak']['out']}" if it["peak"] else "")
              + ("  (无峰谷)" if not it["peak"] else ""))
        for p in probs + warns:
            print(f"          ⚠ {p}")
    print("[3/3] 完成。以上为核验通过的草稿（未写库）；确认后请用 add / 面板录入。")
    c.close()


def cmd_dump(a):
    c = conn()
    rows = c.execute("SELECT * FROM snapshots ORDER BY captured_at, platform, model, plan").fetchall()
    if not rows:
        print("（空）")
        return
    out = a.output or (Path(__file__).resolve().parent / "snapshots_export.csv")
    cols = [d[0] for d in c.execute("SELECT * FROM snapshots LIMIT 0").description]
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(dict(r))
    print(f"已导出 {len(rows)} 行 → {out}")


def main():
    ap = argparse.ArgumentParser(description="CheepSeek Radar CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add", help="录入一次价格快照")
    for name, dest, dflt in [("--date", "date", None), ("--platform", "platform", None), ("--plan", "plan", None),
                             ("--model", "model", None), ("--fee", "fee", None), ("--fee-ccy", "fee_ccy", "USD"),
                             ("--quota", "quota", None), ("--quota-ccy", "quota_ccy", "USD"), ("--window", "window", None),
                             ("--in", "inv", None), ("--cache", "cachev", None), ("--out", "outv", None),
                             ("--in-p", "inp", None), ("--cache-p", "cachep", None), ("--out-p", "outp", None),
                             ("--currency", "currency", "USD"), ("--promo", "promo", None),
                             ("--url", "url", None), ("--note", "note", None)]:
        p.add_argument(name, dest=dest, default=dflt)
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("latest", help="最新状态表")
    for name, dest in [("--platform", "platform"), ("--model", "model"), ("--plan", "plan")]:
        p.add_argument(name, dest=dest, default=None)
    p.set_defaults(fn=cmd_latest)

    p = sub.add_parser("diff", help="对比最近两轮快照")
    for name, dest in [("--platform", "platform"), ("--model", "model"), ("--plan", "plan")]:
        p.add_argument(name, dest=dest, default=None)
    p.set_defaults(fn=cmd_diff)

    p = sub.add_parser("history", help="某平台/模型时间线")
    for name, dest in [("--platform", "platform"), ("--model", "model")]:
        p.add_argument(name, dest=dest, default=None)
    p.set_defaults(fn=cmd_history)

    p = sub.add_parser("fetch", help="自动抓取+多维核验（对话内用，只出草稿不写库）")
    p.add_argument("--platform", required=True, help="ollama / opencode / commandcode")
    p.add_argument("--with-prev", action="store_true", help="与库内最近快照做偏差对比")
    p.set_defaults(fn=cmd_fetch)

    p = sub.add_parser("dump", help="导出 CSV")
    p.add_argument("-o", "--output", default=None)
    p.set_defaults(fn=cmd_dump)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
