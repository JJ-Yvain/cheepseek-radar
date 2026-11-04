# 维护手册 — 日常更新与发布流程

> 面向后续维护者（人类或 Agent）。发布通道只有一条：`main` 分支 → GitHub Actions → GitHub Pages。
> 本地管理环境与公开站点完全分离：数据与草稿只存在本机，公开内容全部经 `build_public.py` 产出。

## 一、三条日常流程

### 1. 更新价格数据（巡检后）

```
本地巡检（fetch → 核对 → monitor.py add / 面板录入）
  → python build_public.py        # 导出最新 site/data/*.json 并重建报告
  → 本地预览验收（monitor/server.py 打开面板 + site/ 抽查）
  → git add site/ && git commit && git push
  → Actions 自动部署（约 1 分钟），公网抽查榜单数字
```

要点：`plans.db` 永不出本机；只提交 `site/` 里的 JSON 产物。历史快照只追加，不覆盖。

### 2. 发布研究报告

```
本地写 reports/posts/<slug>.md（中文稿，status: draft）
  → 生成英文稿 <slug>.en.md（保留数据/事实/引用/结论，仅翻译）
  → python reports/build.py --preview   # 本地预览，含草稿
  → 【用户确认内容】
  → 在 .gitignore 中为两份稿件加白名单豁免：
      !reports/posts/<slug>.md
      !reports/posts/<slug>.en.md
  → 把两稿的 status 改为 published
  → python build_public.py  →  git add -A && git commit && git push
```

要点：`reports/posts/*` 默认不入仓库（草稿隔离靠 .gitignore 白名单，不靠 build 参数）；
未走白名单豁免的稿件绝不会出现在公开仓库或公开站点。

### 3. 更新网站功能

```
本地开发 → 面板与 site/ 双重验收 → 用户确认 → build_public.py → commit && push
```

要点：不要让未验收的实验改动混进发布提交；功能改动同时保持中英文与三主题可用。

## 二、发布机制速查

| 项 | 值 |
|---|---|
| 托管 | GitHub Pages（Actions 构建，`deploy-pages.yml`） |
| 部署内容 | 仓库内 `site/` 目录（本地构建后提交，CI 不做构建） |
| 触发 | push 到 `main`（或手动 workflow_dispatch） |
| 线上地址 | `https://jj-yvain.github.io/cheepseek-radar/` |
| 数据来源 | `site/data/snapshots.json` + `meta.json`（与本地 /api 同构） |
| 只读开关 | `site/index.html` 头部注入 `window.CSR_PUBLIC = true` |

## 三、回退

任一次发布有问题：`git revert <commit> && git push` 即回滚站点（纯静态，秒级生效）。
本机另有 `archive/回退点历史/repo-backup-before-public.bundle` 保存公开化之前的完整本地历史。

## 四、底线

- 凭据、plans.db、HANDOFF.md、archive/、报告草稿：**永不入库**（.gitignore 已固化）。
- 源代码 source-available、无开源许可证；原创报告 All Rights Reserved（见 `COPYRIGHT.md`，改授权前须与权利人确认）。
- 发布前若改了面板/报告构建，必须重跑 `build_public.py`——站点不会自动从源码生成。
