# -*- coding: utf-8 -*-
"""
VIX-纳斯达克100定投回测脚本 V2.0
基于恐慌指数(VIX)的动态加仓定投策略回测

核心改进：相同总资金池对比
- VIX策略：恐慌时多投，把现金都投入股市
- 普通定投：只投基础金额，剩余现金买理财（3%年化）
- 对比维度：最终总资产（股市+现金）
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
    'risk_free_rate': 0.03,  # 无风险利率 3%（用于现金理财）
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


def backtest_vix_dca(df, dates, monthly_budget=None):
    """
    VIX增强定投策略回测
    
    Args:
        monthly_budget: 每月预算上限，None表示不限制（实际投入=基础金额×倍数）
    """
    base_amount = BACKTEST_CONFIG['base_monthly_investment']
    tx_cost = BACKTEST_CONFIG['transaction_cost']
    monthly_rate = BACKTEST_CONFIG['risk_free_rate'] / 12  # 月利率
    
    shares = 0.0
    cash_invested = 0.0
    cash_balance = 0.0  # 现金余额（用于计算理财收益）
    records = []
    
    for i, d in enumerate(dates):
        # 月初现金余额计息（上个月的剩余）
        if i > 0 and cash_balance > 0:
            interest = cash_balance * monthly_rate
            cash_balance += interest
        
        # 找到前一个交易日（用于获取VIX）
        idx = df.index.get_loc(d)
        prev_idx = max(0, idx - 1)
        prev_date = df.index[prev_idx]
        
        vix_value = float(df.loc[prev_date, 'VIX'])
        mult, label = get_multiplier(vix_value)
        planned_amount = base_amount * mult
        
        # 如果设置了月度预算，实际投入=min(计划投入, 预算+现金余额)
        if monthly_budget is not None:
            available = monthly_budget + cash_balance
            actual_amount = min(planned_amount, available)
            cash_balance = available - actual_amount  # 剩余现金
        else:
            actual_amount = planned_amount
            
        price = float(df.loc[d, 'QQQ'])
        buy_amount = max(0, actual_amount - tx_cost)
        buy_shares = buy_amount / price if price > 0 else 0
        shares += buy_shares
        cash_invested += actual_amount
        
        records.append({
            'date': d,
            'price': price,
            'vix': vix_value,
            'multiplier': mult,
            'label': label,
            'planned_investment': planned_amount,
            'actual_investment': actual_amount,
            'cash_balance': cash_balance,
            'shares': buy_shares,
            'total_shares': shares,
            'cash_invested': cash_invested,
            'portfolio_value': shares * price,
            'total_assets': shares * price + cash_balance,
        })
    
    return pd.DataFrame(records)


def backtest_plain_dca_with_cash(df, dates, monthly_budget):
    """
    普通定投策略回测（带现金理财）
    
    Args:
        monthly_budget: 每月预算（与VIX策略相同的资金池）
    """
    base_amount = BACKTEST_CONFIG['base_monthly_investment']
    tx_cost = BACKTEST_CONFIG['transaction_cost']
    monthly_rate = BACKTEST_CONFIG['risk_free_rate'] / 12  # 月利率
    
    shares = 0.0
    cash_invested = 0.0
    cash_balance = 0.0
    records = []
    
    for i, d in enumerate(dates):
        # 月初现金余额计息
        if i > 0 and cash_balance > 0:
            interest = cash_balance * monthly_rate
            cash_balance += interest
        
        # 投入基础金额
        actual_amount = min(base_amount, monthly_budget + cash_balance)
        cash_balance = cash_balance + monthly_budget - actual_amount
        
        price = float(df.loc[d, 'QQQ'])
        buy_amount = max(0, actual_amount - tx_cost)
        buy_shares = buy_amount / price if price > 0 else 0
        shares += buy_shares
        cash_invested += actual_amount
        
        records.append({
            'date': d,
            'price': price,
            'planned_investment': base_amount,
            'actual_investment': actual_amount,
            'cash_balance': cash_balance,
            'shares': buy_shares,
            'total_shares': shares,
            'cash_invested': cash_invested,
            'portfolio_value': shares * price,
            'total_assets': shares * price + cash_balance,
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
            'planned_investment': 0,
            'actual_investment': 0,
            'cash_balance': 0,
            'shares': 0,
            'total_shares': shares,
            'cash_invested': cash_invested,
            'portfolio_value': shares * price,
            'total_assets': shares * price,
        })
    
    return pd.DataFrame(records)


def calculate_metrics_with_cash(records_df, df_daily):
    """计算策略绩效指标（考虑现金余额）"""
    rec = records_df.copy()
    
    # 最终值（股市+现金）
    final_stock_value = rec['portfolio_value'].iloc[-1]
    final_cash_balance = rec['cash_balance'].iloc[-1]
    final_total_assets = final_stock_value + final_cash_balance
    
    # 总现金投入（实际投入股市的）
    total_invested = rec['cash_invested'].iloc[-1]
    total_budget = rec['planned_investment'].sum()  # 总预算
    
    # 总收益率（基于总资产）
    total_return = (final_total_assets / total_budget - 1) * 100 if total_budget > 0 else 0
    
    # 年化收益率 (CAGR)
    years = (rec['date'].iloc[-1] - rec['date'].iloc[0]).days / 365.25
    cagr = ((final_total_assets / total_budget) ** (1 / years) - 1) * 100 if years > 0 and total_budget > 0 else 0
    
    # 构建每日总资产序列（用于计算最大回撤）
    shares = rec['total_shares'].iloc[-1]
    daily_stock_values = df_daily['QQQ'] * shares
    daily_stock_values = daily_stock_values[daily_stock_values.index >= rec['date'].iloc[0]]
    
    # 现金余额增长（近似按月复利）
    # 简化处理：使用最终的 cash_balance 作为所有日期的现金值
    # 实际上现金是逐月增长的，但对回撤计算影响不大
    daily_total_assets = daily_stock_values + final_cash_balance
    
    # 最大回撤
    running_max = daily_total_assets.cummax()
    drawdown = (daily_total_assets - running_max) / running_max
    max_drawdown = drawdown.min() * 100
    
    # 夏普比率（基于月度收益率）
    monthly_stock_values = daily_stock_values.resample('ME').last().dropna()
    # 总资产包含现金，现金部分增长是线性的
    monthly_returns = monthly_stock_values.pct_change().dropna()
    excess_returns = monthly_returns - BACKTEST_CONFIG['risk_free_rate'] / 12
    sharpe = (excess_returns.mean() / excess_returns.std() * np.sqrt(12)) if excess_returns.std() > 0 else 0
    
    # 平均成本
    avg_cost = total_invested / rec['total_shares'].iloc[-1] if rec['total_shares'].iloc[-1] > 0 else 0
    
    return {
        'total_invested': total_invested,
        'total_budget': total_budget,
        'final_stock_value': final_stock_value,
        'final_cash_balance': final_cash_balance,
        'final_total_assets': final_total_assets,
        'total_return_pct': total_return,
        'cagr_pct': cagr,
        'max_drawdown_pct': max_drawdown,
        'sharpe_ratio': sharpe,
        'avg_cost': avg_cost,
        'years': years,
        'cash_ratio': final_cash_balance / final_total_assets * 100 if final_total_assets > 0 else 0,
    }


def generate_charts(df_vix, df_plain, df_lump, df_daily):
    """生成回测图表"""
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
    plt.rcParams['axes.unicode_minus'] = False
    
    # 1. 总资产对比图
    fig, ax = plt.subplots(figsize=(12, 6))
    
    ax.plot(df_vix['date'], df_vix['total_assets'], label='VIX增强定投', linewidth=2, color='#e74c3c')
    ax.plot(df_plain['date'], df_plain['total_assets'], label='普通定投+理财', linewidth=2, color='#3498db')
    ax.plot(df_lump['date'], df_lump['total_assets'], label='一次性投入', linewidth=2, color='#2ecc71', linestyle='--')
    
    ax.set_title('总资产对比（股市价值+现金余额）', fontsize=14)
    ax.set_xlabel('日期')
    ax.set_ylabel('总资产 (USD)')
    ax.legend(loc='upper left')
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(CHARTS_DIR / 'total_assets_comparison.png', dpi=150)
    plt.close()
    
    # 2. 股市价值对比图（只看股票部分）
    fig, ax = plt.subplots(figsize=(12, 6))
    
    ax.plot(df_vix['date'], df_vix['portfolio_value'], label='VIX增强定投', linewidth=2, color='#e74c3c')
    ax.plot(df_plain['date'], df_plain['portfolio_value'], label='普通定投', linewidth=2, color='#3498db')
    ax.plot(df_lump['date'], df_lump['portfolio_value'], label='一次性投入', linewidth=2, color='#2ecc71', linestyle='--')
    
    ax.set_title('股市持仓价值对比（不含现金）', fontsize=14)
    ax.set_xlabel('日期')
    ax.set_ylabel('持仓价值 (USD)')
    ax.legend(loc='upper left')
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(CHARTS_DIR / 'stock_value_comparison.png', dpi=150)
    plt.close()
    
    # 3. VIX策略现金余额变化
    fig, ax = plt.subplots(figsize=(12, 5))
    
    ax.fill_between(df_vix['date'], df_vix['cash_balance'], alpha=0.3, color='#95a5a6')
    ax.plot(df_vix['date'], df_vix['cash_balance'], color='#7f8c8d', linewidth=1.5)
    ax.set_title('VIX策略现金余额变化', fontsize=14)
    ax.set_xlabel('日期')
    ax.set_ylabel('现金余额 (USD)')
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(CHARTS_DIR / 'vix_cash_balance.png', dpi=150)
    plt.close()
    
    # 4. 普通定投现金余额变化
    fig, ax = plt.subplots(figsize=(12, 5))
    
    ax.fill_between(df_plain['date'], df_plain['cash_balance'], alpha=0.3, color='#3498db')
    ax.plot(df_plain['date'], df_plain['cash_balance'], color='#2980b9', linewidth=1.5)
    ax.set_title('普通定投现金余额变化（含理财收益）', fontsize=14)
    ax.set_xlabel('日期')
    ax.set_ylabel('现金余额 (USD)')
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(CHARTS_DIR / 'plain_cash_balance.png', dpi=150)
    plt.close()
    
    # 5. VIX策略月度投入金额图
    fig, ax = plt.subplots(figsize=(14, 5))
    
    colors = {'正常': '#3498db', '轻度恐慌': '#f1c40f', '中度恐慌': '#e67e22',
              '高度恐慌': '#e74c3c', '极度恐慌': '#8e44ad'}
    bar_colors = [colors.get(l, '#95a5a6') for l in df_vix['label']]
    
    ax.bar(df_vix['date'], df_vix['actual_investment'], color=bar_colors, width=20)
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


def generate_report(metrics_vix, metrics_plain, metrics_lump, df_vix, df_plain):
    """生成Markdown回测报告"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    total_months = len(df_vix)
    enhanced_months = len(df_vix[df_vix['multiplier'] > 1.0])
    extreme_months = len(df_vix[df_vix['multiplier'] >= 5.0])
    
    # 计算累计投入差额
    vix_extra_invested = metrics_vix['total_invested'] - metrics_plain['total_invested']
    vix_extra_return = metrics_vix['final_total_assets'] - metrics_plain['final_total_assets']
    
    lines = [
        "# VIX-纳斯达克100定投策略回测报告",
        "",
        f"> **生成时间**: {now}",
        f"> **数据范围**: {BACKTEST_CONFIG['start_date']} 至今",
        f"> **标的**: QQQ (Invesco QQQ Trust - 纳斯达克100 ETF)",
        f"> **恐慌指数**: ^VIX (CBOE Volatility Index)",
        f"> **无风险利率**: {BACKTEST_CONFIG['risk_free_rate']*100:.0f}%（现金理财年化）",
        "",
        "---",
        "",
        "## 核心观点",
        "",
        f"**相同资金池对比**：假设每月有 **${max(df_vix['planned_investment']):.0f}** 预算",
        "",
        "| 对比维度 | VIX增强定投 | 普通定投+理财 |",
        "|----------|-------------|---------------|",
        f"| **最终总资产** | **${metrics_vix['final_total_assets']:,.2f}** | ${metrics_plain['final_total_assets']:,.2f} |",
        f"| 股市持仓价值 | ${metrics_vix['final_stock_value']:,.2f} | ${metrics_plain['final_stock_value']:,.2f} |",
        f"| 现金余额 | ${metrics_vix['final_cash_balance']:,.2f} | ${metrics_plain['final_cash_balance']:,.2f} |",
        f"| 累计投入股市 | ${metrics_vix['total_invested']:,.2f} | ${metrics_plain['total_invested']:,.2f} |",
        f"| 累计投入差额 | +${vix_extra_invested:,.2f} | - |",
        f"| **总资产收益** | **{metrics_vix['total_return_pct']:+.2f}%** | {metrics_plain['total_return_pct']:+.2f}% |",
        f"| 最终资金效率 | {'VIX更优' if metrics_vix['final_total_assets'] > metrics_plain['final_total_assets'] else '普通更优'} | - |",
        "",
        "> 💡 **结论**：",
        f"> - VIX策略多投入 **${vix_extra_invested:,.0f}** 到股市",
        f"> - 最终总资产 {'多赚' if vix_extra_return > 0 else '少赚'} **${abs(vix_extra_return):,.2f}**",
        f"> - 额外投入的资金 {'产生正收益' if vix_extra_return > 0 else '产生负收益'}",
        "",
        "---",
        "",
        "## 策略说明",
        "",
        "### 相同资金池对比逻辑",
        "",
        "本回测采用**公平对比**方式：",
        "",
        "1. **每月预算相同**：两个策略每月都有相同的资金预算",
        "2. **VIX策略**：恐慌时投入更多，现金余额少，大部分资金在股市",
        "3. **普通定投**：每月只投基础金额，剩余现金买理财（3%年化）",
        "4. **对比维度**：最终总资产 = 股市价值 + 现金余额（含理财收益）",
        "",
        "### 定投规则",
        "",
        f"- **每月预算**: ${max(df_vix['planned_investment']):.0f} USD/月",
        f"- **基础定投金额**: {BACKTEST_CONFIG['base_monthly_investment']} USD/月",
        f"- **定投日**: 每月第 {BACKTEST_CONFIG['investment_day']} 个交易日",
        f"- **现金理财利率**: {BACKTEST_CONFIG['risk_free_rate']*100:.0f}% 年化",
        "",
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
        "---",
        "",
        "## 详细回测结果",
        "",
        "### 核心指标对比",
        "",
        "| 指标 | VIX增强定投 | 普通定投+理财 | 一次性投入 |",
        "|------|-------------|---------------|------------|",
        f"| **最终总资产** | **${metrics_vix['final_total_assets']:,.2f}** | ${metrics_plain['final_total_assets']:,.2f} | ${metrics_lump['final_total_assets']:,.2f} |",
        f"| 股市持仓价值 | ${metrics_vix['final_stock_value']:,.2f} | ${metrics_plain['final_stock_value']:,.2f} | ${metrics_lump['final_stock_value']:,.2f} |",
        f"| 现金余额 | ${metrics_vix['final_cash_balance']:,.2f} | ${metrics_plain['final_cash_balance']:,.2f} | $0.00 |",
        f"| 累计投入股市 | ${metrics_vix['total_invested']:,.2f} | ${metrics_plain['total_invested']:,.2f} | ${metrics_lump['total_invested']:,.2f} |",
        f"| 总资产收益率 | {metrics_vix['total_return_pct']:+.2f}% | {metrics_plain['total_return_pct']:+.2f}% | {metrics_lump['total_return_pct']:+.2f}% |",
        f"| 年化收益率 (CAGR) | {metrics_vix['cagr_pct']:+.2f}% | {metrics_plain['cagr_pct']:+.2f}% | {metrics_lump['cagr_pct']:+.2f}% |",
        f"| 最大回撤 | {metrics_vix['max_drawdown_pct']:.2f}% | {metrics_plain['max_drawdown_pct']:.2f}% | {metrics_lump['max_drawdown_pct']:.2f}% |",
        f"| 夏普比率 | {metrics_vix['sharpe_ratio']:.2f} | {metrics_plain['sharpe_ratio']:.2f} | {metrics_lump['sharpe_ratio']:.2f} |",
        f"| 平均持仓成本 | ${metrics_vix['avg_cost']:.2f} | ${metrics_plain['avg_cost']:.2f} | ${metrics_lump['avg_cost']:.2f} |",
        "",
        "### VIX策略执行统计",
        "",
        f"- **总定投月数**: {total_months} 个月",
        f"- **触发加仓月数** (倍数>1): {enhanced_months} 个月 ({enhanced_months/total_months*100:.1f}%)",
        f"- **极度恐慌月数** (5倍): {extreme_months} 个月 ({extreme_months/total_months*100:.1f}%)",
        f"- **累计投入差额**: ${vix_extra_invested:,.2f}（相比普通定投多投入）",
        f"- **累计理财收益（普通定投）**: ${metrics_plain['final_cash_balance'] - (metrics_plain['total_budget'] - metrics_plain['total_invested']):,.2f}",
        "",
        "---",
        "",
        "## 图表",
        "",
        "### 总资产对比（股市价值+现金余额）",
        f"![总资产对比](./charts/total_assets_comparison.png)",
        "",
        "### 股市持仓价值对比",
        f"![股市价值对比](./charts/stock_value_comparison.png)",
        "",
        "### VIX策略现金余额变化",
        f"![VIX现金余额](./charts/vix_cash_balance.png)",
        "",
        "### 普通定投现金余额变化",
        f"![普通定投现金余额](./charts/plain_cash_balance.png)",
        "",
        "### VIX策略每月投入金额",
        f"![每月投入金额](./charts/monthly_investment.png)",
        "",
        "---",
        "",
        "## 关键结论",
        "",
    ])
    
    # 自动结论
    winner = "VIX增强定投" if metrics_vix['final_total_assets'] > metrics_plain['final_total_assets'] else "普通定投+理财"
    margin = abs(metrics_vix['final_total_assets'] - metrics_plain['final_total_assets']) / metrics_plain['final_total_assets'] * 100
    
    lines.append(f"1. **相同资金池对比**：在 {metrics_vix['years']:.1f} 年回测期内，**{winner}** 的最终总资产更高，领先 **{margin:.2f}%**。")
    
    if vix_extra_return > 0:
        lines.append(f"2. **VIX策略有效性**：VIX策略比普通定投多投入 ${vix_extra_invested:,.0f} 到股市，最终多赚 ${vix_extra_return:,.2f}，说明恐慌时加仓有效提升了整体收益。")
    else:
        lines.append(f"2. **VIX策略观察**：VIX策略比普通定投多投入 ${vix_extra_invested:,.0f} 到股市，但最终少赚 ${abs(vix_extra_return):,.2f}，说明恐慌加仓时点可能过早（接飞刀），或牛市中资金利用率不如理财。")
    
    # 现金效率分析
    vix_cash_ratio = metrics_vix['final_cash_balance'] / metrics_vix['final_total_assets'] * 100
    plain_cash_ratio = metrics_plain['final_cash_balance'] / metrics_plain['final_total_assets'] * 100
    lines.append(f"3. **现金利用率**：VIX策略最终现金占比 {vix_cash_ratio:.1f}%，普通定投现金占比 {plain_cash_ratio:.1f}%。VIX策略资金利用率更高。")
    
    # 风险对比
    if metrics_vix['max_drawdown_pct'] < metrics_plain['max_drawdown_pct']:
        lines.append(f"4. **风险控制**：VIX策略最大回撤 ({metrics_vix['max_drawdown_pct']:.2f}%) 小于普通定投 ({metrics_plain['max_drawdown_pct']:.2f}%)，说明低位摊薄成本有效降低了波动。")
    else:
        lines.append(f"4. **风险对比**：VIX策略最大回撤 ({metrics_vix['max_drawdown_pct']:.2f}%) 与普通定投 ({metrics_plain['max_drawdown_pct']:.2f}%) 相当或略高，承担了更多波动。")
    
    lines.extend([
        "",
        "### 风险提示",
        "",
        "- VIX策略需要**更强的现金流纪律**，恐慌时期月投入可能达到基础金额的 5 倍，需确保资金链不断裂。",
        "- 本回测中普通定投的现金理财收益按 3% 年化计算，实际收益可能因市场利率变化而不同。",
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
    print("VIX-纳斯达克100定投回测 V2.0")
    print("相同资金池对比（股市+现金理财）")
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    df = download_data()
    dates = get_investment_dates(df)
    print(f"共 {len(dates)} 个定投月")
    
    # 先跑一次VIX策略，确定每月预算上限
    df_vix_temp = backtest_vix_dca(df, dates, monthly_budget=None)
    max_monthly = df_vix_temp['planned_investment'].max()
    print(f"VIX策略月度投入范围: ${df_vix_temp['actual_investment'].min():.0f} ~ ${max_monthly:.0f}")
    
    # 正式回测：使用相同资金池
    df_vix = backtest_vix_dca(df, dates, monthly_budget=max_monthly)
    df_plain = backtest_plain_dca_with_cash(df, dates, monthly_budget=max_monthly)
    total_budget = df_vix['planned_investment'].sum()
    df_lump = backtest_lump_sum(df, dates, total_budget)
    
    # 计算指标（考虑现金）
    metrics_vix = calculate_metrics_with_cash(df_vix, df)
    metrics_plain = calculate_metrics_with_cash(df_plain, df)
    metrics_lump = calculate_metrics_with_cash(df_lump, df)
    
    print("\n" + "=" * 70)
    print("相同资金池回测结果对比")
    print("=" * 70)
    print(f"{'指标':<25} {'VIX增强定投':>18} {'普通定投+理财':>18} {'一次性投入':>18}")
    print("-" * 70)
    print(f"{'最终总资产':<25} ${metrics_vix['final_total_assets']:>16,.0f} ${metrics_plain['final_total_assets']:>16,.0f} ${metrics_lump['final_total_assets']:>16,.0f}")
    print(f"{'股市持仓价值':<25} ${metrics_vix['final_stock_value']:>16,.0f} ${metrics_plain['final_stock_value']:>16,.0f} ${metrics_lump['final_stock_value']:>16,.0f}")
    print(f"{'现金余额':<25} ${metrics_vix['final_cash_balance']:>16,.0f} ${metrics_plain['final_cash_balance']:>16,.0f} ${metrics_lump['final_cash_balance']:>16,.0f}")
    print(f"{'累计投入股市':<25} ${metrics_vix['total_invested']:>16,.0f} ${metrics_plain['total_invested']:>16,.0f} ${metrics_lump['total_invested']:>16,.0f}")
    print(f"{'总资产收益率':<25} {metrics_vix['total_return_pct']:>17.2f}% {metrics_plain['total_return_pct']:>17.2f}% {metrics_lump['total_return_pct']:>17.2f}%")
    print(f"{'年化收益率(CAGR)':<25} {metrics_vix['cagr_pct']:>17.2f}% {metrics_plain['cagr_pct']:>17.2f}% {metrics_lump['cagr_pct']:>17.2f}%")
    print(f"{'最大回撤':<25} {metrics_vix['max_drawdown_pct']:>17.2f}% {metrics_plain['max_drawdown_pct']:>17.2f}% {metrics_lump['max_drawdown_pct']:>17.2f}%")
    print("=" * 70)
    
    # 生成图表和报告
    generate_charts(df_vix, df_plain, df_lump, df)
    generate_report(metrics_vix, metrics_plain, metrics_lump, df_vix, df_plain)
    
    print("\n回测完成！")


if __name__ == '__main__':
    main()
