# -*- coding: utf-8 -*-
"""
模拟投资组合自动决策引擎 V1.0（对应模板 V5.5.12）

功能：
1. 拉取模拟组合标的最新收盘价（yfinance）
2. 按规则执行自动决策（卖出触发 / 回撤加仓）
3. 更新持仓状态、现金余额、组合净值、收益率
4. 生成每日监控文件（08-决策追踪/每日股价监控.md）
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import yfinance as yf


ROOT = Path(__file__).resolve().parents[1]
TRACK_DIR = ROOT / "08-决策追踪"
STATE_FILE = TRACK_DIR / "simulation_state.json"
TRADES_FILE = TRACK_DIR / "simulation_trades.csv"
DAILY_FILE = TRACK_DIR / "simulation_daily_snapshot.csv"
REPORT_FILE = TRACK_DIR / "每日股价监控.md"

INITIAL_CAPITAL = 500000.0
START_DATE = "2026-03-26"
START_CASH = 52500.0


@dataclass
class PricePoint:
    close: float
    prev_close: float
    trade_date: str


INITIAL_POSITIONS = [
    {
        "name": "京投交通科技",
        "code": "01522",
        "ticker": "01522.HK",
        "lot_size": 2000,
        "shares": 342000,
        "avg_cost": 0.365,
        "initial_investment": 124830.0,
        "sell_trigger": 0.60,
        "max_weight": 0.25,
        "position_type": "核心",
    },
    {
        "name": "汇贤产业信托",
        "code": "87001",
        "ticker": "87001.HK",
        "lot_size": 1000,
        "shares": 250000,
        "avg_cost": 0.50,
        "initial_investment": 125000.0,
        "sell_trigger": 1.00,
        "max_weight": 0.25,
        "position_type": "核心",
    },
    {
        "name": "天津发展",
        "code": "00882",
        "ticker": "00882.HK",
        "lot_size": 1000,
        "shares": 40000,
        "avg_cost": 2.50,
        "initial_investment": 100000.0,
        "sell_trigger": 4.50,
        "max_weight": 0.20,
        "position_type": "核心",
    },
    {
        "name": "华润医药",
        "code": "03320",
        "ticker": "03320.HK",
        "lot_size": 500,
        "shares": 15000,
        "avg_cost": 6.50,
        "initial_investment": 97500.0,
        "sell_trigger": 9.00,
        "max_weight": 0.20,
        "position_type": "卫星",
    },
]


def ensure_state() -> Dict:
    """初始化状态文件。"""
    TRACK_DIR.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))

    positions: Dict[str, Dict] = {}
    for row in INITIAL_POSITIONS:
        positions[row["ticker"]] = {
            **row,
            "added_cost_total": 0.0,
            "realized_pnl": 0.0,
        }

    state = {
        "template_version": "V5.5.12",
        "engine_version": "V1.0",
        "initial_capital": INITIAL_CAPITAL,
        "cash": START_CASH,
        "last_trade_date": START_DATE,
        "positions": positions,
    }

    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    seed_baseline_files(state)
    return state


def seed_baseline_files(state: Dict) -> None:
    """首次初始化时写入建仓日基线记录。"""
    if not TRADES_FILE.exists():
        records = []
        for p in state["positions"].values():
            records.append(
                {
                    "date": START_DATE,
                    "ticker": p["ticker"],
                    "name": p["name"],
                    "action": "INIT_BUY",
                    "price": p["avg_cost"],
                    "shares": p["shares"],
                    "amount": round(p["shares"] * p["avg_cost"], 2),
                    "cash_after": START_CASH,
                    "reason": "初始建仓",
                }
            )
        pd.DataFrame(records).to_csv(TRADES_FILE, index=False, encoding="utf-8-sig")

    if DAILY_FILE.exists():
        return

    market_value = 0.0
    rows = []
    for p in state["positions"].values():
        mv = p["shares"] * p["avg_cost"]
        market_value += mv
        rows.append(
            {
                "date": START_DATE,
                "ticker": p["ticker"],
                "name": p["name"],
                "code": p["code"],
                "close": p["avg_cost"],
                "prev_close": p["avg_cost"],
                "change_pct": 0.0,
                "shares": p["shares"],
                "avg_cost": p["avg_cost"],
                "action": "INIT",
                "action_shares": 0,
                "action_price": 0.0,
                "action_amount": 0.0,
                "market_value": mv,
                "unrealized_pnl": 0.0,
                "cash_after": START_CASH,
                "net_value": market_value + START_CASH,
                "total_return_pct": ((market_value + START_CASH) / INITIAL_CAPITAL - 1) * 100,
            }
        )
    pd.DataFrame(rows).to_csv(DAILY_FILE, index=False, encoding="utf-8-sig")


def fetch_price_point(ticker: str) -> PricePoint | None:
    """获取最新收盘价和前收盘价。"""
    try:
        hist = yf.Ticker(ticker).history(period="7d", interval="1d", auto_adjust=False)
        if hist is None or hist.empty:
            return None
        latest = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) >= 2 else latest
        trade_date = pd.Timestamp(hist.index[-1]).strftime("%Y-%m-%d")
        return PricePoint(
            close=float(latest["Close"]),
            prev_close=float(prev["Close"]),
            trade_date=trade_date,
        )
    except Exception as exc:  # pragma: no cover
        print(f"[WARN] 获取 {ticker} 行情失败: {exc}")
        return None


def choose_trade_date(price_map: Dict[str, PricePoint]) -> str:
    """选择本次决策使用的交易日（取多数日期）。"""
    date_count: Dict[str, int] = {}
    for pp in price_map.values():
        date_count[pp.trade_date] = date_count.get(pp.trade_date, 0) + 1
    return sorted(date_count.items(), key=lambda x: (-x[1], x[0]))[0][0]


def maybe_sell(position: Dict, price: float) -> Tuple[str, int, float, float, str]:
    """卖出规则：达到目标价即全仓卖出。"""
    shares = int(position["shares"])
    if shares <= 0:
        return ("HOLD", 0, 0.0, 0.0, "无持仓")
    if price >= float(position["sell_trigger"]):
        amount = shares * price
        realized = (price - float(position["avg_cost"])) * shares
        return ("SELL", shares, price, amount, f"达到卖出触发价 {position['sell_trigger']}")
    return ("HOLD", 0, 0.0, 0.0, "未达到卖出条件")


def maybe_add(position: Dict, price: float, cash: float) -> Tuple[str, int, float, float, str]:
    """
    加仓规则：
    1) 当前价 <= 成本价*95%
    2) 单标总仓位不超过 max_weight
    3) 累计加仓金额不超过初始投入的30%
    4) 必须按每手整数买入
    """
    shares = int(position["shares"])
    if shares <= 0:
        return ("HOLD", 0, 0.0, 0.0, "已清仓，不加仓")

    avg_cost = float(position["avg_cost"])
    if price > avg_cost * 0.95:
        return ("HOLD", 0, 0.0, 0.0, "未达到回撤5%加仓线")

    max_value = INITIAL_CAPITAL * float(position["max_weight"])
    current_value = shares * price
    remain_weight_budget = max(0.0, max_value - current_value)
    remain_add_budget = max(0.0, float(position["initial_investment"]) * 0.30 - float(position["added_cost_total"]))
    budget = min(remain_weight_budget, remain_add_budget, cash)

    lot_size = int(position["lot_size"])
    lot_cost = lot_size * price
    if lot_cost <= 0:
        return ("HOLD", 0, 0.0, 0.0, "手数配置异常")

    buy_lots = int(budget // lot_cost)
    buy_shares = buy_lots * lot_size
    if buy_shares <= 0:
        return ("HOLD", 0, 0.0, 0.0, "现金或仓位上限不足")

    amount = buy_shares * price
    return ("BUY_ADD", buy_shares, price, amount, "触发回撤5%自动加仓")


def append_trade_records(records: List[Dict]) -> None:
    if not records:
        return
    if TRADES_FILE.exists():
        old = pd.read_csv(TRADES_FILE, encoding="utf-8-sig")
        new_df = pd.concat([old, pd.DataFrame(records)], ignore_index=True)
    else:
        new_df = pd.DataFrame(records)
    new_df.to_csv(TRADES_FILE, index=False, encoding="utf-8-sig")


def append_daily_rows(rows: List[Dict]) -> None:
    if DAILY_FILE.exists():
        old = pd.read_csv(DAILY_FILE, encoding="utf-8-sig")
        new_df = pd.concat([old, pd.DataFrame(rows)], ignore_index=True)
    else:
        new_df = pd.DataFrame(rows)
    new_df.to_csv(DAILY_FILE, index=False, encoding="utf-8-sig")


def generate_report() -> None:
    """从 daily snapshot 自动生成监控 Markdown。"""
    if not DAILY_FILE.exists():
        return

    df = pd.read_csv(DAILY_FILE, encoding="utf-8-sig")
    if df.empty:
        return

    latest_date = str(df["date"].max())
    today = df[df["date"] == latest_date].copy()
    today = today.sort_values("ticker")

    total_market_value = float(today["market_value"].sum())
    cash_after = float(today["cash_after"].iloc[-1])
    net_value = total_market_value + cash_after
    total_return = (net_value / INITIAL_CAPITAL - 1) * 100

    lines = [
        "# 每日股价监控（模拟投资组合-自动更新）",
        "",
        f"> **交易日期**：{latest_date}",
        f"> **更新时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "> **决策引擎**：V1.0（卖出触发 + 回撤加仓 + 仓位上限）",
        "",
        "---",
        "",
        "## 📊 当日持仓与盈亏",
        "",
        "| 标的 | 代码 | 持仓股数 | 成本价 | 收盘价 | 涨跌% | 当日动作 | 持仓市值 | 浮动盈亏 |",
        "|------|------|----------|--------|--------|-------|----------|----------|----------|",
    ]

    for _, r in today.iterrows():
        code = str(r["code"]).zfill(5)
        lines.append(
            f"| {r['name']} | {code} | {int(r['shares'])} | "
            f"{float(r['avg_cost']):.3f} | {float(r['close']):.3f} | "
            f"{float(r['change_pct']):+.2f}% | {r['action']} | "
            f"{float(r['market_value']):,.2f} | {float(r['unrealized_pnl']):+,.2f} |"
        )

    lines.extend(
        [
            f"| **股票合计** | - | - | - | - | - | - | **{total_market_value:,.2f}** | - |",
            f"| **现金余额** | - | - | - | - | - | - | **{cash_after:,.2f}** | - |",
            f"| **组合净值** | - | - | - | - | - | - | **{net_value:,.2f}** | **{total_return:+.2f}%** |",
            "",
            "## 🧾 当日交易动作",
            "",
        ]
    )

    action_rows = today[today["action"].isin(["BUY_ADD", "SELL"])]
    if action_rows.empty:
        lines.append("- 今日无交易动作（全部 HOLD）。")
    else:
        for _, r in action_rows.iterrows():
            lines.append(
                f"- {r['name']} {r['action']}：{int(r['action_shares'])} 股 @ {float(r['action_price']):.3f}，"
                f"金额 {float(r['action_amount']):,.2f} HKD"
            )

    lines.extend(
        [
            "",
            "## 📈 最近10个交易日净值",
            "",
            "| 日期 | 组合净值 | 累计收益率 |",
            "|------|----------|------------|",
        ]
    )

    net_hist = (
        df.groupby("date", as_index=False)
        .agg({"net_value": "last", "total_return_pct": "last"})
        .sort_values("date")
        .tail(10)
    )
    for _, r in net_hist.iterrows():
        lines.append(f"| {r['date']} | {float(r['net_value']):,.2f} | {float(r['total_return_pct']):+.2f}% |")

    lines.extend(
        [
            "",
            "## ✅ 规则说明（已自动执行）",
            "",
            "1. 卖出规则：收盘价 >= 卖出触发价，自动全仓卖出。",
            "2. 加仓规则：收盘价 <= 成本价95%，且满足仓位上限/现金上限/加仓预算后，按每手整数自动加仓。",
            "3. 风控边界：单标仓位不超过组合上限（核心25%，卫星20%），单标累计加仓不超过初始投入30%。",
            "",
            f"*模板版本：V5.5.12；最新交易日：{latest_date}*",
        ]
    )

    REPORT_FILE.write_text("\n".join(lines), encoding="utf-8")


def run() -> int:
    state = ensure_state()

    # 拉行情
    price_map: Dict[str, PricePoint] = {}
    for ticker in state["positions"].keys():
        pp = fetch_price_point(ticker)
        if pp:
            price_map[ticker] = pp

    if not price_map:
        print("[WARN] 未获取到任何行情，跳过本次更新。")
        generate_report()
        return 0

    trade_date = choose_trade_date(price_map)
    if trade_date <= str(state.get("last_trade_date", "")):
        print(f"[INFO] 最新交易日 {trade_date} 未超过已处理日期 {state.get('last_trade_date')}，仅刷新报告。")
        generate_report()
        return 0

    cash = float(state["cash"])
    daily_rows: List[Dict] = []
    trade_records: List[Dict] = []

    # 先卖后买，确保现金先回流
    ordered_tickers = sorted(state["positions"].keys())
    for ticker in ordered_tickers:
        pos = state["positions"][ticker]
        pp = price_map.get(ticker)
        if not pp or pp.trade_date != trade_date:
            continue
        action, action_shares, action_price, action_amount, reason = maybe_sell(pos, pp.close)
        if action == "SELL":
            old_shares = int(pos["shares"])
            realized = (pp.close - float(pos["avg_cost"])) * old_shares
            pos["shares"] = 0
            pos["added_cost_total"] = float(pos.get("added_cost_total", 0.0))
            pos["realized_pnl"] = float(pos.get("realized_pnl", 0.0)) + realized
            cash += action_amount
            trade_records.append(
                {
                    "date": trade_date,
                    "ticker": ticker,
                    "name": pos["name"],
                    "action": action,
                    "price": round(action_price, 4),
                    "shares": int(action_shares),
                    "amount": round(action_amount, 2),
                    "cash_after": round(cash, 2),
                    "reason": reason,
                }
            )

    for ticker in ordered_tickers:
        pos = state["positions"][ticker]
        pp = price_map.get(ticker)
        if not pp or pp.trade_date != trade_date:
            continue

        action = "HOLD"
        action_shares = 0
        action_price = 0.0
        action_amount = 0.0

        if int(pos["shares"]) > 0:
            add_action, add_shares, add_price, add_amount, add_reason = maybe_add(pos, pp.close, cash)
            if add_action == "BUY_ADD":
                old_shares = int(pos["shares"])
                old_cost = float(pos["avg_cost"])
                new_shares = old_shares + int(add_shares)
                new_avg_cost = (old_shares * old_cost + add_amount) / new_shares
                pos["shares"] = new_shares
                pos["avg_cost"] = new_avg_cost
                pos["added_cost_total"] = float(pos.get("added_cost_total", 0.0)) + add_amount
                cash -= add_amount
                action = add_action
                action_shares = int(add_shares)
                action_price = float(add_price)
                action_amount = float(add_amount)
                trade_records.append(
                    {
                        "date": trade_date,
                        "ticker": ticker,
                        "name": pos["name"],
                        "action": action,
                        "price": round(action_price, 4),
                        "shares": int(action_shares),
                        "amount": round(action_amount, 2),
                        "cash_after": round(cash, 2),
                        "reason": add_reason,
                    }
                )

        market_value = int(pos["shares"]) * float(pp.close)
        unrealized = (float(pp.close) - float(pos["avg_cost"])) * int(pos["shares"])

        daily_rows.append(
            {
                "date": trade_date,
                "ticker": ticker,
                "name": pos["name"],
                "code": pos["code"],
                "close": round(pp.close, 4),
                "prev_close": round(pp.prev_close, 4),
                "change_pct": round((pp.close / pp.prev_close - 1) * 100 if pp.prev_close else 0.0, 4),
                "shares": int(pos["shares"]),
                "avg_cost": round(float(pos["avg_cost"]), 6),
                "action": action,
                "action_shares": int(action_shares),
                "action_price": round(action_price, 4),
                "action_amount": round(action_amount, 2),
                "market_value": round(market_value, 2),
                "unrealized_pnl": round(unrealized, 2),
                "cash_after": round(cash, 2),
                "net_value": 0.0,
                "total_return_pct": 0.0,
            }
        )

    total_market_value = sum(float(r["market_value"]) for r in daily_rows)
    net_value = total_market_value + cash
    total_return_pct = (net_value / INITIAL_CAPITAL - 1) * 100
    for r in daily_rows:
        r["net_value"] = round(net_value, 2)
        r["total_return_pct"] = round(total_return_pct, 4)
        r["cash_after"] = round(cash, 2)

    state["cash"] = round(cash, 2)
    state["last_trade_date"] = trade_date
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    append_trade_records(trade_records)
    append_daily_rows(daily_rows)
    generate_report()

    print(f"[OK] 模拟组合已更新，交易日: {trade_date}")
    print(f"[OK] 组合净值: {net_value:,.2f} HKD，累计收益率: {total_return_pct:+.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
