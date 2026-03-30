# -*- coding: utf-8 -*-
"""
VIX-纳斯达克100定投回测脚本 V1.0
基于恐慌指数(VIX)的动态加仓定投策略回测
"""

import warnings
warnings.filterwarnings('ignore')

import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime

# 路径配置
ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "05-策略框架" / "VIX-纳斯达克100定投策略"
CHARTS_DIR = OUTPUT_DIR / "charts"
REPORT_FILE = OUTPUT_DIR / "backtest_report.md"

# 确保目录存在
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

# 回测配置
BACKTEST_CONFIG = {
    'start_date': '2015-01-01',
    'base_monthly_investment': 1000,   # USD
    'investment_day': 1,               # 每月第1个交易日
    'vix_rules': [
        # (vix_low, vix_high, multiplier, label)
        (0,  15, 1.0, '正常'),
        (15, 20, 1.5, '轻度恐慌'),
        (20, 25, 2.0, '中度恐慌'),
        (25, 30, 3.0, '高度恐慌'),
        (30, 999, 5.0, '极度恐慌'),
    ],
    'risk_free_rate': 0.03,  # 无风险利率 3%
    'transaction_cost': 0,    # 每笔交易成本（USD），默认0
}


def get_multiplier(vix_value):
    """根据VIX值获取加仓倍数"""
    for low, high, mult, label in BACKTEST_CONFIG['vix_rules']:
        if low <= vix_value < high:
            return mult, label
    return 1.0, '正常'


def download_data():
    """下载VIX和QQQ历史数据"""
    print("正在下载历史数据...")
    start = BACKTEST_CONFIG['start_date']
    end = datetime.now().strftime('%Y-%m-%d')
    
    # 下载 QQQ (纳斯达克100 ETF，已复权)
    qqq = yf.download('QQQ', start=start, end=end, progress=False, auto_adjust=True)
    # 下载 VIX
    vix = yf.download('^VIX', start=start, end=end, progress=False, auto_adjust=True)
    
    # 处理多级列索引（yfinance新版本可能返回MultiIndex）
    if isinstance(qqq.columns, pd.MultiIndex):
        qqq.columns = qqq.columns.get_level_values(0)
    if isinstance(vix.columns, pd.MultiIndex):
        vix.columns = vix.columns.get_level_values(0)
    
    # 确保是Series或一维DataFrame
    qqq_close = qqq['Close'].squeeze()
    vix_close = vix['Close'].squeeze()
    
    # 合并数据
    df = pd.DataFrame({
        'QQQ': qqq_close,
        'VIX': vix_close,
    })
    df = df.dropna()
    print(f"数据下载完成，共 {len(df)} 个交易日，从 {df.index[0].strftime('%Y-%m-%d')} 到 {df.index[-1].strftime('%Y-%m-%d')}")
    return df


def get_investment_dates(df):
    """获取每月第N个交易日"""
    df = df.copy()
    df['year_month'] = df.index.to_period('M')
    
    # 按年月分组，取第 investment_day 个交易日
    n = BACKTEST_CONFIG['investment_day']
    grouped = df.groupby('year_month')
    dates = []
    for _, group in grouped:
        if len(group) >= n:
            dates.append(group.index[n - 1])
    return pd.DatetimeIndex(dates)


def backtest_vix_dca(df, dates):
    """VIX增强定投策略回测"""
    base_amount = BACKTEST_CONFIG['base_monthly_investment']
    tx_cost = BACKTEST_CONFIG['transaction_cost']
    
    shares = 0.0
    cash_invested = 0.0
    records = []
    
    for d in dates:
        # 找到前一个交易日（用于获取VIX）
        idx = df.index.get_loc(d)
        prev_idx = max(0, idx - 1)
        prev_date = df.index[prev_idx]
        
        vix_value = float(df.loc[prev_date, 'VIX'])
        mult, label = get_multiplier(vix_value)
        amount = base_amount * mult
        
        price = float(df.loc[d, 'QQQ'])
        buy_amount = max(0, amount - tx_cost)
        buy_shares = buy_amount / price if price > 0 else 0
        shares += buy_shares
        cash_invested += amount
        
        records.append({
            'date': d,
            'price': price,
            'vix': vix_value,
            'multiplier': mult,
            'label': label,
            'investment': amount,
            'shares': buy_shares,
            'total_shares': shares,
            'cash_invested': cash_invested,
            'portfolio_value': shares * price,
        })
    
    return pd.DataFrame(records)


def backtest_plain_dca(df, dates):
    """普通定投策略回测"""
    base_amount = BACKTEST_CONFIG['base_monthly_investment']
    tx_cost = BACKTEST_CONFIG['transaction_cost']
    
    shares = 0.0
    cash_invested = 0.0
    records = []
    
    for d in dates:
        price = float(df.loc[d, 'QQQ'])
        buy_amount = max(0, base_amount - tx_cost)
        buy_shares = buy_amount / price if price > 0 else 0
        shares += buy_shares
        cash_invested += base_amount
        
        records.append({
            'date': d,
            'price': price,
            'investment': base_amount,
            'shares': buy_shares,
            'total_shares': shares,
            'cash_invested': cash_invested,
            'portfolio_value': shares * price,
        })
    
    return pd.DataFrame(records)


def backtest_lump_sum(df, dates, total_cash):
    """一次性投入策略回测"""
    tx_cost = BACKTEST_CONFIG['transaction_cost']
    first_date = dates[0]
    price = float(df.loc[first_date, 'QQQ'])
    buy_amount = max(0, total_cash - tx_cost)
    shares = buy_amount / price if price > 0 else 0
    cash_invested = total_cash
    
    records = []
    for d in dates:
        price = float(df.loc[d, 'QQQ'])
        records.append({
            'date': d,
            'price': price,
            'investment': 0,
            'shares': 0,
            'total_shares': shares,
            'cash_invested': cash_invested,
            'portfolio_value': shares * price,
        })
    
    return pd.DataFrame(records)


def calculate_metrics(records_df, df_daily):
    """计算策略绩效指标"""
    rec = records_df.copy()
    
    # 最终值
    final_value = rec['portfolio_value'].iloc[-1]
    total_invested = rec['cash_invested'].iloc[-1]
    total_return = (final_value / total_invested - 1) * 100
    
    # 年化收益率 (CAGR)
    years = (rec['date'].iloc[-1] - rec['date'].iloc[0]).days / 365.25
    cagr = ((final_value / total_invested) ** (1 / years) - 1) * 100 if years > 0 else 0
    
    # 构建每日净值序列（用于计算最大回撤和夏普）
    shares = rec['total_shares'].iloc[-1]
    daily_values = df_daily['QQQ'] * shares
    daily_values = daily_values[daily_values.index >= rec['date'].iloc[0]]
    
    # 最大回撤
    running_max = daily_values.cummax()
    drawdown = (daily_values - running_max) / running_max
    max_drawdown = drawdown.min() * 100
    
    # 夏普比率（基于月度收益率）
    monthly_values = daily_values.resample('ME').last().dropna()
    monthly_returns = monthly_values.pct_change().dropna()
    excess_returns = monthly_returns - BACKTEST_CONFIG['risk_free_rate'] / 12
    sharpe = (excess_returns.mean() / excess_returns.std() * np.sqrt(12)) if excess_returns.std() > 0 else 0
    
    # 平均成本
    avg_cost = total_invested / rec['total_shares'].iloc[-1] if rec['total_shares'].iloc[-1] > 0 else 0
    
    return {
        'total_invested': total_invested,
        'final_value': final_value,
        'total_return_pct': total_return,
        'cagr_pct': cagr,
        'max_drawdown_pct': max_drawdown,
        'sharpe_ratio': sharpe,
        'avg_cost': avg_cost,
        'years': years,
    }


def generate_charts(df_vix, df_plain, df_lump, df_daily):
    """生成回测图表"""
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
    plt.rcParams['axes.unicode_minus'] = False
    
    # 1. 组合净值对比图
    fig, ax = plt.subplots(figsize=(12, 6))
    
    shares_vix = df_vix['total_shares'].iloc[-1]
    shares_plain = df_plain['total_shares'].iloc[-1]
    shares_lump = df_lump['total_shares'].iloc[-1]
    
    start_date = df_vix['date'].iloc[0]
    daily_slice = df_daily[df_daily.index >= start_date].copy()
    
    nav_vix = daily_slice['QQQ'] * shares_vix
    nav_plain = daily_slice['QQQ'] * shares_plain
    nav_lump = daily_slice['QQQ'] * shares_lump
    
    ax.plot(nav_vix.index, nav_vix.values, label='VIX增强定投', linewidth=2, color='#e74c3c')
    ax.plot(nav_plain.index, nav_plain.values, label='普通定投', linewidth=2, color='#3498db')
    ax.plot(nav_lump.index, nav_lump.values, label='一次性投入', linewidth=2, color='#2ecc71', linestyle='--')
    
    ax.set_title('VIX-纳斯达克100定投策略：组合净值对比', fontsize=14)
    ax.set_xlabel('日期')
    ax.set_ylabel('组合净值 (USD)')
    ax.legend(loc='upper left')
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(CHARTS_DIR / 'nav_comparison.png', dpi=150)
    plt.close()
    
    # 2. 回撤对比图
    fig, ax = plt.subplots(figsize=(12, 5))
    
    def calc_drawdown(nav):
        rm = nav.cummax()
        return (nav - rm) / rm * 100
    
    dd_vix = calc_drawdown(nav_vix)
    dd_plain = calc_drawdown(nav_plain)
    dd_lump = calc_drawdown(nav_lump)
    
    ax.fill_between(dd_vix.index, dd_vix.values, alpha=0.3, color='#e74c3c')
    ax.fill_between(dd_plain.index, dd_plain.values, alpha=0.3, color='#3498db')
    ax.fill_between(dd_lump.index, dd_lump.values, alpha=0.2, color='#2ecc71')
    
    ax.plot(dd_vix.index, dd_vix.values, label='VIX增强定投', color='#e74c3c', linewidth=1.5)
    ax.plot(dd_plain.index, dd_plain.values, label='普通定投', color='#3498db', linewidth=1.5)
    ax.plot(dd_lump.index, dd_lump.values, label='一次性投入', color='#2ecc71', linewidth=1.5, linestyle='--')
    
    ax.set_title('最大回撤对比', fontsize=14)
    ax.set_xlabel('日期')
    ax.set_ylabel('回撤 (%)')
    ax.legend(loc='lower left')
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(CHARTS_DIR / 'drawdown_comparison.png', dpi=150)
    plt.close()
    
    # 3. VIX策略月度投入金额图
    fig, ax = plt.subplots(figsize=(14, 5))
    
    colors = {'正常': '#3498db', '轻度恐慌': '#f1c40f', '中度恐慌': '#e67e22',
              '高度恐慌': '#e74c3c', '极度恐慌': '#8e44ad'}
    bar_colors = [colors.get(l, '#95a5a6') for l in df_vix['label']]
    
    ax.bar(df_vix['date'], df_vix['investment'], color=bar_colors, width=20)
    ax.axhline(y=BACKTEST_CONFIG['base_monthly_investment'], color='gray', linestyle='--', alpha=0.7, label='基础定投额')
    ax.set_title('VIX增强策略：每月实际投入金额', fontsize=14)
    ax.set_xlabel('日期')
    ax.set_ylabel('投入金额 (USD)')
    
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=colors[k], label=k) for k in colors if k in df_vix['label'].values]
    ax.legend(handles=legend_elements, loc='upper left')
    ax.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    plt.savefig(CHARTS_DIR / 'monthly_investment.png', dpi=150)
    plt.close()
    
    print(f"图表已保存到 {CHARTS_DIR}")


def generate_report(metrics_vix, metrics_plain, metrics_lump, df_vix):
    """生成Markdown回测报告"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    total_months = len(df_vix)
    enhanced_months = len(df_vix[df_vix['multiplier'] > 1.0])
    extreme_months = len(df_vix[df_vix['multiplier'] >= 5.0])
    
    lines = [
        "# VIX-纳斯达克100定投策略回测报告",
        "",
        f"> **生成时间**: {now}",
        f"> **数据范围**: {BACKTEST_CONFIG['start_date']} 至今",
        f"> **标的**: QQQ (Invesco QQQ Trust - 纳斯达克100 ETF)",
        f"> **恐慌指数**: ^VIX (CBOE Volatility Index)",
        "",
        "---",
        "",
        "## 策略说明",
        "",
        "本策略的核心思想是：**在正常情况下执行标准定投，当市场恐慌情绪（以VIX衡量）升温时，加大定投金额，从而在低位积累更多筹码。**",
        "",
        "### 定投规则",
        "",
        f"- **基础定投金额**: {BACKTEST_CONFIG['base_monthly_investment']} USD/月",
        f"- **定投日**: 每月第 {BACKTEST_CONFIG['investment_day']} 个交易日",
        "- **VIX加仓规则**（以前一交易日VIX收盘价为准）：",
        "",
        "| VIX区间 | 加仓倍数 | 市场情绪 |",
        "|---------|----------|----------|",
    ]
    
    for low, high, mult, label in BACKTEST_CONFIG['vix_rules']:
        high_str = f"< {high}" if high < 999 else "≥ 30"
        lines.append(f"| {low} ≤ VIX {high_str} | {mult:.1f}x | {label} |")
    
    lines.extend([
        "",
        "### 对比基准",
        "",
        "1. **普通定投**: 每月固定投入基础金额，不加仓。",
        "2. **一次性投入**: 在回测起始日一次性投入与VIX策略相同的总现金。",
        "",
        "---",
        "",
        "## 回测结果对比",
        "",
        "### 核心指标",
        "",
        "| 指标 | VIX增强定投 | 普通定投 | 一次性投入 |",
        "|------|-------------|----------|------------|",
        f"| 总投入金额 | ${metrics_vix['total_invested']:,.2f} | ${metrics_plain['total_invested']:,.2f} | ${metrics_lump['total_invested']:,.2f} |",
        f"| 最终组合价值 | ${metrics_vix['final_value']:,.2f} | ${metrics_plain['final_value']:,.2f} | ${metrics_lump['final_value']:,.2f} |",
        f"| 总收益率 | {metrics_vix['total_return_pct']:+.2f}% | {metrics_plain['total_return_pct']:+.2f}% | {metrics_lump['total_return_pct']:+.2f}% |",
        f"| 年化收益率 (CAGR) | {metrics_vix['cagr_pct']:+.2f}% | {metrics_plain['cagr_pct']:+.2f}% | {metrics_lump['cagr_pct']:+.2f}% |",
        f"| 最大回撤 | {metrics_vix['max_drawdown_pct']:.2f}% | {metrics_plain['max_drawdown_pct']:.2f}% | {metrics_lump['max_drawdown_pct']:.2f}% |",
        f"| 夏普比率 | {metrics_vix['sharpe_ratio']:.2f} | {metrics_plain['sharpe_ratio']:.2f} | {metrics_lump['sharpe_ratio']:.2f} |",
        f"| 平均持仓成本 | ${metrics_vix['avg_cost']:.2f} | ${metrics_plain['avg_cost']:.2f} | ${metrics_lump['avg_cost']:.2f} |",
        "",
        "### 定投执行统计",
        "",
        f"- **总定投月数**: {total_months} 个月",
        f"- **触发加仓月数** (倍数>1): {enhanced_months} 个月 ({enhanced_months/total_months*100:.1f}%)",
        f"- **极度恐慌月数** (5倍): {extreme_months} 个月 ({extreme_months/total_months*100:.1f}%)",
        f"- **额外投入资金**: ${metrics_vix['total_invested'] - metrics_plain['total_invested']:,.2f} (相比普通定投)",
        f"- **额外收益**: ${metrics_vix['final_value'] - metrics_plain['final_value']:,.2f} (相比普通定投)",
        "",
        "---",
        "",
        "## 图表",
        "",
        "### 组合净值对比",
        f"![组合净值对比](./charts/nav_comparison.png)",
        "",
        "### 最大回撤对比",
        f"![最大回撤对比](./charts/drawdown_comparison.png)",
        "",
        "### VIX策略每月投入金额",
        f"![每月投入金额](./charts/monthly_investment.png)",
        "",
        "---",
        "",
        "## 关键结论",
        "",
    ])
    
    best_strategy = max([
        ('VIX增强定投', metrics_vix['total_return_pct']),
        ('普通定投', metrics_plain['total_return_pct']),
        ('一次性投入', metrics_lump['total_return_pct']),
    ], key=lambda x: x[1])
    
    lines.append(f"1. **收益表现**: 在 {metrics_vix['years']:.1f} 年回测期内，**{best_strategy[0]}** 的总收益率最高，达到 {best_strategy[1]:+.2f}%。")
    
    if metrics_vix['total_return_pct'] > metrics_plain['total_return_pct']:
        lines.append(f"2. **VIX策略有效性**: VIX增强定投相比普通定投多投入 ${metrics_vix['total_invested'] - metrics_plain['total_invested']:,.0f}，最终多赚 ${metrics_vix['final_value'] - metrics_plain['final_value']:,.0f}，额外投入的边际效益显著。")
    else:
        lines.append(f"2. **VIX策略观察**: 本次回测中VIX增强定投并未跑赢普通定投，可能是因为恐慌加仓时点后续仍有下跌，或牛市中加仓机会较少导致资金利用率不足。")
    
    if metrics_vix['max_drawdown_pct'] > metrics_plain['max_drawdown_pct']:
        lines.append(f"3. **回撤控制**: VIX策略的最大回撤 ({metrics_vix['max_drawdown_pct']:.2f}%) 大于普通定投 ({metrics_plain['max_drawdown_pct']:.2f}%)，说明恐慌时加大投入会在短期内承受更大账面浮亏，但长期可能摊薄成本。")
    else:
        lines.append(f"3. **回撤控制**: VIX策略的最大回撤 ({metrics_vix['max_drawdown_pct']:.2f}%) 小于或接近普通定投，说明低位加仓有效降低了平均成本。")
    
    lines.extend([
        f"4. **夏普比率**: VIX策略夏普比率为 {metrics_vix['sharpe_ratio']:.2f}，风险调整后收益{'优于' if metrics_vix['sharpe_ratio'] > metrics_plain['sharpe_ratio'] else '弱于'}普通定投 ({metrics_plain['sharpe_ratio']:.2f})。",
        "",
        "### 风险提示",
        "",
        "- VIX策略需要**更强的现金流支撑**，恐慌时期月投入可能达到基础金额的 5 倍，需确保资金链不断裂。",
        "- 历史回测不代表未来表现，VIX与QQQ的相关性可能随市场环境变化。",
        "- 本回测未考虑交易成本、税费、汇率（若用非美元资金）及滑点。",
        "",
        "---",
        "",
        "*报告由 `scripts/vix_ndx_backtest.py` 自动生成*",
    ])
    
    REPORT_FILE.write_text('\n'.join(lines), encoding='utf-8')
    print(f"报告已生成: {REPORT_FILE}")


def main():
    print("=" * 70)
    print("VIX-纳斯达克100定投回测")
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    df = download_data()
    dates = get_investment_dates(df)
    print(f"共 {len(dates)} 个定投日")
    
    df_vix = backtest_vix_dca(df, dates)
    df_plain = backtest_plain_dca(df, dates)
    total_cash = df_vix['cash_invested'].iloc[-1]
    df_lump = backtest_lump_sum(df, dates, total_cash)
    
    metrics_vix = calculate_metrics(df_vix, df)
    metrics_plain = calculate_metrics(df_plain, df)
    metrics_lump = calculate_metrics(df_lump, df)
    
    print("\n" + "=" * 70)
    print("回测结果对比")
    print("=" * 70)
    print(f"{'指标':<20} {'VIX增强定投':>15} {'普通定投':>15} {'一次性投入':>15}")
    print("-" * 70)
    print(f"{'总投入金额':<20} ${metrics_vix['total_invested']:>13,.0f} ${metrics_plain['total_invested']:>13,.0f} ${metrics_lump['total_invested']:>13,.0f}")
    print(f"{'最终组合价值':<20} ${metrics_vix['final_value']:>13,.0f} ${metrics_plain['final_value']:>13,.0f} ${metrics_lump['final_value']:>13,.0f}")
    print(f"{'总收益率':<20} {metrics_vix['total_return_pct']:>14.2f}% {metrics_plain['total_return_pct']:>14.2f}% {metrics_lump['total_return_pct']:>14.2f}%")
    print(f"{'年化收益率(CAGR)':<20} {metrics_vix['cagr_pct']:>14.2f}% {metrics_plain['cagr_pct']:>14.2f}% {metrics_lump['cagr_pct']:>14.2f}%")
    print(f"{'最大回撤':<20} {metrics_vix['max_drawdown_pct']:>14.2f}% {metrics_plain['max_drawdown_pct']:>14.2f}% {metrics_lump['max_drawdown_pct']:>14.2f}%")
    print(f"{'夏普比率':<20} {metrics_vix['sharpe_ratio']:>15.2f} {metrics_plain['sharpe_ratio']:>15.2f} {metrics_lump['sharpe_ratio']:>15.2f}")
    print(f"{'平均持仓成本':<20} ${metrics_vix['avg_cost']:>13.2f} ${metrics_plain['avg_cost']:>13.2f} ${metrics_lump['avg_cost']:>13.2f}")
    print("=" * 70)
    
    generate_charts(df_vix, df_plain, df_lump, df)
    generate_report(metrics_vix, metrics_plain, metrics_lump, df_vix)
    
    print("\n回测完成！")


if __name__ == '__main__':
    main()
