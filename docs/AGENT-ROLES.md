# CC-Boost Agent 角色手册

> 各 Agent 的定位、能力、记忆配置、hooks 参数。
> 后续新增 Agent 时在此追加。

---

## Hook 配置参数速查

所有钩子脚本同一份，通过 `detect_project()` 根据 `$PWD` 自动切换模式。

| 参数 | TP | TPM | IP | WP |
|------|----|-----|----|-----|
| **ChromaDB collection** | cc-boost-memory | cc-boost-memory | investment-memory | ❌ 无 |
| **记忆目录** | `terminal-partner/memory/` | `terminal-partner/memory/` | `investment-partner/memory/` | 软链到 TP |
| **BEHAVIOR_RULES 条数** | 5 条（铁律） | 5 条（铁律） | 6 条（数据规则） | ASP 3 条 |
| **时间注入** | ✅ `build_time_context()` | ✅ 同 TP | ✅ `build_time_context()` | ❌ |
| **写入校验** | ✅ self_check | ✅ 同 TP | ✅ self_check | ❌ |
| **索引同步** | ✅ index_sync | ✅ 同 TP | ✅ index_sync | ❌ |
| **会话日志** | `-Terminal-Partner/` | `-Terminal-Partner-Mobile/` | `-Investment-Partner/` | `-Wechat-Partner/` |

---

## 一、TP — Terminal Partner（终端陪伴）

### 定位
全能主力。日常陪伴、知识、代码、投资、情感。

### 能力
| 功能 | 说明 |
|------|------|
| 记忆注入 | ✅ ChromaDB (`cc-boost-memory`, 15 条) |
| 时间感知 | ✅ `build_time_context()` |
| 行为规则 | ✅ 5 条铁律每轮注入 |
| 主动写记忆 | ✅ 模型自觉 + self_check 校验 |
| 索引同步 | ✅ `index_sync.py` |
| 外部修改检测 | ✅ `_ensure_index_fresh()` |
| 质疑验证 | ✅ `/rusure` |

### 记忆配置
- **记忆池**：`~/.claude/projects/terminal-partner/memory/`（17 条）
- **索引**：`cc-boost-memory` collection（15 条）
- **会话日志**：`~/.claude/projects/terminal-partner/`
- **CLAUDE.md**：`~/Terminal-Partner/CLAUDE.md`

### 启动
```bash
cd ~/Terminal-Partner && claude
```

### BEHAVIOR_RULES（5 条，每轮注入）
1. 先查后说 — 不确定的不写不编造
2. 被反问时不改口 — 查记录站稳或修正
3. 信息来源规范 — 标来源写逻辑链
4. 先共情再分析 — 不转话锋
5. 变换肯定方式 — 不固定回"你说得对"

---

## 二、TPM — Terminal Partner Mobile（移动端终端）

### 定位
TP 的手机版。通过 SSH 手机连接 WSL2 运行，功能与 TP 完全一致。
日志与 TP 隔离，方便 `--resume` 区分。

### 能力
同 TP（继承 CLAUDE.md 软链 + settings.json 复制）

### 记忆配置
- **记忆池**：同 TP（共享）
- **索引**：同 TP（共享）
- **会话日志**：`~/.claude/projects/terminal-partner-Mobile/`
- **CLAUDE.md**：软链到 TP 的

### 待实现
- `memory_inject.py` 的 `detect_project()` 需添加 `Terminal-Partner-Mobile` 识别

---

## 三、WP — Wechat Partner（微信陪伴）

### 定位
随身陪伴。碎片时间轻量聊天。
hook 受 cc-connect 限制不可用，靠 ASP 静态规则兜底。

### 能力
| 功能 | 说明 |
|------|------|
| 记忆注入 | ❌ cc-connect stdio 限制 |
| 时间感知 | ❌ 靠 CLAUDE.md "记得 date" |
| 行为规则 | ⚠️ `append_system_prompt` 3 条精简版 |
| 主动写记忆 | ⚠️ 靠 autoMemory（软链到共享池） |
| 质疑验证 | ✅ `/rusure` |

### 记忆配置
- **记忆池**：`~/.claude/projects/terminal-partner/memory/`（软链到 TP 共享池）
- **会话日志**：`~/.claude/projects/wechat-partner/`
- **CLAUDE.md**：`~/Wechat-Partner/CLAUDE.md`
- **ASP**：`~/.cc-connect/config.toml` 中 `append_system_prompt`

### 启动
```bash
cc-connect  # 自动桥接，无需手动
```

### ASP 规则（3 条，静态，不衰减）
1. 先查后说 — 不确定的不写不编造
2. 被反问时不改口 — 查记录，有支撑就站稳
3. 先共情再分析 — 先共情不审判

---

## 四、IP — Investment Partner（投资伙伴）

### 定位
投资分析专家。数据驱动、多维度、时效优先。
**不阅读** WP 或个人记忆文件。

### 能力
| 功能 | 说明 |
|------|------|
| 记忆注入 | ✅ ChromaDB (`investment-memory`, 7 条) |
| 时间感知 | ✅ `build_time_context()` + 规则 #6 "时效性优先" |
| 行为规则 | ✅ 6 条数据规则每轮注入 |
| 主动写记忆 | ✅ 模型自觉 + self_check 校验 |
| 索引同步 | ✅ `index_sync.py` |
| 质疑验证 | ✅ `/rusure` |
| 数据隔离 | ✅ CLAUDE.md 限制（不读 WP/个人记忆） |

### 记忆配置
- **记忆池**：`~/.claude/projects/investment-partner/memory/`（7 条）
- **索引**：`investment-memory` collection（7 条）
- **会话日志**：`~/.claude/projects/investment-partner/`
- **CLAUDE.md**：`~/Investment-Partner/CLAUDE.md`

### 启动
```bash
cd ~/Investment-Partner && claude
```

### BEHAVIOR_RULES（6 条，每轮注入）
1. 数据必须联网核实 — 行情/指数必须 WebSearch
2. 交叉验证再开口 — 查已有分析再下结论
3. 信息来源规范 — 标来源写逻辑链
4. 多维度思考 — bull case / bear case 都要列
5. 主动扩展信息面 — 推荐不知道的渠道/工具
6. 时效性优先 — 涉及时间先 date

---

## 五、Knowledge — 教学伙伴

### 定位
学科教授。走全局 CLAUDE.md，无 hooks。

### 启动
```bash
cd ~/knowledge-xxx && claude
```

---

## 六、总览对比

| Agent | 定位 | ChromaDB | rules 注入 | 时间感知 | hooks | 日志路径 |
|-------|------|----------|-----------|---------|-------|---------|
| **TP** | 全能主力 | cc-boost(15条) | 5 条铁律 | ✅ | ✅ 全栈 | `-TP/` |
| **TPM** | TP 手机版 | 同 TP | 同 TP | ✅ | ✅ 全栈 | `-TP-Mobile/` |
| **WP** | 随身陪伴 | ❌ | ASP 3 条 | ❌ | ❌ | `-WP/` |
| **IP** | 投资分析 | invest(7条) | 6 条数据 | ✅ | ✅ 全栈 | `-IP/` |
| **教学** | 知识教授 | ❌ | 走全局 | ❌ | ❌ | 各自 |

---

## 七、附录：路径速查

```
settings.json（hooks）：
  TP:    ~/Terminal-Partner/.claude/settings.json          ✅ UserPromptSubmit + PostToolUse
  TPM:   ~/Terminal-Partner-Mobile/.claude/settings.json    ✅ 同 TP（待 detect_project 适配）
  IP:    ~/Investment-Partner/.claude/settings.json         ✅ UserPromptSubmit + PostToolUse
  WP:    ~/Wechat-Partner/.claude/settings.json             ❌ 无 hooks
  全局:  ~/.claude/settings.json                             ❌ 无 hooks

CLAUDE.md：
  全局:  ~/.claude/CLAUDE.md
  TP:    ~/Terminal-Partner/CLAUDE.md
  TPM:   软链到 TP CLAUDE.md
  WP:    ~/Wechat-Partner/CLAUDE.md
  IP:    ~/Investment-Partner/CLAUDE.md
  教学:  无项目级，走全局

ChromaDB（~/.chromadb/）：
  cc-boost-memory:      15 条（TP + TPM 共用）
  investment-memory:     7 条（IP 独用）

记忆池：
  TP/TPM/WP 共享:   ~/...terminal-partner/memory/          17 条
  IP 独立:          ~/...investment-partner/memory/               7 条

hook 脚本：~/project-cc-boost/hooks/*.py（所有项目共用同一份）
```
