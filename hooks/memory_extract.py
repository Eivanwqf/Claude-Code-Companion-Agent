#!/usr/bin/env python3
"""
CC-Boost: 对话记忆提取
=================================
用途: 从最近对话中提取值得记录的信息，写入记忆。

调用方式:
  - 作为 Stop hook（session 结束时自动触发）
  - 手动运行（./memory_extract.py --last N）

策略:
  - 纯规则匹配，不调用大模型
  - 扫描最新 N 轮对话，寻找：
    1. 用户明确表达的好恶（喜欢/不喜欢/觉得）
    2. 用户做的决定（决定/打算/计划）
    3. 行为反馈（纠偏信号）
    4. 新事件（今天/昨天/刚才发生了什么）
  - 去重：检查是否已有记忆覆盖同样主题
  - 输出：写入 memory 目录或输出建议
"""

import json
import os
import re
import sys
import glob
from datetime import datetime

# ── 配置 ──────────────────────────────────────────────────────────
MEMORY_DIR = os.path.expanduser("~/.claude/projects/terminal-partner/memory/")
SESSION_DIR = os.path.expanduser("~/.claude/projects/terminal-partner/")
MAX_EXCHANGES = 10  # 扫描最近多少轮对话
STAGING_FILE = os.path.join(MEMORY_DIR, "_pending_extract.json")


# ── 信号检测 ──────────────────────────────────────────────────────

# 用户表达偏好/好恶（中文）
PREFERENCE_PATTERNS = re.compile(
    r'(我喜欢|我不喜欢|我觉得|我感觉|我更[愿意喜欢倾向]|'
    r'我讨厌|我受不了|我接受不了|我不吃|我不碰|'
    r'我比较喜欢|我最喜欢|我最讨厌)'
)

# 用户做决定
DECISION_PATTERNS = re.compile(
    r'(我决定|我打算|我计划|我想试试|我准备|'
    r'我打定主意|我下决心|我选|我挑|我要开始|'
    r'从今天起|从下周开始|明天开始)'
)

# 行为反馈（纠偏信号）
FEEDBACK_PATTERNS = re.compile(
    r'(不对|错了|不是|你确定[吗么]|你又|'
    r'你每次都|你从来没|你老是|你怎么又|'
    r'你又在|你根本没|你没看|你没查|'
    r'记下来|记一下|记住|这个要记)'
)

# 新事件
EVENT_PATTERNS = re.compile(
    r'(今天.*(了|的)|昨天.*(了|的)|刚才.*(了|的)|'
    r'发生了|经历了|遇到了|收到了|完成了|'
    r'结束了|开始了|辞职|入职|面试|考试|'
    r'看病|吃药|检查|体检)'
)

# 情绪表达（可记录的情绪事件）
EMOTION_PATTERNS = re.compile(
    r'(心情不好|心情很[差糟烂]|崩溃|难受|'
    r'睡不着|失眠|焦虑|烦躁|开心|高兴|'
    r'激动|感动|难过|伤心|委屈)'
)


def scan_exchanges(jsonl_path, max_exchanges=MAX_EXCHANGES):
    """
    扫描 JSONL 文件，提取最近 N 轮对话。
    返回轮次列表，每轮含 user 和 assistant 消息。
    """
    if not os.path.exists(jsonl_path):
        return []

    exchanges = []
    current = {"user": "", "assistant": ""}
    try:
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                role = entry.get("role", "")
                content = entry.get("content", "")
                if not isinstance(content, str):
                    if isinstance(content, list):
                        # 处理 content 为数组的情况（tool_calls 等）
                        content = " ".join([
                            c.get("text", "") if isinstance(c, dict) else str(c)
                            for c in content
                        ])
                    else:
                        content = str(content)

                if role == "user":
                    if current["user"] or current["assistant"]:
                        exchanges.append(current)
                    current = {"user": content, "assistant": ""}
                elif role == "assistant":
                    current["assistant"] = content

        # 追加最后一轮
        if current["user"]:
            exchanges.append(current)

    except Exception:
        return []

    return exchanges[-max_exchanges:]


def extract_facts(exchanges):
    """
    从对话轮次中提取事实性信息。
    返回列表，每项为 (category, fact, source_quote, timestamp)
    """
    facts = []
    now = datetime.now().isoformat()

    for i, xchg in enumerate(exchanges):
        user_msg = xchg.get("user", "")

        # 偏好
        for m in PREFERENCE_PATTERNS.finditer(user_msg):
            # 提取整句
            start = max(0, m.start() - 30)
            end = min(len(user_msg), m.end() + 50)
            snippet = user_msg[start:end].strip()
            facts.append(("偏好", m.group(), snippet, now))

        # 决定
        for m in DECISION_PATTERNS.finditer(user_msg):
            start = max(0, m.start() - 20)
            end = min(len(user_msg), m.end() + 50)
            snippet = user_msg[start:end].strip()
            facts.append(("决定", m.group(), snippet, now))

        # 反馈
        for m in FEEDBACK_PATTERNS.finditer(user_msg):
            start = max(0, m.start() - 20)
            end = min(len(user_msg), m.end() + 50)
            snippet = user_msg[start:end].strip()
            facts.append(("反馈", m.group(), snippet, now))

        # 事件
        for m in EVENT_PATTERNS.finditer(user_msg):
            start = max(0, m.start() - 20)
            end = min(len(user_msg), m.end() + 50)
            snippet = user_msg[start:end].strip()
            facts.append(("事件", m.group(), snippet, now))

        # 情绪
        for m in EMOTION_PATTERNS.finditer(user_msg):
            start = max(0, m.start() - 20)
            end = min(len(user_msg), m.end() + 50)
            snippet = user_msg[start:end].strip()
            facts.append(("情绪", m.group(), snippet, now))

    return facts


def check_dedup(fact_snippet):
    """
    检查是否已有记忆覆盖相同内容。
    简单策略：检查 snippet 中的核心词是否出现在已有记忆中。
    """
    try:
        # 提取关键字符（3-5字片段）
        key_ngrams = set()
        text = fact_snippet
        for i in range(len(text) - 2):
            ngram = text[i:i+3]
            if re.match(r'[一-鿿]{3}', ngram):  # 3个连续中文字
                key_ngrams.add(ngram)

        if not key_ngrams:
            return False, []

        # 扫描现有记忆文件
        pattern = os.path.join(MEMORY_DIR, "*.md")
        matches = []
        for f in glob.glob(pattern):
            if f.endswith("_pending_extract.json") or os.path.basename(f) == "MEMORY.md":
                continue
            try:
                with open(f, 'r', encoding='utf-8') as fh:
                    content = fh.read()
                # 检查是否有足够多的 ngram 匹配
                hit_count = sum(1 for ng in key_ngrams if ng in content)
                if hit_count >= 3:
                    matches.append((os.path.basename(f), hit_count))
            except Exception:
                continue

        if matches:
            matches.sort(key=lambda x: -x[1])
            return True, matches
        return False, []

    except Exception:
        return False, []


def write_pending(facts):
    """将提取结果写入 staging 文件，供下次 session 使用。"""
    if not facts:
        return

    existing = []
    if os.path.exists(STAGING_FILE):
        try:
            with open(STAGING_FILE, 'r', encoding='utf-8') as f:
                existing = json.load(f)
        except Exception:
            existing = []

    existing.extend(facts)
    # 最多保留 50 条
    existing = existing[-50:]

    try:
        with open(STAGING_FILE, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def format_output(facts, dedup_skipped):
    """格式化成可读输出。"""
    if not facts:
        return None

    lines = ["📝 从最近对话中提取到以下值得记录的信息：\n"]

    for cat, trigger, snippet, ts in facts:
        date_str = datetime.fromisoformat(ts).strftime("%m-%d %H:%M")
        lines.append(f"[{cat}] {snippet}")
        lines.append(f"       触发词: \"{trigger}\" @ {date_str}")

    if dedup_skipped:
        lines.append(f"\n（已跳过 {dedup_skipped} 条与已有记忆重复的内容）")

    lines.append("\n💡 如需写入记忆，请使用 /commit-memory")
    return "\n".join(lines)


# ── 主入口 ────────────────────────────────────────────────────────

def main():
    # 检查是否作为 hook 运行（从 stdin 读）
    is_hook = not sys.stdin.isatty()

    if is_hook:
        try:
            input_data = json.load(sys.stdin)
        except Exception:
            input_data = {}
    else:
        # 手动运行模式
        input_data = {}

    # 获取最新 JSONL 文件
    try:
        pattern = os.path.join(SESSION_DIR, "*.jsonl")
        jsons = glob.glob(pattern)
        if not jsons:
            if not is_hook:
                print("未找到 session 日志")
            sys.exit(0)
        latest = max(jsons, key=os.path.getmtime)
    except Exception:
        sys.exit(0)

    # 扫描对话
    exchanges = scan_exchanges(latest, MAX_EXCHANGES)
    if not exchanges:
        sys.exit(0)

    # 提取
    raw_facts = extract_facts(exchanges)

    # 去重
    dedup_skipped = 0
    new_facts = []
    for fact in raw_facts:
        is_dup, matches = check_dedup(fact[2])
        if is_dup:
            dedup_skipped += 1
        else:
            new_facts.append(fact)

    # 写 staging
    if new_facts:
        write_pending(new_facts)

    # 输出
    output = format_output(new_facts, dedup_skipped)

    if is_hook:
        if output:
            # Stop hook 输出格式：systemMessage 或 reawakeMessage
            result = {
                "systemMessage": output
            }
            print(json.dumps(result, ensure_ascii=False), file=sys.stdout)
        else:
            print(json.dumps({}), file=sys.stdout)
    else:
        if output:
            print(output)
        else:
            print("未发现新的值得记录的信息。")

    sys.exit(0)


if __name__ == "__main__":
    main()
