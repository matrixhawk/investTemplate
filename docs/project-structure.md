# 项目结构说明

本项目只保留一套运行源。旧目录、历史模板和迁移前数据统一放在 `archive/`，不参与日常分析、脚本写入或网页构建。

## 当前目录结构

```text
investTemplate/
├── README.md                         # 项目入口与快速开始
├── AGENTS.md                         # AI助手当前有效约束
├── analysis-template.md              # 个股分析总入口
├── index.md                          # VitePress首页
├── package.json                      # 文档站点构建配置
│
├── template/                         # 当前分析模板
│   ├── 00-报告输出契约.md             # 新报告最小结构
│   ├── 01-数据核查与地缘政治排除.md
│   ├── 02-央国企筛选与流派识别.md
│   ├── 03-深度负债与周期分析.md
│   ├── 04-动态现金与周期拐点.md
│   ├── 05-极端情景测试.md
│   ├── 06-估值与安全边际.md
│   ├── 07-决策流程与持仓管理.md
│   ├── 08-高级烟蒂股分析框架.md
│   ├── 09-估值修复框架.md
│   ├── 10-特殊轻资产模式.md
│   ├── 11-ST*.md
│   ├── 12-扩张期消费品牌分析框架.md
│   └── 13-消费分层与AI时代防御框架.md
│
├── analysis-reports/                 # 个股分析报告唯一源
├── stock-tracking/                   # 标的跟踪唯一源
├── decision-tracking/                # 决策、模拟组合、VIX策略唯一源
│   └── vix_dca_strategy/
├── strategy-framework/               # 策略研究与回测输出
│
├── config/                           # YAML/JSON配置与数据校验输入
├── scripts/                          # 自动化脚本和校验工具
├── portfolio/                        # 网页展示用投资组合页面
├── public/                           # VitePress静态数据与资源
├── docs/                             # 项目说明、约束细则、变更日志
├── .vitepress/                       # VitePress站点配置
│
└── archive/                          # 只读历史和迁移备份，不作为运行源
    ├── templates/                    # 历史模板版本
    └── legacy/                       # 旧目录结构与迁移前副本
```

## 唯一真相源

| 内容 | 唯一路径 | 禁止继续使用 |
|------|----------|--------------|
| 当前模板 | `template/` | 旧版本模板、`archive/templates/` |
| 个股报告 | `analysis-reports/` | `07-分析输出/` |
| 决策与模拟组合 | `decision-tracking/` | `08-决策追踪/` |
| 标的跟踪 | `stock-tracking/` | `07-标的追踪/` |
| 策略研究 | `strategy-framework/` | `05-策略框架/` |
| 历史资料 | `archive/` | 不得被脚本读取或写入 |

## 常用入口

| 需求 | 路径 |
|------|------|
| 开始个股分析 | `analysis-template.md` |
| 新报告输出结构 | `template/00-报告输出契约.md` |
| 查看当前模板版本 | `config/template-version.yaml` |
| 校验财务数据 | `scripts/validate_data.py` |
| 查看个股报告 | `analysis-reports/` |
| 查看模拟组合 | `decision-tracking/` |
| 查看变更日志 | `docs/CHANGELOG.md` |
| 查看历史资料 | `archive/` |

## 目录使用规则

1. 新文件只能写入上表中的当前路径，不得新建带数字前缀的平行目录。
2. 脚本中的路径必须指向唯一真相源；不得为兼容旧目录继续双写。
3. 历史文件只能进入 `archive/`，不得混入当前报告、策略或决策数据目录。
4. 修改目录后必须运行 `npm run docs:build`，并运行相关数据校验脚本。
