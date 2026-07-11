import os
import sys
import csv
import json
import re
import yaml
import time
from datetime import datetime
from typing import Dict, List, Any, Optional

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

try:
    import akshare as ak
except ImportError:
    print("[ERROR] akshare not installed. Install with: pip install akshare")
    sys.exit(1)


CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'screen_config.yaml')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'output')


def load_config() -> Dict[str, Any]:
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def log(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


def get_all_hk_stocks() -> List[Dict[str, Any]]:
    log("获取港股列表...")
    try:
        df = ak.stock_hk_spot_em()
        stocks = []
        for _, row in df.iterrows():
            stock = {
                'code': str(row.get('代码', '')),
                'name': row.get('名称', ''),
                'price': float(row.get('最新价', 0)),
                'change_percent': float(row.get('涨跌幅', 0)),
                'volume': float(row.get('成交量', 0)),
                'turnover': float(row.get('成交额', 0)),
            }
            if stock['code'] and stock['price'] > 0:
                stocks.append(stock)
        log(f"获取到 {len(stocks)} 只港股")
        return stocks
    except Exception as e:
        log(f"获取港股列表失败: {e}")
        return []


def get_stock_fundamentals(code: str) -> Optional[Dict[str, Any]]:
    try:
        df = ak.stock_financial_analysis_indicator_em(symbol=f"hk{code}")
        if df.empty:
            return None
        
        latest = df.iloc[0]
        return {
            'pe': float(latest.get('市盈率', 0)),
            'pb': float(latest.get('市净率', 0)),
            'roe': float(latest.get('净资产收益率', 0)),
            'dividend_yield': float(latest.get('股息率', 0)),
            'market_cap': float(latest.get('总市值', 0)),
            'net_asset': float(latest.get('净资产', 0)),
            'total_assets': float(latest.get('总资产', 0)),
            'total_liability': float(latest.get('总负债', 0)),
            'revenue': float(latest.get('营业收入', 0)),
            'profit': float(latest.get('净利润', 0)),
        }
    except Exception as e:
        return None


def get_stock_balance_sheet(code: str) -> Optional[Dict[str, Any]]:
    try:
        df = ak.stock_balance_sheet_em(symbol=f"hk{code}")
        if df.empty:
            return None
        
        latest = df.iloc[0]
        return {
            'cash': float(latest.get('货币资金', 0)),
            'total_assets': float(latest.get('总资产', 0)),
            'total_liability': float(latest.get('总负债', 0)),
            'current_liability': float(latest.get('流动负债', 0)),
        }
    except Exception as e:
        return None


def is_excluded(name: str, exclusions: List[str]) -> bool:
    for pattern in exclusions:
        if pattern in name:
            return True
    return False


def filter_net_cash(stock: Dict, fundamentals: Dict, balance: Dict, config: Dict) -> bool:
    min_ratio = config.get('min_net_cash_to_market_ratio', 1.0)
    max_pe = config.get('max_pe', 15)
    
    market_cap = fundamentals.get('market_cap', 0)
    if market_cap <= 0:
        return False
    
    cash = balance.get('cash', 0)
    total_liability = balance.get('total_liability', 0)
    net_cash = cash - total_liability
    
    if net_cash <= 0:
        return False
    
    ratio = net_cash / market_cap
    pe = fundamentals.get('pe', 999)
    
    return ratio >= min_ratio and pe > 0 and pe <= max_pe


def filter_cigar_butt(stock: Dict, fundamentals: Dict, config: Dict) -> bool:
    max_pb = config.get('max_pb', 0.5)
    min_market_cap = config.get('min_market_cap', 500)
    max_pe = config.get('max_pe', 20)
    
    pb = fundamentals.get('pb', 999)
    market_cap = fundamentals.get('market_cap', 0)
    pe = fundamentals.get('pe', 999)
    
    return pb > 0 and pb <= max_pb and market_cap >= min_market_cap and pe > 0 and pe <= max_pe


def filter_high_dividend(stock: Dict, fundamentals: Dict, config: Dict) -> bool:
    min_yield = config.get('min_dividend_yield', 5.0)
    max_pe = config.get('max_pe', 12)
    
    dividend_yield = fundamentals.get('dividend_yield', 0)
    pe = fundamentals.get('pe', 999)
    
    return dividend_yield >= min_yield and pe > 0 and pe <= max_pe


def filter_undervalued(stock: Dict, fundamentals: Dict, config: Dict) -> bool:
    max_pe = config.get('max_pe', 8)
    min_roe = config.get('min_roe', 5.0)
    min_market_cap = config.get('min_market_cap', 1000)
    
    pe = fundamentals.get('pe', 999)
    roe = fundamentals.get('roe', 0)
    market_cap = fundamentals.get('market_cap', 0)
    
    return pe > 0 and pe <= max_pe and roe >= min_roe and market_cap >= min_market_cap


def screen_stocks(config: Dict) -> Dict[str, List[Dict]]:
    stocks = get_all_hk_stocks()
    if not stocks:
        return {}
    
    exclusions = config.get('exclusions', [])
    strategies = config.get('screen_strategies', {})
    
    results = {}
    
    for strategy_key, strategy_config in strategies.items():
        log(f"筛选策略: {strategy_config['name']}")
        filtered = []
        
        for i, stock in enumerate(stocks):
            if i % 100 == 0:
                log(f"  进度: {i}/{len(stocks)}")
            
            if is_excluded(stock['name'], exclusions):
                continue
            
            fundamentals = get_stock_fundamentals(stock['code'])
            if not fundamentals:
                continue
            
            balance = get_stock_balance_sheet(stock['code'])
            if not balance:
                continue
            
            matched = False
            if strategy_key == 'net_cash':
                matched = filter_net_cash(stock, fundamentals, balance, strategy_config['filters'])
            elif strategy_key == 'cigar_butt':
                matched = filter_cigar_butt(stock, fundamentals, strategy_config['filters'])
            elif strategy_key == 'high_dividend':
                matched = filter_high_dividend(stock, fundamentals, strategy_config['filters'])
            elif strategy_key == 'undervalued':
                matched = filter_undervalued(stock, fundamentals, strategy_config['filters'])
            
            if matched:
                cash = balance.get('cash', 0)
                total_liability = balance.get('total_liability', 0)
                net_cash = cash - total_liability
                market_cap = fundamentals.get('market_cap', 0)
                
                filtered.append({
                    'code': stock['code'],
                    'name': stock['name'],
                    'price': stock['price'],
                    'pe': fundamentals.get('pe', 0),
                    'pb': fundamentals.get('pb', 0),
                    'roe': fundamentals.get('roe', 0),
                    'dividend_yield': fundamentals.get('dividend_yield', 0),
                    'market_cap': market_cap,
                    'net_cash': net_cash,
                    'net_cash_ratio': net_cash / market_cap if market_cap > 0 else 0,
                    'strategy': strategy_config['name'],
                })
        
        filtered.sort(key=lambda x: x.get('net_cash_ratio', 0) if strategy_key == 'net_cash' else x.get('pb', 999), reverse=False)
        
        top_n = config.get('output', {}).get('top_n', 20)
        results[strategy_key] = filtered[:top_n]
        
        log(f"  筛选出 {len(filtered)} 只，保留前 {len(results[strategy_key])} 只")
    
    return results


def save_results(results: Dict[str, List[Dict]], config: Dict):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    all_stocks = []
    for strategy_key, stocks in results.items():
        strategy_name = config['screen_strategies'][strategy_key]['name']
        for stock in stocks:
            stock['strategy'] = strategy_name
            all_stocks.append(stock)
    
    csv_path = os.path.join(OUTPUT_DIR, f'screen_results_{timestamp}.csv')
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'code', 'name', 'price', 'pe', 'pb', 'roe', 'dividend_yield',
            'market_cap', 'net_cash', 'net_cash_ratio', 'strategy'
        ])
        writer.writeheader()
        writer.writerows(all_stocks)
    
    log(f"结果已保存: {csv_path}")
    
    latest_path = os.path.join(OUTPUT_DIR, 'latest_results.csv')
    with open(latest_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'code', 'name', 'price', 'pe', 'pb', 'roe', 'dividend_yield',
            'market_cap', 'net_cash', 'net_cash_ratio', 'strategy'
        ])
        writer.writeheader()
        writer.writerows(all_stocks)
    
    log(f"最新结果已保存: {latest_path}")
    
    json_path = os.path.join(OUTPUT_DIR, 'latest_results.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    log(f"JSON结果已保存: {json_path}")


def main():
    log("=" * 60)
    log("港股全市场筛选器")
    log("=" * 60)
    
    config = load_config()
    results = screen_stocks(config)
    save_results(results, config)
    
    log("=" * 60)
    log("筛选完成!")
    log("=" * 60)


if __name__ == '__main__':
    main()