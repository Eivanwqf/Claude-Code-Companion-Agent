#!/usr/bin/env python3
"""
CC-Boost: 记忆向量索引管理
=================================
管理 ChromaDB 中的记忆向量索引。

用法:
  python3 memory_index.py build    # 从现有 memory 文件构建/更新索引
  python3 memory_index.py query "用户消息"  # 查询相似记忆
  python3 memory_index.py stats    # 查看索引状态
"""

import argparse
import glob
import json
import os
import sys
import time
from datetime import datetime
from typing import List, Optional

import chromadb
from chromadb import Documents, EmbeddingFunction, Embeddings
from chromadb.config import Settings

# ── 配置 ──────────────────────────────────────────────────────────
MEMORY_DIR_TP = os.path.expanduser("~/.claude/projects/terminal-partner/memory/")
CHROMA_DIR = os.path.expanduser("~/.chromadb/")
COLLECTION_NAME = "terminal-partner-memory"


# ── 自定义 Embedding 函数 ────────────────────────────────────────

class FastEmbedWrapper(EmbeddingFunction):
    """将 fastembed 包装为 ChromaDB EmbeddingFunction。"""

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        from fastembed import TextEmbedding
        cache_dir = os.path.expanduser("~/.cache/fastembed")
        os.makedirs(cache_dir, exist_ok=True)
        self._model = TextEmbedding(model_name=model_name, max_length=512, cache_dir=cache_dir)
        self._model_name = model_name

    def __call__(self, input: Documents) -> Embeddings:
        # fastembed 返回生成器，转换为列表
        results = list(self._model.embed(input))
        return results


# ── 索引管理 ──────────────────────────────────────────────────────

def get_client() -> chromadb.ClientAPI:
    """获取 ChromaDB 客户端（持久化模式）。"""
    os.makedirs(CHROMA_DIR, exist_ok=True)
    client = chromadb.PersistentClient(
        path=CHROMA_DIR,
        settings=Settings(anonymized_telemetry=False),
    )
    return client


def get_or_create_collection(client: chromadb.ClientAPI, collection_name=COLLECTION_NAME):
    """获取或创建集合。"""
    ef = FastEmbedWrapper()
    try:
        collection = client.get_collection(collection_name, embedding_function=ef)
        print(f"  → 已有索引：{collection.count()} 条记录")
        return collection
    except (ValueError, chromadb.errors.NotFoundError):
        collection = client.create_collection(collection_name, embedding_function=ef)
        print(f"  → 创建新索引")
        return collection




def extract_preview(content):
    """从记忆文件内容中提取可读预览。
    
    策略：跳到 YAML frontmatter 的 description 字段，
    加上后续第一段有意义的内容。
    不依赖 frontmatter 格式完整性，容错。
    """
    desc = ""
    body_start = 0
    
    if content.startswith('---'):
        end_fm = content.find('---', 3)
        if end_fm > 0:
            fm = content[3:end_fm]
            body_start = end_fm + 3
            for line in fm.split('\n'):
                line = line.strip()
                if line.startswith('description:'):
                    val = line.split(':', 1)[1].strip()
                    desc = val.strip('"\'')
                    break
    
    # 取正文前 2 个非空行
    body_lines = []
    if body_start > 0:
        for line in content[body_start:].split('\n'):
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                body_lines.append(stripped[:80])
            if len(body_lines) >= 2:
                break
    
    parts = []
    if desc:
        parts.append(desc)
    for bl in body_lines:
        parts.append(bl)
    
    result = " — ".join(parts) if parts else content[:150].replace('\n', ' ').strip()
    return result[:300]

def read_memory_files(memory_dir=None):
    """读取所有 memory 文件，返回 (id, 内容, 元数据) 列表。"""
    files = []
    md = memory_dir or MEMORY_DIR_TP
    for dirpath, _, filenames in os.walk(md):
        for fn in filenames:
            if not fn.endswith(".md") or fn == "MEMORY.md":
                continue
            full = os.path.join(dirpath, fn)
            try:
                with open(full, 'r', encoding='utf-8') as f:
                    content = f.read()
                mtime = os.path.getmtime(full)
                # 从文件名生成 stable ID
                doc_id = os.path.splitext(fn)[0]
                # 提取 preview：description + 第一段正文要点
                preview = extract_preview(content)
                files.append({
                    "id": doc_id,
                    "content": content,
                    "metadata": {
                        "filename": fn,
                        "path": os.path.relpath(full, MEMORY_DIR_TP),
                        "mtime": datetime.fromtimestamp(mtime).isoformat(),
                        "size": len(content),
                        "preview": preview,
                    }
                })
            except Exception as e:
                print(f"  ⚠ 跳过 {fn}: {e}", file=sys.stderr)
    return files


def build_index(force: bool = False, collection_name=COLLECTION_NAME, memory_dir=None):
    """构建或更新向量索引。"""
    print("📦 构建记忆向量索引...")
    print(f"  记忆目录: {memory_dir or MEMORY_DIR_TP}")
    print(f"  索引目录: {CHROMA_DIR}")

    client = get_client()

    # 读取文件（在这之前获取现有索引状态）
    files = read_memory_files(memory_dir)
    print(f"  找到 {len(files)} 个记忆文件")

    if force:
        try:
            client.delete_collection(collection_name)
            print("  → 已删除旧索引")
        except (ValueError, chromadb.errors.NotFoundError):
            pass
        collection = get_or_create_collection(client, collection_name)
        existing_ids = set()
    else:
        collection = get_or_create_collection(client, collection_name)
        existing_ids = set(collection.get()["ids"]) if collection.count() > 0 else set()
        print(f"  已有 {len(existing_ids)} 条记录")

        # ── 清理：删除索引中已不存在的文件 ──
        disk_ids = {f["id"] for f in files}
        stale_ids = existing_ids - disk_ids
        if stale_ids:
            print(f"  - 清理 {len(stale_ids)} 条已删除的记录...")
            collection.delete(ids=list(stale_ids))
            existing_ids -= stale_ids
            print("    ✓ 已清除")

    # 需要新增的
    new_files = [f for f in files if f["id"] not in existing_ids]
    # 需要更新的（mtime 变了）
    update_files = []
    if not force:
        existing_data = collection.get() if existing_ids else {"metadatas": []}
        existing_meta = {m["filename"]: m for m in (existing_data.get("metadatas") or []) if m}
        for f in files:
            if f["id"] in existing_ids:
                old_meta = existing_meta.get(f["metadata"]["filename"], {})
                old_mtime = old_meta.get("mtime", "")
                if old_mtime != f["metadata"]["mtime"]:
                    update_files.append(f)

    if force:
        to_add = files
        to_update = []
    else:
        to_add = new_files
        to_update = update_files

    # 添加新文件
    if to_add:
        print(f"  + 新增 {len(to_add)} 条...")
        batch_size = 10
        for i in range(0, len(to_add), batch_size):
            batch = to_add[i:i + batch_size]
            collection.add(
                ids=[b["id"] for b in batch],
                documents=[b["content"] for b in batch],
                metadatas=[b["metadata"] for b in batch],
            )
        print(f"    ✓ 完成")

    # 更新已变更的文件
    if to_update:
        print(f"  ~ 更新 {len(to_update)} 条（内容已变更）...")
        for f in to_update:
            collection.update(
                ids=[f["id"]],
                documents=[f["content"]],
                metadatas=[f["metadata"]],
            )
        print(f"    ✓ 完成")

    total = collection.count()
    print(f"\n✅ 索引完成，共 {total} 条记录")

    return total


def query_index(query: str, n_results: int = 5, collection_name=COLLECTION_NAME):
    """查询与 query 最相似的记忆。"""
    client = get_client()
    ef = FastEmbedWrapper()

    try:
        collection = client.get_collection(collection_name, embedding_function=ef)
    except (ValueError, chromadb.errors.NotFoundError):
        print("❌ 索引不存在，请先运行 build")
        return []

    results = collection.query(
        query_texts=[query],
        n_results=min(n_results, collection.count()),
    )

    items = []
    for i in range(len(results["ids"][0])):
        items.append({
            "id": results["ids"][0][i],
            "distance": results["distances"][0][i] if results.get("distances") else None,
            "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
            "document": results["documents"][0][i][:200] if results.get("documents") else "",
        })

    return items


def show_stats(collection_name=COLLECTION_NAME):
    """显示索引统计。"""
    client = get_client()
    try:
        collection = client.get_collection(collection_name)
    except (ValueError, chromadb.errors.NotFoundError):
        print("❌ 索引不存在，请先运行 build")
        return

    count = collection.count()
    print(f"📊 索引统计")
    print(f"  记录数: {count}")
    print(f"  集合名: {collection_name}")
    print(f"  存储路径: {CHROMA_DIR}")

    if count > 0:
        data = collection.get(limit=count)
        print(f"\n  文件列表:")
        for i, meta in enumerate(data["metadatas"] or []):
            fn = meta.get("filename", "?")
            preview = meta.get("preview", "")[:60]
            mtime = meta.get("mtime", "")[:10]
            print(f"    {i+1}. {fn} ({mtime}) — {preview}...")


# ── CLI ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="CC-Boost 记忆索引管理")
    sub = parser.add_subparsers(dest="command")

    build_p = sub.add_parser("build", help="构建/更新索引")
    build_p.add_argument("--collection", default=COLLECTION_NAME, help="collection 名称（默认 terminal-partner-memory）")
    build_p.add_argument("--memory-dir", default=None, help="记忆目录路径（默认使用 MEMORY_DIR_TP 常量）")
    build_p.add_argument("--force", "-f", action="store_true", help="强制重建")

    query_p = sub.add_parser("query", help="查询相似记忆")
    query_p.add_argument("--collection", default=COLLECTION_NAME, help="collection 名称")
    query_p.add_argument("text", help="查询文本")
    query_p.add_argument("--top", "-n", type=int, default=5, help="返回条数")

    stats_p = sub.add_parser("stats", help="查看索引状态")
    stats_p.add_argument("--collection", default=COLLECTION_NAME, help="collection 名称")

    args = parser.parse_args()

    if args.command == "build":
        mem_dir = args.memory_dir if args.memory_dir else MEMORY_DIR_TP
        build_index(force=getattr(args, "force", False), collection_name=args.collection, memory_dir=mem_dir)
    elif args.command == "query":
        results = query_index(args.text, args.top, collection_name=args.collection)
        if results:
            print(f"🔍 查询: \"{args.text}\"")
            print(f"  集合: {args.collection}\n")
            for i, r in enumerate(results):
                md = r["metadata"]
                dist = r.get("distance", 0)
                sim = 1 - dist*dist/2 if dist else 0
                print(f"{i+1}. {md.get('filename', r['id'])} "
                      f"(距离: {dist:.4f}, 相似度: {sim:.3f})")
                print(f"   描述: {md.get('preview', '')[:100]}")
                print()
    elif args.command == "stats":
        show_stats(collection_name=getattr(args, "collection", COLLECTION_NAME))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
