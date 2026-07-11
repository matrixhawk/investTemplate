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
import datetime
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

        # 先拦截旧版/错误结构，避免后续校验出现难以理解的AttributeError
        if not self._validate_schema_compatibility():
            self.result.errors = self.errors
            self.result.warnings = self.warnings
            self.result.passed = False
            return self.result
        
        # 1. 元数据校验
        self._validate_metadata()
        
        # 2. 现金数据校验（S级）
        self._validate_cash_data()
        
        # 3. 负债数据校验（S级）
        self._validate_debt_data()
        
        # 4. 利润数据校验（S级）
        self._validate_profit_data()

        # 4.5 估值适用性与TTM时点校验（V5.5.23）
        self._validate_valuation_data()
        
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

    def _validate_schema_compatibility(self) -> bool:
        """确认输入使用当前YAML结构；旧版文件给出迁移提示而不是直接崩溃。"""
        if 'analysis_metadata' not in self.data or 'core_financial_data' not in self.data:
            self.errors.append(
                "[SCHEMA] 输入文件不是当前数据校验结构。请从 "
                "config/data_validation_template.yaml 重新复制，旧版 basic_info/data_sources 需迁移。"
            )
            return False

        core = self.data.get('core_financial_data')
        if not isinstance(core, dict):
            self.errors.append("[SCHEMA] core_financial_data必须是对象")
            return False

        return True
    
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
        
        # 时效性校验（新增）
        self._validate_data_freshness(meta)

        if not any(e for e in self.errors if e.startswith('[METADATA]')):
            print("   [PASS] 元数据校验通过")
    
    def _validate_data_freshness(self, meta: Dict[str, Any]):
        """校验数据时效性（强化）"""
        freshness = meta.get('data_freshness_control', {})
        report_type = meta.get('report_type', 'annual')
        is_latest_full_year = meta.get('is_latest_full_year', False)

        # 1. 检查是否使用年报
        if report_type != 'annual':
            self.warnings.append("[TIMING] 使用非年报数据（中报/季报），置信度应降级")
            # 如果是中报，检查是否明确标注
            if report_type == 'interim':
                self.warnings.append("[TIMING] [WARNING] 使用中报数据，必须降级置信度为B级")

        # 2. 检查是否是最新年报
        if not is_latest_full_year:
            self.warnings.append("[TIMING] 可能不是最新完整年度年报，请确认")

        # 3. 检查数据时效
        try:
            current_date_str = freshness.get('current_date', '2026-03-22')
            annual_report_date_str = meta.get('annual_report_date', '')

            if annual_report_date_str:
                current_date = datetime.datetime.strptime(current_date_str, '%Y-%m-%d').date()
                annual_report_date = datetime.datetime.strptime(annual_report_date_str, '%Y-%m-%d').date()

                # 计算数据时效天数
                data_age_days = (current_date - annual_report_date).days

                max_allowed = freshness.get('max_allowed_age_days', 365)
                if data_age_days > max_allowed:
                    self.errors.append(
                        f"[TIMING] 数据过时: {data_age_days}天前发布（最大允许{max_allowed}天）"
                    )
                elif data_age_days > 180:  # 超过半年
                    self.warnings.append(
                        f"[TIMING] 数据较旧: {data_age_days}天前发布（建议使用最新数据）"
                    )

                # 检查是否使用上年数据（年报发布日期应在合理范围内）
                annual_report_year = meta.get('annual_report_year', 0)
                if annual_report_year > 0:
                    current_year = current_date.year
                    if annual_report_year < current_year - 1:
                        self.errors.append(
                            f"[TIMING] 年报年份过旧: {annual_report_year}年（当前{current_year}年）"
                        )
        except Exception as e:
            self.warnings.append(f"[TIMING] 日期解析错误: {e}")

        # 4. 检查核心数据一致性（报表期）
        self._validate_report_period_consistency()

    def _validate_report_period_consistency(self):
        """校验所有核心数据的报表期是否一致"""
        core = self.data.get('core_financial_data', {})

        # 收集所有报表期
        periods = []

        cash_period = core.get('cash_and_bank_balances', {}).get('report_period')
        if cash_period:
            periods.append(("现金", cash_period))

        # 检查负债数据报表期
        debt = core.get('interest_bearing_debt', {})
        for comp in ['short_term', 'long_term', 'bonds', 'lease_liabilities']:
            comp_data = debt.get(comp, {})
            period = comp_data.get('report_period')
            if period:
                periods.append((f"负债-{comp}", period))

        # 检查利润数据报表期
        for item in ['revenue', 'net_profit', 'net_profit_attributable']:
            item_data = core.get(item, {})
            period = item_data.get('report_period')
            if period:
                periods.append((item, period))

        # 检查现金流数据报表期
        for item in ['operating_cash_flow', 'capex']:
            item_data = core.get(item, {})
            period = item_data.get('report_period')
            if period:
                periods.append((item, period))

        # 检查所有报表期是否一致
        if periods:
            unique_periods = set(period for _, period in periods)
            if len(unique_periods) > 1:
                self.errors.append(
                    f"[TIMING] 核心数据报表期不一致: {unique_periods}"
                )
            else:
                print(f"   [PASS] 核心数据报表期一致: {list(unique_periods)[0]}")

    def _validate_cash_data(self):
        """校验现金数据（S级强制）"""
        meta = self.data.get('analysis_metadata', {})
        report_type = meta.get('report_type', 'annual')
        level_label = "S级" if report_type == 'annual' else "B级"
        print(f"\n[2] 现金数据校验（{level_label}）")

        cash = self.data.get('core_financial_data', {}).get('cash_and_bank_balances', {})

        # 检查置信度（中报数据允许B级）
        expected_confidence = 'S' if report_type == 'annual' else 'B'
        if cash.get('confidence') != expected_confidence:
            if report_type == 'annual':
                self.errors.append("[CASH] 现金数据必须是S级（年报原文）")
            else:
                self.errors.append(f"[CASH] 中报/季报数据必须是B级（当前：{cash.get('confidence', '未标注')}）")

        # 检查来源
        source = cash.get('source', '')
        if report_type == 'annual':
            # 年报数据必须来自年报原文
            if not source or 'annual_report' not in source:
                self.errors.append("[CASH] 现金数据必须来自年报原文（source字段必须包含annual_report）")
        else:
            # 中报/季报数据必须来自相应报告
            if not source or ('interim_report' not in source and 'quarter_report' not in source):
                self.errors.append("[CASH] 非年报数据必须标注来源（source字段应包含interim_report或quarter_report）")
        
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

        # 检查报表期（新增）
        if not cash.get('report_period'):
            self.warnings.append("[CASH] 建议标注现金数据的报表期")
        
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
        
        # 检查报表期（新增）
        components = ['short_term', 'long_term', 'bonds', 'lease_liabilities']
        for comp in components:
            comp_data = debt.get(comp, {})
            if comp_data.get('value', 0) > 0 and not comp_data.get('report_period'):
                self.warnings.append(f"[DEBT] {comp}有数值但未标注报表期")

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
        
        # 检查报表期（新增）
        for item in [revenue, profit]:
            if item.get('value', 0) > 0 and not item.get('report_period'):
                self.warnings.append(f"[PROFIT] {item.get('display_unit', '数据')}未标注报表期")

        if not any(e for e in self.errors if e.startswith('[PROFIT]')):
            print(f"   [PASS] 利润数据校验通过")
    
    def _validate_cashflow_data(self):
        """校验现金流数据（S级强制）"""
        meta = self.data.get('analysis_metadata', {})
        report_type = meta.get('report_type', 'annual')
        level_label = "S级" if report_type == 'annual' else "B级"
        print(f"\n[5] 现金流数据校验（{level_label}）")

        core = self.data.get('core_financial_data', {})
        ocf = core.get('operating_cash_flow', {})
        capex = core.get('capex', {})

        # 检查经营现金流置信度（中报数据允许B级）
        expected_confidence = 'S' if report_type == 'annual' else 'B'
        if ocf.get('confidence') != expected_confidence:
            if report_type == 'annual':
                self.errors.append("[CASHFLOW] 经营现金流必须是S级")
            else:
                self.errors.append(f"[CASHFLOW] 中报/季报经营现金流必须是B级（当前：{ocf.get('confidence', '未标注')}）")

        if not ocf.get('verification_checked', False):
            self.errors.append("[CASHFLOW] 必须勾选确认经营现金流已核查")
        
        # 检查资本开支（即使为0也要明确）
        if 'value' not in capex:
            self.errors.append("[CASHFLOW] 必须明确填写资本开支（即使为0）")
        
        # 检查报表期（新增）
        for item in [ocf, capex]:
            if 'value' in item and not item.get('report_period'):
                self.warnings.append(f"[CASHFLOW] {'经营现金流' if item is ocf else '资本开支'}未标注报表期")

        if not any(e for e in self.errors if e.startswith('[CASHFLOW]')):
            print(f"   [PASS] 现金流数据校验通过")

    def _validate_valuation_data(self):
        """校验估值方法适用性和TTM四季度数据（V5.5.23）"""
        print("\n[4.5] 估值适用性与TTM校验")

        meta = self.data.get('analysis_metadata', {})
        policy = meta.get('valuation_policy')
        if not policy:
            self.warnings.append("[VALUATION] 未声明valuation_policy，无法确认主估值方法和PE适用性")
            return

        primary_method = policy.get('primary_method', '')
        if primary_method not in {'PE', 'PB', 'DPU_FFO', 'MID_CYCLE', 'PS', 'PROBABILITY_WEIGHTED'}:
            self.errors.append("[VALUATION] primary_method必须是PE/PB/DPU_FFO/MID_CYCLE/PS/PROBABILITY_WEIGHTED之一")

        if not policy.get('price_as_of'):
            self.errors.append("[VALUATION] 必须填写股价基准日price_as_of")
        if not policy.get('fx_as_of'):
            self.errors.append("[VALUATION] 必须填写汇率日期fx_as_of")

        if not policy.get('pe_applicable', False):
            print(f"   [PASS] PE不适用，主估值方法: {primary_method or '未填写'}")
            return

        core = self.data.get('core_financial_data', {})
        quarters = core.get('ttm_quarters', [])
        if len(quarters) != 4:
            self.errors.append(f"[VALUATION] PE适用时TTM必须填写4个季度，当前为{len(quarters)}个")
            return

        for index, quarter in enumerate(quarters, 1):
            if not quarter.get('period'):
                self.errors.append(f"[VALUATION] TTM第{index}个季度缺少period")
            if quarter.get('value') is None:
                self.errors.append(f"[VALUATION] TTM第{index}个季度缺少value")
            if not quarter.get('source'):
                self.errors.append(f"[VALUATION] TTM第{index}个季度缺少source")
            if not quarter.get('page_number'):
                self.warnings.append(f"[VALUATION] TTM第{index}个季度缺少page_number，若来源不是年报请填写公告日期/章节")

        ttm_total = sum((quarter.get('value') or 0) for quarter in quarters)
        metrics = core.get('calculated_metrics', {})
        ttm_profit = metrics.get('ttm_net_profit', {}).get('value')
        if ttm_profit is not None and abs(ttm_total - ttm_profit) > 0.01:
            self.errors.append(f"[VALUATION] TTM净利润错误: 四季度合计{ttm_total}，但填写为{ttm_profit}")

        print(f"   [PASS] TTM四季度数据已填写，总额: {ttm_total:,.2f}")
    
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

            # 数据时效性检查（新增）
            if item.get('id') == 'data_freshness' and item.get('checked', False):
                # 检查是否使用非年报数据
                meta = self.data.get('analysis_metadata', {})
                report_type = meta.get('report_type', 'annual')
                if report_type != 'annual':
                    if not item.get('freshness_explanation'):
                        self.warnings.append(
                            "[CHECKLIST] 使用非年报数据（中报/季报），建议填写解释原因"
                        )
        
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
