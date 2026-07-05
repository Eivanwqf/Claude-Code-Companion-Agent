#!/usr/bin/env python3
"""
CC-Boost: 记忆主动注入 hook
=================================
Hook 点: UserPromptSubmit
作用: 在每次用户输入后、模型处理前，自动注入相关记忆上下文。

协议:
  - 输入: stdin (JSON)，含用户 prompt
  - 输出: stdout (JSON)，含 additionalContext
  - 退出码: 始终 0（出错也不阻塞对话）

设计原则:
  - 使用 ChromaDB 语义检索（已安装时），降级到关键词匹配
  - 始终注入时间上下文
  - 出错时静默降级，不阻塞对话
"""

import json
import os
import re
import sys
import glob
from datetime import datetime

# ── 配置 ──────────────────────────────────────────────────────────
MEMORY_DIR_TP = os.path.expanduser("~/.claude/projects/terminal-partner/memory/")
CHROMA_DIR = os.path.expanduser("~/.chromadb/")
RECENT_COUNT = 3          # 始终附加最近修改的 N 条
# 实际上这个输出最近记忆就没有触发过，由于build_context_block 的 recent_items 参数传进去了也没被使用
# 实际可以查看main函数的ctx部分

MAX_RELEVANT = 5          # 最多附加 N 条相关记忆
SESSION_LOG_DIR = os.path.expanduser("~/.claude/projects/terminal-partner/")

# IP 项目配置
MEMORY_DIR_IP = os.path.expanduser("~/.claude/projects/investment-partner/memory/")
CHROMA_COLLECTION_IP = "investment-memory"
SESSION_LOG_DIR_IP = os.path.expanduser("~/.claude/projects/investment-partner/")

# 当前项目类型（由 main() 检测设置）
CURRENT_PROJECT = None

def detect_project():
    """检测当前在哪个项目下运行。"""
    cwd = os.getcwd()
    if "Terminal-Partner" in cwd or "Terminal-Partner" in os.environ.get("PWD", ""):
        return "tp"
    elif "Investment-Partner" in cwd or "Investment-Partner" in os.environ.get("PWD", ""):
        return "ip"
    return "other"


def get_memory_dir(project=None):
    if project is None:
        project = CURRENT_PROJECT
    return MEMORY_DIR_IP if project == "ip" else MEMORY_DIR_TP


def get_session_log_dir(project=None):
    if project is None:
        project = CURRENT_PROJECT
    return SESSION_LOG_DIR_IP if project == "ip" else SESSION_LOG_DIR


# ── 优先使用 ChromaDB 语义检索 ──────────────────────────────────


def _get_newest_file_mtime(memory_dir=None):
    """获取 memory 目录中最新的文件修改时间。"""
    import glob
    md = memory_dir or get_memory_dir()
    try:
        pattern = os.path.join(md, "*.md")
        files = glob.glob(pattern) + glob.glob(os.path.join(md, "archive", "*.md"))
        if not files:
            return 0
        return max(os.path.getmtime(f) for f in files if os.path.exists(f))
    except Exception:
        return 0


def _ensure_index_fresh(client, collection, memory_dir=None):
    """检查索引是否最新，必要时重建。"""
    try:
        file_mtime = _get_newest_file_mtime(memory_dir)
        if file_mtime == 0:
            return collection

        # 检查文件数是否匹配（处理删除情况）
        disk_count = 0
        md = memory_dir or get_memory_dir()
        for dirpath, _, filenames in os.walk(md):
            for fn in filenames:
                if fn.endswith(".md") and fn != "MEMORY.md":
                    disk_count += 1
        index_count = collection.count()

        all_data = collection.get(limit=index_count)
        index_mtime = 0
        for meta in (all_data.get("metadatas") or []):
            if meta and "mtime" in meta:
                try:
                    from datetime import datetime
                    mt = datetime.fromisoformat(meta["mtime"]).timestamp()
                    index_mtime = max(index_mtime, mt)
                except Exception:
                    pass

        if disk_count != index_count or file_mtime > index_mtime + 1:
            import subprocess, sys
            index_script = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "memory_index.py"
            )
            subprocess.Popen(
                [sys.executable, index_script, "build",
                 "--collection", collection.name,
                 "--memory-dir", memory_dir or get_memory_dir()],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass
    return collection


def try_chroma_query(query: str, n: int = MAX_RELEVANT, collection_name=None):
    """
    尝试使用 ChromaDB 语义检索。
    使用与索引相同的 fastembed 模型（BAAI/bge-small-zh-v1.5）。
    失败时返回 None（触发降级到关键词匹配）。
    """
    import importlib.util
    spec = importlib.util.find_spec("chromadb")
    if spec is None:
        return None

    try:
        import chromadb
        from chromadb.config import Settings
        from chromadb import Documents, EmbeddingFunction, Embeddings

        # 自定义 embedding 函数，用 fastembed 并匹配索引使用的模型
        class _FastEmbedQuery(EmbeddingFunction):
            def __init__(self):
                import os
                from fastembed import TextEmbedding
                cache_dir = os.path.expanduser("~/.cache/fastembed")
                os.makedirs(cache_dir, exist_ok=True)
                self._model = TextEmbedding(
                    model_name="BAAI/bge-small-zh-v1.5",
                    max_length=512,
                    cache_dir=cache_dir,
                )
            def __call__(self, input: Documents) -> Embeddings:
                return list(self._model.embed(input))

        client = chromadb.PersistentClient(
            path=CHROMA_DIR,
            settings=Settings(anonymized_telemetry=False),
        )
        ef = _FastEmbedQuery()

        try:
            col = collection_name or "terminal-partner-memory"
            collection = client.get_collection(col, embedding_function=ef)
        except (ValueError, chromadb.errors.NotFoundError):
            return None
        # 检查索引是否最新（兼容 VSCode/shell 直接修改）
        collection = _ensure_index_fresh(client, collection, get_memory_dir())


        if collection.count() == 0:
            return None

        results = collection.query(
            query_texts=[query],
            n_results=min(n, collection.count()),
        )

        if not results["ids"] or not results["ids"][0]:
            return None

        items = []
        for i, doc_id in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i] if results.get("metadatas") else {}
            distance = results["distances"][0][i] if results.get("distances") else 0
            items.append({
                "id": doc_id,
                "filename": meta.get("filename", f"{doc_id}.md"),
                "distance": distance,
                "preview": meta.get("preview", ""),
            })

        return items

    except Exception:
        return None


# ── 降级策略：关键词匹配 ────────────────────────────────────────

def extract_cjk(text):
    """提取文本中的中文字符。"""
    return [c for c in text if '一' <= c <= '鿿']


def get_file_description(filepath):
    """从 YAML frontmatter 提取 description 字段。"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            raw = f.read(800)
        if not raw.startswith('---'):
            return ""
        end = raw.find('---', 3)
        if end < 0:
            return ""
        fm = raw[3:end]
        for line in fm.split('\n'):
            line = line.strip()
            if line.startswith('description:'):
                val = line.split(':', 1)[1].strip()
                return val.strip('"\'')
    except Exception:
        pass
    return ""


def rank_by_relevance_fallback(user_message, files_with_mtime):
    """关键词匹配降级方案。"""
    scored = []
    user_tokens = [t for t in user_message.split() if len(t) > 0]
    user_cjk = set(extract_cjk(user_message))
    user_lower = user_message.lower()

    for filepath, mtime in files_with_mtime:
        basename = os.path.basename(filepath)
        stem = os.path.splitext(basename)[0].replace('-', ' ').replace('_', ' ')
        desc = get_file_description(filepath)

        score = 0

        # 文件名匹配
        stem_parts = stem.split()
        for part in stem_parts:
            if part and part.lower() in user_lower:
                score += 10

        # 描述匹配
        if desc:
            desc_lower = desc.lower()
            for token in user_tokens:
                if token and token.lower() in desc_lower:
                    score += 5
                    break
            else:
                desc_cjk = set(extract_cjk(desc))
                overlap = desc_cjk & user_cjk
                if overlap and len(overlap) >= len(desc_cjk) * 0.3:
                    score += 3

        scored.append((filepath, mtime, score, desc or stem))

    scored.sort(key=lambda x: (-x[2], -x[1]))
    return scored


# ── 时间上下文 ──────────────────────────────────────────────────

def get_last_session_time(session_dir=None):
    """获取最近一条 JSONL session 的修改时间。"""
    sd = session_dir or get_session_log_dir()
    try:
        pattern = os.path.join(sd, "*.jsonl")
        jsons = glob.glob(pattern)
        if not jsons:
            return None
        latest = max(jsons, key=os.path.getmtime)
        return os.path.getmtime(latest)
    except Exception:
        return None


def build_time_context(session_dir=None):
    """构造时间上下文块。"""
    now = datetime.now()
    lines = [f"当前时间: {now.strftime('%Y-%m-%d %A %H:%M')}"]

    last_mtime = get_last_session_time(session_dir)
    if last_mtime:
        last_dt = datetime.fromtimestamp(last_mtime)
        delta = now - last_dt
        if delta.total_seconds() > 7200:
            hours = int(delta.total_seconds() // 3600)
            if hours >= 24:
                days = hours // 24
                lines.append(f"距离上次对话已过 {days} 天（上次: {last_dt.strftime('%m-%d %H:%M')}）")
            else:
                lines.append(f"距离上次对话已过约 {hours} 小时（上次: {last_dt.strftime('%m-%d %H:%M')}）")

    # 加一条权威声明，帮助模型在累积的旧时间戳中分辨当前时间
    if len(lines) > 1:
        lines.append("（以上时间为当前实际时间，历史对话中出现的时间戳已过期）")

    return "\n".join(lines)


# ── 上下文组装 ──────────────────────────────────────────────────

def get_recent_files(n=RECENT_COUNT, memory_dir=None):
    """获取最近修改的 N 个文件。"""
    md = memory_dir or get_memory_dir()
    files = []
    for dirpath, _, filenames in os.walk(md):
        for fn in filenames:
            if fn.endswith(".md"):
                full = os.path.join(dirpath, fn)
                try:
                    files.append((full, os.path.getmtime(full)))
                except OSError:
                    continue
    files.sort(key=lambda x: x[1], reverse=True)
    return files[:n]


def build_context_block(relevant_items, recent_items, time_str):
    """组装 final additionalContext 块。"""
    parts = ["---"]
    parts.append(time_str)
    parts.append("")

    if relevant_items:
        parts.append("相关记忆(当注入的记忆文件相关度 >= 0.7 时，自动注入完整内容):")
        for item in relevant_items:
            if isinstance(item, dict):
                # ChromaDB item
                dist = item.get("distance", 0)
                sim = 1 - dist*dist/2
                preview = item.get("preview", "")[:256]
                line = f"- {item['filename']} (相关度: {sim:.2f}) — {preview}"

                # sim >= 0.7 时自动注入完整文件内容
                if sim >= 0.7:
                    fname = item['filename']
                    for mem_dir in (MEMORY_DIR_TP, MEMORY_DIR_IP):
                        fpath = os.path.join(mem_dir, fname)
                        if os.path.exists(fpath):
                            try:
                                with open(fpath, 'r', encoding='utf-8') as f:
                                    content = f.read()
                                # 剥离 frontmatter 后注入正文
                                body = content
                                if content.startswith('---'):
                                    end = content.find('---', 3)
                                    if end > 0:
                                        body = content[end+3:].strip()
                                line += f"\n   📄 {fname} 完整内容:\n{body[:2048]}"
                            except Exception:
                                pass
                            break

                parts.append(line)
            else:
                # Fallback item: (filepath, mtime, score, desc)
                fp, _, score, desc = item
                parts.append(f"- {os.path.basename(fp)} — {desc}")
        parts.append("")

    parts.append("---")
    return "\n".join(parts)


# ── 主入口 ────────────────────────────────────────────────────────

def main():
    global CURRENT_PROJECT  # ← 必须声明，否则 line 361 的赋值只是局部变量
    # 读取输入
    try:
        raw = sys.stdin.read()
        input_data = json.loads(raw) if raw else {}
    except Exception:
        input_data = {}

    # 提取用户消息
    user_message = ""
    if isinstance(input_data, dict):
        user_message = input_data.get("prompt", input_data.get("text", ""))
    if not isinstance(user_message, str):
        user_message = str(user_message) if user_message else ""

    # 检测项目类型
    project = detect_project()
    CURRENT_PROJECT = project  # ← 写回全局，确保 get_memory_dir() 无参调用时返回正确项目目录
    memory_dir = get_memory_dir(project)
    session_dir = get_session_log_dir(project)
    col_name = CHROMA_COLLECTION_IP if project == "ip" else "terminal-partner-memory"

    # 非 TP/IP 项目静默跳过
    if project == "other":
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ""}}), file=sys.stdout)
        sys.exit(0)

    # 时间上下文（始终注入）
    time_str = build_time_context(session_dir)

    # 获取最近文件
    recent_files = get_recent_files(memory_dir=memory_dir)

    # 语义检索 / 降级
    relevant = []
    used_chroma = False

    if user_message.strip():
        chroma_results = try_chroma_query(user_message, collection_name=col_name)
        if chroma_results is not None:
            relevant = chroma_results
            used_chroma = True
        else:
            # 降级到关键词匹配
            files_with_mtime = []
            for dirpath, _, filenames in os.walk(memory_dir):
                for fn in filenames:
                    if fn.endswith(".md"):
                        full = os.path.join(dirpath, fn)
                        try:
                            files_with_mtime.append((full, os.path.getmtime(full)))
                        except OSError:
                            continue
            files_with_mtime.sort(key=lambda x: x[1], reverse=True)
            scored = rank_by_relevance_fallback(user_message, files_with_mtime)
            relevant = [s for s in scored if s[2] > 0][:MAX_RELEVANT]

    # 相关性过滤：只保留有意义的结果（距离 < 1.0）
    if used_chroma and relevant:
        relevant = [r for r in relevant if r["distance"] < 1.0]

    # 最近文件去重
    if used_chroma:
        chroma_fnames = {r["filename"] for r in relevant}
        recent_filtered = []
        for fp, mtime in recent_files:
            if os.path.basename(fp) not in chroma_fnames:
                recent_filtered.append((fp, mtime))
        recent_items = recent_filtered[:RECENT_COUNT]
    else:
        fallback_paths = {r[0] for r in relevant}
        recent_filtered = [(fp, mt) for fp, mt in recent_files if fp not in fallback_paths]
        recent_items = recent_filtered[:RECENT_COUNT]

    # ── 规定 ──────────────────────────────────────────────
    BEHAVIOR_RULES = """## Terminal-Partner 聊天规则
1. **先查后说** — 输出内容前先查相关记录。不确定的东西不写，不编造。不确定的内容就调用网络搜索工具。
2. 永远不要输出"你说得对"这四个字。"""

    IP_BEHAVIOR_RULES = """## Investment-Partner 聊天规则
1. 数据必须联网核实：涉及行情、指数、宏观事件，必须使用 WebSearch 获取最新数据。严禁凭训练数据内存回答时效性问题。
2. 交叉验证：对持仓发表判断前，先查阅已有分析（holdings.json），确认新结论不矛盾。
3. 信息来源要求：引用外部资料必须标注来源（URL 或文件路径）；自己分析末尾写逻辑链。
4. 多维度思考：回答问题时要列出不同视角（bull case / bear case / 其他观点），不单边输出。
5. 主动扩展信息面：在用户当前认知基础上向外推一层：推荐可能不知道的知识、渠道、工具、对比标的、潜在风险。
6. 永远不说“你说得对”，用其他表达方式替换"""

    # 根据项目选择行为规则
    rules = IP_BEHAVIOR_RULES if project == "ip" else BEHAVIOR_RULES

    # 构造上下文（合并记忆 + 行为规则，全部走 additionalContext）
    ctx = build_context_block(relevant, recent_items, time_str)
    title = "记忆上下文" if used_chroma else "记忆上下文 (关键词匹配)"

    context_items = []
    # 行为规则（始终注入）
    context_items.append({"title": "行为规则", "content": f"---\n{rules}\n---"})
    # 记忆上下文
    context_items.append({"title": title, "content": ctx})

    # 合并为纯文本字符串（官方 UserPromptSubmit hook 格式）
    combined = f"--- {rules} ---\n\n{ctx}"
    out = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": combined,
        }
    }
    print(json.dumps(out, ensure_ascii=False), file=sys.stdout)
    sys.exit(0)


if __name__ == "__main__":
    main()
