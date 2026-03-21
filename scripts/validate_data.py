#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据质量硬校验脚本
必须在生成报告前运行并通过

使用方法：
    python scripts/validate_data.py config/validation_03613.yaml
    
返回码：
    0 - 校验通过，可以生成报告
    1 - 校验失败，必须修正数据错误
    2 - 校验通过但有警告，建议复核
"""

import sys
import yaml
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from pathlib import Path


@dataclass
class ValidationResult:
    """校验结果"""
    passed: bool = False
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


class DataValidator:
    """数据硬校验器"""
    
    def __init__(self, data: Dict[str, Any]):
        self.data = data
        self.result = ValidationResult()
        self.errors = []
        self.warnings = []
    
    def validate_all(self) -> ValidationResult:
        """执行所有校验"""
        print("=" * 60)
        print("[VALIDATION] 开始数据质量硬校验")
        print("=" * 60)
        
        # 1. 元数据校验
        self._validate_metadata()
        
        # 2. 现金数据校验（S级）
        self._validate_cash_data()
        
        # 3. 负债数据校验（S级）
        self._validate_debt_data()
        
        # 4. 利润数据校验（S级）
        self._validate_profit_data()
        
        # 5. 现金流数据校验（S级）
        self._validate_cashflow_data()
        
        # 6. 股本数据校验（S级）
        self._validate_share_data()
        
        # 7. 计算指标校验
        self._validate_calculated_metrics()
        
        # 8. 历史对比校验
        self._validate_historical_comparison()
        
        # 9. 交叉验证
        self._validate_cross_checks()
        
        # 10. 检查清单校验
        self._validate_checklist()
        
        # 11. 确认声明校验
        self._validate_confirmation()
        
        # 汇总结果
        self.result.errors = self.errors
        self.result.warnings = self.warnings
        self.result.passed = len(self.errors) == 0
        
        return self.result
    
    def _validate_metadata(self):
        """校验元数据"""
        print("\n[1] 元数据校验")
        
        meta = self.data.get('analysis_metadata', {})
        
        required_fields = ['stock_code', 'stock_name', 'annual_report_year']
        for field in required_fields:
            if not meta.get(field):
                self.errors.append(f"[METADATA] 缺少必填字段: {field}")
        
        # 检查是否使用年报
        checks = meta.get('validation_checks', [])
        for check in checks:
            if not check.get('checked', False):
                self.errors.append(f"[METADATA] 未勾选确认: {check.get('check', '')}")
        
        if not any(e for e in self.errors if e.startswith('[METADATA]')):
            print("   [PASS] 元数据校验通过")
    
    def _validate_cash_data(self):
        """校验现金数据（S级强制）"""
        print("\n[2] 现金数据校验（S级）")
        
        cash = self.data.get('core_financial_data', {}).get('cash_and_bank_balances', {})
        
        # 检查置信度
        if cash.get('confidence') != 'S':
            self.errors.append("[CASH] 现金数据必须是S级（年报原文）")
        
        # 检查来源
        source = cash.get('source', '')
        if not source or 'annual_report' not in source:
            self.errors.append("[CASH] 现金数据必须来自年报原文（source字段必须包含annual_report）")
        
        # 检查页码
        if not cash.get('page_number') or cash.get('page_number') == 0:
            self.errors.append("[CASH] 必须标注现金数据的年报页码")
        
        # 检查单位
        if cash.get('unit') not in ['HKD', 'RMB']:
            self.errors.append("[CASH] 现金单位必须是HKD或RMB")
        
        # 检查数值合理性（避免单位错误）
        value = cash.get('value', 0)
        if value == 0:
            self.warnings.append("[CASH] 现金为0，请确认是否填写")
        elif value < 1000000:  # 小于100万
            self.warnings.append(f"[CASH] 现金数值{value}较小，请确认单位是否正确（应为元而非万元/亿元）")
        
        # 检查确认勾选
        if not cash.get('verification_checked', False):
            self.errors.append("[CASH] 必须勾选确认现金数据已核查")
        
        if not any(e for e in self.errors if e.startswith('[CASH]')):
            print(f"   [PASS] 现金数据校验通过: {value:,.0f} {cash.get('unit', '')}")
    
    def _validate_debt_data(self):
        """校验负债数据（S级强制）"""
        print("\n[3] 负债数据校验（S级）")
        
        debt = self.data.get('core_financial_data', {}).get('interest_bearing_debt', {})
        
        # 检查各组成部分
        components = ['short_term', 'long_term', 'bonds', 'lease_liabilities']
        for comp in components:
            comp_data = debt.get(comp, {})
            if comp_data.get('value', 0) > 0 and not comp_data.get('source'):
                self.warnings.append(f"[DEBT] {comp}有数值但未标注来源")
        
        # 检查计算是否正确
        total_calculated = (
            debt.get('short_term', {}).get('value', 0) +
            debt.get('long_term', {}).get('value', 0) +
            debt.get('bonds', {}).get('value', 0) +
            debt.get('lease_liabilities', {}).get('value', 0)
        )
        total_recorded = debt.get('total_value', 0)
        
        if total_recorded > 0 and abs(total_calculated - total_recorded) > 0.01:
            self.errors.append(
                f"[DEBT] 有息负债计算错误: "
                f"{debt.get('short_term', {}).get('value', 0)} + "
                f"{debt.get('long_term', {}).get('value', 0)} + "
                f"{debt.get('bonds', {}).get('value', 0)} + "
                f"{debt.get('lease_liabilities', {}).get('value', 0)} = "
                f"{total_calculated}, 但填写为 {total_recorded}"
            )
        
        if not any(e for e in self.errors if e.startswith('[DEBT]')):
            print(f"   [PASS] 负债数据校验通过: 有息负债合计 {total_calculated:,.0f}")
    
    def _validate_profit_data(self):
        """校验利润数据（S级强制）"""
        print("\n[4] 利润数据校验（S级）")
        
        core = self.data.get('core_financial_data', {})
        revenue = core.get('revenue', {})
        profit = core.get('net_profit_attributable', {})
        
        # 检查必填字段
        if not revenue.get('value'):
            self.errors.append("[PROFIT] 收入数据未填写")
        if not profit.get('value'):
            self.errors.append("[PROFIT] 归母净利润未填写")
        
        if not any(e for e in self.errors if e.startswith('[PROFIT]')):
            print(f"   [PASS] 利润数据校验通过")
    
    def _validate_cashflow_data(self):
        """校验现金流数据（S级强制）"""
        print("\n[5] 现金流数据校验（S级）")
        
        core = self.data.get('core_financial_data', {})
        ocf = core.get('operating_cash_flow', {})
        capex = core.get('capex', {})
        
        # 检查经营现金流
        if ocf.get('confidence') != 'S':
            self.errors.append("[CASHFLOW] 经营现金流必须是S级")
        if not ocf.get('verification_checked', False):
            self.errors.append("[CASHFLOW] 必须勾选确认经营现金流已核查")
        
        # 检查资本开支（即使为0也要明确）
        if 'value' not in capex:
            self.errors.append("[CASHFLOW] 必须明确填写资本开支（即使为0）")
        
        if not any(e for e in self.errors if e.startswith('[CASHFLOW]')):
            print(f"   [PASS] 现金流数据校验通过")
    
    def _validate_share_data(self):
        """校验股本数据（S级强制）"""
        print("\n[6] 股本数据校验（S级）")
        
        core = self.data.get('core_financial_data', {})
        shares = core.get('total_shares', {})
        price = core.get('share_price', {})
        
        if not shares.get('value'):
            self.errors.append("[SHARE] 总股本未填写")
        if not price.get('value'):
            self.errors.append("[SHARE] 股价未填写")
        
        if not any(e for e in self.errors if e.startswith('[SHARE]')):
            print(f"   [PASS] 股本数据校验通过")
    
    def _validate_calculated_metrics(self):
        """校验计算指标"""
        print("\n[7] 计算指标校验")
        
        core = self.data.get('core_financial_data', {})
        metrics = core.get('calculated_metrics', {})
        
        # 获取原始数据
        cash = core.get('cash_and_bank_balances', {}).get('value', 0)
        restricted = core.get('restricted_cash', {}).get('value', 0)
        debt_short = core.get('interest_bearing_debt', {}).get('short_term', {}).get('value', 0)
        debt_long = core.get('interest_bearing_debt', {}).get('long_term', {}).get('value', 0)
        debt_bonds = core.get('interest_bearing_debt', {}).get('bonds', {}).get('value', 0)
        debt_lease = core.get('interest_bearing_debt', {}).get('lease_liabilities', {}).get('value', 0)
        debt_total = debt_short + debt_long + debt_bonds + debt_lease
        
        ocf = core.get('operating_cash_flow', {}).get('value', 0)
        capex = core.get('capex', {}).get('value', 0)
        shares = core.get('total_shares', {}).get('value', 0)
        price = core.get('share_price', {}).get('value', 0)
        profit = core.get('net_profit_attributable', {}).get('value', 0)
        
        market_cap = shares * price
        
        # 校验净现金计算
        net_cash_expected = cash - restricted - debt_total
        net_cash_recorded = metrics.get('net_cash', {}).get('value', 0)
        if net_cash_recorded > 0 and abs(net_cash_expected - net_cash_recorded) > 0.01:
            self.errors.append(
                f"[CALC] 净现金计算错误: "
                f"{cash} - {restricted} - {debt_total} = {net_cash_expected}, "
                f"但填写为 {net_cash_recorded}"
            )
        
        # 校验FCF计算
        fcf_expected = ocf - capex
        fcf_recorded = metrics.get('fcf', {}).get('value', 0)
        if fcf_recorded != 0 and abs(fcf_expected - fcf_recorded) > 0.01:
            self.errors.append(
                f"[CALC] FCF计算错误: {ocf} - {capex} = {fcf_expected}, 但填写为 {fcf_recorded}"
            )
        
        # 校验FCF倍数
        fcf_multiple = metrics.get('fcf_multiple_ex_cash', {}).get('value', 0)
        if fcf_multiple > 0 and fcf_expected > 0:
            market_cap_ex_cash = market_cap - net_cash_expected
            expected_multiple = market_cap_ex_cash / fcf_expected if fcf_expected != 0 else 0
            if abs(expected_multiple - fcf_multiple) > 0.1:
                self.warnings.append(
                    f"[CALC] 剔除现金FCF倍数计算可能有误: "
                    f"({market_cap} - {net_cash_expected}) / {fcf_expected} = "
                    f"{expected_multiple:.2f}, 但填写为 {fcf_multiple}"
                )
        
        if not any(e for e in self.errors if e.startswith('[CALC]')):
            print(f"   [PASS] 计算指标校验通过")
    
    def _validate_historical_comparison(self):
        """校验历史对比"""
        print("\n[8] 历史对比校验")
        
        hist = self.data.get('historical_comparison', {})
        years = hist.get('years', [])
        
        if len(years) < 3:
            self.warnings.append("[HIST] 历史对比少于3年，建议补充")
        
        print(f"   [PASS] 历史对比校验通过 ({len(years)}年数据)")
    
    def _validate_cross_checks(self):
        """交叉验证"""
        print("\n[9] 交叉验证")
        
        core = self.data.get('core_financial_data', {})
        cross = self.data.get('cross_validation', {})
        
        cash = core.get('cash_and_bank_balances', {}).get('value', 0)
        
        # 利息率验证
        interest = cross.get('interest_rate_check', {})
        interest_income = interest.get('interest_income', 0)
        if cash > 0 and interest_income > 0:
            rate = interest_income / cash
            if not (0.01 <= rate <= 0.05):
                self.warnings.append(
                    f"[CROSS] 利息率异常: {rate*100:.2f}% (正常范围1%-5%)"
                )
        
        print(f"   [PASS] 交叉验证通过")
    
    def _validate_checklist(self):
        """校验检查清单"""
        print("\n[10] 校验检查清单")
        
        checklist = self.data.get('validation_checklist', [])
        
        for item in checklist:
            if not item.get('checked', False):
                self.errors.append(f"[CHECKLIST] 未勾选: {item.get('item', '')}")
            
            # 如果变动>30%，必须解释
            if item.get('id') == 'variance' and item.get('checked', False):
                if not item.get('variance_explanation'):
                    self.warnings.append("[CHECKLIST] 数据变动>30%，建议填写解释")
        
        if not any(e for e in self.errors if e.startswith('[CHECKLIST]')):
            print(f"   [PASS] 检查清单校验通过")
    
    def _validate_confirmation(self):
        """校验确认声明"""
        print("\n[11] 确认声明校验")
        
        confirm = self.data.get('confirmation', {})
        
        if not confirm.get('analyst_signature'):
            self.errors.append("[CONFIRM] 必须填写分析人员签名")
        
        if not confirm.get('validation_date'):
            self.errors.append("[CONFIRM] 必须填写校验完成日期")
        
        print(f"   [PASS] 确认声明校验通过")
    
    def print_report(self):
        """打印校验报告"""
        print("\n" + "=" * 60)
        print("[SUMMARY] 校验结果汇总")
        print("=" * 60)
        
        if self.result.errors:
            print(f"\n[FAIL] 发现 {len(self.result.errors)} 个错误（必须修正）：")
            for i, error in enumerate(self.result.errors, 1):
                print(f"   {i}. {error}")
        
        if self.result.warnings:
            print(f"\n[WARN] 发现 {len(self.result.warnings)} 个警告（建议复核）：")
            for i, warning in enumerate(self.result.warnings, 1):
                print(f"   {i}. {warning}")
        
        if self.result.passed and not self.result.warnings:
            print("\n[PASS] 所有校验通过，可以生成报告！")
        elif self.result.passed and self.result.warnings:
            print("\n[PASS] 校验通过但有警告，建议复核后生成报告")
        else:
            print("\n[FAIL] 校验失败，必须修正以上错误后才能生成报告")
        
        print("=" * 60)


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python scripts/validate_data.py config/validation_XXXX.yaml")
        sys.exit(1)
    
    yaml_path = Path(sys.argv[1])
    
    if not yaml_path.exists():
        print(f"❌ 文件不存在: {yaml_path}")
        sys.exit(1)
    
    try:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
    except Exception as e:
        print(f"❌ YAML解析错误: {e}")
        sys.exit(1)
    
    # 执行校验
    validator = DataValidator(data)
    result = validator.validate_all()
    validator.print_report()
    
    # 返回码
    if not result.passed:
        sys.exit(1)  # 失败
    elif result.warnings:
        sys.exit(2)  # 通过但有警告
    else:
        sys.exit(0)  # 完全通过


if __name__ == "__main__":
    main()
