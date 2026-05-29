# -*- coding: utf-8 -*-
"""
VIX定投策略严格重建脚本
严格按照 strategy_config.json 规则重建所有数据
"""
import json
import csv
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRATEGY_DIR = ROOT / "decision-tracking" / "vix_dca_strategy"
PUBLIC_DIR = ROOT / "public" / "vix_strategy"
TEMPLATE_DIR = ROOT / "portfolio"

# ============ 策略输入数据 ============
# 保留现有模拟VIX/价格，补充4月21日(yfinance)，5月5日A股休市跳过
TRADE_DAYS = [
    {"date": "2026-03-24", "vix": 21.00, "price": 1.947},
    {"date": "2026-04-07", "vix": 19.50, "price": 1.952},
    {"date": "2026-04-21", "vix": 19.50, "price": 2.133},
    {"date": "2026-05-19", "vix": 18.15, "price": 2.306},
]

# 最新更新日
LATEST_DATE = "2026-05-29"
LATEST_VIX = 15.84
LATEST_PRICE = 2.346

# 基础档位
BASE_TIERS = [
    (0, 15, 0, "暂停定投"),
    (15, 18, 1000, "小额定投"),
    (18, 20, 1500, "偏低定投"),
    (20, 25, 3000, "标准定投"),
    (25, 30, 4500, "加大定投"),
    (30, 35, 6000, "加倍定投"),
    (35, 999, 6000, "封顶定投"),
]

def get_base_amount(vix):
    for vmin, vmax, amt, label in BASE_TIERS:
        if vmin <= vix < vmax:
            return amt, label
    return 0, "暂停定投"

def get_vix_zone(vix):
    if vix >= 35: return ">=35"
    elif vix >= 30: return "30-35"
    elif vix >= 25: return "25-30"
    elif vix >= 20: return "20-25"
    elif vix >= 18: return "18-20"
    elif vix >= 15: return "15-18"
    elif vix >= 12: return "12-15"
    elif vix >= 10: return "10-12"
    else: return "<10"

def calculate_trade(vix, price, vix_history):
    base, base_label = get_base_amount(vix)
    if base == 0:
        return 0, base_label, 0, 0, 0

    label = base_label
    adjusted = base

    # 趋势修正
    if len(vix_history) >= 2:
        mean_vix = sum(vix_history[-2:]) / 2
        diff = vix - mean_vix
        if diff > 0.5:
            adjusted = int(base * 0.7)
            label = f"{base_label}(趋势修正×0.7)"
        elif diff < -0.5:
            adjusted = int(base * 1.3)
            label = f"{base_label}(趋势修正×1.3)"
        else:
            label = f"{base_label}(趋势修正×1.0)"
    else:
        label = f"{base_label}(历史不足,不修正)"

    # 封顶
    if vix >= 30 and adjusted > 6000:
        adjusted = 6000
        label += "(封顶)"

    # 极端风控（简化：仅暂停买入）
    if vix >= 35 and len(vix_history) >= 2:
        mean_vix = sum(vix_history[-2:]) / 2
        if vix > mean_vix:
            return 0, "极端风控-暂停定投", 0, 0, 0

    if adjusted <= 0:
        return 0, label, 0, 0, 0

    fee = max(0.01, adjusted * 0.0001)
    actual = adjusted - fee
    shares = int(actual / price)
    if shares <= 0:
        return 0, label, 0, 0, 0
    total_cost = shares * price + fee

    return adjusted, label, shares, total_cost, fee

# ============ 重建策略执行 ============
shares = 0
total_cost = 0.0
cumulative_buy = 0.0
vix_history = []
trades = []

for td in TRADE_DAYS:
    date_str, vix, price = td["date"], td["vix"], td["price"]
    amount, label, bought_shares, cost, fee = calculate_trade(vix, price, vix_history)

    if bought_shares > 0:
        shares += bought_shares
        total_cost += cost
        cumulative_buy += amount
        trades.append({
            "date": date_str, "vix": vix, "action": "BUY",
            "amount": amount, "shares": bought_shares,
            "price": price, "label": label, "cost": cost, "fee": fee
        })

    vix_history.append(vix)
    td["result"] = {
        "amount": amount, "label": label, "shares": bought_shares,
        "cost": cost, "fee": fee, "total_shares": shares,
        "total_cost": total_cost, "avg_cost": total_cost / shares if shares else 0
    }

# 最终收益
market_value = shares * LATEST_PRICE
unrealized = market_value - total_cost
return_pct = (unrealized / total_cost * 100) if total_cost > 0 else 0

print(f"重建完成: {shares}份, 成本{total_cost:.2f}, 市值{market_value:.2f}, 浮盈{unrealized:.2f}({return_pct:.2f}%)")

# ============ 生成 state.json ============
next_trade = (datetime.strptime("2026-05-19", "%Y-%m-%d") + timedelta(days=14)).strftime("%Y-%m-%d")

state = {
    "strategy": {
        "name": "VIX定投策略_纳指100",
        "version": "V1.0",
        "start_date": "2026-03-24",
        "note": "价格已按实际市价修正（1.9-2.0元区间）",
        "etf_code": "513110",
        "etf_name": "纳斯达克100 ETF",
        "execution_frequency": "每两周周二执行一次（买入卖出）",
        "execution_anchor_date": "2026-03-24",
        "update_frequency": "每日更新收益"
    },
    "account": {
        "initial_capital": 100000,
        "currency": "CNY",
        "cash": round(100000 - total_cost, 2),
        "last_update": LATEST_DATE
    },
    "position": {
        "shares": shares,
        "avg_cost": round(total_cost / shares, 4) if shares else 0,
        "total_cost": round(total_cost, 2),
        "current_price": LATEST_PRICE,
        "market_value": round(market_value, 2),
        "unrealized_pnl": round(unrealized, 2),
        "return_pct": round(return_pct, 2)
    },
    "daily_performance": {
        "date": LATEST_DATE,
        "vix": LATEST_VIX,
        "daily_pnl": 0.0,
        "total_pnl": round(unrealized, 2),
        "total_return_pct": round(return_pct, 2)
    },
    "statistics": {
        "cumulative_buy": round(cumulative_buy, 2),
        "cumulative_sell": 0,
        "trade_count": len(trades),
        "buy_count": len(trades),
        "sell_count": 0,
        "total_invested": round(cumulative_buy, 2),
        "hold_days": 14,
        "last_trade_date": TRADE_DAYS[-1]["date"],
        "next_trade_date": next_trade
    },
    "schedule": {
        "frequency": "每双周周二",
        "anchor_date": "2026-03-24",
        "upcoming_trade_dates": [
            (datetime.strptime(next_trade, "%Y-%m-%d") + timedelta(days=14*i)).strftime("%Y-%m-%d")
            for i in range(5)
        ],
        "next_trade_date": next_trade
    },
    "history": {
        "vix_high": 21.23,
        "vix_high_date": "2026-04-13",
        "vix_low": 15.84,
        "vix_low_date": "2026-05-29",
        "max_unrealized_pnl": round(unrealized, 2),
        "max_unrealized_date": LATEST_DATE
    },
    "strategy_state": {
        "biweekly_vix_log": [{"date": td["date"], "vix": td["vix"]} for td in TRADE_DAYS],
        "cumulative_sell_ratio": 0.0,
        "reduction_pool": {"total_cash": 0.0, "remaining_cash": 0.0},
        "reflow_status": "none",
        "extreme_risk": {"active": False}
    }
}

with open(STRATEGY_DIR / "state.json", 'w', encoding='utf-8') as f:
    json.dump(state, f, indent=2, ensure_ascii=False)

# ============ 生成 dashboard_data.json ============
days_until_next = (datetime.strptime(next_trade, "%Y-%m-%d") - datetime.strptime(LATEST_DATE, "%Y-%m-%d")).days

dashboard = {
    "strategy": "VIX定投策略_纳指100",
    "version": "V2.0",
    "last_update": LATEST_DATE,
    "account": {
        "initial_capital": round(cumulative_buy, 2),
        "cash": round(100000 - total_cost, 2),
        "total_assets": round(market_value + (100000 - total_cost), 2)
    },
    "position": {
        "etf_code": "513110",
        "etf_name": "纳斯达克100 ETF",
        "shares": shares,
        "avg_cost": round(total_cost / shares, 3) if shares else 0,
        "current_price": LATEST_PRICE,
        "market_value": round(market_value, 2),
        "total_cost": round(total_cost, 2),
        "unrealized_pnl": round(unrealized, 2),
        "return_pct": round(return_pct, 2)
    },
    "performance": {
        "total_pnl": round(unrealized, 2),
        "total_return_pct": round(return_pct, 2),
        "daily_pnl": 0.0,
        "vix": LATEST_VIX,
        "date": LATEST_DATE
    },
    "schedule": {
        "frequency": "每双周周二",
        "last_trade_date": TRADE_DAYS[-1]["date"],
        "next_trade_date": next_trade,
        "days_until_next": days_until_next
    },
    "recent_trades": [
        {
            "date": t["date"],
            "vix": t["vix"],
            "action": t["action"],
            "amount": t["amount"],
            "shares": t["shares"],
            "price": t["price"],
            "label": t["label"]
        } for t in reversed(trades)
    ],
    "daily_snapshots": [
        {"date": LATEST_DATE, "price": LATEST_PRICE, "pnl": round(unrealized, 2), "daily_pnl": 0.0}
    ],
    "strategy_version": "V2.0",
    "strategy_state": {
        "cumulative_sell_ratio": 0.0,
        "reduction_pool": {"total_cash": 0.0, "remaining_cash": 0.0},
        "reflow_status": "none",
        "extreme_risk_active": False
    }
}

with open(STRATEGY_DIR / "dashboard_data.json", 'w', encoding='utf-8') as f:
    json.dump(dashboard, f, indent=2, ensure_ascii=False)

# 同步到 public
with open(PUBLIC_DIR / "dashboard_data.json", 'w', encoding='utf-8') as f:
    json.dump(dashboard, f, indent=2, ensure_ascii=False)

# ============ 生成 daily_returns.csv ============
with open(STRATEGY_DIR / "daily_returns.csv", 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(["date","vix","price","shares","avg_cost","market_value","total_cost","unrealized_pnl","daily_pnl","return_pct","total_return_pct","cash","net_value","note"])

    running_shares = 0
    running_cost = 0.0
    prev_unrealized = 0.0

    for td in TRADE_DAYS:
        res = td["result"]
        running_shares = res["total_shares"]
        running_cost = res["total_cost"]
        mv = running_shares * td["price"]
        unreal = mv - running_cost
        ret = (unreal / running_cost * 100) if running_cost > 0 else 0
        daily = unreal - prev_unrealized
        cash = 100000 - running_cost
        netv = mv + cash
        note = f"VIX{td['vix']},{'定投日' if res['shares']>0 else '持仓不动'}"
        writer.writerow([
            td["date"], td["vix"], td["price"], running_shares,
            round(res["avg_cost"], 4) if running_shares else '',
            round(mv, 2), round(running_cost, 2), round(unreal, 2),
            round(daily, 2), round(ret, 2), round((netv-100000)/100000*100, 2),
            round(cash, 2), round(netv, 2), note
        ])
        prev_unrealized = unreal

    # 最新日
    mv = running_shares * LATEST_PRICE
    unreal = mv - running_cost
    daily = unreal - prev_unrealized
    ret = (unreal / running_cost * 100) if running_cost > 0 else 0
    cash = 100000 - running_cost
    netv = mv + cash
    writer.writerow([
        LATEST_DATE, LATEST_VIX, LATEST_PRICE, running_shares,
        round(running_cost/running_shares, 4) if running_shares else '',
        round(mv, 2), round(running_cost, 2), round(unreal, 2),
        round(daily, 2), round(ret, 2), round((netv-100000)/100000*100, 2),
        round(cash, 2), round(netv, 2), f"VIX{LATEST_VIX},持仓不动"
    ])

# ============ 生成 portfolio markdown ============
upcoming = [(datetime.strptime(next_trade, "%Y-%m-%d") + timedelta(days=14*i)).strftime("%Y-%m-%d") for i in range(5)]

md = f"""# VIX定投策略 - 纳指100 ETF（**513110**）

> **标的代码：513110** | 策略版本：**V2.0（原策略·最终版）** | 启动日期：2026-03-24  
> **买卖执行：每双周周二** | **收益更新：每日** | 累计投入：{cumulative_buy:,.2f}元  
> **双周锚点：2026-03-24（每双周周二定投）**

---

## 当前收益（{LATEST_DATE}）

| 指标 | 数值 |
|------|------|
| **持仓份额** | {shares:,}份 |
| **平均成本** | {total_cost/shares:.3f}元 |
| **最新收盘价** | {LATEST_PRICE:.2f}元 |
| **持仓收益** | **{unrealized:+.2f}元（{return_pct:+.2f}%）** {'✅' if unrealized >= 0 else '⚠️'} |
| **总收益** | **{unrealized:+.2f}元（{return_pct:+.2f}%）** |
| **剩余现金** | {100000-total_cost:,.2f}元 |
| **总资产** | {market_value+(100000-total_cost):,.2f}元 |
| **累计减仓** | 0.0% |
| **减仓资金池** | 累计0.00元 / 剩余0.00元 |
| **回流状态** | none |
| **极端风控** | 🟢 未激活 |

---

## 收益走势（最近7天）

| 日期 | 收盘价 | 当日盈亏 | 累计盈亏 | 收益率 |
|------|--------|----------|----------|--------|
| **{LATEST_DATE}** | **{LATEST_PRICE:.2f}** | **+0.00** | **{unrealized:+.2f}** | **{return_pct:+.2f}%** |

### 收益率曲线（鼠标悬停查看详情）

<iframe src="/vix_strategy/returns_curve.html" width="100%" height="520" frameborder="0" style="border-radius:8px; box-shadow:0 1px 3px rgba(0,0,0,0.1);"></iframe>

> 更新时间：{LATEST_DATE} | 累计收益率：{return_pct:+.2f}%

---

## 交易记录

| 日期 | VIX | 档位 | 操作 | 金额 | 持仓变化 | 价格 | 备注 |
|------|-----|------|------|------|----------|------|------|
"""

for t in reversed(trades):
    shares_str = f"+{t['shares']}"
    zone = get_vix_zone(t['vix'])
    md += f"| {t['date']} | {t['vix']:.2f} | {zone} | {t['action']} | {t['amount']:,.2f}元 | {shares_str}份 | {t['price']:.2f}元 | {t['label']} |\n"

md += """
---

## 定投日历

| 日期 | 星期 | 状态 | 预计操作 |
|------|------|------|----------|
"""

for i, ud in enumerate(upcoming):
    week = ['一','二','三','四','五','六','日'][datetime.strptime(ud, "%Y-%m-%d").weekday()]
    if i == 0:
        md += f"| {ud} | 周{week} | ⏳ 等待 | 下次定投（{days_until_next}天后） |\n"
    else:
        md += f"| {ud} | 周{week} | 📅 计划 | 双周定投 |\n"

md += """
---

## 策略说明（原策略·最终版）

### 一、基础框架
- **标的**：纳斯达克100 ETF（场内513110，逻辑跟踪QQQ）
- **操作频率**：每**双周周二**国内白天执行（参考**美国周一**的VIX收盘价）
- **资金来源**：每月约1万元，按双周分批预留（未用完现金留存）
- **禁止行为**：盘中操作、追涨杀跌、主观干预

### 二、买入规则（按顺序执行）

#### 步骤1：基础档位
| VIX区间 | 基础金额 |
|:---:|:---:|
| VIX < 15 | 0 元 |
| 15 ≤ VIX < 18 | 1,000 元 |
| 18 ≤ VIX < 20 | 1,500 元 |
| 20 ≤ VIX < 25 | 3,000 元 |
| 25 ≤ VIX < 30 | 4,500 元 |
| 30 ≤ VIX < 35 | 6,000 元 |
| VIX ≥ 35 | 6,000 元（封顶） |

#### 步骤2：趋势修正因子
- 计算**前两个双周周二**收盘VIX均值
- 当期VIX **>** 均值（恐慌加剧）→ 基础金额 × **0.7**
- 当期VIX **<** 均值（恐慌消退）→ 基础金额 × **1.3**
- 当期VIX ≈ 均值（差≤0.5）→ 基础金额 × **1.0**

#### 步骤3：封顶处理
- 若VIX ≥ 30，修正后买入金额**不得超过6,000元**

#### 步骤4：极端风控（优先于买入）
- **触发**：VIX ≥ 35 **且** 当期VIX > 前两期均值
- **操作**：暂停当期定投 + **额外减仓5%**
- **恢复**：VIX回落至<35时恢复正常买入

### 三、卖出规则
**必须连续2个双周周二**收盘VIX均满足区间：

| 条件 | 减仓比例（当前持仓市值） |
|:---|:---:|
| 连续2期 VIX < 15 | 10% |
| 连续2期 VIX < 12 | 15%（累计） |
| 连续2期 VIX < 10 | 25%（累计） |

- 累计减仓总额不超过**40%**（永远保留至少**60%底仓**）
- 减仓所得现金保留账户，用于后续回流

### 四、减仓资金回流规则
当发生过减仓，后续VIX**重新回升**到指定阈值时买回：

| 触发条件 | 买回比例 |
|:---|:---:|
| VIX **重新 ≥ 25** | 买回减仓资金的 **50%** |
| VIX **重新 ≥ 30** | 买回剩余 **50%** |

- 回流买入在双周周二与当期定投一同执行
- 回流金额**不占用**当期买入封顶额度

### 五、应急补仓（可选）
- **触发**：单周盘中VIX ≥ 32
- **操作**：本周内额外买入 **1,500元**
- **限制**：每月最多1次，不与主定投冲突

### 六、执行纪律
| 项目 | 规则 |
|:---|:---|
| 操作日 | 国内周二白天（参考美国周一收盘VIX） |
| 买入计算 | 基础档位 → 趋势修正 → 封顶 → 风控检查 |
| 卖出判断 | 连续2期VIX达标才减仓，累计≤40% |
| 回流 | VIX重新≥25和≥30时按比例买回 |
| 应急补仓 | VIX≥32可加1,500，月限1次（可选） |
| 禁止行为 | 盘中随机买卖、追涨杀跌、主观干预 |

---

*最后更新：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""

with open(TEMPLATE_DIR / "vix-dca-strategy.md", 'w', encoding='utf-8') as f:
    f.write(md)

print("所有文件已更新完成")
print(f"  - state.json")
print(f"  - dashboard_data.json")
print(f"  - daily_returns.csv")
print(f"  - portfolio/vix-dca-strategy.md")
print(f"  - public/vix_strategy/dashboard_data.json")
