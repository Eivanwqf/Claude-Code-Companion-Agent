# CC-Boost 项目全文件清单

> 完整盘点项目中所有文件、路径、作用范围。
> 最后更新：2026-07-05

---

## 一、项目目录

| 项目 | 路径 | 角色 | Hooks |
|------|------|------|-------|
| **TP**（主力） | `~/Terminal-Partner/` | 全能聊天陪伴 | ✅ 全开 |
| **IP**（投资） | `~/Investment-Partner/` | 投资分析 | ✅ 全开（独立记忆池） |
| **WP**（微信） | `~/Wechat-Partner/` | 微信桥接陪伴 | ❌ cc-connect 限制 |
| **CC-Boost**（开发） | `~/project-cc-boost/` | 增强系统工作区 | — |

---

## 二、Hook 系统

### 2.1 Hook 脚本

所有脚本位于 `~/project-cc-boost/hooks/`：

| 脚本 | 挂载点 | 触发条件 | 作用 |
|------|--------|---------|------|
| `memory_inject.py` | `UserPromptSubmit` | 每次用户输入后 | 注入时间上下文 + ChromaDB 语义检索 + 五条铁律 |
| `index_sync.py` | `PostToolUse` | Edit/Write 操作后 | 自动重建 ChromaDB 索引 + 清理多余 metadata |
| `self_check.py` | `PostToolUse` | Edit/Write/MultiEdit 后 | 写入格式校验（YAML/日期/冲突检测） |
| `memory_index.py` | CLI 工具 | 手动调用 | 构建/查询/统计/重建向量索引 |
| `memory_extract.py` | CLI（未启用） | 手动调用 | 从对话日志提取记忆 |

### 2.2 Hook 配置（settings.json）

各项目 `settings.json` 中的 hooks 配置：

**TP** (`~/Terminal-Partner/.claude/settings.json`):
```json
UserPromptSubmit → memory_inject.py (timeout: 16384ms)
PostToolUse(Edit|Write) → index_sync.py (timeout: 1000ms)
```

**IP** (`~/Investment-Partner/.claude/settings.json`):
```json
UserPromptSubmit → memory_inject.py (timeout: 10000ms)
PostToolUse(Edit|Write|MultiEdit) → self_check.py (timeout: 3000ms)
PostToolUse(Edit|Write) → index_sync.py (timeout: 1000ms)
```

**WP** (`~/Wechat-Partner/.claude/settings.json`): 无 hooks

**全局** (`~/.claude/settings.json`): 无 hooks（只有环境变量 + 权限）

---

## 三、Memory 系统

### 3.1 记忆文件

| 项目 | 路径 | 文件数 |
|------|------|--------|
| **TP/WP（共享池）** | `~/.claude/projects/terminal-partner/memory/` | 22 |
| **IP（独立池）** | `~/.claude/projects/investment-partner/memory/` | 9 |

TP 记忆文件清单（含 MEMORY.md）：

```
behavior-trigger-chain.md   death-anxiety.md           english-proficiency.md
dad-car-story.md            feedback_emoji_usage.md    feedback_memory_write.md
first-mistress.md           ideal-type.md              investment-profile.md
life-chapter-2026-06.md     mental-health-journey.md   music.md
privacy-boundary.md         relationship-history.md    relationship-scoring-model.md
user-basics.md              user-finance.md            user-personality.md
windows-commands.md         workout-log.md             workout-plan.md
xuanxuan-ex-girlfriend.md   MEMORY.md
```

### 3.2 ChromaDB 向量索引

**数据路径：** `~/.chromadb/chroma.sqlite3`

| Collection | 记录数 | 属于 | 嵌入模型 |
|-----------|--------|------|---------|
| `terminal-partner-memory` | 22 | TP/WP | bge-small-zh-v1.5 |
| `investment-memory` | 9 | IP | bge-small-zh-v1.5 |

**模型缓存：** `~/.cache/fastembed/`（91MB，避免 /tmp 重启丢失）

### 3.3 记忆操作日志

**路径：** `~/memory-log.txt`
**格式：** `日期 | 图标 | 文件名 | 操作描述`
**记录：** 新建/追加/删除/清理 metadata 操作

---

## 四、CLAUDE.md 约束文件

| 级别 | 路径 | 作用范围 |
|------|------|---------|
| **全局用户** | `~/.claude/CLAUDE.md` | 所有项目通用规则 |
| **TP 项目** | `~/Terminal-Partner/CLAUDE.md` | TP 聊天规则 |
| **IP 项目** | `~/Investment-Partner/CLAUDE.md` | IP 规则 |
| **WP 项目** | `~/Wechat-Partner/CLAUDE.md` | WP 规则 |

---

## 五、Skills

所有 Skill 位于 `~/.claude/skills/`：

| 命令 | 路径 | 功能 |
|------|------|------|
| `/rusure` | `skills/rusure/SKILL.md` | 质疑验证：被质疑时执行事实验证 |
| `/wm` | `skills/wm/SKILL.md` | 记忆写入/删除：手动管理记忆文件 |
| `/guizang-ppt-skill` | `skills/guizang-ppt-skill/SKILL.md` | 杂志风网页 PPT 生成 |
| `/guizang-social-card-skill` | `skills/guizang-social-card-skill/SKILL.md` | 小红书/公众号社交卡片生成 |
| `/create-ex` | `skills/create-ex/SKILL.md` | 前任技能蒸馏 |
| `/ex-rollback` | `skills/ex-rollback/SKILL.md` | 前任技能回滚 |
| `/let-go` | `skills/let-go/SKILL.md` | 放下前任 |
| `/list-exes` | `skills/list-exes/SKILL.md` | 列出所有前任技能 |
| `/pre-compact` | `skills/pre-compact/SKILL.md` | 压缩前整理协议 |
| `/last30days` | `skills/last30days/SKILL.md` | 最近30天话题研究 |

---

## 六、项目文档

位于 `~/project-cc-boost/`：

| 文件 | 说明 | 重要度 |
|------|------|--------|
| `CC-Boost-SUMMARY.md` | 新 Agent 入职手册（项目总纲） | ⭐ 核心 |
| `CC-Boost-v0.2.md` | 架构文档（当前版本） | ⭐ 核心 |
| `AGENT-ROLES.md` | 各 Agent 配置速查表 | 有用 |
| `TO-RESOLVE.md` | 痛点跟踪 | 维护 |
| `PATHS.md` | 路径总览（过期，仅供参考） | 参考 |
| `BOOST-HANDOVER.md` | 项目任务书（原始需求） | 历史 |
| `CC-Boost-v0.1.md` | 旧版架构 | 历史 |
| `CC-Boost-v0.1.1.md` | 旧版架构 | 历史 |
| `CC-Boost-v0.1.2.md` | 旧版架构 | 历史 |
| `June-27-log.md` | 开发日志 | 历史 |
| `cc-boost-project.md` | 项目记忆（旧格式） | 历史 |
| `share-update.md` | 小红书分享文章 | TP 资产 |

---

## 七、TP 项目资产

| 文件 | 路径 |
|------|------|
| TP CLAUDE.md | `~/Terminal-Partner/CLAUDE.md` |
| TP settings.json | `~/Terminal-Partner/.claude/settings.json` |
| TP1 legacy | `~/Terminal-Partner/TP1-legacy.md` |
| Memory log | `~/memory-log.txt` |
| 分享文章 | `~/Terminal-Partner/share-update.md` |

---

## 八、cc-connect 微信桥接

**配置文件：** `~/.cc-connect/config.toml`
**工作目录：** `~/Wechat-Partner/`
**限制：** cc-connect 占用 stdio，无法挂载 hooks

---

## 九、会话日志（JSONL）

| 项目 | 路径 |
|------|------|
| TP | `~/.claude/projects/terminal-partner/` |
| IP | `~/.claude/projects/investment-partner/` |
| WP | `~/.claude/projects/wechat-partner/` |
| CC-Boost | `~/.claude/projects/cc-boost/` |

---

## 十、废弃路径（不再使用）

| 路径 | 说明 |
|------|------|
| `~/.claude/projects//user/memory/` | 旧 TP 记忆池，已迁移 |
| `~/.claude/projects//user/` | 旧 TP 会话日志，已切换 |
| `~/.chromadb/` | 旧 ChromaDB 路径，现已转移到 `~/.chromadb/` |
| `~/project-cc-boost/hooks/filter_ndd.py` | MessageDisplay 钩子脚本，已废弃删除 |
