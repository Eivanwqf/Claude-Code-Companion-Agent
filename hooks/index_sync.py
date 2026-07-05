#!/usr/bin/env python3
"""
CC-Boost: 索引保持同步 hook + metadata 自动清理
=================================================
Hook 点: PostToolUse
匹配器: Edit|Write
作用: 检测 memory 文件写入后自动清理多余的 metadata，并同步 ChromaDB 索引。
"""

import json
import os
import sys

MEMORY_DIR_TP = os.path.expanduser("~/.claude/projects/terminal-partner/memory/")
MEMORY_DIR_IP = os.path.expanduser("~/.claude/projects/investment-partner/memory/")
INDEX_SCRIPT = os.path.expanduser("~/project-cc-boost/hooks/memory_index.py")
MEMORY_LOG = os.path.expanduser("~/.claude/memory-log.txt")


# ── metadata 清理函数 ────────────────────────────────────────────

def strip_metadata(content):
    """
    删除 YAML frontmatter 中的 metadata: 块（含缩进子字段）。
    返回修改后的内容，若没有 metadata 块则返回 None。
    """
    if not content.startswith("---"):
        return None

    end = content.find("---", 3)
    if end < 0:
        return None

    fm = content[3:end]
    body = content[end + 3 :]

    has_metadata = any(line.strip().startswith("metadata:") for line in fm.split("\n"))
    if not has_metadata:
        return None

    lines = fm.split("\n")
    new_lines = []
    in_metadata = False

    for line in lines:
        if line.strip().startswith("metadata:"):
            in_metadata = True
            continue
        if in_metadata:
            if line == "" or (line and line[0] not in (" ", "\t")):
                in_metadata = False
                new_lines.append(line)
            continue
        new_lines.append(line)

    new_fm = "\n".join(new_lines)
    body_stripped = body.lstrip("\n")
    leading_newlines = len(body) - len(body_stripped)
    body_sep = "\n" * max(1, leading_newlines)

    return f"---{new_fm}\n---{body_sep}{body_stripped}"


# ── 文件检测 ─────────────────────────────────────────────────────

def is_memory_file(filepath):
    try:
        return (os.path.realpath(filepath).startswith(os.path.realpath(MEMORY_DIR_TP))
                or os.path.realpath(filepath).startswith(os.path.realpath(MEMORY_DIR_IP)))
    except Exception:
        return False


def detect_project_from_path(filepath):
    real = os.path.realpath(filepath)
    if real.startswith(os.path.realpath(MEMORY_DIR_IP)):
        return "ip"
    if real.startswith(os.path.realpath(MEMORY_DIR_TP)):
        return "tp"
    return None


# ── 主逻辑 ──────────────────────────────────────────────────────

def main():
    try:
        input_data = json.load(sys.stdin)
    except Exception:
        input_data = {}

    tool_input = input_data.get("tool_input", {})
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except Exception:
            tool_input = {}

    filepath = tool_input.get("file_path", "")

    if not filepath or not is_memory_file(filepath):
        print(json.dumps({}), file=sys.stdout)
        sys.exit(0)

    # ── 清理多余的 metadata ──
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            original = f.read()
        cleaned = strip_metadata(original)
        if cleaned is not None:
            saved = len(original) - len(cleaned)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(cleaned)
            from datetime import datetime
            fname = os.path.basename(filepath)
            log_line = (
                f"{datetime.now().strftime('%Y-%m-%d %H:%M')}"
                f" | ⬡ 清理 | {fname} | 删除 metadata 块(省 {saved} chars)\n"
            )
            with open(MEMORY_LOG, 'a', encoding='utf-8') as f:
                f.write(log_line)
    except Exception:
        pass

    # ── 重建索引 ──
    project = detect_project_from_path(filepath)
    if project == "ip":
        col_name = "investment-memory"
        mem_dir = MEMORY_DIR_IP
    else:
        col_name = "terminal-partner-memory"
        mem_dir = MEMORY_DIR_TP

    import subprocess
    subprocess.Popen(
        [sys.executable, INDEX_SCRIPT, "build",
         "--collection", col_name,
         "--memory-dir", mem_dir],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    print(json.dumps({}), file=sys.stdout)
    sys.exit(0)


if __name__ == "__main__":
    main()
