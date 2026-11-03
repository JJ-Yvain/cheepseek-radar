#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CheepSeek Radar 报告生成器

把 reports/posts/*.md 渲染为可直接静态托管的 HTML（中英双语）：

  python reports/build.py --preview     # 本地预览（包含 status: draft）
  python reports/build.py               # 公开发布构建（只包含 status: published）

语言判定：文件名 *.en.md 为英文（lang="en"），其余为中文；front matter 的
lang 字段仅作校验（与文件名判定冲突时以文件名为准）。同一 slug 的中英稿
（X.md 与 X.en.md）互为对照翻译，页面头部提供语言切换链接。

输出目录：reports/dist/
  - index.html          报告目录（中文）
  - <slug>.html         文章页（中文）
  - en/index.html       报告目录（英文）
  - en/<slug>.html      文章页（英文）
  - assets/             样式、图片、站点图标

Markdown 支持：多级标题、段落、列表、引用、链接、图片、表格、围栏代码块、
行内代码、粗体、斜体、删除线与分隔线。报告页不依赖本地 Python 服务运行。
"""
from __future__ import annotations

import argparse
import html
import re
import shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent
POSTS = BASE / "posts"
ASSETS = BASE / "assets"
DEFAULT_OUT = BASE / "dist"

SITE_TITLE = {
    "zh": "研究报告 · CheepSeek Radar",
    "en": "Research Reports · CheepSeek Radar",
}
SITE_DESC = {
    "zh": "CheepSeek Radar 的研究报告：模型套餐价格、订阅额度与每亿 token 口径。",
    "en": "CheepSeek Radar research reports: model plan pricing, quotas and the per-100M-token basis.",
}

# 站点根相对前缀：zh 页面在 dist/ 根（站点根在上一级），en 页面在 dist/en/（上一级再退一级）。
ROOT = {"zh": "../", "en": "../../"}

# UI 文案表：值可能包含 HTML 与 {root}/{n}/{date} 占位符；组装一律用 .replace()
# （ui_value），不要用 str.format，避免与 HTML/URL 中的花括号冲突。含 HTML 的值
# 插入模板时保持原样，不做二次转义。
UI: dict[str, dict[str, str]] = {
    "zh": {
        "html.lang": "zh-CN",
        "lang.toggle": "EN",
        "brand.sub": "模型套餐性价比",
        "nav.aria": "主导航",
        "nav.radar": "榜单",
        "nav.data": "数据台",
        "nav.reports": "报告",
        "index.h1": "研究报告",
        "index.lede": "把模型套餐的价格拆开看：额度、峰谷、缓存与窗口限制，最后都落到同一个可比较的口径。",
        "index.nReports": "篇报告",
        "index.latestLab": "最新发表",
        "index.dirLabel": "目录",
        "index.dateLabel": "按发布日期",
        "preview.note": "本地预览 · 含 {n} 篇草稿；公开发布构建会自动排除草稿。",
        "draft.tag": "草稿",
        "draft.note": "仅本地预览，不会进入公开发布产物",
        "article.by": "作者",
        "article.published": "发表",
        "article.revised": "修订",
        "article.snap": "数据快照",
        "article.reading": "约 {n} 分钟",
        "article.backKicker": "← 研究报告",
        "article.back": "← 返回报告目录",
        "article.footNote": "本文引用的价格为标注日期的快照，不随实时数据更新。当前数据以 CheepSeek Radar 数据台为准。",
        "toc.title": "本文目录",
        "toc.mobileSummary": "本文目录",
        "sources.h": "参考来源",
        "sources.fallback": "来源",
        "sources.accessed": "访问 {date}",
        "sources.note": "来源页面可能随平台更新；本文只对标注快照日期的数据负责。",
        "related.h": "相关数据",
        "related.fallback": "相关数据",
        "empty.h": "暂无已发布报告。",
        "empty.sub": "在 reports/posts/ 新建 Markdown，把 status 改为 published 后重新构建。",
        "foot.left": "© 2026 CheepSeek Radar · 原创研究报告，保留所有权利",
        "foot.right": "价格与额度以标注快照日期为准；当前数据见 <a href=\"{root}#dataSheet\">数据台</a>。",
        "foot.copy": "欢迎分享原文链接；未经授权不得转载或改编。",
    },
    "en": {
        "html.lang": "en",
        "lang.toggle": "中文",
        "brand.sub": "AI Coding-Plan Value",
        "nav.aria": "Main navigation",
        "nav.radar": "Ranking",
        "nav.data": "Data",
        "nav.reports": "Reports",
        "index.h1": "Research Reports",
        "index.lede": "Tear down model-plan pricing: quota, peak/valley, caching and rate limits — normalized to one comparable basis.",
        "index.nReports": "Reports",
        "index.latestLab": "Latest",
        "index.dirLabel": "Index",
        "index.dateLabel": "By date",
        "preview.note": "Local preview · includes {n} draft(s); drafts are excluded from public builds.",
        "draft.tag": "Draft",
        "draft.note": "Local preview only; excluded from public builds",
        "article.by": "By",
        "article.published": "Published",
        "article.revised": "Revised",
        "article.snap": "Data snapshot",
        "article.reading": "~{n} min read",
        "article.backKicker": "← Research reports",
        "article.back": "← Back to all reports",
        "article.footNote": "Prices quoted in this article are snapshots as of their noted dates and do not update in real time. For current data, see the <a href=\"{root}#dataSheet\">CheepSeek Radar data sheet</a>.",
        "toc.title": "On this page",
        "toc.mobileSummary": "On this page",
        "sources.h": "Sources",
        "sources.fallback": "Source",
        "sources.accessed": "accessed {date}",
        "sources.note": "Source pages may change over time; this article stands by the data as of its noted snapshot date.",
        "related.h": "Related",
        "related.fallback": "Related",
        "empty.h": "No published reports yet.",
        "empty.sub": "Add Markdown under reports/posts/ and set status to published, then rebuild.",
        "foot.left": "© 2026 CheepSeek Radar · Original research reports, all rights reserved",
        "foot.right": "Prices and quotas are as of each article's snapshot date; current data in the <a href=\"{root}#dataSheet\">data sheet</a>.",
        "foot.copy": "Sharing the original link is welcome; reproduction or adaptation requires authorization.",
    },
}


def ui_value(lang: str, key: str, **subs: str) -> str:
    """取 UI 文案并替换占位符；值可能含 HTML，调用方不得再转义。"""
    text = UI[lang][key]
    for name, value in subs.items():
        text = text.replace("{" + name + "}", value)
    return text


def localize_body_html(body_html: str, lang: str) -> str:
    """en 页面位于 dist/en/，比 dist/ 根深一层：正文图片与指向站点根的
    相对链接（written for zh depth）需要多退一级。"""
    if lang != "en":
        return body_html
    body_html = body_html.replace('src="assets/', 'src="../assets/')
    body_html = body_html.replace('href="../#', 'href="../../#')
    return body_html


# ---------------- 文本与链接 ----------------

def esc_text(value: str) -> str:
    return html.escape(str(value), quote=False)


def safe_url(value: str) -> str:
    url = html.unescape(str(value)).strip()
    if re.match(r"(?i)^\s*(javascript|data|vbscript):", url):
        return "#"
    return html.escape(url, quote=True)


def inline(text: str) -> str:
    """行内 Markdown：代码、图片、链接、粗体、斜体、删除线。"""
    codes: list[str] = []
    images: list[str] = []
    links: list[str] = []

    def stash_code(m: re.Match) -> str:
        codes.append(html.escape(m.group(1), quote=False))
        return f"\x01C{len(codes) - 1}\x01"

    text = re.sub(r"`([^`]+)`", stash_code, text)

    def stash_image(m: re.Match) -> str:
        alt = html.escape(m.group(1), quote=True)
        src = safe_url(m.group(2))
        title = m.group(3)
        title_attr = f' title="{html.escape(title, quote=True)}"' if title else ""
        images.append(f'<img src="{src}" alt="{alt}"{title_attr} loading="lazy">')
        return f"\x01I{len(images) - 1}\x01"

    text = re.sub(r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)', stash_image, text)

    def stash_link(m: re.Match) -> str:
        label = inline(m.group(1))
        url = safe_url(m.group(2))
        title = m.group(3)
        title_attr = f' title="{html.escape(title, quote=True)}"' if title else ""
        ext = ' target="_blank" rel="noopener noreferrer"' if re.match(r"(?i)^https?://", url) else ""
        links.append(f'<a href="{url}"{title_attr}{ext}>{label}</a>')
        return f"\x01L{len(links) - 1}\x01"

    text = re.sub(r'\[([^\]]+)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)', stash_link, text)
    text = html.escape(text, quote=False)

    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__([^_]+)__", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"<em>\1</em>", text)
    text = re.sub(r"~~([^~]+)~~", r"<del>\1</del>", text)

    for i, value in enumerate(codes):
        text = text.replace(f"\x01C{i}\x01", f"<code>{value}</code>")
    for i, value in enumerate(images):
        text = text.replace(f"\x01I{i}\x01", value)
    for i, value in enumerate(links):
        text = text.replace(f"\x01L{i}\x01", value)
    return text


def is_cjk(ch: str) -> bool:
    return bool(ch) and "\u4e00" <= ch <= "\u9fff"


def join_paragraph(lines: list[str]) -> str:
    """中文段落内换行不插入空格，英文换行保留空格。"""
    if not lines:
        return ""
    out = lines[0].strip()
    for nxt in lines[1:]:
        nxt = nxt.strip()
        if not nxt:
            continue
        if out and (is_cjk(out[-1]) or is_cjk(nxt[0])):
            out += nxt
        else:
            out += " " + nxt
    return out


# ---------------- 块级 Markdown ----------------

def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def is_list_line(line: str) -> bool:
    return bool(re.match(r"^\s*([-*+]|\d+\.)\s+", line))


def split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [cell.strip() for cell in s.split("|")]


def is_table_sep(line: str) -> bool:
    cells = split_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def starts_block(lines: list[str], i: int) -> bool:
    line = lines[i]
    if not line.strip():
        return True
    if re.match(r"^\s*(```|~~~)", line):
        return True
    if re.match(r"^#{1,6}\s+", line):
        return True
    if re.match(r"^\s*([-*_])(?:\s*\1){2,}\s*$", line):
        return True
    if re.match(r"^\s*>\s?", line):
        return True
    if is_list_line(line):
        return True
    if i + 1 < len(lines) and "|" in line and is_table_sep(lines[i + 1]):
        return True
    return False


def render_table(lines: list[str], i: int) -> tuple[str, int]:
    header = split_row(lines[i])
    i += 1
    seps = split_row(lines[i])
    i += 1
    aligns = []
    for sep in seps:
        sep = sep.strip()
        if sep.startswith(":") and sep.endswith(":"):
            aligns.append("center")
        elif sep.endswith(":"):
            aligns.append("right")
        else:
            aligns.append("left")

    rows = []
    while i < len(lines) and lines[i].strip() and "|" in lines[i]:
        rows.append(split_row(lines[i]))
        i += 1

    width = max([len(header)] + [len(row) for row in rows])
    header += [""] * (width - len(header))
    for row in rows:
        row += [""] * (width - len(row))

    def align(idx: int) -> str:
        return aligns[idx] if idx < len(aligns) else "left"

    th = "".join(
        f'<th style="text-align:{align(j)}">{inline(cell)}</th>'
        for j, cell in enumerate(header)
    )
    body = ""
    for row in rows:
        body += "<tr>" + "".join(
            f'<td style="text-align:{align(j)}">{inline(cell)}</td>'
            for j, cell in enumerate(row)
        ) + "</tr>"
    return f'<div class="table-wrap"><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>', i


def render_list(lines: list[str], i: int) -> tuple[str, int]:
    base = indent_of(lines[i])
    ordered = bool(re.match(r"^\s*\d+\.\s+", lines[i]))
    tag = "ol" if ordered else "ul"
    items: list[str] = []
    n = len(lines)

    while i < n:
        line = lines[i]
        if not line.strip():
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            if j < n and is_list_line(lines[j]) and indent_of(lines[j]) >= base:
                i = j
                continue
            break
        m = re.match(r"^(\s*)([-*+]|\d+\.)\s+(.*)$", line)
        if not m:
            break
        indent = len(m.group(1))
        if indent < base:
            break
        if indent > base:
            sub, i = render_list(lines, i)
            if items:
                items[-1] += sub
            else:
                items.append(sub)
            continue

        content = m.group(3).strip()
        i += 1
        cont: list[str] = []
        while i < n:
            nxt = lines[i]
            if not nxt.strip():
                break
            if is_list_line(nxt) and indent_of(nxt) <= base:
                break
            if indent_of(nxt) > base and not is_list_line(nxt):
                cont.append(nxt.strip())
                i += 1
                continue
            break
        if cont:
            content += " " + join_paragraph(cont)
        items.append(inline(content))

    return f"<{tag}>" + "".join(f"<li>{item}</li>" for item in items) + f"</{tag}>", i


def slugify(text: str, used: dict[str, int]) -> str:
    plain = re.sub(r"<[^>]+>", "", text)
    slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", plain.lower()).strip("-")
    slug = slug or "section"
    used[slug] = used.get(slug, 0) + 1
    return slug if used[slug] == 1 else f"{slug}-{used[slug]}"


def render_blocks(lines: list[str], toc: list[tuple[int, str, str]], used: dict[str, int]) -> str:
    out: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        fence = re.match(r"^\s*(```|~~~)\s*([\w+-]*)\s*$", line)
        if fence:
            marker, lang = fence.group(1), fence.group(2)
            i += 1
            buf: list[str] = []
            while i < n and not re.match(rf"^\s*{re.escape(marker)}\s*$", lines[i]):
                buf.append(lines[i])
                i += 1
            if i < n:
                i += 1
            cls = f' class="language-{html.escape(lang, quote=True)}"' if lang else ""
            out.append(f'<pre><code{cls}>{html.escape(chr(10).join(buf), quote=False)}</code></pre>')
            continue

        heading = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if heading:
            level = len(heading.group(1))
            text = heading.group(2).strip()
            hid = slugify(text, used)
            out.append(f'<h{level} id="{hid}">{inline(text)}</h{level}>')
            if level in (2, 3):
                plain = re.sub(r"[*_`\[\]]", "", text)
                toc.append((level, plain, hid))
            i += 1
            continue

        if re.match(r"^\s*([-*_])(?:\s*\1){2,}\s*$", line):
            out.append("<hr>")
            i += 1
            continue

        if i + 1 < n and "|" in line and is_table_sep(lines[i + 1]):
            table, i = render_table(lines, i)
            out.append(table)
            continue

        if re.match(r"^\s*>\s?", line):
            buf = []
            while i < n and re.match(r"^\s*>\s?", lines[i]):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append("<blockquote>" + render_blocks(buf, toc, used) + "</blockquote>")
            continue

        if is_list_line(line):
            block, i = render_list(lines, i)
            out.append(block)
            continue

        buf = []
        while i < n and lines[i].strip() and not starts_block(lines, i):
            buf.append(lines[i])
            i += 1
        if not buf:
            i += 1
            continue
        paragraph = join_paragraph(buf)
        figure = re.fullmatch(r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)', paragraph)
        if figure:
            alt = html.escape(figure.group(1), quote=True)
            src = safe_url(figure.group(2))
            caption = figure.group(3) or figure.group(1)
            caption_html = f"<figcaption>{inline(caption)}</figcaption>" if caption else ""
            out.append(f'<figure><img src="{src}" alt="{alt}" loading="lazy">{caption_html}</figure>')
        else:
            out.append(f"<p>{inline(paragraph)}</p>")

    return "\n".join(out)


# ---------------- Front matter ----------------

def parse_scalar(value: str):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        inside = value[1:-1].strip()
        if not inside:
            return []
        return [item.strip().strip("\"'") for item in inside.split(",") if item.strip()]
    return value


def parse_front_matter(text: str) -> tuple[dict, str]:
    text = text.lstrip("\ufeff")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, text

    data: dict = {}
    key = None
    item = None
    for raw in lines[1:end]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if indent == 0:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key, value = key.strip(), value.strip()
            if value == "":
                data[key] = []
                item = None
            else:
                data[key] = parse_scalar(value)
                key, item = None, None
            continue
        if key is None:
            continue
        if line.startswith("- "):
            rest = line[2:].strip()
            item = {}
            if ":" in rest:
                k, v = rest.split(":", 1)
                item[k.strip()] = parse_scalar(v)
            else:
                item = None
                data[key].append(parse_scalar(rest))
            if item is not None:
                data[key].append(item)
        elif item is not None and ":" in line:
            k, v = line.split(":", 1)
            item[k.strip()] = parse_scalar(v)

    body = "\n".join(lines[end + 1:]).lstrip("\n")
    return data, body


def reading_minutes(text: str) -> int:
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    words = len(re.findall(r"[A-Za-z0-9]+", text))
    return max(1, round(cjk / 400 + words / 220))


def load_post(path: Path) -> dict:
    # 语言判定以文件名为准：X.en.md → en，其余 → zh
    lang = "en" if path.name.endswith(".en.md") else "zh"
    raw = path.read_text(encoding="utf-8")
    meta, body_md = parse_front_matter(raw)

    # front matter 的 lang 字段仅作校验；冲突时以文件名为准
    meta_lang = str(meta.get("lang") or "").strip().lower()
    if meta_lang and meta_lang != lang:
        print(f"警告：{path.name} front matter lang={meta_lang} 与文件名判定（{lang}）不一致，以文件名为准。")

    # slug：中英稿共享同一 slug —— en 文件 X.en.md 的默认 slug 去掉 .en 后缀
    stem = path.stem[:-3] if path.stem.endswith(".en") else path.stem
    slug = str(meta.get("slug") or stem)
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", slug).strip("-") or stem

    toc: list[tuple[int, str, str]] = []
    used: dict[str, int] = {}
    body_html = localize_body_html(render_blocks(body_md.splitlines(), toc, used), lang)

    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    tags = [str(tag).strip() for tag in tags if str(tag).strip()]

    sources = [s for s in (meta.get("sources") or []) if isinstance(s, dict)]
    related = [r for r in (meta.get("related") or []) if isinstance(r, dict)]

    date = str(meta.get("date") or "1970-01-01")
    status = "published" if str(meta.get("status") or "draft").lower() == "published" else "draft"

    return {
        "source": path.name,
        "lang": lang,
        "slug": slug,
        "title": str(meta.get("title") or stem),
        "summary": str(meta.get("summary") or ""),
        "author": str(meta.get("author") or "CheepSeek Radar"),
        "date": date,
        "updated": str(meta.get("updated") or date),
        "data_snapshot": str(meta.get("data_snapshot") or ""),
        "status": status,
        "tags": tags,
        "sources": sources,
        "related": related,
        "body_html": body_html,
        "toc": toc,
        "reading": reading_minutes(body_md),
    }


def load_posts(preview: bool) -> dict[str, list[dict]]:
    """按语言分组加载文章：{"zh": [...], "en": [...]}，各自按日期倒序。"""
    grouped: dict[str, list[dict]] = {"zh": [], "en": []}
    if not POSTS.exists():
        return grouped
    for path in sorted(POSTS.glob("*.md")):
        post = load_post(path)
        if preview or post["status"] == "published":
            grouped[post["lang"]].append(post)
    for posts in grouped.values():
        posts.sort(key=lambda p: (p["date"], p["title"]), reverse=True)
    return grouped


# ---------------- 页面 ----------------

# 主题（Light / Dark / System）：与监控台/海报共用 localStorage csr_theme。
# 纯字面量常量（内部含大括号，不能直接写进 f-string），page_shell 原样插值。

# <head> 预读脚本：尽早按 csr_theme（默认 system）设 data-theme，避免深色用户首帧闪白
THEME_PREREAD = """<script>
/* 主题偏好预读：localStorage csr_theme（light/dark/system）> system；越早执行越少闪烁 */
  (function () {
    var v = "system";
    try { v = localStorage.getItem("csr_theme") || "system"; } catch (e) {}
    if (v !== "light" && v !== "dark" && v !== "system") v = "system";
    var eff = v === "system" ? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : v;
    var h = document.documentElement;
    h.setAttribute("data-theme", eff);
    h.setAttribute("data-theme-pref", v);
    h.style.colorScheme = eff;
    if (v === "system") h.setAttribute("data-theme-sys", matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  })();
</script>"""

# 导航内的三态主题切换器
THEME_SW = """<span class="theme-sw">
      <button type="button" id="themeBtn" title="主题：浅色 → 深色 → 跟随系统 / Theme: light → dark → system" aria-label="切换主题 / Switch theme">☀</button>
    </span>"""

# 页尾脚本：应用主题 / 切换器点击落库 / 跟随系统偏好变化
THEME_INIT = """<script>
  (function () {
    "use strict";
    function applyTheme() {
      var pref = "system";
      try { pref = localStorage.getItem("csr_theme") || "system"; } catch (e) {}
      if (pref !== "light" && pref !== "dark" && pref !== "system") pref = "system";
      var mq = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
      var eff = pref === "system" ? (mq && mq.matches ? "dark" : "light") : pref;
      var h = document.documentElement;
      h.setAttribute("data-theme", eff);
      h.setAttribute("data-theme-pref", pref);
      h.style.colorScheme = eff;
      var b = document.getElementById("themeBtn");
      if (b) b.textContent = (pref === "dark") ? "☾" : (pref === "system" ? "◐" : "☀");
    }
    var tb = document.getElementById("themeBtn");
    if (tb) tb.addEventListener("click", function () {
      var pref = "system";
      try { pref = localStorage.getItem("csr_theme") || "system"; } catch (e) {}
      if (pref !== "light" && pref !== "dark" && pref !== "system") pref = "system";
      var next = (pref === "light") ? "dark" : (pref === "dark" ? "system" : "light");
      try { localStorage.setItem("csr_theme", next); } catch (err) {}
      applyTheme();
    });
    var mq = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
    if (mq) {
      var onChange = function () { applyTheme(); };
      if (mq.addEventListener) mq.addEventListener("change", onChange);
      else if (mq.addListener) mq.addListener(onChange);
    }
    applyTheme();
  })();
</script>"""


def render_toc(toc: list[tuple[int, str, str]], lang: str) -> str:
    if not toc:
        return ""
    items = "".join(
        f'<li class="toc-h{level}"><a href="#{hid}">{esc_text(text)}</a></li>'
        for level, text, hid in toc
    )
    title = esc_text(UI[lang]["toc.title"])
    return f'<p class="toc-title">{title}</p><ol class="toc-list">{items}</ol>'


def render_sources(sources: list[dict], lang: str) -> str:
    if not sources:
        return ""
    u = UI[lang]
    items = []
    for src in sources:
        label = esc_text(src.get("label") or src.get("url") or u["sources.fallback"])
        url = safe_url(src.get("url") or "")
        date = esc_text(src.get("date") or "")
        meta = f'<span class="src-date">{ui_value(lang, "sources.accessed", date=date)}</span>' if date else ""
        name = f'<a href="{url}" target="_blank" rel="noopener noreferrer">{label}</a>' if url and url != "#" else label
        items.append(f"<li>{name}{meta}</li>")
    return (
        f'<section class="block sources"><h3>{u["sources.h"]}</h3>'
        f'<ol class="source-list">{"".join(items)}</ol>'
        f'<p class="block-note">{u["sources.note"]}</p></section>'
    )


def render_related(items: list[dict], lang: str) -> str:
    if not items:
        return ""
    u = UI[lang]
    lis = []
    for item in items:
        label = esc_text(item.get("label") or u["related.fallback"])
        url = str(item.get("url") or "#")
        # en 文章页比 zh 深一层：front matter 里的站点根相对链接按 zh 深度书写，需多退一级
        if lang == "en" and url.startswith("../"):
            url = "../" + url
        url = safe_url(url)
        lis.append(f'<li><a href="{url}">{label}<span class="arrow">→</span></a></li>')
    return (
        f'<section class="block related"><h3>{u["related.h"]}</h3>'
        f'<ul class="related-list">{"".join(lis)}</ul></section>'
    )


def page_shell(title: str, description: str, content: str, lang: str, lang_href: str, active: str = "reports") -> str:
    """页面骨架。root 为站点根前缀（ROOT[lang]）；aroot 为静态资源前缀
    （assets/ 位于 dist/ 根，en 页面深一层需多退一级）。"""
    u = UI[lang]
    root = ROOT[lang]
    aroot = "" if lang == "zh" else "../"
    nav_reports = ' class="on" aria-current="page"' if active == "reports" else ""
    return f"""<!DOCTYPE html>
<html lang="{u['html.lang']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc_text(title)}</title>
<meta name="description" content="{html.escape(description, quote=True)}">
<meta name="color-scheme" content="light dark">
{THEME_PREREAD}
<link rel="icon" href="{aroot}assets/favicon.svg" type="image/svg+xml">
<link rel="icon" href="{aroot}assets/favicon.ico" sizes="16x16 32x32 48x48">
<link rel="apple-touch-icon" href="{aroot}assets/apple-touch-icon.png">
<link rel="stylesheet" href="{aroot}assets/report.css">
</head>
<body>
<header class="site-head">
  <div class="site-head-inner">
    <a class="brand" href="{root}">CheepSeek Radar<span>{u['brand.sub']}</span></a>
    <nav class="site-nav" aria-label="{u['nav.aria']}">
      <a href="{root}#top">{u['nav.radar']}</a>
      <a href="{root}#dataSheet">{u['nav.data']}</a>
      <a href="./"{nav_reports}>{u['nav.reports']}</a>
      <a class="lang-link" href="{lang_href}">{u['lang.toggle']}</a>
      {THEME_SW}
    </nav>
  </div>
</header>
{content}
<footer class="site-foot">
  <div class="site-foot-inner">
    <span>{u['foot.left']}</span>
    <span>{ui_value(lang, 'foot.right', root=root)}</span>
    <span>{u['foot.copy']}</span>
  </div>
</footer>
{THEME_INIT}
</body>
</html>
"""


def render_index(posts: list[dict], preview: bool, lang: str, lang_href: str) -> str:
    u = UI[lang]
    latest = posts[0]["date"] if posts else "—"
    drafts = [p for p in posts if p["status"] == "draft"]
    preview_note = ""
    if preview and drafts:
        preview_note = f'<p class="preview-note">{ui_value(lang, "preview.note", n=str(len(drafts)))}</p>'

    if posts:
        items = []
        for post in posts:
            tags = "".join(f'<span class="tag">{esc_text(tag)}</span>' for tag in post["tags"])
            badge = f'<span class="badge badge-draft">{u["draft.tag"]}</span>' if post["status"] == "draft" else ""
            items.append(
                f"""<li class="issue">
  <a href="{post['slug']}.html">
    <div class="issue-date"><time datetime="{esc_text(post['date'])}">{esc_text(post['date'])}</time>{badge}</div>
    <div class="issue-main">
      <div class="issue-tags">{tags}</div>
      <h2>{esc_text(post['title'])}</h2>
      <p>{esc_text(post['summary'])}</p>
      <div class="issue-meta">{esc_text(post['author'])} · {ui_value(lang, 'article.reading', n=str(post['reading']))}</div>
    </div>
  </a>
</li>"""
            )
        issue_list = f'<ol class="issue-list">{"".join(items)}</ol>'
    else:
        issue_list = (
            '<div class="empty">'
            f"<p>{u['empty.h']}</p>"
            f"<p class=\"empty-sub\">{u['empty.sub']}</p>"
            "</div>"
        )

    content = f"""<main class="page">
  <section class="masthead">
    <div class="masthead-main">
      <p class="kicker">CheepSeek Radar · Research Notes</p>
      <h1>{u['index.h1']}</h1>
      <p class="lede">{u['index.lede']}</p>
      {preview_note}
    </div>
    <div class="masthead-side">
      <div><span class="num">{len(posts)}</span><span class="lab">{u['index.nReports']}</span></div>
      <div><span class="num">{esc_text(latest)}</span><span class="lab">{u['index.latestLab']}</span></div>
    </div>
  </section>
  <section class="issue-index">
    <div class="index-label"><span>{u['index.dirLabel']}</span><span>{u['index.dateLabel']}</span></div>
    {issue_list}
  </section>
</main>"""
    return page_shell(SITE_TITLE[lang], SITE_DESC[lang], content, lang, lang_href)


def render_article(post: dict, preview: bool, lang_href: str) -> str:
    lang = post["lang"]
    u = UI[lang]
    root = ROOT[lang]

    draft_banner = ""
    if preview and post["status"] == "draft":
        draft_banner = (
            f'<div class="draft-banner"><strong>{u["draft.tag"]}</strong>'
            f"<span>{u['draft.note']}</span></div>"
        )

    tags = "".join(f'<span class="tag">{esc_text(tag)}</span>' for tag in post["tags"])
    meta = [
        f"<span>{u['article.by']} {esc_text(post['author'])}</span>",
        f"<span>{u['article.published']} {esc_text(post['date'])}</span>",
        f"<span>{u['article.revised']} {esc_text(post['updated'])}</span>",
    ]
    if post["data_snapshot"]:
        meta.append(f'<span class="snap">{u["article.snap"]} {esc_text(post["data_snapshot"])}</span>')

    toc = render_toc(post["toc"], lang)
    toc_aside = f'<aside class="toc" aria-label="{u["toc.title"]}">{toc}</aside>' if toc else '<div></div>'
    toc_mobile = f'<details class="toc-mobile"><summary>{u["toc.mobileSummary"]}</summary>{toc}</details>' if toc else ""

    content = f"""{draft_banner}<main class="page">
  <header class="article-head">
    <div class="article-kicker"><a href="./">{u['article.backKicker']}</a><span class="sep">/</span><time datetime="{esc_text(post['date'])}">{esc_text(post['date'])}</time></div>
    <h1>{esc_text(post['title'])}</h1>
    <p class="article-summary">{esc_text(post['summary'])}</p>
    <div class="article-meta">{''.join(meta)}</div>
    <div class="article-tags">{tags}</div>
  </header>
  <div class="article-layout">
    {toc_aside}
    <article class="article-body">
      {toc_mobile}
      {post['body_html']}
      {render_related(post['related'], lang)}
      {render_sources(post['sources'], lang)}
      <footer class="article-foot">
        <p>{ui_value(lang, 'article.footNote', root=root)}</p>
        <p><a href="./">{u['article.back']}</a></p>
      </footer>
    </article>
  </div>
</main>"""
    return page_shell(f"{post['title']} · CheepSeek Radar", post["summary"], content, lang, lang_href)


# ---------------- 构建 ----------------

def build(preview: bool = False, out_dir: Path | None = None) -> tuple[Path, list[dict]]:
    out = (Path(out_dir) if out_dir else DEFAULT_OUT).resolve()
    if BASE.resolve() not in out.parents:
        raise ValueError("输出目录必须位于 reports/ 内")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    assets_out = out / "assets"
    assets_out.mkdir(parents=True, exist_ok=True)
    if ASSETS.exists():
        for item in ASSETS.iterdir():
            if item.is_file():
                shutil.copy2(item, assets_out / item.name)
            elif item.is_dir():
                shutil.copytree(item, assets_out / item.name, dirs_exist_ok=True)
    for name in ("favicon.svg", "favicon.ico", "apple-touch-icon.png"):
        src = BASE.parent / "monitor" / name
        if src.exists():
            shutil.copy2(src, assets_out / name)

    grouped = load_posts(preview)
    zh_slugs = {p["slug"] for p in grouped["zh"]}
    en_slugs = {p["slug"] for p in grouped["en"]}

    # 中文：dist/index.html + dist/<slug>.html；语言切换 → 存在 en 对照稿则指向
    # en/<slug>.html，否则指向英文目录 en/（en 目录始终构建，含空状态页）。
    (out / "index.html").write_text(render_index(grouped["zh"], preview, "zh", "en/"), encoding="utf-8")
    for post in grouped["zh"]:
        slug = post["slug"]
        lang_href = f"en/{slug}.html" if slug in en_slugs else "en/"
        (out / f"{slug}.html").write_text(render_article(post, preview, lang_href), encoding="utf-8")

    # 英文：dist/en/index.html + dist/en/<slug>.html；语言切换 → 存在 zh 对照稿
    # 则指向 ../<slug>.html，否则指向中文目录 ../。
    (out / "en").mkdir(parents=True, exist_ok=True)
    (out / "en" / "index.html").write_text(render_index(grouped["en"], preview, "en", "../"), encoding="utf-8")
    for post in grouped["en"]:
        slug = post["slug"]
        lang_href = f"../{slug}.html" if slug in zh_slugs else "../"
        (out / "en" / f"{slug}.html").write_text(render_article(post, preview, lang_href), encoding="utf-8")

    return out, grouped["zh"] + grouped["en"]


def main() -> None:
    parser = argparse.ArgumentParser(description="CheepSeek Radar 报告生成器")
    parser.add_argument("--preview", action="store_true", help="包含 status: draft 的草稿")
    parser.add_argument("--out", default=None, help="输出目录（默认 reports/dist）")
    args = parser.parse_args()
    out, posts = build(args.preview, Path(args.out) if args.out else None)
    zh = [p for p in posts if p["lang"] == "zh"]
    en = [p for p in posts if p["lang"] == "en"]
    zh_drafts = sum(1 for p in zh if p["status"] == "draft")
    en_drafts = sum(1 for p in en if p["status"] == "draft")
    print(f"已生成 zh {len(zh)} 篇（草稿 {zh_drafts} 篇）+ en {len(en)} 篇（草稿 {en_drafts} 篇）→ {out}")
    if not args.preview:
        print("公开发布构建：已排除所有草稿。")


if __name__ == "__main__":
    main()
