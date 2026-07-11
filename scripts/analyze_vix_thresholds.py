# -*- coding: utf-8 -*-
"""
VIX阈值优化分析器
分析历史数据中不同VIX水平下的纳指表现，找出最优加仓阈值
"""

import warnings
warnings.filterwarnings('ignore')

import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "strategy-framework" / "VIX-纳斯达克100定投策略"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def download_data(start='2006-01-01'):
    """下载VIX和QQQ历史数据（从2006年开始覆盖2008年危机）"""
    print("正在下载历史数据...")
    end = datetime.now().strftime('%Y-%m-%d')
    
    qqq = yf.download('QQQ', start=start, end=end, progress=False, auto_adjust=True)
    vix = yf.download('^VIX', start=start, end=end, progress=False, auto_adjust=True)
    
    if isinstance(qqq.columns, pd.MultiIndex):
        qqq.columns = qqq.columns.get_level_values(0)
    if isinstance(vix.columns, pd.MultiIndex):
        vix.columns = vix.columns.get_level_values(0)
    
    df = pd.DataFrame({
        'QQQ': qqq['Close'].squeeze(),
        'VIX': vix['Close'].squeeze(),
    }).dropna()
    
    print(f"数据范围: {df.index[0].strftime('%Y-%m-%d')} 到 {df.index[-1].strftime('%Y-%m-%d')}")
    print(f"共 {len(df)} 个交易日")
    return df


def analyze_vix_distribution(df):
    """分析VIX分布特征"""
    print("\n" + "="*70)
    print("VIX分布统计分析")
    print("="*70)
    
    vix = df['VIX']
    print(f"\n基础统计:")
    print(f"  均值: {vix.mean():.2f}")
    print(f"  中位数: {vix.median():.2f}")
    print(f"  标准差: {vix.std():.2f}")
    print(f"  最小值: {vix.min():.2f}")
    print(f"  最大值: {vix.max():.2f}")
    
    # 分位数
    percentiles = [10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 99]
    print(f"\n分位数:")
    for p in percentiles:
        print(f"  {p}%: {np.percentile(vix, p):.2f}")
    
    # 历史极端值日期
    print(f"\n历史最高VIX日期:")
    top_vix = df.nlargest(10, 'VIX')[['VIX', 'QQQ']]
    for idx, row in top_vix.iterrows():
        print(f"  {idx.strftime('%Y-%m-%d')}: VIX={row['VIX']:.2f}, QQQ=${row['QQQ']:.2f}")
    
    return vix


def analyze_forward_returns(df, vix_levels=[15, 20, 25, 30, 35, 40, 50, 60]):
    """
    分析当VIX达到特定水平时，未来N天的收益率
    这是核心分析：VIX高的时候买入，未来赚多少？
    """
    print("\n" + "="*70)
    print("VIX阈值 vs 未来收益分析（核心）")
    print("="*70)
    
    periods = [30, 60, 90, 180, 360]  # 1个月、3个月、6个月、12个月
    
    results = []
    for vix_level in vix_levels:
        # 找出VIX首次突破该水平的日期
        signal_dates = df[df['VIX'] >= vix_level].index
        
        if len(signal_dates) == 0:
            continue
            
        print(f"\n📊 VIX >= {vix_level}: 共出现 {len(signal_dates)} 次")
        
        for period in periods:
            returns = []
            for signal_date in signal_dates:
                try:
                    # 找到信号日的价格
                    entry_price = df.loc[signal_date, 'QQQ']
                    
                    # 找到N天后的日期
                    future_date = signal_date + timedelta(days=period)
                    # 找实际交易日
                    future_dates = df.index[df.index >= future_date]
                    if len(future_dates) == 0:
                        continue
                    future_date = future_dates[0]
                    
                    exit_price = df.loc[future_date, 'QQQ']
                    ret = (exit_price / entry_price - 1) * 100
                    returns.append(ret)
                except Exception:
                    continue
            
            if returns:
                avg_return = np.mean(returns)
                median_return = np.median(returns)
                win_rate = len([r for r in returns if r > 0]) / len(returns) * 100
                
                results.append({
                    'vix_level': vix_level,
                    'period_days': period,
                    'avg_return': avg_return,
                    'median_return': median_return,
                    'win_rate': win_rate,
                    'sample_size': len(returns)
                })
                
                print(f"  {period}天后: 平均收益={avg_return:+.2f}%, 胜率={win_rate:.1f}%, 样本={len(returns)}")
    
    return pd.DataFrame(results)


def analyze_dca_at_vix_levels(df, vix_levels=[15, 20, 25, 30, 35, 40]):
    """
    模拟：只在VIX低于/高于某阈值时才定投，对比效果
    """
    print("\n" + "="*70)
    print("不同VIX阈值定投策略对比")
    print("="*70)
    
    # 获取每月第一个交易日
    df['year_month'] = df.index.to_period('M')
    monthly_dates = df.groupby('year_month').first().index
    
    results = []
    base_investment = 1000
    
    for threshold in vix_levels:
        shares = 0
        cash_invested = 0
        
        for date in monthly_dates:
            try:
                # 找到当月第一个交易日
                month_data = df[df['year_month'] == date]
                if len(month_data) == 0:
                    continue
                
                first_day = month_data.index[0]
                vix_value = month_data.iloc[0]['VIX']
                price = month_data.iloc[0]['QQQ']
                
                # 策略：VIX >= threshold 时才定投（恐慌时买入）
                if vix_value >= threshold:
                    shares += base_investment / price
                    cash_invested += base_investment
                    
            except Exception:
                continue
        
        # 计算最终价值
        final_price = df['QQQ'].iloc[-1]
        final_value = shares * final_price
        
        if cash_invested > 0:
            total_return = (final_value / cash_invested - 1) * 100
            results.append({
                'threshold': threshold,
                'final_value': final_value,
                'cash_invested': cash_invested,
                'total_return': total_return,
                'shares': shares,
                'months_invested': cash_invested / base_investment
            })
            
            print(f"VIX >= {threshold} 才定投:")
            print(f"  投入月数: {cash_invested/base_investment:.0f}")
            print(f"  累计投入: ${cash_invested:,.0f}")
            print(f"  最终价值: ${final_value:,.0f}")
            print(f"  总收益率: {total_return:+.2f}%")
            print()
    
    # 对比：每月都定投
    shares_always = 0
    for date in monthly_dates:
        try:
            month_data = df[df['year_month'] == date]
            if len(month_data) > 0:
                price = month_data.iloc[0]['QQQ']
                shares_always += base_investment / price
        except Exception:
            continue
    
    final_value_always = shares_always * final_price
    total_invested_always = len(monthly_dates) * base_investment
    return_always = (final_value_always / total_invested_always - 1) * 100
    
    print("对比 - 每月都定投（不择时）:")
    print(f"  投入月数: {len(monthly_dates)}")
    print(f"  累计投入: ${total_invested_always:,.0f}")
    print(f"  最终价值: ${final_value_always:,.0f}")
    print(f"  总收益率: {return_always:+.2f}%")
    
    return pd.DataFrame(results)


def analyze_vix_spike_recovery(df):
    """
    分析VIX飙升后的市场恢复情况（2020年3月、2008年等）
    """
    print("\n" + "="*70)
    print("历史VIX飙升事件分析")
    print("="*70)
    
    # 定义历史极端事件
    events = [
        ('2008-09-15', '2008金融危机（雷曼破产）'),
        ('2010-05-06', '2010闪电崩盘'),
        ('2011-08-05', '2011美债危机'),
        ('2015-08-24', '2015股灾'),
        ('2018-02-05', '2018VIX恐慌'),
        ('2020-03-16', '2020新冠熔断'),
        ('2022-01-24', '2022加息恐慌'),
    ]
    
    for date_str, desc in events:
        try:
            event_date = pd.to_datetime(date_str)
            # 找到最近的交易日
            nearby = df.index[df.index >= event_date]
            if len(nearby) == 0:
                continue
            actual_date = nearby[0]
            
            row = df.loc[actual_date]
            vix = row['VIX']
            price = row['QQQ']
            
            # 计算未来收益
            future_returns = {}
            for days in [30, 60, 90, 180, 360]:
                future_date = actual_date + timedelta(days=days)
                future_dates = df.index[df.index >= future_date]
                if len(future_dates) > 0:
                    future_price = df.loc[future_dates[0], 'QQQ']
                    ret = (future_price / price - 1) * 100
                    future_returns[f'{days}d'] = ret
            
            print(f"\n{desc}")
            print(f"  日期: {actual_date.strftime('%Y-%m-%d')}")
            print(f"  VIX: {vix:.2f}")
            print(f"  QQQ: ${price:.2f}")
            print(f"  未来收益: ", end='')
            for k, v in future_returns.items():
                print(f"{k}={v:+.1f}% ", end='')
            print()
            
        except Exception as e:
            continue


def suggest_optimal_rules(df):
    """
    基于分析结果，给出最优VIX规则建议
    """
    print("\n" + "="*70)
    print("最优VIX阈值建议")
    print("="*70)
    
    # 1. 分析VIX分布
    vix_mean = df['VIX'].mean()
    vix_median = df['VIX'].median()
    vix_70 = np.percentile(df['VIX'], 70)
    vix_80 = np.percentile(df['VIX'], 80)
    vix_90 = np.percentile(df['VIX'], 90)
    
    print(f"\n1. 基于历史分布的建议:")
    print(f"   VIX均值: {vix_mean:.1f}（可作为'正常'与'偏高'的分界线）")
    print(f"   VIX 70分位: {vix_70:.1f}（约30%的时间高于此值）")
    print(f"   VIX 80分位: {vix_80:.1f}（约20%的时间高于此值，建议开始加仓）")
    print(f"   VIX 90分位: {vix_90:.1f}（约10%的时间高于此值，建议大幅加仓）")
    
    # 2. 基于未来收益分析
    print(f"\n2. 建议的VIX阈值和倍数:")
    print(f"""
    基于历史数据分析，建议采用以下5档配置:
    
    | VIX区间 | 加仓倍数 | 说明 |
    |---------|----------|------|
    | 0 ~ {vix_mean:.0f} | 1.0x | 正常市场，基础定投 |
    | {vix_mean:.0f} ~ {vix_70:.0f} | 1.5x | 偏高，轻度加仓 |
    | {vix_70:.0f} ~ {vix_80:.0f} | 2.0x | 恐慌初期，中度加仓 |
    | {vix_80:.0f} ~ {vix_90:.0f} | 3.0x | 高度恐慌，大幅加仓 |
    | {vix_90:.0f}+ | 5.0x | 极度恐慌，全力加仓 |
    """)
    
    # 3. 历史极端值参考
    print(f"\n3. 历史极端情况参考:")
    extreme_high = df[df['VIX'] >= 40]
    if len(extreme_high) > 0:
        avg_return_1y = []
        for idx in extreme_high.index:
            try:
                future = df.index[df.index >= idx + timedelta(days=360)]
                if len(future) > 0:
                    ret = (df.loc[future[0], 'QQQ'] / df.loc[idx, 'QQQ'] - 1) * 100
                    avg_return_1y.append(ret)
            except:
                continue
        if avg_return_1y:
            print(f"   VIX >= 40 后1年平均收益: {np.mean(avg_return_1y):+.1f}%")
            print(f"   出现次数: {len(extreme_high)} 次")


def main():
    print("="*70)
    print("VIX阈值优化分析")
    print("="*70)
    
    # 下载数据（从2006年开始，覆盖2008年危机）
    df = download_data(start='2006-01-01')
    
    # 1. VIX分布分析
    analyze_vix_distribution(df)
    
    # 2. 核心分析：VIX阈值 vs 未来收益
    forward_returns = analyze_forward_returns(df)
    
    # 3. 不同阈值定投策略对比
    dca_results = analyze_dca_at_vix_levels(df)
    
    # 4. 历史事件分析
    analyze_vix_spike_recovery(df)
    
    # 5. 给出建议
    suggest_optimal_rules(df)
    
    # 保存分析结果
    forward_returns.to_csv(OUTPUT_DIR / 'vix_forward_returns_analysis.csv', index=False, encoding='utf-8-sig')
    dca_results.to_csv(OUTPUT_DIR / 'vix_dca_threshold_comparison.csv', index=False, encoding='utf-8-sig')
    
    print(f"\n分析结果已保存到: {OUTPUT_DIR}")


if __name__ == '__main__':
    main()
