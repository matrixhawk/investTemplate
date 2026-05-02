#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
港股金龟筛选器 V1.2 (V5.5.10数据质量硬约束整合版)
基于投资模板V5.5.10标准自动筛选港股标的
数据来源：东方财富（akshare）

【V5.5.10更新】数据质量硬约束整合版（卖资产第一视角）：
- 硬门槛：剔除净现金FCF倍数 <= 10倍（核心）
- 坚决排除：能源/煤炭/航运/有色/化工/地产/影视游戏
- 优先投资：银行/公用事业/医药流通/食品饮料/收费公路
- 毛利率稳定性：过去5年标准差 < 5%（严格<3%）
"""

import akshare as ak
import pandas as pd
import time
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# ==========================================
# 筛选标准配置（V5.5.10 数据质量硬约束整合版）
# ==========================================
# 核心原则：消除变量，利润可线性外推，非周期性
# 排除：能源、煤炭、航运、石油、有色、化工等强周期行业
# 优先：银行、公用事业、医药流通、控股平台

SCREENING_CONFIG = {
    # 估值硬门槛（卖资产第一视角）
    'adjusted_fcf_multiple_max': 10.0,   # 剔除净现金FCF倍数 <= 10 才有买入机会
    'adjusted_fcf_multiple_strong': 6.0, # <= 6 视为强机会

    # 基础门槛
    'market_cap_min': 10,             # 市值 > 10亿港元
    
    # 央国企白名单
    'central_soe_prefix': ['01', '02', '03', '11', '12', '13', '23', '33', '39', '60', '61', '68'],
    
    # ====== 行业筛选配置（消除变量核心）======
    
    # 严格排除的周期行业（利润依赖大宗商品价格）
    'exclude_industries': [
        # 能源/资源类（强周期）
        '石油', '原油', '天然气', '页岩气',
        '煤炭', '焦煤', '动力煤', '焦炭',
        '铁矿', '铜', '铝', '锌', '铅', '镍', '钴', '锂矿', '稀土',
        '黄金', '白银', '贵金属',
        '航运', '船舶', '海运', '港口', '集装箱',
        '化工', '化肥', '农药', '化纤', '塑料', '橡胶',
        '钢铁', '冶金', '矿业', '矿产',
        
        # 创作类（依赖项目）
        '影视', '电影', '游戏', '手游', '网游', '内容',
        
        # 其他排除
        '博彩', '赌', '加密货币', '区块链',
        '地产开发', '房地产开发',  # 高负债+项目制
    ],
    
    # 优先行业白名单（利润可线性外推）
    'preferred_industries': [
        '银行', '内银', '商业银行',
        '公用事业', '电力', '水务', '燃气',
        '医药', '医药流通', '医药零售',
        '食品', '饮料', '乳业',
        '物业', '物业管理',
        '高速公路', '铁路', '机场',  # 特许经营权型
    ],
    
    # 缓存设置
    'delay': 0.5,
}

# ==========================================
# 数据获取模块
# ==========================================

def get_hk_stock_list():
    """
    获取港股全市场股票列表（含基础指标）
    """
    print("📊 正在获取港股列表...")
    try:
        # 获取港股实时行情（包含PE/PB/股息率等）
        df = ak.stock_hk_ggt_components_em()
        print(f"✅ 获取到港股通成分股 {len(df)} 只")
        return df
    except Exception as e:
        print(f"❌ 获取港股列表失败: {e}")
        return pd.DataFrame()

def get_stock_detail(code):
    """
    获取个股详细财务数据
    """
    try:
        time.sleep(SCREENING_CONFIG['delay'])
        
        # 获取财务指标
        financial = ak.stock_financial_hk_analysis_indicator_em(symbol=code)
        
        # 获取公司资料（用于判断国企背景）
        profile = ak.stock_hk_profile_em(symbol=code)
        
        return {
            'financial': financial,
            'profile': profile
        }
    except Exception as e:
        return None

def get_stock_financial_data(code, name):
    """
    获取个股详细财务数据（用于深度分析）
    尝试获取：净利润、现金流、现金余额、负债等
    """
    try:
        time.sleep(SCREENING_CONFIG['delay'])
        
        result = {
            'code': code,
            'name': name,
            'net_profit': None,           # 净利润
            'operating_cash_flow': None,  # 经营现金流
            'capex': None,                # 资本开支（现金流口径，通常为正数表示现金流出）
            'cash_and_equivalents': None, # 现金及等价物
            'total_liabilities': None,    # 总负债
            'interest_bearing_debt': None, # 有息负债
            'total_equity': None,         # 股东权益
            'dividend': None,             # 派息金额
        }
        
        # 尝试获取财务摘要
        try:
            summary = ak.stock_hk_financial_summary_em(symbol=code)
            if not summary.empty:
                # 解析财务摘要数据
                for _, row in summary.iterrows():
                    item = row.get('项目', '')
                    value = row.get('数值', '')
                    
                    if '净利润' in item or '股东应占溢利' in item:
                        result['net_profit'] = parse_number(value)
                    elif '经营现金流' in item or '经营活动所得现金' in item:
                        result['operating_cash_flow'] = parse_number(value)
                    elif ('购建固定资产' in item or '资本开支' in item or
                          '购置固定资产' in item or '资本性支出' in item):
                        capex_value = parse_number(value)
                        if capex_value is not None:
                            # 若抓到负值，取绝对值统一为“支出额”
                            result['capex'] = abs(capex_value)
                    elif '现金及现金等价物' in item:
                        result['cash_and_equivalents'] = parse_number(value)
                    elif '总负债' in item:
                        result['total_liabilities'] = parse_number(value)
                    elif ('有息负债' in item or '借款总额' in item or '总借款' in item or
                          '银行借款' in item or '短期借款' in item or '长期借款' in item):
                        debt_value = parse_number(value)
                        if debt_value is not None:
                            if result['interest_bearing_debt'] is None:
                                result['interest_bearing_debt'] = debt_value
                            else:
                                # 若抓到分项，按分项累加
                                result['interest_bearing_debt'] += debt_value
                    elif '股东权益' in item or '净资产' in item:
                        result['total_equity'] = parse_number(value)
                    elif '派息' in item or '股息' in item:
                        result['dividend'] = parse_number(value)
        except:
            pass
        
        return result
    except Exception as e:
        return None

def parse_number(value_str):
    """解析数值字符串"""
    if pd.isna(value_str) or value_str == '-' or value_str == '':
        return None
    
    # 处理带单位的字符串
    value_str = str(value_str).replace(',', '').replace('港元', '').replace('人民币', '')
    
    try:
        # 处理亿、万等单位
        if '亿' in value_str:
            return float(value_str.replace('亿', ''))
        elif '万' in value_str:
            return float(value_str.replace('万', '')) / 10000
        else:
            return float(value_str)
    except:
        return None

def parse_float(value):
    """稳健解析数值（兼容字符串百分号/逗号/空值）"""
    if pd.isna(value) or value in ['', '-', None]:
        return None
    value = str(value).replace('%', '').replace(',', '').strip()
    try:
        return float(value)
    except:
        return None

# ==========================================
# 筛选逻辑模块
# ==========================================

def is_likely_central_soe(code, name, profile_df=None):
    """
    判断是否可能是央国企（启发式判断，非100%准确）
    """
    # 从名称判断
    central_keywords = [
        '中国', '中國', '中信', '中建', '中铁', '中交', '中航',
        '中远', '中外运', '中粮', '华润', '保利', '招商',
        '工商', '农业', '建设', '中国', '银行', '保险',
        '石油', '石化', '移动', '联通', '电信', '海洋',
        '国航', '南航', '东航', '中车', '中煤', '中铝',
        '中化', '国药', '中烟', '中广核', '华能', '大唐',
        '华电', '国电', '长江', '三峡', '国家', '中核',
        '中金', '光大', '广发', '海通', '华泰', '国泰',
        '北京', '上海', '天津', '重庆', '广东', '深圳',
        '广州', '厦门', '青岛', '宁波', '南京', '成都',
        '武汉', '西安', '沈阳', '大连', '济南', '杭州',
        '苏州', '无锡', '佛山', '东莞', '长沙', '郑州',
        '石家庄', '太原', '合肥', '南昌', '福州', '昆明',
        '贵阳', '南宁', '海口', '兰州', '银川', '西宁',
        '乌鲁木齐', '拉萨', '呼和浩特', '哈尔滨', '长春'
    ]
    
    name_upper = str(name).upper()
    
    # 检查关键词
    for keyword in central_keywords:
        if keyword in name_upper:
            return True, f"名称含'{keyword}'"
    
    # 从代码前缀判断（粗略）
    code_prefix = str(code)[:2]
    if code_prefix in SCREENING_CONFIG['central_soe_prefix']:
        return True, f"代码前缀{code_prefix}"
    
    return False, "疑似民营"

def should_exclude_industry(name, profile_df=None):
    """
    判断是否属于排除行业
    """
    name_upper = str(name).upper()
    
    for industry in SCREENING_CONFIG['exclude_industries']:
        if industry in name_upper:
            return True, industry
    
    return False, None

def is_preferred_industry(name, profile_df=None):
    """
    判断是否属于优先行业
    """
    name_upper = str(name).upper()
    for industry in SCREENING_CONFIG['preferred_industries']:
        if industry in name_upper:
            return True, industry
    return False, None

def calculate_adjusted_valuation(financial_data, market_cap_yi):
    """
    计算卖资产第一视角的核心指标：
    - 净现金 = 现金及等价物 - 有息负债
    - 剔除净现金市值 = 总市值 - 净现金
    - 剔除净现金FCF倍数 = 剔除净现金市值 / FCF（简化用经营现金流替代）
    """
    if not financial_data or market_cap_yi is None:
        return None

    ocf = financial_data.get('operating_cash_flow')
    capex = financial_data.get('capex')
    cash = financial_data.get('cash_and_equivalents')
    debt = financial_data.get('interest_bearing_debt')

    if ocf is None or cash is None or debt is None:
        return None

    # FCF口径：优先使用 OCF-CAPEX，缺失时降级为 OCF 代理
    if capex is not None:
        fcf = ocf - capex
        fcf_method = "FCF=OCF-CAPEX"
    else:
        fcf = ocf
        fcf_method = "FCF=OCF(代理)"

    if fcf <= 0:
        return {
            'fcf_estimate': fcf,
            'ocf': ocf,
            'capex': capex,
            'fcf_method': fcf_method,
            'net_cash': cash - debt,
            'adjusted_market_cap': None,
            'adjusted_fcf_multiple': None
        }

    net_cash = cash - debt
    adjusted_market_cap = market_cap_yi - net_cash
    # 剔除净现金后若<=0，视作极端低估，倍率按0处理
    adjusted_fcf_multiple = 0.0 if adjusted_market_cap <= 0 else adjusted_market_cap / fcf

    return {
        'fcf_estimate': fcf,
        'ocf': ocf,
        'capex': capex,
        'fcf_method': fcf_method,
        'net_cash': net_cash,
        'adjusted_market_cap': adjusted_market_cap,
        'adjusted_fcf_multiple': adjusted_fcf_multiple
    }

def screen_stocks(output_file=None):
    """
    主筛选函数
    """
    print("="*60)
    print("🚀 港股金龟筛选器启动")
    print(f"⏰ 当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    # 1. 获取基础列表
    base_df = get_hk_stock_list()
    
    if base_df.empty:
        print("❌ 未能获取数据，请检查网络连接")
        return pd.DataFrame()
    
    print(f"\n📋 开始筛选 {len(base_df)} 只港股...")
    print(f"📏 筛选标准: 剔除净现金FCF倍数<={SCREENING_CONFIG['adjusted_fcf_multiple_max']}（硬门槛）")
    print("-"*60)
    
    results = []
    excluded_count = {
        'market_cap': 0,
        'industry': 0,
        'missing_financial': 0,
        'fcf_non_positive': 0,
        'over_adjusted_fcf_multiple': 0,
        'data_error': 0,
    }
    
    # 2. 遍历筛选
    for idx, row in base_df.iterrows():
        code = row.get('代码', '')
        name = row.get('名称', '')
        
        # 获取基础指标
        try:
            pb = parse_float(row.get('市净率'))
            pe = parse_float(row.get('市盈率'))
            dividend = parse_float(row.get('股息率')) or 0.0

            # 尝试兼容多种字段名（单位统一折算为“亿港元”）
            market_cap_yi = None
            for cap_col in ['总市值', '市值', '总市值(港元)', '市值(港元)']:
                cap_raw = parse_float(row.get(cap_col))
                if cap_raw is None:
                    continue
                # 经验规则：若大于1e6，视作“港元”金额，转为亿港元
                market_cap_yi = cap_raw / 1e8 if cap_raw > 1e6 else cap_raw
                break

            pb = pb if pb is not None else 999
            pe = pe if pe is not None else 999
        except:
            excluded_count['data_error'] += 1
            continue
        
        # 检查排除行业
        should_exclude, industry = should_exclude_industry(name)
        if should_exclude:
            excluded_count['industry'] += 1
            continue

        # 市值门槛（配置项生效）
        if market_cap_yi is None or market_cap_yi < SCREENING_CONFIG['market_cap_min']:
            excluded_count['market_cap'] += 1
            continue
        
        # 判断央国企背景
        is_soe, soe_reason = is_likely_central_soe(code, name)
        is_preferred, preferred_reason = is_preferred_industry(name)
        
        # 获取详细财务数据（可选，深度分析时用）
        print(f"  🔍 深度分析: {name}({code}) PB={pb:.2f} PE={pe:.1f} 股息={dividend:.1f}%")
        financial_data = get_stock_financial_data(code, name)

        valuation = calculate_adjusted_valuation(financial_data, market_cap_yi)
        if not valuation:
            excluded_count['missing_financial'] += 1
            continue

        fcf_estimate = valuation['fcf_estimate']
        ocf = valuation['ocf']
        capex = valuation['capex']
        fcf_method = valuation['fcf_method']
        net_cash = valuation['net_cash']
        adjusted_market_cap = valuation['adjusted_market_cap']
        adjusted_fcf_multiple = valuation['adjusted_fcf_multiple']

        if fcf_estimate is None or fcf_estimate <= 0:
            excluded_count['fcf_non_positive'] += 1
            continue

        if adjusted_fcf_multiple is None or adjusted_fcf_multiple > SCREENING_CONFIG['adjusted_fcf_multiple_max']:
            excluded_count['over_adjusted_fcf_multiple'] += 1
            continue
        
        # 构建结果
        result = {
            '代码': code,
            '名称': name,
            'PB': round(pb, 2),
            'PE': round(pe, 1),
            '股息率(%)': round(dividend, 2),
            '总市值(亿港元)': round(market_cap_yi, 2) if market_cap_yi is not None else 'N/A',
            '经营现金流(亿)': round(ocf, 2) if ocf is not None else 'N/A',
            '资本开支(亿)': round(capex, 2) if capex is not None else 'N/A',
            'FCF估算(亿)': round(fcf_estimate, 2) if fcf_estimate is not None else 'N/A',
            'FCF口径': fcf_method,
            '净现金(亿)': round(net_cash, 2),
            '剔除净现金市值(亿)': round(adjusted_market_cap, 2),
            '剔除净现金FCF倍数': round(adjusted_fcf_multiple, 2),
            '最新价': row.get('最新价', 'N/A'),
            '涨跌幅(%)': row.get('涨跌幅', 'N/A'),
            '央国企': '✅' if is_soe else '⚠️',
            '央国企判断': soe_reason,
            '优先行业': '✅' if is_preferred else '⚪',
            '行业匹配': preferred_reason if is_preferred else '非优先行业',
        }
        
        results.append(result)
        
        # 每10个显示进度
        if len(results) % 10 == 0:
            print(f"  📊 已发现 {len(results)} 只候选标的")
    
    # 3. 整理结果
    print("-"*60)
    print(f"✅ 筛选完成！")
    print(f"   总计检查: {len(base_df)} 只")
    print(f"   符合条件: {len(results)} 只")
    print(f"   排除原因: 市值不足({excluded_count['market_cap']}), 排除行业({excluded_count['industry']}), "
          f"财务数据缺失({excluded_count['missing_financial']}), FCF<=0({excluded_count['fcf_non_positive']}), "
          f"剔除净现金FCF倍数超标({excluded_count['over_adjusted_fcf_multiple']}), 数据错误({excluded_count['data_error']})")
    
    if not results:
        print("⚠️ 未找到符合条件的标的，请放宽筛选条件重试")
        return pd.DataFrame()
    
    result_df = pd.DataFrame(results)
    
    # 4. 排序（优先央国企，再按综合评分）
    result_df['央国企排序'] = result_df['央国企'].apply(lambda x: 0 if x == '✅' else 1)
    result_df['综合评分'] = (
        result_df['央国企排序'] * 10 +  # 央国企优先
        result_df['优先行业'].apply(lambda x: 0 if x == '✅' else 2) +
        result_df['剔除净现金FCF倍数'] * 3 +
        result_df['PB'] * 1 +
        (10 - result_df['股息率(%)']) * 0.5
    )
    result_df = result_df.sort_values('综合评分').reset_index(drop=True)
    result_df = result_df.drop(columns=['央国企排序', '综合评分'])
    
    # 5. 输出结果
    print("\n" + "="*60)
    print("📈 候选标的列表（按投资吸引力排序）")
    print("="*60)
    print(result_df.to_string(index=False))
    
    # 6. 分类输出
    print("\n" + "="*60)
    print("🏆 强机会（剔除净现金FCF倍数 <= 6）")
    print("="*60)
    golden_turtles = result_df[result_df['剔除净现金FCF倍数'] <= SCREENING_CONFIG['adjusted_fcf_multiple_strong']]
    if not golden_turtles.empty:
        print(golden_turtles[['代码', '名称', '剔除净现金FCF倍数', '净现金(亿)', '央国企判断']].to_string(index=False))
        print(f"\n共 {len(golden_turtles)} 只强机会标的")
    else:
        print("暂无符合强机会标准的标的")
    
    print("\n" + "="*60)
    print("🥈 研究候选（6 < 剔除净现金FCF倍数 <= 10）")
    print("="*60)
    silver_turtles = result_df[
        (result_df['剔除净现金FCF倍数'] > SCREENING_CONFIG['adjusted_fcf_multiple_strong']) &
        (result_df['剔除净现金FCF倍数'] <= SCREENING_CONFIG['adjusted_fcf_multiple_max'])
    ]
    if not silver_turtles.empty:
        print(silver_turtles[['代码', '名称', '剔除净现金FCF倍数', 'PB', 'PE', '股息率(%)', '央国企']].head(20).to_string(index=False))
        if len(silver_turtles) > 20:
            print(f"... 及其他 {len(silver_turtles) - 20} 只标的")
    
    # 7. 保存到文件
    if output_file:
        result_df.to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"\n💾 结果已保存到: {output_file}")
    
    # 8. 生成AI分析用的提示词
    print("\n" + "="*60)
    print("🤖 AI深度分析提示词（复制使用）")
    print("="*60)
    
    top_10_codes = result_df.head(10)['代码'].tolist()
    top_10_names = result_df.head(10)['名称'].tolist()
    
    stock_list = ", ".join([f"{name}({code})" for code, name in zip(top_10_codes, top_10_names)])
    
    prompt = f"""
我使用"个股分析标准模版V5.5.10（数据质量硬约束整合版）"进行港股投资。

**核心筛选标准（V5.5.10更新）**：
- 卖资产第一视角：剔除净现金FCF倍数 <= 10倍才有买入机会
- 分层：<=6倍（强机会），6-10倍（研究区间），>10倍（暂不考虑）
- 消除变量原则：坚决排除能源/煤炭/航运/有色/化工/地产开发/影视游戏
- 优先行业：银行/公用事业（水务/燃气）/医药流通/食品饮料/收费公路
- 风险约束：必须FCF>0、净现金可计算（现金-有息负债）
- FCF口径优先：FCF=经营现金流-资本开支；缺失CAPEX时降级为经营现金流代理（需人工复核）

已通过初筛的候选标的：
{stock_list}

请按以下步骤分析：

**步骤1：行业筛选（消除变量第一关）** ⭐⭐⭐⭐⭐
- 是否为能源/煤炭/航运/石油/有色/化工/地产/影视游戏？→ ❌ 排除
- 是否为银行/公用事业/医药流通/食品饮料/收费公路？→ ✅ 优先

**步骤2：5分钟快速初筛**（模板第一章1.5节）
1. 地缘政治核查（非洲/冲突区资产>10%？一票否决）
2. 价格位置检查（距52周高点<30%？）
3. 负债快速扫描（财务费用>5亿？）
4. 现金覆盖率检查（现金<市值20%？）

**步骤3：毛利率稳定性检查**（V5.5.10沿用）
- 过去5年毛利率标准差 < 5%？（严格<3%）
- 利润是否依赖大宗商品价格？

**步骤4：深度估值分析**（卖资产视角）
- 剔除净现金FCF倍数（核心指标）：<=10倍保留，<=6倍优先
- 流派判定：优先纯硬收息型（银行/公用事业），谨慎价值发现型（周期底）
- 持仓状态标签：🟢正常/🔵已回本/🟡高位/🟠关注/🔴遗留

输出格式（表格）：
| 代码 | 名称 | 行业筛选 | 净现金 | 剔除净现金FCF倍数 | 估值分层 | 操作建议 |
|------|------|---------|-------|-------------------|---------|---------|
"""
    print(prompt)
    
    return result_df

def main():
    """
    主函数
    """
    print("\n")
    
    # 设置输出文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"hk_candidates_{timestamp}.csv"
    
    # 执行筛选
    results = screen_stocks(output_file=output_file)
    
    if not results.empty:
        print("\n" + "="*60)
        print("✨ 筛选完成！建议操作：")
        print("="*60)
        print("1. 先看【强机会】列表（剔除净现金FCF倍数<=6）")
        print("2. 复制【AI深度分析提示词】到AI对话中")
        print(f"3. 详细数据已保存到: {output_file}")
        print("4. 对AI分析后的最终候选，务必人工复核年报数据（S级数据源）")
        print("="*60)
    
    return results

if __name__ == "__main__":
    main()
