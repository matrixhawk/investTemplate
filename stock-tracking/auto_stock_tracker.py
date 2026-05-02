#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日港股标的追踪脚本 V1.0（对应模板 V5.5.10）

用途：
1. 拉取关注港股近一年价格数据
2. 生成每日追踪报告（Markdown）
3. 输出当日快照（CSV）
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List

import pandas as pd
import yfinance as yf


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "07-分析输出"
OUTPUT_DIR = Path(__file__).resolve().parent / "stock_data"
TRACKED_CODES_FILE = Path(__file__).resolve().parent / "tracked_codes.txt"


@dataclass
class StockSnapshot:
    ticker: str
    code: str
    close: float
    change_5d_pct: float
    high_52w: float
    low_52w: float
    drawdown_from_high_pct: float
    rebound_from_low_pct: float
    signal: str


def load_tracked_hk_codes() -> List[str]:
    """从追踪代码文件读取港股代码（格式：06049.HK，每行一个）。"""
    if not TRACKED_CODES_FILE.exists():
        return []
    raw_lines = TRACKED_CODES_FILE.read_text(encoding="utf-8").splitlines()
    tickers: List[str] = []
    for line in raw_lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if re.fullmatch(r"\d{5}\.HK", s):
            tickers.append(s)
    return sorted(set(tickers))


def fetch_history(ticker: str) -> pd.DataFrame:
    """拉取单标的一年日线。"""
    data = yf.download(
        tickers=ticker,
        period="1y",
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    if data is None or data.empty:
        return pd.DataFrame()
    return data.dropna(how="all")


def build_snapshot(ticker: str, df: pd.DataFrame) -> StockSnapshot | None:
    """从价格序列构建追踪快照。"""
    if df.empty or "Close" not in df.columns:
        return None
    close = float(df["Close"].iloc[-1])
    close_5d = float(df["Close"].iloc[-6]) if len(df) >= 6 else float(df["Close"].iloc[0])
    high_52w = float(df["High"].max())
    low_52w = float(df["Low"].min())
    change_5d_pct = (close / close_5d - 1) * 100 if close_5d else 0.0
    drawdown_from_high_pct = (1 - close / high_52w) * 100 if high_52w else 0.0
    rebound_from_low_pct = (close / low_52w - 1) * 100 if low_52w else 0.0

    # 简化买入信号：距离52周低点不超过10%，且较52周高点回撤超过45%
    is_buy = rebound_from_low_pct <= 10 and drawdown_from_high_pct >= 45
    signal = "🔴 **可买**" if is_buy else "⚪ 观察"

    code = ticker.replace(".HK", "")
    return StockSnapshot(
        ticker=ticker,
        code=code,
        close=close,
        change_5d_pct=change_5d_pct,
        high_52w=high_52w,
        low_52w=low_52w,
        drawdown_from_high_pct=drawdown_from_high_pct,
        rebound_from_low_pct=rebound_from_low_pct,
        signal=signal,
    )


def write_outputs(rows: List[StockSnapshot]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    df = pd.DataFrame(
        [
            {
                "ticker": r.ticker,
                "code": r.code,
                "close": round(r.close, 3),
                "change_5d_pct": round(r.change_5d_pct, 2),
                "high_52w": round(r.high_52w, 3),
                "low_52w": round(r.low_52w, 3),
                "drawdown_from_high_pct": round(r.drawdown_from_high_pct, 2),
                "rebound_from_low_pct": round(r.rebound_from_low_pct, 2),
                "signal": r.signal,
            }
            for r in rows
        ]
    ).sort_values(["signal", "drawdown_from_high_pct"], ascending=[True, False])

    csv_path = OUTPUT_DIR / f"daily_snapshot_{ts}.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    buy_rows = [r for r in rows if "可买" in r.signal]
    report_path = OUTPUT_DIR / "daily_report.md"
    with report_path.open("w", encoding="utf-8") as f:
        f.write("# 每日港股标的追踪报告\n\n")
        f.write(f"- 日期（UTC）: {today}\n")
        f.write(f"- 追踪数量: {len(rows)}\n")
        f.write("- 规则: 距52周低点<=10% 且 距52周高点回撤>=45%\n\n")
        f.write("## 🔔 买入提醒\n\n")
        if buy_rows:
            for r in buy_rows:
                f.write(
                    f"- {r.signal} {r.code}（{r.ticker}）："
                    f"较52周高点回撤 {r.drawdown_from_high_pct:.1f}%，"
                    f"距52周低点反弹 {r.rebound_from_low_pct:.1f}%\n"
                )
        else:
            f.write("- 今日暂无触发条件的标的\n")

        f.write("\n## 📊 全量快照\n\n")
        f.write("| 代码 | 收盘价 | 5日涨跌 | 较52周高点回撤 | 距52周低点反弹 | 信号 |\n")
        f.write("|------|--------|---------|------------------|----------------|------|\n")
        for r in rows:
            f.write(
                f"| {r.code} | {r.close:.3f} | {r.change_5d_pct:.2f}% | "
                f"{r.drawdown_from_high_pct:.2f}% | {r.rebound_from_low_pct:.2f}% | {r.signal} |\n"
            )

    print(f"[OK] 生成报告: {report_path}")
    print(f"[OK] 生成快照: {csv_path}")


def main() -> int:
    tickers = load_tracked_hk_codes()
    if not tickers:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        (OUTPUT_DIR / "daily_report.md").write_text(
            "# 每日港股标的追踪报告\n\n"
            f"- 日期（UTC）: {today}\n"
            "- `tracked_codes.txt` 为空或不存在，已跳过行情查询。\n",
            encoding="utf-8",
        )
        print("[INFO] tracked_codes.txt 为空或不存在，已跳过行情查询。")
        return 0

    rows: List[StockSnapshot] = []
    for ticker in tickers:
        try:
            hist = fetch_history(ticker)
            snap = build_snapshot(ticker, hist)
            if snap:
                rows.append(snap)
        except Exception as e:
            print(f"[WARN] 拉取 {ticker} 失败: {e}")

    if not rows:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / "daily_report.md").write_text(
            "# 每日港股标的追踪报告\n\n- 今日未获取到有效行情数据，请稍后重试。\n",
            encoding="utf-8",
        )
        print("[WARN] 未生成有效快照，仅输出空报告。")
        return 0

    write_outputs(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
