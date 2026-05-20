#!/usr/bin/env python3
"""MedHarness 客户化向导

> 用法：python tools/customize.py
> 作用：交互式问答 → 生成 .memory/项目档案.md / .claude/settings.json 覆写 / 选择性 Skill 子集

不可逆：会写入 .medharness-customized 标记文件，二次运行需要 --force 重置。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEMORY_TEMPLATE = ROOT / ".memory" / "项目档案.md"
MEMORY_FILE = ROOT / ".memory" / "项目档案.local.md"
SETTINGS_FILE = ROOT / ".claude" / "settings.json"
MARKER = ROOT / ".medharness-customized"


COMPANY_TYPES = {
    "1": "医疗数据 SaaS",
    "2": "互联网医院",
    "3": "数据中台",
    "4": "药企 CRO",
    "5": "医院信息部",
    "6": "其他",
}

COMPLIANCE_FRAMEWORKS = {
    "1": ["HIPAA"],
    "2": ["PIPL", "数据安全法", "健康医疗数据安全指南"],
    "3": ["HIPAA", "PIPL", "数据安全法", "健康医疗数据安全指南"],
}

MODELS = {
    "1": "Claude Opus 4.7",
    "2": "DeepSeek V4-Pro (公共 API)",
    "3": "DeepSeek V4-Pro (私有部署)",
    "4": "Qwen 32B (本地)",
    "5": "其他",
}


def ask(prompt: str, choices: dict[str, str] | None = None, default: str | None = None) -> str:
    while True:
        if choices:
            print(f"\n{prompt}")
            for k, v in choices.items():
                print(f"  {k}) {v}")
            default_hint = f" [{default}]" if default else ""
            answer = input(f"选项{default_hint}: ").strip() or (default or "")
            if answer in choices:
                return choices[answer]
            print("无效选项，请重试。")
        else:
            default_hint = f" [{default}]" if default else ""
            answer = input(f"{prompt}{default_hint}: ").strip() or (default or "")
            if answer:
                return answer


def banner() -> None:
    print("=" * 60)
    print(" MedHarness 客户化向导 · v0.1.0")
    print("=" * 60)
    print("\n问 8 个问题，5 分钟生成你的项目档案。\n")


def check_marker(force: bool) -> None:
    if MARKER.exists() and not force:
        print("\n⚠️  本仓库已被 customize.py 客户化过。")
        print(f"   标记文件：{MARKER}")
        print("   如需重置：python tools/customize.py --force\n")
        sys.exit(1)


def collect() -> dict:
    answers: dict = {}
    answers["project_name"] = ask("1. 项目名（英文 + 数字，将出现在 repo / Skill description 中）",
                                   default="my-medharness-project")
    answers["company_type"] = ask("2. 公司类型", COMPANY_TYPES, default="1")
    answers["team_size"] = ask("3. 团队规模（数字）", default="20")
    answers["compliance"] = COMPLIANCE_FRAMEWORKS[
        ask("4. 主合规框架", {"1": "仅 HIPAA", "2": "仅 PIPL 系", "3": "HIPAA + PIPL 双合规"}, default="3")
    ]
    answers["residency"] = ask("5. 数据驻留",
                                {"1": "境内 only", "2": "境内 + 境外可分流"}, default="1")
    answers["model_main"] = ask("6. 编码主力模型", MODELS, default="1")
    answers["model_compliance"] = ask("7. 合规 Agent 模型（必须与编码主力**异构**）", MODELS, default="2")
    answers["phase"] = ask("8. 当前阶段（M1-M6）", default="M1")
    answers["timestamp"] = datetime.now(timezone.utc).isoformat()
    return answers


def write_memory(answers: dict) -> None:
    # 读模板，写到 .local.md（已 gitignore，防止 fork 用户把私有配置 commit）
    template = MEMORY_TEMPLATE.read_text(encoding="utf-8")
    replacements = {
        r"项目名：<your-project-name>": f"项目名：{answers['project_name']}",
        r"公司类型：医疗 SaaS / 数据中台 / 互联网医院 / 药企 CRO / 其他":
            f"公司类型：{answers['company_type']}",
        r"团队规模：__ 人": f"团队规模：{answers['team_size']} 人",
        r"主合规框架：HIPAA / PIPL / 数据安全法 / 健康医疗数据安全指南":
            f"主合规框架：{' + '.join(answers['compliance'])}",
        r"数据驻留：境内 only / 境内\+境外可分流": f"数据驻留：{answers['residency']}",
        r"\| 编码主力 \| ____ \| 公共 API / 私有 \|":
            f"| 编码主力 | {answers['model_main']} | 见上 |",
        r"\| 合规 Agent（异构 · 必填） \| ____ \| 同 \|":
            f"| 合规 Agent（异构 · 必填） | {answers['model_compliance']} | 见上 |",
        r"当前月：M__": f"当前月：{answers['phase']}",
    }
    for old, new in replacements.items():
        template = re.sub(old, new, template, count=1)
    MEMORY_FILE.write_text(template, encoding="utf-8")
    print(f"✅ 已写入 {MEMORY_FILE.relative_to(ROOT)}")


def warn_heterogeneity(answers: dict) -> None:
    if answers["model_main"] == answers["model_compliance"]:
        print("\n🚨 合规警告：编码主力 与 合规 Agent 模型**相同**！")
        print("   异构性强制要求两者不同厂商家族。")
        print("   请重新运行向导或手动改 .memory/项目档案.md")
        sys.exit(2)


def write_marker(answers: dict) -> None:
    MARKER.write_text(
        json.dumps({"customized_at": answers["timestamp"],
                    "project_name": answers["project_name"]},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"✅ 标记文件 {MARKER.relative_to(ROOT)} 已生成")


def next_steps(answers: dict) -> None:
    print("\n" + "=" * 60)
    print(" 下一步")
    print("=" * 60)
    print(f"""
1. 跑 dryrun：
   bash dryrun_e2e_v2.sh

2. 阅读项目档案：
   cat .memory/项目档案.md

3. 看示例 change：
   cat examples/示例-患者匹配最小可行版/proposal.md

4. 你的第一个 change：
   - 改 .memory/项目档案.md 填完 5/6 项剩余内容
   - 跑 .claude 中的 compliance-precheck Skill
""")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="覆盖已客户化的仓库")
    args = parser.parse_args()
    check_marker(args.force)
    banner()
    answers = collect()
    warn_heterogeneity(answers)
    write_memory(answers)
    write_marker(answers)
    next_steps(answers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
