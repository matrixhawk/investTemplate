#!/usr/bin/env python3
"""审计分析报告的模板版本和最小输出契约。"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "analysis-reports"
VERSION_FILE = ROOT / "config" / "template-version.yaml"
VERSION_PATTERN = re.compile(r"V5\.5\.\d+")
R6_REVISION_PATTERN = re.compile(
    r"(?:2026-09-06-r6|V5\.5\.24-r6)",
    re.IGNORECASE,
)
R7_REVISION_PATTERN = re.compile(
    r"(?:2026-10-10-r7|V5\.5\.24-r7)",
    re.IGNORECASE,
)


@dataclass
class ReportAudit:
    path: Path
    version: str | None
    current: bool
    errors: list[str] = field(default_factory=list)


REQUIRED_PATTERNS = {
    "一句话结论": re.compile(r"^\s*>?\s*\*\*一句话结论\*\*：", re.MULTILINE),
    "主框架": re.compile(r"\|\s*主框架\s*\|"),
    "上市板块": re.compile(r"\|\s*上市板块\s*\|"),
    "流程状态": re.compile(r"\|\s*流程状态\s*\|"),
    "股东关系": re.compile(r"\|\s*股东关系\s*\|"),
    "数据截止日": re.compile(r"数据截止日"),
    "股价基准日": re.compile(r"股价基准日"),
    "建议仓位上限": re.compile(r"建议仓位上限"),
    "下次复核日": re.compile(r"下次复核日"),
    "证伪条件": re.compile(r"证伪条件"),
    "税前股息率": re.compile(r"税前股息率"),
    "FCF/市值": re.compile(r"FCF\s*/\s*(?:当前)?市值|FCF收益率|FCF 收益率", re.IGNORECASE),
    "市值/FCF": re.compile(r"市值\s*/\s*FCF", re.IGNORECASE),
    "跨期平均FCF": re.compile(r"(?:两年|三年|跨期|多年).{0,12}(?:平均|均值)?.{0,8}FCF|平均\s*FCF", re.IGNORECASE),
    "即时净现金/市值": re.compile(r"即时净现金\s*/\s*市值|即时净现金.{0,20}占.{0,8}市值"),
    "广义净现金": re.compile(r"广义净现金"),
    "审慎即时净现金": re.compile(r"审慎即时净现金"),
    "现金可动用性": re.compile(r"随时可动用|立即动用|即时可用|现金可动用性"),
}

# These checks only establish that an r6 report has named sections/fields.
# Presence of a label does not validate the rate, sustainability, or decision.
R6_REQUIRED_TEXT_PATTERNS = {
    "税后股息率": re.compile(r"税后股息率"),
    "普通股息": re.compile(r"普通股息"),
    "特别股息": re.compile(r"特别股息"),
    "分红覆盖": re.compile(r"分红覆盖"),
    "两年不涨": re.compile(r"两年不涨"),
    "分红准入": re.compile(r"分红准入"),
}

R7_REQUIRED_TEXT_PATTERNS = {
    "盈利收益率": re.compile(r"盈利收益率"),
    "审慎净现金/市值": re.compile(r"审慎净现金\s*/\s*市值|审慎净现金.{0,20}市值"),
    "融资义务/市值": re.compile(r"融资性现金义务.{0,20}市值|融资义务.{0,20}市值"),
    "负债现金分类": re.compile(r"負債按現金屬性分類|负债按现金属性分类|負債分類|负债分类"),
}


def load_current_version() -> str:
    data = yaml.safe_load(VERSION_FILE.read_text(encoding="utf-8"))
    return data["template"]["id"]


def audit_report(path: Path, current_version: str) -> ReportAudit:
    text = path.read_text(encoding="utf-8")
    match = VERSION_PATTERN.search(text)
    version = match.group(0) if match else None
    audit = ReportAudit(path=path, version=version, current=version == current_version)

    if not audit.current:
        return audit

    nonempty_lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not nonempty_lines or not nonempty_lines[0].startswith("# "):
        audit.errors.append("首个非空行必须是H1标题")
    if len(nonempty_lines) < 2 or "**一句话结论**：" not in nonempty_lines[1]:
        audit.errors.append("H1后的首个正文行必须是一句话结论")

    for label, pattern in REQUIRED_PATTERNS.items():
        if not pattern.search(text):
            audit.errors.append(f"缺少{label}")

    # r6 is opt-in by explicit revision marker so existing reports can be
    # migrated on their normal review cycle.  This is a textual presence
    # check only; numerical and analytical quality require human/data checks.
    if audit.current and (
        R6_REVISION_PATTERN.search(text) or R7_REVISION_PATTERN.search(text)
    ):
        for label, pattern in R6_REQUIRED_TEXT_PATTERNS.items():
            if not pattern.search(text):
                audit.errors.append(f"缺少{label}")
    if audit.current and R7_REVISION_PATTERN.search(text):
        for label, pattern in R7_REQUIRED_TEXT_PATTERNS.items():
            if not pattern.search(text):
                audit.errors.append(f"缺少{label}")
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-current",
        action="store_true",
        help="当前版本报告数量为0时返回失败，适合发布前检查",
    )
    args = parser.parse_args()

    current_version = load_current_version()
    paths = sorted(REPORT_DIR.glob("*_投资分析报告.md"))
    audits = [audit_report(path, current_version) for path in paths]
    current = [audit for audit in audits if audit.current]
    legacy = [audit for audit in audits if not audit.current]
    invalid = [audit for audit in current if audit.errors]

    print(f"当前模板: {current_version}")
    print(f"报告总数: {len(audits)} | 当前版本: {len(current)} | 存量版本: {len(legacy)}")

    if legacy:
        versions: dict[str, int] = {}
        for audit in legacy:
            key = audit.version or "未标注"
            versions[key] = versions.get(key, 0) + 1
        summary = "、".join(f"{version}={count}" for version, count in sorted(versions.items()))
        print(f"存量版本分布: {summary}")

    for audit in invalid:
        print(f"[FAIL] {audit.path.name}: {'；'.join(audit.errors)}")

    if invalid:
        return 1
    if args.require_current and not current:
        print("[FAIL] 没有当前版本报告，不能宣称报告目录已按当前契约迁移")
        return 1

    print("[PASS] 当前版本报告均满足最小输出契约；存量报告已单独统计")
    return 0


if __name__ == "__main__":
    sys.exit(main())
