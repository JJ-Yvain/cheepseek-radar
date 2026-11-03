# 研究报告系统

报告系统把 `reports/posts/*.md` 渲染成可直接静态托管的 HTML。本地预览、未来 GitHub Pages 发布共用同一套页面实现，报告页本身不依赖 Python 服务运行。

## 目录

```text
reports/
├─ posts/                  # Markdown 源文件（一篇报告 = 一个 .md）
├─ assets/                 # 图片、样式等静态资源
│  ├─ report.css
│  └─ demo-price-comparison.svg
├─ build.py                # 静态生成器
├─ dist/                   # 生成产物（构建时重建，不手改）
└─ README.md
```

## 新增一篇报告

1. 在 `reports/posts/` 新建 Markdown 文件，例如 `my-report.md`。
2. 写入 front matter 与正文：

```markdown
---
title: "报告标题"
slug: my-report
summary: "一两句话说明这篇报告回答什么问题。"
author: CheepSeek Radar
date: 2026-11-03
updated: 2026-11-03
data_snapshot: 2026-11-02
status: draft
tags: [DeepSeek, 价格口径]
sources:
  - label: 来源名称
    url: https://example.com/source
    date: 2026-11-02
related:
  - label: 数据台 · 全部快照
    url: ../#dataSheet
---

正文从这里开始。
```

3. 启动本地服务，打开 `http://127.0.0.1:8765/reports/`。服务检测到报告请求时会自动重建预览产物。
4. 确认内容与排版后，把 `status` 改成 `published`，再执行公开发布构建：

```bash
python reports/build.py
```

## 草稿与发布

| 状态 | 本地预览 | 公开发布构建 |
|---|---|---|
| `status: draft` | 显示，带「草稿」标记与预览提示 | **排除**，不会出现在 `dist/` |
| `status: published` | 显示 | 包含 |

- 未写 `status` 时默认按 `draft` 处理。
- 公开发布构建会**先清空 `reports/dist/`**，因此不会残留上一次预览生成的草稿页。
- 草稿页面顶部有「仅本地预览」提示；列表页也有草稿徽章。
- 当前演示报告 `deepseek-coding-plan-2026-11.md` 为 `draft`，等待确认后再改为 `published`。

## 本地预览

### 通过监控台（推荐）

```bash
cd monitor
python server.py --port 8765 --open
```

打开 `http://127.0.0.1:8765/reports/`。报告路由会调用 `reports/build.py --preview`，修改 Markdown 后刷新页面即可看到更新。

### 只构建、不启动服务

```bash
python reports/build.py --preview
# 输出：reports/dist/
```

可用任意静态服务器托管 `reports/dist/`，例如：

```bash
python -m http.server 8000 --directory reports/dist
```

## 公开发布构建

```bash
python reports/build.py
```

- 只包含 `status: published` 的报告。
- 输出 `reports/dist/index.html`、文章 HTML 与 `assets/`。
- 未来接入 GitHub Pages 时，发布 `reports/dist/` 即可；当前不做部署配置。
- 报告页的「榜单 / 数据台」导航使用 `../` 回到站点根目录，因此假设面板部署在同一站点根下；单独托管 `dist/` 时这两个入口会指向上级目录。

## Markdown 支持

- 多级标题（`#` ~ `######`），自动生成文内目录（h2 / h3）
- 段落、粗体、斜体、删除线、行内代码
- 有序 / 无序列表，支持一层嵌套
- 引用、链接、图片
- 表格（GFM 风格，窄屏可横向滚动）
- 围栏代码块（```lang）
- 分隔线
- 图片单独成段时渲染为 `<figure>`，图片 `title` 作为图注

## 图片与链接

- 图片放 `reports/assets/`，Markdown 中写 `assets/文件名`；构建时会复制到 `dist/assets/`。
- 站内链接使用相对路径：
  - 榜单：`../#hero`
  - 数据台：`../#dataSheet`
  - 报告目录：`./`
- 外部来源链接会自动加 `target="_blank"` 与 `rel="noopener noreferrer"`。
- 引用价格时必须写明快照日期，避免把历史数据当成当前价。

## Front matter 字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `title` | 是 | 文章标题 |
| `slug` | 建议 | 输出文件名；缺省用 Markdown 文件名 |
| `summary` | 建议 | 列表页摘要与页面描述 |
| `author` | 否 | 默认 `CheepSeek Radar` |
| `date` | 是 | 发布日期 `YYYY-MM-DD` |
| `updated` | 否 | 修订日期，默认同 `date` |
| `data_snapshot` | 建议 | 引用的数据快照日期，显示在文章头部 |
| `status` | 是 | `draft` / `published`；缺省为 `draft` |
| `tags` | 否 | 标签数组 |
| `sources` | 否 | `label` / `url` / `date` 列表，渲染为「参考来源」 |
| `related` | 否 | `label` / `url` 列表，渲染为「相关数据」 |

## 注意

- 不要手改 `reports/dist/`；它会在每次构建时被重建。
- 报告页不使用 JavaScript 渲染正文；所有内容在构建时生成，静态托管可用。
- 新增或修改 `reports/build.py` 后，先跑一次 `--preview`，确认列表、文章、图片与表格都正常。
