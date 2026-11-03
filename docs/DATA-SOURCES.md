# 数据源与更新规则 — CheepSeek Radar

> 本文定义「数据从哪里来、怎么核验、什么算合格」。计价算法见 `ARCHITECTURE.md`，产品定位见 `PRODUCT.md`。

## 数据原则

1. **有源可查**：每条快照必须带 `source_url` 与 `captured_at`；没有来源的价格不录入。
2. **原文优先**：以平台定价页 / 官方文档为准；第三方转述只作线索，不作数据源。
3. **口径一致**：录入谷价（Off-Peak）；峰价单独填峰价列；月费 / 额度按页面原文的币种与粒度。
4. **模型级额度**：额度按模型分别核对，不假设同平台所有模型同额。
5. **历史只追加**：调价通过新增快照表达，不覆盖旧行。
6. **不确定就标注**：版本未确认、促销未核实、额度为推算值，写进 `note`，不要伪装成确定事实。

## 当前数据源

| 平台 | 套餐 | 数据源 | 抓取方式 | 备注 |
|---|---|---|---|---|
| DeepSeek 官方 API | 按量 | `platform.deepseek.com` 定价页 | 人工核对 | 模型名 `deepseek-flash`；当前对应 V4.1-Flash-1017；人民币计价 |
| Command Code | GOAT | `commandcode.ai/docs/plans/goat` | 自动（`fetch --platform commandcode`） | Monthly credits 表为纯文本行，部分模型条目不会自动出现在草稿，需人工补 |
| OpenCode | Go | `opencode.ai/docs/go` | 自动（`fetch --platform opencode`） | 窗口按 docs「5h=月额度 20% / 周=50% / 月=100%」推算 |
| Ollama | Pro | `ollama.com/pricing` | 自动（`fetch --platform ollama`） | 价表结构：无后缀行 = 峰价，`(Off-Peak)` 行 = 谷价；$60 为账户共享 credits |

## 模型线与额度粒度

| 模型线 | 状态 | 平台 | 额度口径 |
|---|---|---|---|
| `deepseek-v4.1-flash-1017` | 当前 | 官方 / CC / OC / Ollama | CC $100、OC $100、Ollama $60 共享 credits、官方按量 |
| `deepseek-v4.1-flash` | 历史（09-10 版） | 官方 / CC / OC | CC 旧 $60、OC 旧 $60；保留对比 |
| `deepseek-v4-flash-0731` | 历史（旧线） | 官方 / CC / OC / Ollama | 旧价旧额度；旧名可能路由到新模型 |

> 关键：CC / OC 的额度是**模型级月额度**，不是套餐总 credit；Ollama 的 $60 是**账户共享 credits**。跨代际、跨平台比较前必须核对各自 quota。
> 当前只跟踪 DeepSeek 模型线；GLM 数据已于 2026-11-03 从活动库移除。

## 更新频率

| 平台 | 建议频率 | 触发条件 |
|---|---|---|
| DeepSeek 官方 | 月查 | 官方公告、模型发版、费率调整 |
| Command Code | 月查 | 额度 / 窗口调整、模型目录更新 |
| OpenCode | 月查；促销敏感期周查 | 4× 横幅变化、额度回落、模型上新 |
| Ollama | 双周 | credits 政策、模型上架、价表结构变化 |

## 巡检流程

```text
1. 抓取
   python monitor.py fetch --platform ollama --with-prev
   python monitor.py fetch --platform opencode --with-prev
   python monitor.py fetch --platform commandcode --with-prev

2. 核验
   · 双通道解析交叉比对
   · 价格合理性：正数 / 峰 ≥ 谷 / 字段完整
   · 与库内最近快照偏差 > ±30% 告警
   · 促销变化提示

3. 人工确认
   · 核对源页面原文与窗口 / 模型级额度
   · 官方 API 直接抓页面人工核对

4. 入库
   python monitor.py add ...  或面板新增

5. 复盘
   python monitor.py diff
   · ±50% 级变化先判断是否为口径迁移（额度口径 / 模型线 / 币种），再当调价处理
```

`fetch` **只出草稿、不写库**；解析失败会明确报「规则失效」，不会写入猜测数据。

## 数据质量规则

### 必填

- `captured_at`、`platform`、`plan`、`model`
- 价格：至少输入 / 输出谷价；缓存价缺失时在 `note` 说明
- `source_url`

### 口径

- **谷价进 `in_v/cache_v/out_v`**；峰价进 `in_p/cache_p/out_p`。页面只给单一价格时，峰价留空并在 `note` 说明「无峰谷」。
- **官方 API 用 CNY 原始价**，不要先折算再录入；展示层统一换算。
- **窗口限制**按页面原文录入；推算值必须写进 `note`。
- **促销**：`promo` 写清「内容 + 生效日」，如 `限时10%（09-12起）`；未核实的促销留空，不把营销横幅当事实。
- **历史线**：旧模型 / 旧额度保留，不覆盖；新快照用于表达当前状态。

### 复核

- 新快照与上一轮差异 > ±30%：复核来源与字段口径。
- 差异 > ±50%：优先怀疑「额度口径 / 模型线 / 币种」迁移，而不是直接认定调价。
- 同一监测项连续多轮无变化：也要保留巡检记录（可只更新 `captured_at` 与 `note`）。

## 当前数据集

截至 **2026-11-02**：

- **15 条快照**
- **4 个平台**：DeepSeek 官方 API / Command Code / OpenCode / Ollama
- **3 条模型线**
- **11 个监测项**

历史数据（旧模型线、旧额度）全部保留；已停止跟踪的渠道数据已从活动库移除。

## 免责声明

价格与额度来自平台公开页面，可能因促销、地区、页面改版而滞后或变化。本产品输出为基于公开报价与使用画像的估算，不构成购买建议；实际费用以平台结算为准。发现数据错误请按 `CONTRIBUTING.md` 提交修正。
