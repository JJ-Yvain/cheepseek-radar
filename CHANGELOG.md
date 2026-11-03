# Changelog

本项目的重要变更记录。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)；版本号在产品化后启用。

## [0.2.0] - 2026-11-04

国际化、主题与公共化发布准备。

### Added

- **完整双语界面（zh / en）**：面板、海报、报告系统全量中英文案（277 组词条）；
  品牌条/工具条/报告页一键切换，偏好存浏览器本地（csr_lang），首次打开跟随浏览器语言；
  数据内专有名（模型 ID、平台名等）保留原文，展示层做显示翻译（如「官方API → Official API」「月重置 → Monthly reset」）。
- **英文演示报告与图表**：deepseek-coding-plan-2026-11.en.md 与 demo-price-comparison.en.svg（与中文稿同 slug、同数值、互链切换）。
- **报告系统双语构建**：reports/build.py 支持双语源（X.md / X.en.md 同 slug），
  产物 dist/（中文）与 dist/en/（英文），站点根链接按目录深度自适应，互为对照翻译链接。
- **三态主题**：浅色 / 深色 / 跟随系统；深色延续暖纸+铜金编辑式气质；
  偏好存浏览器本地（csr_theme），跟随系统实时响应系统主题变化；head 预读脚本避免加载闪烁；
  **导出图文卡与海报画布钉浅色**（类选择器局部重声明变量），导出图不随站点主题变化。
- **公共静态站点构建**：新增根目录 build_public.py——导出 plans.db 为 site/data/*.json（与 /api 同构），
  注入 window.CSR_PUBLIC 后复制面板为只读站点（隐藏新增/编辑/删除/模板维护/停服务，无心跳），
  报告公开构建（自动排除草稿）+ 海报 + 品牌图标一并装入 site/，全相对路径可直接托管 GitHub Pages。
- README.en.md（英文 README）与 README.md 新能力说明。

### Changed

- 面板/海报/报告页新增语言与主题切换控件（品牌条/工具条/报告页头部）。
- 榜单格平台名避让右上额度标签（padding-right + 标签 background:inherit）；移动端（≤760px）额度标签改为流内右对齐。
- 数据台列宽重排（平台 9%、总额度 8% 等）与促销列自动换行，适配英文更长文案；表格总额度单位用短版（42.1 亿 tokens / 42.1 ×100M）。
- 英文平台名定为「Official API」；英文额度标签「PAYG · no quota」。

### Data
- 数据与计价逻辑零改动：15 条快照 / 4 平台 / 3 条模型线 / 11 个监测项（截至 2026-11-02）。

## [0.1.0] - 2026-11-03

产品化起点：从一次性项目转为可长期维护的产品。

### Added

- `docs/PRODUCT.md`：产品定位、目标用户、价值主张、原则与非目标。
- `docs/ARCHITECTURE.md`：组件、数据模型、计价算法、API、扩展点与验证方法。
- `docs/DATA-SOURCES.md`：数据源、模型级额度口径、巡检流程与数据质量规则。
- `CONTRIBUTING.md`：数据贡献与代码贡献指南。
- `CHANGELOG.md`、`.gitignore`。
- 导出图署名配置项：`panel.html` 的 `IMAGE_SIGNATURE`、`poster.html` 的 `SIGNATURE`。
- README 产品截图：`docs/assets/panel.png`。
- 研究报告系统：`reports/build.py`（Markdown → 静态 HTML）、报告列表与文章页、`reports/posts/` 源文件、`reports/assets/` 样式与图表。
- 面板顶部导航整合「榜单 / 数据台 / 报告」；本地服务新增 `/reports/` 静态路由与预览构建。
- 报告草稿机制：`status: draft` 仅本地预览可见，公开构建自动排除。
- 演示报告：`reports/posts/deepseek-coding-plan-2026-11.md`（草稿）。
- 三套内置计算画像：95/4/1、97/2.5/0.5、98/1.6/0.4（均峰谷 6:4）。
- 数据台直接编辑全量 token 三项占比（缓存读取 / 普通输入 / 模型输出），自动保持合计 100%。
- 单卡与双卡弹窗内嵌计算画像参数条：预设切换、自定义、实时重算、恢复初始；参数只影响当前卡。

### Changed

- `README.md` 重写为产品 README：定位、核心能力、快速开始、计价口径、当前覆盖与文档索引。
- `HANDOFF.md` 重写为产品开发交接：当前状态、关键决策、待办、风险与约束。
- `monitor/README.md` 调整为产品操作手册，统一产品术语。
- 面板标题与品牌条、`server.py` / `monitor.py` 文件头、Windows 启动器标题统一为 **CheepSeek Radar**。
- `poster.html` 更新为当前模型线（V4.1-Flash-1017）与当前快照统计。
- 移除「上下文档位 / 常规占比」控件及相关计算、表单字段与数据库字段（产品不再跟踪按上下文长度分档的模型）。
- 模板下拉去掉「默认」字样，内置模板改为参数标签。
- 计价参数由「缓存率 + 非缓存输入占比」改为全量 token 三项占比；模板新增 `input_pct/output_pct`，旧 `input_share` 仅兼容读取并自动迁移。
- 图文卡改为「当前画像 + 参考画像」两块，参考画像在当前为默认时取高缓存、否则取默认；双卡两列使用同一组假设。
- 图文卡预览在窄屏等比缩放，导出仍使用 480×640 原始卡片 DOM。
- 头页卡片：去掉左上角序号；同价显示「并列最低」，其他渠道改为「最低价的 X 倍」文字；每张卡右上角显示当前画像下的月度 token 总额度（官方 API 显示「按量无额度」），并放大字号；导出卡同步，并用上下布局避免文字截断。
- 数据台「变化」列改为按「平台 + 套餐 + 模型系列」对比上一轮，只比较当前画像下的每亿价；跨代际显示「较上代」，并展示对比模型、日期与前后价格。

### Archived

- 历史产物移入 `archive/research-era/`：早期报告、任务方案、执行日志、`evidence/`、`report_v3.html`、`report_v4.html`；保留可追溯，不再作为产品文档引用。

### Data

- 活动库：**15 条快照 / 4 平台 / 3 条模型线 / 11 个监测项**，数据截至 2026-11-02。
- 平台：DeepSeek 官方 API、Command Code（GOAT）、OpenCode（Go）、Ollama（Pro）。
- 模型线：`deepseek-v4.1-flash-1017`（当前）、`deepseek-v4.1-flash`（历史）、`deepseek-v4-flash-0731`（历史）。
- 2026-11-03 移除 GLM：删除 5 条 `glm-5.3-flash` 快照；删除前备份 `archive/回退点历史/plans.db.bak-2026-11-03-before-glm-removal`。

### Notes

- 产品化前的完整开发历史见 `archive/research-era/进度.md`。
- 开源协议暂未指定；`LICENSE` 待补。
