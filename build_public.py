#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CheepSeek Radar 公共站点构建器

把本地维护环境（SQLite + 本地面板 + 报告源文件）发布为纯静态只读站点 site/：

  python build_public.py                # 公开构建（报告排除草稿）
  python build_public.py --preview-reports   # 调试用：报告含草稿

产物布局（GitHub Pages 根目录直接指向 site/）：
  site/index.html        只读面板（window.CSR_PUBLIC=true，数据来自 data/*.json）
  site/data/*.json       由 plans.db 导出的快照与元数据（与 /api 同构）
  site/reports/          reports/build.py 的静态产物（含 en/）
  site/poster.html       独立海报页
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / "monitor" / "plans.db"
MONITOR = ROOT / "monitor"
REPORTS = ROOT / "reports"
SITE = ROOT / "site"


def export_data() -> tuple[list[dict], dict]:
    """从 plans.db 导出与 /api/snapshots、/api/meta 同构的 JSON 数据。"""
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    snaps = [dict(r) for r in conn.execute(
        "SELECT * FROM snapshots ORDER BY captured_at DESC, id DESC")]
    platforms = sorted({s["platform"] for s in snaps if s["platform"]})
    models = sorted({s["model"] for s in snaps if s["model"]})
    plans = sorted({s["plan"] for s in snaps if s["plan"]})
    pbp: dict[str, list] = {}
    for s in snaps:
        if s["platform"] and s["plan"]:
            pbp.setdefault(s["platform"], [])
            if s["plan"] not in pbp[s["platform"]]:
                pbp[s["platform"]].append(s["plan"])
    for k in pbp:
        pbp[k].sort()
    meta = {"platforms": platforms, "models": models,
            "plans": plans, "plans_by_platform": pbp}
    return snaps, meta


def build_site(preview_reports: bool = False) -> None:
    snaps, meta = export_data()
    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "data").mkdir(parents=True)
    (SITE / "data" / "snapshots.json").write_text(
        json.dumps(snaps, ensure_ascii=False), encoding="utf-8")
    (SITE / "data" / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    # 只读面板：在 </head> 前注入 PUBLIC 标志（主脚本运行前生效）
    panel = (MONITOR / "panel.html").read_text(encoding="utf-8")
    marker = "</head>"
    assert marker in panel, "panel.html 缺少 </head> 锚点"
    panel_public = panel.replace(
        marker, "<script>window.CSR_PUBLIC = true;</script>\n" + marker, 1)
    (SITE / "index.html").write_text(panel_public, encoding="utf-8")

    for name in ("favicon.svg", "favicon.ico", "apple-touch-icon.png", "poster.html"):
        src = MONITOR / name
        if src.exists():
            shutil.copy2(src, SITE / name)

    # 报告：公开构建排除草稿；--preview-reports 供调试
    cmd = [sys.executable, str(REPORTS / "build.py")]
    if preview_reports:
        cmd.append("--preview")
    subprocess.run(cmd, check=True)
    shutil.copytree(REPORTS / "dist", SITE / "reports")

    mode = "预览（含草稿）" if preview_reports else "公开（排除草稿）"
    print(f"site/ 构建完成：{len(snaps)} 条快照 / {len(meta['platforms'])} 平台；报告 {mode}")


def main() -> None:
    ap = argparse.ArgumentParser(description="CheepSeek Radar 公共站点构建器")
    ap.add_argument("--preview-reports", action="store_true",
                    help="报告构建包含草稿（调试用；公开发布不要加）")
    args = ap.parse_args()
    build_site(args.preview_reports)


if __name__ == "__main__":
    main()
