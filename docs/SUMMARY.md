# CC-Boost 项目总纲

> 任何新 Agent 接手时，请先读此文件。
> 读完你就知道这个项目是什么、the user 是什么样的人、架构怎么跑、下一步能做什么。

---

## 一、这个项目是什么

CC-Boost 是一个 **Claude Code 增强系统**。它通过 hook + 向量数据库 + 行为规则注入，给 Claude Code 装上持久记忆和人格惯性。

目标：让用户每次打开 Claude Code，不需要重复介绍自己。模型已经知道他是什么样的人、喜欢什么沟通方式、遇过什么事、做过什么决定。

---

## 二、与用户的工作方式

- **沟通直接**：不客套，需要实话不是安慰。讨厌和稀泥和被糊弄。
- **纠偏信号**：他说"你确定吗"是让你去查记录，不是让你翻案。有支撑就站稳，没支撑才修正。
- **工作流**：方案文档 → 他评审 → 通过后开发 → 测试 → 迭代。
- **关键纪律**：改关键文件前先备份，改完后用 `diff` 对比确认只改了预期部分。
- **你的角色**：架构师兼核心开发者。这是一个真实软件项目，不是对话实验。

---

## 三、架构总览

```
你发消息
  ↓
UserPromptSubmit hook → memory_inject.py
  ├─ 时间注入（绝对日期 + 跨夜检测 + 过期声明）
  ├─ ChromaDB 语义检索（相关记忆，d<1.0 阈值）
  └─ 五条铁律注入（additionalContext）
  ↓
模型收到：系统提示词 + <行为规则> + <记忆上下文> + 你的消息
  ↓
模型回答（如有需要主动写记忆）
  ↓
PostToolUse hooks → self_check.py（格式校验）+ index_sync.py（重建索引）
```

### 三个关键概念

**Hook** — 在特定事件点自动运行的脚本。不靠模型自觉，系统替你做的事。
**additionalContext** — hook 注入到模型上下文的内容。不是系统提示词，以 `<system-reminder>` 块存在。
**ChromaDB** — 本地方向量数据库。把记忆文件转成向量，实现语义检索。

---

## 四、项目文件结构

```
~/project-cc-boost/                    ← 开发工作区
├── BOOST-HANDOVER.md                  ← 项目任务书（原始需求）
├── TO-RESOLVE.md                      ← 痛点清单
├── CC-Boost-v0.1.2.md                 ← 当前架构报告
├── AGENT-ROLES.md                     ← Agent 分工手册
├── June-27-log.md                     ← 开发日志
│
└── hooks/                             ← hook 脚本（核心）
    ├── memory_inject.py               ← 记忆注入 + 时间 + 五条铁律
    ├── self_check.py                  ← 写入校验（YAML/日期/冲突）
    ├── index_sync.py                  ← 写文件后重建 ChromaDB
    ├── memory_index.py                ← CLI：索引管理
    └── memory_extract.py              ← 记忆提取（待启用）

~/.claude/
├── settings.json                      ← 全局配置（无 hooks）
├── CLAUDE.md                          ← 通用规则
└── skills/rusure/SKILL.md             ← /rusure 质疑验证

~/Terminal-Partner/                    ← TP 项目（唯一有 hooks 的）
├── CLAUDE.md                          ← 聊天规则
└── .claude/settings.json              ← hooks 配置

~/Wechat-Partner/                      ← WP 项目（无 hooks）
├── CLAUDE.md                          ← 聊天规则
└── .claude/settings.json              ← 无 hooks

~/.cc-connect/config.toml              ← work_dir → Wechat-Partner
                                       ← ASP 三条精简规则

~/.chromadb/                    ← ChromaDB 向量索引（15条记录）
```

---

## 五、当前状态（v0.1.2）

### 已完成

| 功能 | 位置 | 说明 |
|------|------|------|
| 语义记忆检索 | `memory_inject.py` → ChromaDB | 每轮注入相关记忆 |
| 时间感知 | `build_time_context()` | 绝对日期 + 跨夜检测 + 过期声明 |
| 行为规则注入 | `BEHAVIOR_RULES` | 五条铁律每轮注入 |
| 写入校验 | `self_check.py` | YAML 格式/日期/冲突校验 |
| 索引同步 | `index_sync.py` | 写文件后自动重建 |
| 外部修改检测 | `_ensure_index_fresh()` | VSCode/shell 改后自动重建 |
| 质疑验证 | `/rusure` skill | 三路分支，全局可用 |
| WP 软链共享池 | `~/...Wechat-Partner/memory/` → 共享池 | WP 写 = TP 索引 |

### 未解决

| 痛点 | 说明 | 
|------|------|
| IP 项目接入 hooks + 向量库 | 投资场景需要独立 collection、数据规则、时间轴 |
| 自动记忆写入 | `memory_extract.py` 已写未启用，等记忆持久化方案 |
| 记忆持久化存储 | 当前文件+索引分布多个路径，需统一方案 |
| 聊天记录命名 | JSONL 文件名是 UUID，不可读 |
| 人格一致性 | 等持久化方案定下来 |

### 已知限制

1. **cc-connect 无法转发 hook 输出** — stdout 被 `--permission-prompt-tool stdio` 占用
2. **行为规则无法强制执行** — 模型对"关于规则的规则"存在天然衰减
3. **`additionalContext` 累积** — Issue #40216，每次追加不替换

---

## 六、Agent 分工

| Agent | 定位 | hooks | 记忆池 | 规则注入 |
|-------|------|-------|--------|---------|
| **TP** (Terminal) | 全能主力 | ✅ UserPromptSubmit + PostToolUse | 共享池 15条 | ✅ 五条铁律每轮 |
| **WP** (Wechat) | 随身陪伴 | ❌ cc-connect 限制 | 软链到共享池 | ⚠️ ASP 3条静态 |
| **IP** (Investment) | 投资分析 | ⏳ 待实现 | 待建独立池 | ⏳ 数据驱动 |
| **教学/代码** | 知识教授 | ❌ 不需要 | 无 | ❌ 走全局规则 |

---

## 七、关键设计决策（做过什么选择，为什么）

| 决策 | 选了什么 | 没选什么 | 为什么 |
|------|---------|---------|--------|
| 记忆存储 | 文件 + ChromaDB | cognee / Mem0 | 0 服务、0 依赖，当前规模够用 |
| 约束机制 | hook `additionalContext` | `systemMessage` / ASP | `systemMessage` 是 UI 通知，不喂模型 |
| 模型选择 | bge-small-zh-v1.5 (24M) | bge-large / OpenAI | 本地运行，不上传数据 |
| 项目分离 | 运行时检测 `$PWD` | 多份 settings.json | 避免项目级 hook 加载 bug |
| 行为规则 | 每轮注入 | 只放 CLAUDE.md | 防止衰减 |
| WP 记忆 | 软链共享池 | 独立池 | 确保 WP 写的内容 TP 能索引 |

---

## 八、给新 Agent 的接手指南

### 第一步：读文件

按顺序读：
1. 本文件（CC-Boost-SUMMARY.md）
2. BOOST-HANDOVER.md — 原始需求
3. TO-RESOLVE.md — 痛点清单
4. CC-Boost-v0.1.2.md — 架构细节
5. AGENT-ROLES.md — 各 Agent 分工

### 第二步：测试环境

```bash
cd ~/project-cc-boost
python3 hooks/memory_index.py stats    # 检查索引
echo '{"prompt":"测试"}' | python3 hooks/memory_inject.py | python3 -m json.tool  # 测 hook
```

### 第三步：摸清用户的风格

- 他直接、不客套，讨厌和稀泥
- "你确定吗"是纠偏信号，让你查记录不是翻案
- 他喜欢"方案对比→你推荐→他决策→你执行"的工作流
- 改关键文件前必须备份
- 改完后必须做 diff 对比，确认只改了预期部分

### 第四步：开始干活

当前最优先级：**IP 项目接入 hooks + 向量库**
需要先和用户讨论 IP 的记忆应该记什么、怎么分类，再动手实现。
