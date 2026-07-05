# CC-Boost

> 给 Claude Code 装上持久记忆和行为惯性的 Hook 增强系统。

---

## 这是什么

CC-Boost 是一组 **Hook 脚本** + **Skill** + **架构方案**，解决 Claude Code 在**长期陪伴聊天**场景下的核心痛点：

- 模型没有时间感知 → 每轮自动注入当前日期 + 跨夜检测
- CLAUDE.MD规则写了不执行 → 通过 `additionalContext` 每轮注入行为定律
- 记忆写了不读 → ChromaDB 语义检索 + 自动注入相关记忆到上下文
- 记忆不校验 → 写入后自动校验 YAML 格式/日期/冲突
- 纠偏靠人肉 → 系统自动完成

## 架构

```
用户发消息
  ↓
UserPromptSubmit hook → memory_inject.py
  ├─ 时间注入（绝对日期 + 跨夜检测 + 过期声明）
  ├─ ChromaDB 语义检索（相关记忆注入上下文）
  └─ 行为规则注入（五条铁律）
  ↓
模型收到：系统提示词 + <行为规则> + <记忆上下文> + 用户消息
  ↓
模型回答
  ↓
PostToolUse hook → self_check.py + index_sync.py
```

## 文件结构

```
├── hooks/                          # Hook 脚本（核心）
│   ├── memory_inject.py            # UserPromptSubmit：记忆注入 + 时间 + 规则
│   ├── memory_index.py             # CLI：构建/查询/统计 ChromaDB 索引
│   ├── index_sync.py               # PostToolUse：写入后重建索引
│   ├── self_check.py               # PostToolUse：写入格式校验
│   └── memory_extract.py           # [待启用] 对话日志记忆提取
├── skills/                         # 用户侧技能
│   ├── rusure/                     # /rusure — 质疑验证
│   ├── wm/                         # /wm — 记忆写入/删除
│   └── pre-compact/                # /pre-compact — 压缩前整理
├── docs/                           # 文档
│   ├── SUMMARY.md                  # 项目总纲（新手必读）
│   ├── AGENT-ROLES.md              # Agent 角色与分工
│   └── project-inventory.md        # 完整文件清单
└── README.md                       # 本文件
```

## 快速上手

### 1. 配置项目

在你的 Claude Code 项目（如 `~/my-chat-project/`）下创建 `.claude/settings.json`：

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/cc-boost/hooks/memory_inject.py",
            "timeout": 16384
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/cc-boost/hooks/index_sync.py",
            "timeout": 1000
          }
        ]
      }
    ]
  }
}
```

> 如果你需要记忆写入校验，在 PostToolUse 中增加 `self_check.py`。

### 2. 装依赖

```bash
pip install chromadb fastembed
```

ChromaDB + bge-small-zh-v1.5 自动下载，本地运行，不上传数据。

### 3. 创建记忆目录

```bash
mkdir -p ~/.claude/projects/terminal-partner/memory/
```

在 `memory/` 下写 `.md` 文件作为记忆库。索引构建：

```bash
python3 /path/to/cc-boost/hooks/memory_index.py build
```

### 4. 安装 Skill（可选）

将 `skills/` 下的 SKILL.md 复制到 `~/.claude/skills/<name>/`：

```bash
cp -r skills/rusure ~/.claude/skills/rusure
cp -r skills/wm ~/.claude/skills/wm
cp -r skills/pre-compact ~/.claude/skills/pre-compact
```

## 原理

**为什么不用 Auto Memory？**

Claude Code 的 Auto Memory 是文件级笔记系统——在会话开始时把 `MEMORY.md` 前 200 行的description字段塞进上下文，其他文件等 Claude 自己去 Read。对于代码场景够用，但陪伴聊天是动态的，模型在聊天节奏下不会主动去翻目录，命中率不到 10%。

**Hook 解决什么？**

在特定事件点插入自动脚本，把"应该做的事"从模型自觉变成系统默认路径：

- `UserPromptSubmit` → 每次用户输入后，自动注入时间和相关记忆
- `PostToolUse` → 每次文件写入后，自动校验 + 重建向量索引

**向量数据库（ChromaDB）**

把记忆文件转成向量（bge-small-zh-v1.5，本地运行），语义检索，不依赖关键词匹配。"我想买个电脑"和"最近在看笔记本配置"在向量空间里彼此靠近。

## 设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| 语义检索 | ChromaDB + bge-small-zh-v1.5 | 本地运行，不上传数据 |
| 记忆存储 | 文件 + ChromaDB 双写 | 文件可读可改，向量库供检索 |
| 约束机制 | Hook additionalContext | 每轮强制执行，不依赖模型自觉 |
| 项目分离 | 运行时检测 $PWD | 不同项目可挂不同记忆池 |

## License

MIT
