# -*- coding: utf-8 -*-
"""
模拟持仓自动决策引擎 V2.0（报告池动态筛选版）

核心规则：
1. 监控池来自 07-分析输出/*_投资分析报告.md（动态增删）
2. 单个持仓上限 15%（不压票，避免重仓单押）
3. 达到卖出触发价即卖出（不压票执行）
4. 回撤 5% 可加仓，但仍受 15% 上限与现金约束
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import akshare as ak
import pandas as pd
import yfinance as yf


ROOT = Path(__file__).resolve().parents[1]
REPORT_POOL_DIR = ROOT / "07-分析输出"
TRACK_DIR = ROOT / "08-决策追踪"
STATE_FILE = TRACK_DIR / "simulation_state.json"
TRADES_FILE = TRACK_DIR / "simulation_trades.csv"
DAILY_FILE = TRACK_DIR / "simulation_daily_snapshot.csv"
REPORT_FILE = TRACK_DIR / "每日股价监控.md"

INITIAL_CAPITAL = 500000.0
MIN_CASH_RESERVE = INITIAL_CAPITAL * 0.10
POSITION_CAP = 0.15
START_DATE = "2026-03-26"
START_CASH = 52500.0

HK_SPOT_CACHE: pd.DataFrame | None = None
A_SPOT_CACHE: pd.DataFrame | None = None
AK_HK_FAILED = False
AK_A_FAILED = False

# 保留原始4只建仓，作为历史初始状态
INITIAL_POSITIONS = [
    {"name": "京投交通科技", "code": "01522", "ticker": "1522.HK", "shares": 342000, "avg_cost": 0.365, "sell_trigger": 0.60, "lot_size": 2000},
    {"name": "汇贤产业信托", "code": "87001", "ticker": "87001.HK", "shares": 250000, "avg_cost": 0.50, "sell_trigger": 1.00, "lot_size": 1000},
    {"name": "天津发展", "code": "00882", "ticker": "882.HK", "shares": 40000, "avg_cost": 2.50, "sell_trigger": 4.50, "lot_size": 1000},
    {"name": "华润医药", "code": "03320", "ticker": "3320.HK", "shares": 15000, "avg_cost": 6.50, "sell_trigger": 9.00, "lot_size": 500},
]


@dataclass
class PricePoint:
    close: float
    prev_close: float
    trade_date: str


def build_ticker(code: str) -> str:
    if len(code) == 5:
        return f"{int(code)}.HK"
    if code.startswith("6"):
        return f"{code}.SS"
    return f"{code}.SZ"


def default_lot_size(code: str) -> int:
    return 1000 if len(code) == 5 else 100


def parse_report_pool() -> Dict[str, Dict]:
    pool: Dict[str, Dict] = {}
    for report in REPORT_POOL_DIR.glob("*_投资分析报告.md"):
        m = re.match(r"(.+?)_(\d+)_投资分析报告", report.stem)
        if not m:
            continue
        name, code = m.group(1), m.group(2)
        ticker = build_ticker(code)
        content = report.read_text(encoding="utf-8")

        buy_prices = []
        for line in content.splitlines():
            if "买点" in line and ("元" in line or "港元" in line):
                pm = re.search(r"(\d+(?:\.\d+)?)\s*[元港]", line)
                if pm:
                    buy_prices.append(float(pm.group(1)))
        target_buy = max(buy_prices) if buy_prices else None

        sm = re.search(r"卖出触发(?:价|条件)?[^\d]{0,10}(\d+(?:\.\d+)?)", content)
        sell_trigger = float(sm.group(1)) if sm else (target_buy * 1.35 if target_buy else 0.0)

        lm = re.search(r"每手数量[^\d]{0,10}([\d,]+)\s*股", content)
        lot_size = int(lm.group(1).replace(",", "")) if lm else default_lot_size(code)

        status = "观望"
        if "可建仓" in content or "买入" in content:
            status = "可买入"
        if "回避" in content:
            status = "回避"

        pool[ticker] = {
            "name": name,
            "code": code,
            "ticker": ticker,
            "target_buy": target_buy,
            "sell_trigger": sell_trigger,
            "lot_size": lot_size,
            "status": status,
            "max_weight": POSITION_CAP,
        }
    return pool


def seed_state() -> Dict:
    positions: Dict[str, Dict] = {}
    for p in INITIAL_POSITIONS:
        positions[p["ticker"]] = {
            **p,
            "max_weight": POSITION_CAP,
            "target_buy": p["avg_cost"],
            "added_cost_total": 0.0,
            "realized_pnl": 0.0,
        }
    return {
        "template_version": "V5.5.12",
        "engine_version": "V2.0",
        "initial_capital": INITIAL_CAPITAL,
        "cash": START_CASH,
        "last_trade_date": START_DATE,
        "positions": positions,
    }


def ensure_state() -> Dict:
    TRACK_DIR.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    state = seed_state()
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state


def sync_positions_with_pool(state: Dict, pool: Dict[str, Dict]) -> Dict:
    old_positions = state["positions"]
    positions: Dict[str, Dict] = {}

    # 迁移老状态中的港股 ticker（01522.HK -> 1522.HK）
    for old_ticker, p in old_positions.items():
        if old_ticker.endswith(".HK"):
            try:
                code_part = old_ticker.split(".")[0]
                new_ticker = f"{int(code_part)}.HK"
                positions[new_ticker] = p
                positions[new_ticker]["ticker"] = new_ticker
            except ValueError:
                positions[old_ticker] = p
        else:
            positions[old_ticker] = p

    for ticker, info in pool.items():
        if ticker not in positions:
            positions[ticker] = {
                "name": info["name"],
                "code": info["code"],
                "ticker": ticker,
                "shares": 0,
                "avg_cost": 0.0,
                "sell_trigger": info["sell_trigger"],
                "target_buy": info["target_buy"],
                "lot_size": info["lot_size"],
                "max_weight": POSITION_CAP,
                "added_cost_total": 0.0,
                "realized_pnl": 0.0,
            }
        else:
            p = positions[ticker]
            p["name"] = info["name"]
            p["code"] = info["code"]
            p["lot_size"] = info["lot_size"]
            p["sell_trigger"] = info["sell_trigger"] or p.get("sell_trigger", 0.0)
            p["target_buy"] = info["target_buy"] if info["target_buy"] else p.get("target_buy")
            p["max_weight"] = POSITION_CAP

    # 从报告池移除后，若无持仓则从状态删除
    active_tickers = set(pool.keys())
    to_drop = []
    for ticker, p in positions.items():
        if ticker not in active_tickers and int(p.get("shares", 0)) == 0:
            to_drop.append(ticker)
    for ticker in to_drop:
        positions.pop(ticker, None)

    state["positions"] = positions
    return state


def fetch_price_point(ticker: str) -> PricePoint | None:
    return fetch_price_point_with_fallback(ticker, "")


def load_hk_spot() -> pd.DataFrame:
    global HK_SPOT_CACHE
    global AK_HK_FAILED
    if AK_HK_FAILED:
        return pd.DataFrame()
    if HK_SPOT_CACHE is None:
        try:
            HK_SPOT_CACHE = ak.stock_hk_spot_em()
        except Exception as exc:  # pragma: no cover
            AK_HK_FAILED = True
            print(f"[WARN] akshare 港股现价接口不可用，已切换兜底源: {exc}")
            return pd.DataFrame()
    return HK_SPOT_CACHE


def load_a_spot() -> pd.DataFrame:
    global A_SPOT_CACHE
    global AK_A_FAILED
    if AK_A_FAILED:
        return pd.DataFrame()
    if A_SPOT_CACHE is None:
        try:
            A_SPOT_CACHE = ak.stock_zh_a_spot_em()
        except Exception as exc:  # pragma: no cover
            AK_A_FAILED = True
            print(f"[WARN] akshare A股现价接口不可用，已切换兜底源: {exc}")
            return pd.DataFrame()
    return A_SPOT_CACHE


def parse_float(v) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).replace(",", "").replace("%", "").strip()
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fetch_price_from_akshare(code: str) -> PricePoint | None:
    try:
        if len(code) == 5:  # 港股
            df = load_hk_spot()
            if df is None or df.empty or "代码" not in df.columns:
                return None
            code5 = str(code).zfill(5)
            cand = df[df["代码"].astype(str).str.zfill(5) == code5]
        else:  # A股
            df = load_a_spot()
            if df is None or df.empty or "代码" not in df.columns:
                return None
            code6 = str(code).zfill(6)
            cand = df[df["代码"].astype(str).str.zfill(6) == code6]

        if cand.empty:
            return None
        row = cand.iloc[0]
        close = parse_float(row.get("最新价"))
        change_pct = parse_float(row.get("涨跌幅"))
        if close is None:
            return None
        if change_pct is None:
            prev_close = close
        else:
            prev_close = close / (1 + change_pct / 100) if change_pct != -100 else close
        return PricePoint(
            close=float(close),
            prev_close=float(prev_close),
            trade_date=datetime.now().strftime("%Y-%m-%d"),
        )
    except Exception:  # pragma: no cover
        return None


def fetch_price_point_with_fallback(ticker: str, code: str) -> PricePoint | None:
    # 主源：akshare（东方财富）
    if code:
        ak_pp = fetch_price_from_akshare(code)
        if ak_pp:
            return ak_pp

    # 兜底：yfinance（港股多格式兼容）
    candidates = [ticker]
    if len(code) == 5:
        candidates = []
        if code.startswith("0"):
            candidates.extend(
                [
                    f"{code[1:]}.HK",     # 00882 -> 0882
                    f"{code}.HK",         # 00882 -> 00882
                    f"{int(code)}.HK",
                ]
            )
        else:
            candidates.extend([f"{code}.HK", f"{int(code)}.HK"])
    unique_candidates = []
    for c in candidates:
        if c not in unique_candidates:
            unique_candidates.append(c)

    for tk in unique_candidates:
        try:
            hist = yf.Ticker(tk).history(period="7d", interval="1d", auto_adjust=False)
            if hist is None or hist.empty:
                continue
            latest = hist.iloc[-1]
            prev = hist.iloc[-2] if len(hist) >= 2 else latest
            return PricePoint(
                close=float(latest["Close"]),
                prev_close=float(prev["Close"]),
                trade_date=pd.Timestamp(hist.index[-1]).strftime("%Y-%m-%d"),
            )
        except Exception:
            continue
    return None


def choose_trade_date(price_map: Dict[str, PricePoint]) -> str:
    counts: Dict[str, int] = {}
    for p in price_map.values():
        counts[p.trade_date] = counts.get(p.trade_date, 0) + 1
    return sorted(counts.items(), key=lambda x: (-x[1], x[0]))[0][0]


def maybe_sell(position: Dict, price: float) -> Tuple[str, int, float, float, str]:
    shares = int(position.get("shares", 0))
    if shares <= 0:
        return ("WATCH", 0, 0.0, 0.0, "无持仓")
    trigger = float(position.get("sell_trigger", 0.0))
    if trigger > 0 and price >= trigger:
        amount = shares * price
        return ("SELL", shares, price, amount, f"达到卖出触发价 {trigger}")
    return ("HOLD", 0, 0.0, 0.0, "未触发卖出")


def maybe_open(position: Dict, price: float, cash: float) -> Tuple[str, int, float, float, str]:
    shares = int(position.get("shares", 0))
    if shares > 0:
        return ("HOLD", 0, 0.0, 0.0, "已有持仓")

    target_buy = position.get("target_buy")
    if not target_buy or price > float(target_buy):
        return ("WATCH", 0, 0.0, 0.0, "未到买点")

    available_cash = max(0.0, cash - MIN_CASH_RESERVE)
    if available_cash <= 0:
        return ("WATCH", 0, 0.0, 0.0, "保留现金不足")

    max_value = INITIAL_CAPITAL * POSITION_CAP
    budget = min(max_value, available_cash)
    lot_size = int(position.get("lot_size", 1000))
    lot_cost = lot_size * price
    if lot_cost <= 0:
        return ("WATCH", 0, 0.0, 0.0, "手数异常")
    buy_lots = int(budget // lot_cost)
    buy_shares = buy_lots * lot_size
    if buy_shares <= 0:
        return ("WATCH", 0, 0.0, 0.0, "预算不足一手")

    amount = buy_shares * price
    return ("BUY_OPEN", buy_shares, price, amount, "到达买点自动开仓")


def maybe_add(position: Dict, price: float, cash: float) -> Tuple[str, int, float, float, str]:
    shares = int(position.get("shares", 0))
    if shares <= 0:
        return ("WATCH", 0, 0.0, 0.0, "无持仓")

    avg_cost = float(position.get("avg_cost", 0.0))
    if avg_cost <= 0 or price > avg_cost * 0.95:
        return ("HOLD", 0, 0.0, 0.0, "未触发回撤加仓")

    max_value = INITIAL_CAPITAL * POSITION_CAP
    current_value = shares * price
    remain_cap = max(0.0, max_value - current_value)
    if remain_cap <= 0:
        return ("HOLD", 0, 0.0, 0.0, "达到单仓15%上限")

    available_cash = max(0.0, cash - MIN_CASH_RESERVE)
    budget = min(remain_cap, available_cash, max_value * 0.30)
    lot_size = int(position.get("lot_size", 1000))
    lot_cost = lot_size * price
    if lot_cost <= 0:
        return ("HOLD", 0, 0.0, 0.0, "手数异常")

    buy_lots = int(budget // lot_cost)
    buy_shares = buy_lots * lot_size
    if buy_shares <= 0:
        return ("HOLD", 0, 0.0, 0.0, "现金不足一手")

    amount = buy_shares * price
    return ("BUY_ADD", buy_shares, price, amount, "回撤5%自动加仓")


def append_table(file: Path, rows: List[Dict]) -> None:
    if not rows:
        return
    if file.exists():
        old = pd.read_csv(file, encoding="utf-8-sig")
        df = pd.concat([old, pd.DataFrame(rows)], ignore_index=True)
    else:
        df = pd.DataFrame(rows)
    df.to_csv(file, index=False, encoding="utf-8-sig")


def generate_report() -> None:
    if not DAILY_FILE.exists():
        return
    df = pd.read_csv(DAILY_FILE, encoding="utf-8-sig")
    if df.empty:
        return

    latest_date = str(df["date"].max())
    today = df[df["date"] == latest_date].copy().sort_values(["action", "ticker"])
    total_market = float(today["market_value"].sum())
    cash = float(today["cash_after"].iloc[-1])
    net_value = total_market + cash
    ret = (net_value / INITIAL_CAPITAL - 1) * 100

    lines = [
        "# 每日股价监控（模拟投资组合-自动更新）",
        "",
        f"> **交易日期**：{latest_date}",
        f"> **更新时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "> **规则**：报告池动态筛选 + 单仓上限15% + 不压票动态卖出",
        "",
        "## 📊 当日监控",
        "",
        "| 标的 | 代码 | 股数 | 成本价 | 收盘价 | 涨跌% | 当日动作 | 持仓市值 | 浮动盈亏 |",
        "|------|------|------|--------|--------|-------|----------|----------|----------|",
    ]

    for _, r in today.iterrows():
        code = str(r["code"]).zfill(5)
        lines.append(
            f"| {r['name']} | {code} | {int(r['shares'])} | {float(r['avg_cost']):.3f} | {float(r['close']):.3f} | "
            f"{float(r['change_pct']):+.2f}% | {r['action']} | {float(r['market_value']):,.2f} | {float(r['unrealized_pnl']):+,.2f} |"
        )

    lines.extend(
        [
            f"| **股票合计** | - | - | - | - | - | - | **{total_market:,.2f}** | - |",
            f"| **现金余额** | - | - | - | - | - | - | **{cash:,.2f}** | - |",
            f"| **组合净值** | - | - | - | - | - | - | **{net_value:,.2f}** | **{ret:+.2f}%** |",
            "",
        ]
    )

    REPORT_FILE.write_text("\n".join(lines), encoding="utf-8")


def run() -> int:
    state = ensure_state()
    pool = parse_report_pool()
    state = sync_positions_with_pool(state, pool)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    tickers = sorted(state["positions"].keys())
    price_map: Dict[str, PricePoint] = {}
    for t in tickers:
        pp = fetch_price_point_with_fallback(t, str(state["positions"][t].get("code", "")))
        if pp:
            price_map[t] = pp

    if not price_map:
        print("[WARN] 未获取到有效行情。")
        return 0

    trade_date = choose_trade_date(price_map)
    if trade_date <= str(state.get("last_trade_date", "")):
        print(f"[INFO] 最新交易日 {trade_date} 未超过 {state.get('last_trade_date')}，刷新报告。")
        generate_report()
        return 0

    cash = float(state["cash"])
    trades: List[Dict] = []
    daily_rows: List[Dict] = []

    # 1) 先卖出，执行不压票
    for t in tickers:
        p = state["positions"][t]
        pp = price_map.get(t)
        if not pp or pp.trade_date != trade_date:
            continue
        action, shares, px, amount, reason = maybe_sell(p, pp.close)
        if action == "SELL":
            old_shares = int(p["shares"])
            realized = (pp.close - float(p["avg_cost"])) * old_shares
            p["shares"] = 0
            p["realized_pnl"] = float(p.get("realized_pnl", 0.0)) + realized
            cash += amount
            trades.append({
                "date": trade_date, "ticker": t, "name": p["name"], "action": action,
                "price": round(px, 4), "shares": shares, "amount": round(amount, 2),
                "cash_after": round(cash, 2), "reason": reason
            })

    # 2) 开仓/加仓
    for t in tickers:
        p = state["positions"][t]
        pp = price_map.get(t)
        if not pp or pp.trade_date != trade_date:
            continue

        action = "WATCH"
        act_shares = 0
        act_px = 0.0
        act_amt = 0.0

        if int(p["shares"]) == 0:
            action, act_shares, act_px, act_amt, reason = maybe_open(p, pp.close, cash)
            if action == "BUY_OPEN":
                p["shares"] = int(act_shares)
                p["avg_cost"] = float(act_px)
                cash -= act_amt
                trades.append({
                    "date": trade_date, "ticker": t, "name": p["name"], "action": action,
                    "price": round(act_px, 4), "shares": int(act_shares), "amount": round(act_amt, 2),
                    "cash_after": round(cash, 2), "reason": reason
                })
        else:
            action = "HOLD"
            add_action, add_shares, add_px, add_amt, reason = maybe_add(p, pp.close, cash)
            if add_action == "BUY_ADD":
                old_shares = int(p["shares"])
                new_shares = old_shares + int(add_shares)
                p["avg_cost"] = (old_shares * float(p["avg_cost"]) + add_amt) / new_shares
                p["shares"] = new_shares
                p["added_cost_total"] = float(p.get("added_cost_total", 0.0)) + add_amt
                cash -= add_amt
                action, act_shares, act_px, act_amt = add_action, int(add_shares), float(add_px), float(add_amt)
                trades.append({
                    "date": trade_date, "ticker": t, "name": p["name"], "action": action,
                    "price": round(act_px, 4), "shares": int(act_shares), "amount": round(act_amt, 2),
                    "cash_after": round(cash, 2), "reason": reason
                })

        mv = int(p["shares"]) * float(pp.close)
        pnl = (float(pp.close) - float(p["avg_cost"])) * int(p["shares"])
        daily_rows.append({
            "date": trade_date,
            "ticker": t,
            "name": p["name"],
            "code": p["code"],
            "close": round(pp.close, 4),
            "prev_close": round(pp.prev_close, 4),
            "change_pct": round((pp.close / pp.prev_close - 1) * 100 if pp.prev_close else 0.0, 4),
            "shares": int(p["shares"]),
            "avg_cost": round(float(p["avg_cost"]), 6),
            "action": action,
            "action_shares": int(act_shares),
            "action_price": round(act_px, 4),
            "action_amount": round(act_amt, 2),
            "market_value": round(mv, 2),
            "unrealized_pnl": round(pnl, 2),
            "cash_after": round(cash, 2),
            "net_value": 0.0,
            "total_return_pct": 0.0,
        })

    total_market = sum(float(r["market_value"]) for r in daily_rows)
    net = total_market + cash
    ret = (net / INITIAL_CAPITAL - 1) * 100
    for r in daily_rows:
        r["cash_after"] = round(cash, 2)
        r["net_value"] = round(net, 2)
        r["total_return_pct"] = round(ret, 4)

    state["cash"] = round(cash, 2)
    state["last_trade_date"] = trade_date
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    append_table(TRADES_FILE, trades)
    append_table(DAILY_FILE, daily_rows)
    generate_report()

    print(f"[OK] 报告池标的数量: {len(pool)}")
    print(f"[OK] 模拟组合更新完成，交易日: {trade_date}")
    print(f"[OK] 组合净值: {net:,.2f} HKD，累计收益率: {ret:+.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
