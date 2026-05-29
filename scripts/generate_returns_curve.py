# -*- coding: utf-8 -*-
"""生成收益率曲线 HTML（与重建后的策略数据保持一致）"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRATEGY_DIR = ROOT / "decision-tracking" / "vix_dca_strategy"
PUBLIC_DIR = ROOT / "public" / "vix_strategy"

# 价格数据 (yfinance 真实数据)
prices = {
    '2026-03-24': 1.952, '2026-03-25': 1.965, '2026-03-26': 1.947, '2026-03-27': 1.933,
    '2026-03-30': 1.902, '2026-03-31': 1.887, '2026-04-01': 1.968, '2026-04-02': 1.939,
    '2026-04-03': 1.945, '2026-04-07': 1.952, '2026-04-08': 2.045, '2026-04-09': 2.026,
    '2026-04-10': 2.038, '2026-04-13': 2.028, '2026-04-14': 2.064, '2026-04-15': 2.100,
    '2026-04-16': 2.143, '2026-04-17': 2.128, '2026-04-20': 2.130, '2026-04-21': 2.133,
    '2026-04-22': 2.141, '2026-04-23': 2.150, '2026-04-24': 2.157, '2026-04-27': 2.196,
    '2026-04-28': 2.197, '2026-04-29': 2.188, '2026-04-30': 2.196, '2026-05-06': 2.270,
    '2026-05-07': 2.315, '2026-05-08': 2.318, '2026-05-11': 2.378, '2026-05-12': 2.348,
    '2026-05-13': 2.360, '2026-05-14': 2.371, '2026-05-15': 2.355, '2026-05-18': 2.312,
    '2026-05-19': 2.306, '2026-05-20': 2.317, '2026-05-21': 2.346, '2026-05-22': 2.379,
    '2026-05-25': 2.477, '2026-05-26': 2.442, '2026-05-27': 2.490, '2026-05-28': 2.468,
    '2026-05-29': 2.540,
}

# VIX 数据
vixs = {
    '2026-03-24': 26.95, '2026-03-25': 25.33, '2026-03-26': 27.44, '2026-03-27': 31.05,
    '2026-03-30': 30.61, '2026-03-31': 25.25, '2026-04-01': 24.54, '2026-04-02': 23.87,
    '2026-04-06': 24.17, '2026-04-07': 25.78, '2026-04-08': 21.04, '2026-04-09': 19.49,
    '2026-04-10': 19.23, '2026-04-13': 19.12, '2026-04-14': 18.36, '2026-04-15': 18.17,
    '2026-04-16': 17.94, '2026-04-17': 17.48, '2026-04-20': 18.87, '2026-04-21': 19.50,
    '2026-04-22': 18.92, '2026-04-23': 19.31, '2026-04-24': 18.71, '2026-04-27': 18.02,
    '2026-04-28': 17.83, '2026-04-29': 18.81, '2026-04-30': 16.89, '2026-05-01': 16.99,
    '2026-05-04': 18.29, '2026-05-05': 17.38, '2026-05-06': 17.39, '2026-05-07': 17.08,
    '2026-05-08': 17.19, '2026-05-11': 18.38, '2026-05-12': 17.99, '2026-05-13': 17.87,
    '2026-05-14': 17.26, '2026-05-15': 18.43, '2026-05-18': 17.82, '2026-05-19': 18.06,
    '2026-05-20': 17.44, '2026-05-21': 16.76, '2026-05-22': 16.70, '2026-05-25': 16.59,
    '2026-05-26': 17.01, '2026-05-27': 16.29, '2026-05-28': 15.74, '2026-05-29': 15.81,
}

# 持仓变化 (日期: 累计份额, 累计成本)
positions = {
    '2026-03-23': (0, 0.0),
    '2026-03-24': (1540, 2998.68),
    '2026-04-06': (1540, 2998.68),
    '2026-04-07': (2308, 4497.97),
    '2026-04-20': (2308, 4497.97),
    '2026-04-21': (3222, 6447.73),
    '2026-05-18': (3222, 6447.73),
    '2026-05-19': (4067, 8396.49),
}

def get_position(date_str):
    sorted_dates = sorted(positions.keys())
    current = (0, 0.0)
    for pd in sorted_dates:
        if pd <= date_str:
            current = positions[pd]
    return current

# 生成每日数据
all_dates = sorted(prices.keys())
raw_data = []
prev_pnl = 0.0

for d in all_dates:
    price = prices[d]
    vix = vixs.get(d)
    shares, cost = get_position(d)
    mv = shares * price
    unrealized = mv - cost if cost > 0 else 0
    daily_pnl = unrealized - prev_pnl
    return_pct = (unrealized / cost * 100) if cost > 0 else 0
    
    raw_data.append({
        "date": d,
        "price": round(price, 3),
        "vix": round(vix, 2) if vix else None,
        "market_value": round(mv, 2),
        "unrealized_pnl": round(unrealized, 2),
        "daily_pnl": round(daily_pnl, 2),
        "total_return_pct": round(return_pct, 2),
    })
    prev_pnl = unrealized

latest = raw_data[-1]

# 生成 HTML
html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>VIX定投策略 — 累计收益率曲线</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; background: #f8fafc; padding: 16px; }}
  .chart-container {{ width: 100%; max-width: 960px; margin: 0 auto; background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); padding: 20px; }}
  .chart-header {{ display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 12px; }}
  .chart-title {{ font-size: 18px; font-weight: 600; color: #1f2937; }}
  .period-tabs {{ display: flex; gap: 4px; background: #f3f4f6; border-radius: 6px; padding: 3px; }}
  .period-tab {{ padding: 5px 14px; border: none; background: transparent; color: #6b7280; font-size: 12px; font-weight: 500; border-radius: 4px; cursor: pointer; transition: all 0.2s; }}
  .period-tab:hover {{ color: #374151; }}
  .period-tab.active {{ background: #fff; color: #1f2937; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }}
  .chart-subtitle {{ font-size: 12px; color: #9ca3af; margin-bottom: 8px; }}
  #chart {{ width: 100%; height: 400px; }}
  .stats-bar {{ display: flex; justify-content: center; gap: 24px; margin-top: 12px; padding-top: 12px; border-top: 1px solid #e5e7eb; flex-wrap: wrap; }}
  .stat-item {{ text-align: center; }}
  .stat-label {{ font-size: 11px; color: #6b7280; }}
  .stat-value {{ font-size: 14px; font-weight: 600; color: #1f2937; }}
  .stat-value.positive {{ color: #16a34a; }}
  .stat-value.negative {{ color: #dc2626; }}
</style>
</head>
<body>
<div class="chart-container">
  <div class="chart-header">
    <div class="chart-title">VIX定投策略 — 累计收益率曲线</div>
    <div class="period-tabs">
      <button class="period-tab active" data-period="day" onclick="switchPeriod('day')">日</button>
      <button class="period-tab" data-period="week" onclick="switchPeriod('week')">周</button>
      <button class="period-tab" data-period="month" onclick="switchPeriod('month')">月</button>
      <button class="period-tab" data-period="year" onclick="switchPeriod('year')">年</button>
    </div>
  </div>
  <div class="chart-subtitle">鼠标悬停查看详细数据 | 最后更新: {latest['date']}</div>
  <div id="truncation-notice" style="display:none; font-size:12px; color:#d97706; margin-bottom:8px; padding:6px 10px; background:#fffbeb; border-radius:4px; border:1px solid #fcd34d;"></div>
  <div id="chart"></div>
  <div class="stats-bar">
    <div class="stat-item">
      <div class="stat-label">累计收益率</div>
      <div class="stat-value positive">+{latest['total_return_pct']:.2f}%</div>
    </div>
    <div class="stat-item">
      <div class="stat-label">最新价格</div>
      <div class="stat-value">{latest['price']:.3f}元</div>
    </div>
    <div class="stat-item">
      <div class="stat-label">最新VIX</div>
      <div class="stat-value">{latest['vix']:.2f}</div>
    </div>
    <div class="stat-item">
      <div class="stat-label">持仓市值</div>
      <div class="stat-value">{latest['market_value']:,.2f}元</div>
    </div>
    <div class="stat-item">
      <div class="stat-label">浮动盈亏</div>
      <div class="stat-value positive">+{latest['unrealized_pnl']:.2f}元</div>
    </div>
  </div>
</div>
<script>
  var rawData = {json.dumps(raw_data, ensure_ascii=False)};
  var chart = echarts.init(document.getElementById('chart'));
  var currentPeriod = 'day';

  function getWeekKey(dateStr) {{
    var d = new Date(dateStr);
    var day = d.getDay();
    var diff = d.getDate() - day + (day === 0 ? -6 : 1);
    var monday = new Date(d.setDate(diff));
    return monday.getFullYear() + '-W' + String(Math.ceil((d.getDate())/7)).padStart(2,'0');
  }}

  function getYearWeek(dateStr) {{
    var d = new Date(dateStr);
    d.setHours(0,0,0,0);
    d.setDate(d.getDate() + 4 - (d.getDay() || 7));
    var yearStart = new Date(d.getFullYear(), 0, 1);
    var weekNo = Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
    return d.getFullYear() + '-W' + String(weekNo).padStart(2, '0');
  }}

  var PERIOD_LIMITS = {{ day: 180, week: 52, month: 24, year: Infinity }};

  function aggregateData(period) {{
    var data;
    if (period === 'day') {{
      data = rawData;
    }} else {{
      var groups = {{}};
      for (var i = 0; i < rawData.length; i++) {{
        var item = rawData[i];
        var key;
        if (period === 'week') {{
          key = getYearWeek(item.date);
        }} else if (period === 'month') {{
          key = item.date.substring(0, 7);
        }} else if (period === 'year') {{
          key = item.date.substring(0, 4);
        }}
        groups[key] = item;
      }}
      data = [];
      var sortedKeys = Object.keys(groups).sort();
      for (var k = 0; k < sortedKeys.length; k++) {{
        data.push(groups[sortedKeys[k]]);
      }}
    }}
    var limit = PERIOD_LIMITS[period];
    if (data.length > limit) {{
      return {{ data: data.slice(data.length - limit), truncated: true, total: data.length, shown: limit }};
    }}
    return {{ data: data, truncated: false, total: data.length, shown: data.length }};
  }}

  function renderChart(period) {{
    var result = aggregateData(period);
    var data = result.data;
    var dates = data.map(function(d) {{ return d.date; }});
    var totalReturns = data.map(function(d) {{ return d.total_return_pct; }});
    var dailyPnls = data.map(function(d) {{ return d.daily_pnl; }});
    var prices = data.map(function(d) {{ return d.price; }});
    var vixs = data.map(function(d) {{ return d.vix; }});
    var marketValues = data.map(function(d) {{ return d.market_value; }});
    var unrealizedPnls = data.map(function(d) {{ return d.unrealized_pnl; }});

    var noticeEl = document.getElementById('truncation-notice');
    if (result.truncated) {{
      var nextPeriod = {{ day: '周', week: '月', month: '年' }};
      noticeEl.innerHTML = '<span style="color:#d97706;">⚠️ 数据量较大（共' + result.total + '条），当前仅显示最近' + result.shown + '条。建议切换到 <strong>' + nextPeriod[period] + '</strong> 模式查看全部历史 →</span>';
      noticeEl.style.display = 'block';
    }} else {{
      noticeEl.style.display = 'none';
    }}

    var color = totalReturns[totalReturns.length - 1] >= 0 ? '#16a34a' : '#dc2626';
    var areaColorStart = totalReturns[totalReturns.length - 1] >= 0 ? 'rgba(22, 163, 74, 0.2)' : 'rgba(220, 38, 38, 0.2)';
    var areaColorEnd = totalReturns[totalReturns.length - 1] >= 0 ? 'rgba(22, 163, 74, 0.02)' : 'rgba(220, 38, 38, 0.02)';

    var option = {{
      tooltip: {{
        trigger: 'axis',
        backgroundColor: 'rgba(255,255,255,0.95)',
        borderColor: '#e5e7eb',
        borderWidth: 1,
        textStyle: {{ color: '#1f2937', fontSize: 12 }},
        formatter: function(params) {{
          var idx = params[0].dataIndex;
          var c = totalReturns[idx] >= 0 ? '#16a34a' : '#dc2626';
          var vixStr = vixs[idx] !== null && vixs[idx] !== undefined ? vixs[idx].toFixed(2) : '—';
          var mvStr = marketValues[idx] ? marketValues[idx].toLocaleString('zh-CN', {{minimumFractionDigits:2}}) : '—';
          return '<div style="font-weight:600;margin-bottom:6px;">' + dates[idx] + '</div>' +
            '<div style="display:grid;grid-template-columns:auto auto;gap:4px 16px;">' +
            '<span style="color:#6b7280;">累计收益率:</span> <span style="font-weight:600;color:' + c + '">' + (totalReturns[idx] >= 0 ? '+' : '') + totalReturns[idx].toFixed(2) + '%</span>' +
            '<span style="color:#6b7280;">当日盈亏:</span> <span style="font-weight:600;">' + (dailyPnls[idx] >= 0 ? '+' : '') + dailyPnls[idx].toFixed(2) + '元</span>' +
            '<span style="color:#6b7280;">ETF价格:</span> <span style="font-weight:600;">' + (prices[idx] ? prices[idx].toFixed(3) : '—') + '元</span>' +
            '<span style="color:#6b7280;">VIX:</span> <span style="font-weight:600;">' + vixStr + '</span>' +
            '<span style="color:#6b7280;">持仓市值:</span> <span style="font-weight:600;">' + mvStr + '元</span>' +
            '<span style="color:#6b7280;">浮动盈亏:</span> <span style="font-weight:600;color:' + c + '">' + (unrealizedPnls[idx] >= 0 ? '+' : '') + unrealizedPnls[idx].toFixed(2) + '元</span>' +
            '</div>';
        }}
      }},
      grid: {{ left: '3%', right: '4%', bottom: '3%', top: '10%', containLabel: true }},
      xAxis: {{
        type: 'category',
        boundaryGap: false,
        data: dates,
        axisLine: {{ lineStyle: {{ color: '#e5e7eb' }} }},
        axisLabel: {{ color: '#6b7280', fontSize: 10, rotate: period === 'day' ? 30 : 0 }},
        axisTick: {{ show: false }}
      }},
      yAxis: {{
        type: 'value',
        axisLabel: {{ formatter: '{{value}}%', color: '#6b7280', fontSize: 11 }},
        axisLine: {{ show: false }},
        splitLine: {{ lineStyle: {{ color: '#f3f4f6', type: 'dashed' }} }},
        scale: true
      }},
      series: [
        {{
          name: '累计收益率',
          type: 'line',
          smooth: 0.3,
          symbol: 'circle',
          symbolSize: period === 'day' ? 4 : 7,
          showSymbol: period !== 'day',
          lineStyle: {{ width: 3, color: color }},
          itemStyle: {{ color: color, borderWidth: 2, borderColor: '#fff' }},
          areaStyle: {{
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              {{ offset: 0, color: areaColorStart }},
              {{ offset: 1, color: areaColorEnd }}
            ])
          }},
          data: totalReturns,
          markLine: {{
            silent: true,
            symbol: 'none',
            lineStyle: {{ color: '#9ca3af', type: 'solid', width: 1 }},
            data: [{{ yAxis: 0 }}],
            label: {{ show: false }}
          }}
        }}
      ],
      animationDuration: 500,
      animationEasing: 'cubicOut'
    }};

    chart.setOption(option, true);
  }}

  function switchPeriod(period) {{
    currentPeriod = period;
    document.querySelectorAll('.period-tab').forEach(function(btn) {{
      btn.classList.toggle('active', btn.dataset.period === period);
    }});
    renderChart(period);
  }}

  renderChart('day');
  window.addEventListener('resize', function() {{ chart.resize(); }});
</script>
</body>
</html>
'''

with open(STRATEGY_DIR / "returns_curve.html", 'w', encoding='utf-8') as f:
    f.write(html)

# 同步到 public
with open(PUBLIC_DIR / "returns_curve.html", 'w', encoding='utf-8') as f:
    f.write(html)

print("returns_curve.html 已生成")
print(f"  数据点: {len(raw_data)} 个")
print(f"  最新: {latest['date']} 收益率+{latest['total_return_pct']:.2f}% 浮盈+{latest['unrealized_pnl']:.2f}")
