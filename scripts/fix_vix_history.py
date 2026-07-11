# -*- coding: utf-8 -*-
"""
修正VIX定投策略2026-06-03至06-05的历史数据
基于腾讯日K线真实收盘价重新计算
"""

import json
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRATEGY_DIR = ROOT / "decision-tracking" / "vix_dca_strategy"
PUBLIC_DIR = ROOT / "public" / "vix_strategy"
TEMPLATE_DIR = ROOT / "portfolio"

DAILY_RETURNS_FILE = STRATEGY_DIR / "daily_returns.csv"
SNAPSHOT_FILE = STRATEGY_DIR / "daily_snapshot.csv"
STATE_FILE = STRATEGY_DIR / "state.json"
DASHBOARD_FILE = STRATEGY_DIR / "dashboard_data.json"
RETURNS_CURVE_SVG = STRATEGY_DIR / "returns_curve.svg"
RETURNS_CURVE_HTML = STRATEGY_DIR / "returns_curve.html"

# 腾讯K线数据（日期, 开盘, 收盘, 最高, 最低, 成交量）
HISTORY = {
    "2026-06-03": {"price": 2.563, "vix": 16.04},
    "2026-06-04": {"price": 2.499, "vix": 16.60},
    "2026-06-05": {"price": 2.463, "vix": 15.64},
}

# 持仓基础（6月2日交易后）
SHARES = 4566
AVG_COST = 2.1233066141042487
TOTAL_COST = 9695.018
CASH = 91603.51
CUMULATIVE_BUY = 9700.0


def calc_day(date_str, price, prev_unrealized):
    market_value = round(SHARES * price, 2)
    unrealized = round(market_value - TOTAL_COST, 2)
    daily_pnl = round(unrealized - prev_unrealized, 2)
    return_pct = round(unrealized / TOTAL_COST * 100, 2)
    total_return_pct = round((market_value - CUMULATIVE_BUY) / CUMULATIVE_BUY * 100, 2)
    net_value = market_value  # dca mode
    return {
        "date": date_str,
        "price": price,
        "market_value": market_value,
        "unrealized": unrealized,
        "daily_pnl": daily_pnl,
        "return_pct": return_pct,
        "total_return_pct": total_return_pct,
        "net_value": net_value,
    }


def fix_daily_returns():
    rows = []
    with open(DAILY_RETURNS_FILE, 'r', newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        rows = list(reader)

    prev_unrealized = 2185.71  # 6月2日的unrealized

    for i, row in enumerate(rows):
        if row and row[0] in HISTORY:
            h = HISTORY[row[0]]
            calc = calc_day(row[0], h["price"], prev_unrealized)
            row[1] = str(h["vix"])
            row[2] = str(calc["price"])
            row[5] = str(calc["market_value"])
            row[7] = str(calc["unrealized"])
            row[8] = str(calc["daily_pnl"])
            row[9] = str(calc["return_pct"])
            row[10] = str(calc["total_return_pct"])
            row[12] = str(calc["net_value"])
            row[13] = f"VIX{h['vix']}_HOLD"
            prev_unrealized = calc["unrealized"]
            print(f"[修正] daily_returns.csv {row[0]}: 价格->{calc['price']}, 收益->{calc['unrealized']}, 当日->{calc['daily_pnl']}")

    with open(DAILY_RETURNS_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows(rows)
    print("[保存] daily_returns.csv")


def fix_snapshot():
    rows = []
    with open(SNAPSHOT_FILE, 'r', newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        rows = list(reader)

    prev_unrealized = 2185.71

    for i, row in enumerate(rows):
        if row and row[0] in HISTORY:
            h = HISTORY[row[0]]
            calc = calc_day(row[0], h["price"], prev_unrealized)
            row[1] = str(h["vix"])
            row[2] = str(calc["price"])
            row[4] = str(calc["market_value"])
            row[5] = str(CASH)
            row[6] = str(calc["net_value"])
            row[8] = str(calc["unrealized"])
            row[9] = str(calc["daily_pnl"])
            row[10] = str(calc["return_pct"])
            row[11] = f"VIX{h['vix']},持仓不动"
            prev_unrealized = calc["unrealized"]
            print(f"[修正] daily_snapshot.csv {row[0]}: 价格->{calc['price']}, 收益->{calc['unrealized']}, 当日->{calc['daily_pnl']}")

    with open(SNAPSHOT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows(rows)
    print("[保存] daily_snapshot.csv")


def fix_dashboard_snapshots():
    with open(DASHBOARD_FILE, 'r', encoding='utf-8') as f:
        dashboard = json.load(f)

    snaps = dashboard.get('daily_snapshots', [])
    prev_unrealized = 2185.71

    for snap in snaps:
        d = snap.get('date')
        if d in HISTORY:
            h = HISTORY[d]
            calc = calc_day(d, h["price"], prev_unrealized)
            snap['price'] = calc['price']
            snap['pnl'] = calc['unrealized']
            snap['daily_pnl'] = calc['daily_pnl']
            prev_unrealized = calc['unrealized']
            print(f"[修正] dashboard snapshot {d}: 价格->{calc['price']}, 收益->{calc['unrealized']}")

    # 更新performance为最新（6月5日）
    last = HISTORY["2026-06-05"]
    calc = calc_day("2026-06-05", last["price"], 1715.41)  # 6月4日的unrealized
    dashboard['performance'] = {
        'total_pnl': calc['unrealized'],
        'total_return_pct': calc['total_return_pct'],
        'daily_pnl': calc['daily_pnl'],
        'vix': last['vix'],
        'date': '2026-06-05'
    }

    # 更新position
    dashboard['position']['current_price'] = last['price']
    dashboard['position']['market_value'] = calc['market_value']
    dashboard['position']['unrealized_pnl'] = calc['unrealized']
    dashboard['position']['return_pct'] = calc['return_pct']

    with open(DASHBOARD_FILE, 'w', encoding='utf-8') as f:
        json.dump(dashboard, f, indent=2, ensure_ascii=False)
    print("[保存] dashboard_data.json")

    return dashboard


def fix_state():
    with open(STATE_FILE, 'r', encoding='utf-8') as f:
        state = json.load(f)

    last = HISTORY["2026-06-05"]
    market_value = round(SHARES * last['price'], 2)
    unrealized = round(market_value - TOTAL_COST, 2)
    return_pct = round(unrealized / TOTAL_COST * 100, 2)
    total_return_pct = round((market_value - CUMULATIVE_BUY) / CUMULATIVE_BUY * 100, 2)
    daily_pnl = round(unrealized - 1715.41, 2)  # 基于6月4日

    state['position']['current_price'] = last['price']
    state['position']['market_value'] = market_value
    state['position']['unrealized_pnl'] = unrealized
    state['position']['return_pct'] = return_pct

    state['daily_performance'] = {
        'date': '2026-06-05',
        'vix': last['vix'],
        'daily_pnl': daily_pnl,
        'total_pnl': unrealized,
        'total_return_pct': total_return_pct
    }

    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    print("[保存] state.json")
    return state


def regenerate_charts_and_sync():
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from auto_update_vix_dca import (
        load_daily_returns, load_daily_returns_full,
        generate_returns_curve_svg, generate_returns_curve_html,
        update_markdown_template, sync_to_public,
        STATE_FILE, DASHBOARD_FILE, RETURNS_CURVE_SVG, RETURNS_CURVE_HTML
    )

    state = fix_state()
    dashboard = fix_dashboard_snapshots()

    # 重新生成收益率曲线
    returns_history = load_daily_returns()
    if returns_history:
        generate_returns_curve_svg(RETURNS_CURVE_SVG, returns_history)

    returns_history_full = load_daily_returns_full()
    if returns_history_full:
        generate_returns_curve_html(RETURNS_CURVE_HTML, returns_history_full)

    # 重新生成markdown
    update_markdown_template(state, '2026-06-05', 15.64, 2.463)

    # 同步
    sync_to_public(state, dashboard)
    print("[完成] 图表、Markdown和同步")


def main():
    print("=== VIX策略历史数据修正 ===")
    fix_daily_returns()
    fix_snapshot()
    regenerate_charts_and_sync()
    print("\n=== 修正完成 ===")


if __name__ == "__main__":
    main()
