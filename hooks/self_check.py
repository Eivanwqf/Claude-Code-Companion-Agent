#!/usr/bin/env python3
"""
CC-Boost: 后验自检 hook
=================================
Hook 点: PostToolUse
匹配器: Edit|Write|MultiEdit
作用: 在写入记忆文件后校验格式正确性，检测冲突。

协议:
  - 输入: stdin (JSON)，含工具调用详情
  - 输出: stdout (JSON)，含 additionalContext 或 systemMessage
  - 退出码: 始终 0（不阻塞对话）
"""

import json
import os
import re
import sys
import glob
from datetime import datetime

# ── 配置 ──────────────────────────────────────────────────────────
MEMORY_DIR = os.path.expanduser("~/.claude/projects/terminal-partner/memory/")
MEMORY_DIR_IP = os.path.expanduser("~/.claude/projects/investment-partner/memory/")


# ── 校验函数 ──────────────────────────────────────────────────────

def is_memory_file(filepath):
    """判断是否在 memory 目录内。"""
    try:
        real = os.path.realpath(filepath)
        mem_real = os.path.realpath(MEMORY_DIR)
        mem_ip_real = os.path.realpath(MEMORY_DIR_IP)
        return real.startswith(mem_real) or real.startswith(mem_ip_real)
    except Exception:
        return False


def check_yaml_frontmatter(content):
    """检查 YAML frontmatter 格式和必填字段。"""
    issues = []
    if not content.startswith('---'):
        issues.append("缺少 YAML frontmatter（应以 --- 开头）")
        return issues

    end = content.find('---', 3)
    if end < 0:
        issues.append("YAML frontmatter 未闭合（缺少结尾 ---）")
        return issues

    fm = content[3:end]

    # 检查必填字段
    has_name = False
    has_description = False
    has_type = False
    valid_types = ['user', 'feedback', 'project', 'reference']

    for line in fm.split('\n'):
        line = line.strip()
        if line.startswith('name:'):
            has_name = True
        if line.startswith('description:'):
            has_description = True
        if line.startswith('type:'):
            has_type = True
            val = line.split(':', 1)[1].strip().strip('"\'')
            if val not in valid_types:
                issues.append(f"type 字段值 '{val}' 不在有效范围 {valid_types}")

    if not has_name:
        issues.append("缺少 name 字段")
    if not has_description:
        issues.append("缺少 description 字段")
    if not has_type:
        issues.append("缺少 type 字段")

    return issues


def check_date_in_content(content):
    """检查内容中是否包含日期信息。"""
    # 查找 YYYY-MM-DD 格式的日期
    dates = re.findall(r'\d{4}-\d{2}-\d{2}', content)
    if not dates:
        return ["内容中未找到日期信息（建议标注日期）"]
    return []


def detect_conflicts(filepath, content):
    """检测与已有记忆文件的冲突。"""
    conflicts = []
    basename = os.path.basename(filepath)

    # 读取所有记忆文件的 name 字段
    pattern = os.path.join(MEMORY_DIR, "*.md")
    pattern_ip = os.path.join(MEMORY_DIR_IP, "*.md")
    mem_files = glob.glob(pattern) + glob.glob(pattern_ip)
    for f in mem_files:
        if os.path.basename(f) == basename:
            continue
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                fc = fh.read(500)
        except Exception:
            continue

        # 提取 name 字段
        if fc.startswith('---'):
            end = fc.find('---', 3)
            if end > 0:
                fm = fc[3:end]
                for line in fm.split('\n'):
                    line = line.strip()
                    if line.startswith('name:'):
                        other_name = line.split(':', 1)[1].strip().strip('"\'')
                        # 检查当前内容的 name 字段
                        if content.startswith('---'):
                            cend = content.find('---', 3)
                            if cend > 0:
                                cfm = content[3:cend]
                                for cline in cfm.split('\n'):
                                    cline = cline.strip()
                                    if cline.startswith('name:'):
                                        this_name = cline.split(':', 1)[1].strip().strip('"\'')
                                        if this_name and this_name == other_name:
                                            conflicts.append(
                                                f"name '{this_name}' 与 {os.path.basename(f)} 冲突"
                                            )
                        break

    return conflicts


# ── 主入口 ────────────────────────────────────────────────────────

def main():
    try:
        input_data = json.load(sys.stdin)
    except Exception:
        input_data = {}

    # 提取写入的文件路径
    tool_input = input_data.get("tool_input", {})
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except Exception:
            tool_input = {}

    filepath = tool_input.get("file_path", "")

    # 如果不是写 memory 文件，跳过
    if not filepath or not is_memory_file(filepath):
        print(json.dumps({}), file=sys.stdout)
        sys.exit(0)

    # 读取当前文件内容
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        print(json.dumps({}), file=sys.stdout)
        sys.exit(0)

    # 执行校验
    all_issues = []

    fm_issues = check_yaml_frontmatter(content)
    all_issues.extend(fm_issues)

    date_issues = check_date_in_content(content)
    all_issues.extend(date_issues)

    conflict_issues = detect_conflicts(filepath, content)
    all_issues.extend(conflict_issues)

    if not all_issues:
        print(json.dumps({}), file=sys.stdout)
        sys.exit(0)

    # 有 issues — 注入警告
    print(f"[self_check] {os.path.basename(filepath)}: {len(all_issues)} issue(s)", file=sys.stderr)

    warning_lines = [
        f"⚠️ 记忆文件 {os.path.basename(filepath)} 写入后发现以下问题：",
    ]
    for issue in all_issues:
        warning_lines.append(f"- {issue}")
    warning_lines.append("建议在后续操作中修正。")

    context = [{
        "title": "记忆写入校验",
        "content": "---\n" + "\n".join(warning_lines) + "\n---"
    }]

    print(json.dumps({"additionalContext": context}), file=sys.stdout)
    sys.exit(0)


if __name__ == "__main__":
    main()
