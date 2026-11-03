# 架构说明 — CheepSeek Radar

> 面向维护者：讲清组件、数据模型、计价算法、API 与扩展点。产品定位见 `PRODUCT.md`，数据源规则见 `DATA-SOURCES.md`。

## 总览

```text
┌─────────────────────────────────────────────────────────┐
│ 浏览器                                                   │
│  panel.html（榜单 + 数据台 + 图文卡） / poster.html（海报） │
└───────────────┬─────────────────────────────────────────┘
                │ HTTP 127.0.0.1:8765
┌───────────────▼─────────────────────────────────────────┐
│ server.py  本地 REST 服务（Python 标准库）                │
│  · 单实例端口预检   · 心跳保活 / 空闲退出                  │
│  · 静态资源白名单   · snapshots / templates CRUD          │
└───────────────┬─────────────────────────────────────────┘
                │ sqlite3
┌───────────────▼─────────────────────────────────────────┐
│ plans.db   snapshots（快照，只追加） + templates（算法模板）│
└───────────────▲─────────────────────────────────────────┘
                │
┌───────────────┴─────────────────────────────────────────┐
│ monitor.py  CLI：add / latest / diff / history / dump    │
│             fetch：抓取平台页面 → 多维核验 → 草稿（不写库）│
└─────────────────────────────────────────────────────────┘
```

- **零依赖**：运行时只用 Python 标准库；前端为原生 HTML/CSS/JS，无构建步骤。
- **本地优先**：服务默认只绑定 `127.0.0.1`；数据不离开本机。
- **单实例**：启动前做端口预检，避免 Windows 下 `SO_REUSEADDR` 导致多实例叠加。

## 组件职责

| 组件 | 职责 |
|---|---|
| `monitor.py` | 数据层 CLI：录入快照、查看最新状态、对比最近两轮、导出 CSV、抓取草稿 |
| `monitor\server.py` | HTTP 层：静态页面、REST API、心跳、空闲退出、单实例；同时提供 `/reports/` 静态路由 |
| `monitor\panel.html` | 展示与交互：榜单、表格、筛选、排序、参数、图文卡、导出 |
| `monitor\poster.html` | 独立 3:4 海报（静态内容 + 导出） |
| `reports\build.py` | 报告静态生成器：Markdown → `reports\dist\` 的 HTML |
| `reports\posts\` | 报告 Markdown 源文件（front matter + 正文） |
| `reports\dist\` | 报告构建产物（列表、文章、assets），本地服务直接托管 |
| `plans.db` | 持久化：快照与模板 |
| `打开监控台.vbs` / `启动监控台.bat` | Windows 启动器：探测 Python、静默/诊断启动、打开浏览器 |

## 数据模型

### `snapshots`（一行 = 一次抓取的平台 × 模型 × 套餐）

| 字段 | 含义 |
|---|---|
| `id` | 自增主键 |
| `captured_at` | 抓取日期（`YYYY-MM-DD`） |
| `platform` | 平台名，如 `DeepSeek` / `Command Code` / `OpenCode` / `Ollama` |
| `plan` | 套餐名，如 `GOAT` / `Go` / `Pro` / `按量` |
| `model` | 模型线，如 `deepseek-v4.1-flash-1017` |
| `fee` / `fee_currency` | 月费及币种 |
| `quota` / `quota_currency` | 月额度及币种（订阅买额度型才有） |
| `window` | 窗口限制，如 `5h $20 / 7d $50 / 月 $100`、`月重置` |
| `in_v` / `cache_v` / `out_v` | 谷价：输入 / 缓存命中 / 输出（每 1M token） |
| `in_p` / `cache_p` / `out_p` | 峰价；无峰谷时为 `NULL` |
| `currency` | 价格币种（`USD` / `CNY`） |
| `promo` | 促销文本；无促销为 `NULL` |
| `source_url` | 数据来源 URL |
| `note` | 备注（版本待确认、口径说明等） |

索引：`idx_key(platform, model, plan, captured_at)`。

### `templates`（算法模板）

| 字段 | 含义 |
|---|---|
| `name` | 模板名 |
| `cache_rate` | 缓存读取占比（%，占全量 token） |
| `peak_pct` | 峰时段占比（%） |
| `input_pct` | 普通输入占比（%，占全量 token） |
| `output_pct` | 模型输出占比（%，占全量 token） |
| `input_share` | 旧字段：非缓存部分中的输入占比（仅兼容读取） |

三项占比合计 100%；新模板写 `input_pct/output_pct`，旧模板启动时自动从 `cache_rate + input_share` 迁移。

## 计价算法

### 1. 单 token 类型的峰谷加权价

```text
mix(price) = peakPct × peakPrice + (1 − peakPct) × valleyPrice
```

无峰谷时，峰价视为等于谷价。

### 2. 每 1 亿 token 按量价

```text
cacheF = params.cachePct / 100
inputF = params.inputPct / 100
outputF = params.outputPct / 100
（三项合计 100%）

per100M = (inputF × mix(in) + cacheF × mix(cache) + outputF × mix(out)) × 100
```

因为价表单位是「每 1M token」，乘 100 即得到「每 100M token」的价格。

### 3. 订阅渠道实际每亿价

```text
actualPer100M = per100M × (月费 / 月额度)
```

月费是成本，月额度是优惠；该口径衡量「实际付多少钱换多少 token」，用于购买决策。

### 4. 总额度与回本点

```text
capacity(亿/月) = 月额度(USD) / per100M(USD)
breakeven(亿/月) = 月费(USD) / per100M(USD)
```

回本点必须用**按量从价** `per100M`，不能用已含 `fee/quota` 的订阅实际每亿价。

### 5. 币种

- 所有金额先按快照原始币种记录；展示时用 `toDisp(v, origCcy)` 换算，排序与对比统一用 `toUSDBasis`。

### 默认参数与内置画像

| 预设 | 缓存读取 | 普通输入 | 模型输出 | 峰谷 |
|---|---:|---:|---:|---|
| 95/4/1 | 95% | 4% | 1% | 6:4 |
| 97/2.5/0.5 | 97% | 2.5% | 0.5% | 6:4 |
| 98/1.6/0.4 | 98% | 1.6% | 0.4% | 6:4 |

显示币种 / 汇率默认 USD / 6.65。三项占比均以全量 token 为分母，不是输入 token 的缓存命中率；这些是计算情景，不是经过普遍验证的真实平均。

### 图文卡参数隔离

- 打开单卡/双卡弹窗时，从全局 `params` 复制一份卡内 state。
- 卡内参数条修改 state 后重建卡片；构建期间临时把 `params` 指向卡内副本，构建结束立即恢复全局对象。
- 关闭弹窗不涉及全局参数；再次打开重新继承当前全局参数。
- 预览与导出读取同一个 `.c-card` DOM，导出前不会改参数。


## 榜单排序

头页按 `displayPer100M` 升序；同价时 `heroPriced` 三级 tie-break：

1. 优惠期更长者优先；
2. 窗口月额度更宽者优先；
3. 平台名。

官方直充作为「基准格」虚化呈现，不参与冠军竞争。

## 报告系统

报告页是**构建期生成的静态 HTML**，运行时不依赖 Python：

```text
reports/posts/*.md ── build.py ──> reports/dist/
                                   ├─ index.html
                                   ├─ <slug>.html
                                   └─ assets/
本地服务 GET /reports/ ── 预览构建（含 draft）──> 直接托管 dist
未来 GitHub Pages ── 发布构建（仅 published）──> 托管 dist
```

- 本地预览：`server.py` 在 `/reports/` 或 `.html` 请求时调用 `reports/build.py --preview`，包含 `status: draft`。
- 公开构建：`python reports/build.py` 默认只输出 `status: published`，并在构建前清空 `dist/`，避免草稿残留。
- 页面实现只有一套：列表、文章、样式均由同一生成器产出；本地与静态托管一致。
- Markdown 解析、front matter、目录、来源与相关数据渲染均在 `reports/build.py`。

静态路由：

| 路径 | 说明 |
|---|---|
| `GET /reports` | 302 → `/reports/` |
| `GET /reports/` | 报告列表 `dist/index.html` |
| `GET /reports/<slug>.html` | 文章页 |
| `GET /reports/assets/*` | 报告样式、图片、站点图标 |

## 变化对比

面板「变化」列不要求模型名完全相同，而是按 **平台 + 套餐 + 模型系列** 找上一轮：

- 系列规则（`panel.html` 的 `MODEL_SERIES_RULES`）：
  - `deepseek-v* -flash`（含 `0731` / `09-10` / `1017` 等版本）→ `deepseek-flash`
  - 未命中规则时退回精确模型名，避免误合并
- 当前活动数据只包含 DeepSeek 模型线；GLM 数据已于 2026-11-03 移除。
- 只比较当前画像下的**每亿价**（`displayPer100M` 换算到 USD 基准），不比较单项 token 价、月费或促销。
- 基准模型与当前行不同，显示「较上代」；悬浮明细给出对比模型、快照日期和前后每亿价。
- 「变化项」统计与头页「变化 N 项」均基于这一口径。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/snapshots?platform=&model=&plan=` | 快照列表（按抓取日倒序） |
| POST | `/api/snapshots` | 新增快照（JSON，字段同表） |
| PUT | `/api/snapshots/<id>` | 修改快照 |
| DELETE | `/api/snapshots/<id>` | 删除快照 |
| GET | `/api/templates` | 模板列表 |
| POST | `/api/templates` | 新增模板 |
| PUT | `/api/templates/<id>` | 修改模板 |
| DELETE | `/api/templates/<id>` | 删除模板 |
| GET | `/api/meta` | 平台 / 模型 / 套餐去重值（筛选用） |
| GET | `/api/ping` | 心跳（面板每 30 秒一次，不查库） |
| POST | `/api/shutdown` | 停止服务 |

静态资源只放行 `/favicon.svg`、`/favicon.ico`、`/apple-touch-icon.png` 三个固定路径，避免把目录内任意文件暴露出去。

## 数据流

### 巡检与录入（半自动）

```text
平台定价页
   │  fetch（ollama / opencode / commandcode）
   ▼
解析 + 多维核验：双通道解析交叉比对 / 正数 / 峰≥谷 / 字段完整
   │  与库内最近快照偏差 > ±30% 告警 / 促销变化提示
   ▼
草稿（不写库）→ 人工核对 → add 或面板录入 → 新快照
```

官方 API 无解析器，按页面人工核对后录入。

### 查看与导出

```text
plans.db → server API → panel.html
                         ├─ 头页榜单（模型 chip 切换）
                         ├─ 数据台（筛选 / 排序 / 增删改）
                         ├─ 图文卡（单条 / 双条对比，3:4 PNG）
                         └─ CSV 导出
```

## 运行生命周期

- `打开监控台.vbs` 探测 Python → 启动 `server.py` → 打开浏览器。
- 面板每 30 秒请求 `/api/ping`；服务端刷新 `LAST_SEEN`。
- 页面关闭后心跳停止；`--idle-exit N` 分钟后服务自动退出。
- 重复启动时端口预检会提示「已在运行」并直接打开浏览器。

## 扩展点

### 新增平台

1. 在 `monitor.py` 增加 `fetch_<platform>(html)` 解析器与 `fetch --platform` 分支；
2. 按 `DATA-SOURCES.md` 定义字段口径（谷价 / 峰价 / 额度 / 窗口 / 模型级 quota）；
3. 用 `fetch --with-prev` 验证解析与偏差告警；
4. 人工核对后录入首条快照。

### 新增模型线

1. 确认模型名与版本日期；
2. 为每个平台新增快照（历史线保留，不覆盖）；
3. 面板模型 chip 会自动出现，检查默认选中与排序。

### 新增指标 / 参数

1. 在 `panel.html` 的 `params` 与模板表增加字段；
2. 计价函数保持单一入口（`per100M` / `displayPer100M`），禁止在展示层复制公式；
3. 更新 `ARCHITECTURE.md` 与 `monitor/README.md` 的口径说明。

## 验证方法

- **启动**：`python server.py --port 8765 --open`，确认首页、三个图标、API 均 200。
- **数据**：`python monitor.py latest` / `diff` 输出与面板一致。
- **几何回归**（改面板/卡片后）：CDP 驱动 headless Edge，`Emulation.setDeviceMetricsOverride`，断言头页四格、表格无溢出、单卡/双卡 640 高度。
- **导出**：图文卡与海报实际导出 PNG，检查裁切与字号。
- **报告**：`python reports/build.py --preview` 后检查列表、文章、目录、表格、图片、来源与移动端；再跑 `python reports/build.py` 确认草稿不会进入公开产物。

## 约束

- 不引入第三方运行时依赖与构建链。
- 前端保持单文件（`panel.html`），避免部署复杂度。
- 服务只绑定本机回环地址；不要改成 `0.0.0.0` 暴露到公网（无鉴权）。
- 数据修改前备份 `plans.db`；历史快照只追加。
- 不要把渠道数、快照数写死进产品文案。
- `reports/dist/` 是生成产物，不手改；草稿只允许出现在预览构建中。
