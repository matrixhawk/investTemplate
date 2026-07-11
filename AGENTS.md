# AGENTS.md - AI助手当前约束

> **项目语言**: 中文 (Chinese)
> 本文件只保留当前有效的执行约束和操作规范。版本历史、案例复盘和变更记录统一维护在 [docs/CHANGELOG.md](./docs/CHANGELOG.md)。详细规范见 [docs/agents/](./docs/agents/00-INDEX.md)。

---

## 📋 项目概况

本项目是一个**港股/A股个股投资分析模板系统**，属于知识管理型项目。

| 属性 | 说明 |
|------|------|
| **类型** | 投资分析模板 + 辅助工具脚本 |
| **目标用户** | 个人投资者 |
| **投资市场** | 港股（优先）、A股 |
| **投资流派** | 四流派体系（纯硬收息/价值发现/烟蒂股/关联方资源型） |

---

## 📁 核心文件速查

| 文件 | 用途 | 操作 |
|------|------|------|
| `analysis-template.md` | 🔥 **分析框架入口** | 生成报告前必读 |
| `template/*.md` | 分章节详细模板 | 按需查阅 |
| `analysis-reports/` | 个股分析报告归档 | 新报告保存位置 |
| `decision-tracking/` | 决策记录与模拟组合 | 数据存储位置 |

---

## ⚡ 关键规范（执行前必读）

### 1. 生成投资分析报告（当前约束）

```
步骤:
1. 读取 analysis-template.md 获取最新框架
2. 读取 `config/template-version.yaml` 和 `template/00-报告输出契约.md`
3. 使用 S级数据源（年报原文）获取年度核心财务数据，使用最新季度/中报补充TTM和趋势数据
4. **适用PE时强制计算 TTM PE**：最近四个季度净利润之和 ÷ 市值，与静态PE同时展示；不适用PE时必须说明替代估值方法
5. 分开记录报告口径FCF与维护性FCF，估算值标明区间和置信度
6. 保存到 analysis-reports/{公司}_{代码}_投资分析报告.md
7. 更新 .vitepress/config.mjs 侧边栏
8. 更新 analysis-reports/index.md 目录索引
9. 更新 index.md 首页"最新分析报告"列表
```

**首行必须**: `**一句话结论**：<状态+估值+操作建议>`

**PE计算必须（V5.5.20+新增）**:
```
报告估值章节必须同时展示：
├── 静态PE = 市值 / 最近完整年度净利润
├── TTM PE = 市值 / 最近四个季度净利润之和
├── 两者差异及原因（如：会计调整、季节性、一次性损益）
└── 硬约束以 TTM PE 优先（更能反映最新盈利趋势）

例外：若TTM失真（如强季节性行业），以年度PE为准
```

### 1.5 ST 套利策略的调用边界

```
├── 默认状态：用户要求「按标准模板分析个股」时，**完全不涉及**第十一章「ST套利与特殊事件策略」
├── 触发条件：用户**明确说出**「用 ST 策略分析」「按第十一章分析」「分析这只 ST 股」等指令
├── 执行方式：**单独调用** template/11-ST套利与特殊事件策略.md，不叠加第一至第七章标准流程
└── 禁止行为：未经用户明确请求，不得在标准分析报告中提及 ST 套利框架或推荐
```

### 2. 数据源等级（强制执行）

| 等级 | 数据源 | 使用限制 |
|------|--------|----------|
| **S级** | 公司年报原文 | **必须直接使用**，禁止估算 |
| **A级** | 业绩公告 | 需与S级交叉验证 |
| **B级** | 东方财富等 | **不得用于核心财务数据** |
| **C级** | 财经媒体 | 仅供参考 |
| **D级** | AI估算 | **禁止用于投资决策** |

### 3. 修改模拟持仓数据（⚠️ 极易出错）

**必须同时更新以下4个文件**：

```
1️⃣ decision-tracking/simulation_trades.csv      (唯一真相源)
2️⃣ decision-tracking/simulation_state.json       (运行时状态)
3️⃣ decision-tracking/dashboard_snapshot.json     (决策追踪目录)
4️⃣ public/dashboard/dashboard_snapshot.json  (VitePress网页数据源) ⭐易遗漏！
```

**检查命令**：
```bash
grep -q "recent_actions" public/dashboard/dashboard_snapshot.json && echo "OK" || echo "缺少字段!"
```

### 4. 更新VIX定投策略数据（⚠️ 极易遗漏网页显示）

**必须同步更新**：
```
1️⃣ decision-tracking/vix_dca_strategy/daily_snapshot.csv  (每日收益)
2️⃣ decision-tracking/vix_dca_strategy/state.json           (当前状态)
3️⃣ decision-tracking/vix_dca_strategy/daily_returns.csv    (收益率曲线数据源)
4️⃣ portfolio/vix-dca-strategy.md                          (网页展示页面) ⭐易遗漏！
5️⃣ public/vix_strategy/dashboard_data.json                (网页数据源) ⭐易遗漏！
6️⃣ public/vix_strategy/returns_curve.html                 (收益率曲线) ⭐易遗漏！
7️⃣ 不再同步旧目录；`decision-tracking/` 是唯一真相源
```

**更新后验证**：
- [ ] 数据文件已更新
- [ ] 网页展示页面数据一致
- [ ] public目录已同步
- [ ] **收益率曲线(returns_curve.html)与数据保持一致** ⭐易遗漏！价格/收益/市值必须与state.json同步

详细规范见：[docs/agents/06-portfolio-management.md](./docs/agents/06-portfolio-management.md)

---

## 📚 详细规范文档

| 文档 | 内容 | 必读场景 |
|------|------|----------|
| [01-项目概述](./docs/agents/01-project-overview.md) | 投资理论、核心概念 | 首次参与项目 |
| [02-开发规范](./docs/agents/02-dev-guidelines.md) | 版本管理、文件命名 | 日常开发 |
| [03-代码规范](./docs/agents/03-coding-standards.md) | Python/YAML规范 | 编写脚本 |
| [04-投资理论参考](./docs/agents/04-investment-theory.md) | 龟龟理论、估值标准 | 分析报告 |
| [05-数据质量控制](./docs/agents/05-data-quality.md) | 数据核查清单 | 生成报告前 |
| [06-模拟组合管理](./docs/agents/06-portfolio-management.md) | 数据硬约束、一致性 | 修改持仓数据 |

---

## 🎯 投资哲学核心（一句话）

> **防御第一，普通人假设，动态估值，分散持仓，风险记忆**

- **龟龟投资理论**: 追求熊市90%以上时间跑赢指数
- **普通人假设**: 视线仅1-2年，回避高波动变量
- **动态估值**: 比较内在价值与市场报价，弱化3-5年预测
- **分散持仓**: 单只≤10%，持仓约10只
- **风险记忆**: 牢记港股曾跌90%以上，保持提防心理

---

## 🔧 常用命令

```bash
# 读取当前模板政策
grep -n "V5\." README.md | head -3

# 运行股票筛选
cd 01-筛选框架 && python hk_stock_screener.py

# 验证模拟持仓数据
python scripts/validate_simulation_data.py

# 每日工作流（AI驱动，dry-run预演模式）
python scripts/run_daily_workflow.py --dry-run

# 每日工作流（全自动执行）
python scripts/run_daily_workflow.py

# 回滚最近N笔交易
python scripts/rollback_trade.py --last 1

# 验证PE计算（防止市值误算）
python scripts/validate_pe_calculation.py 06049 --price 30.56 --shares 5.5333 --profit 15.50 --currency HKD

# 验证VIX定投策略数据一致性
python scripts/validate_vix_dca.py

# 本地预览
npm run docs:dev
```

---

## ⚠️ 禁止事项

- ❌ 使用 D级数据（AI估算）用于投资决策
- ❌ 为同一公司保留多份历史版本报告
- ❌ 直接修改 state.json 而不更新 trades.csv
- ❌ 修改持仓数据时遗漏 `public/dashboard/` 目录
- ❌ 自动执行 git commit/push（必须由用户确认）

---

## 📞 问题处理

| 问题 | 解决方案 |
|------|----------|
| 数据不一致 | 运行 `python scripts/validate_simulation_data.py` |
| 网页显示错误 | 检查 `public/dashboard/dashboard_snapshot.json` 是否同步 |
| 历史操作不显示 | 检查 `dashboard_snapshot.json` 是否包含 `recent_actions` |
| 规范口径不一致 | 以 `config/template-version.yaml` 和当前模板章节为准 |

---
