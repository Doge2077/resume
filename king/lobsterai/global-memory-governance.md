# LobsterAI 全局记忆治理机制 — 技术深度报告

> **文档版本**: v1.0  
> **生成日期**: 2026-04-01  
> **分析对象**: `src/main/libs/coworkMemoryExtractor.ts`、`src/main/libs/coworkMemoryJudge.ts`、`src/main/coworkStore.ts`、`src/main/libs/coworkRunner.ts`、`src/main/sqliteStore.ts`  

---

## 目录

1. [系统总览](#1-系统总览)
2. [架构分层](#2-架构分层)
3. [层 1 — 提取层（coworkMemoryExtractor.ts）](#3-层-1--提取层)
4. [层 2 — 裁决层（coworkMemoryJudge.ts）](#4-层-2--裁决层)
5. [层 3 — 持久层（coworkStore.ts + sqliteStore.ts）](#5-层-3--持久层)
6. [层 4 — 调度与回注（coworkRunner.ts）](#6-层-4--调度与回注)
7. [AI 主动工具调用路径（memory_user_edits）](#7-ai-主动工具调用路径)
8. [配置参数体系](#8-配置参数体系)
9. [数据流全景图](#9-数据流全景图)
10. [问题评审](#10-问题评审)
11. [改进建议](#11-改进建议)
12. [附录：关键常量速查](#12-附录关键常量速查)

---

## 1. 系统总览

LobsterAI 的**全局记忆治理机制**是一套多层级的用户长期记忆管理系统，其核心目标是：

- **自动捕获**对话中隐含或显式的用户个人事实
- **智能过滤**瞬时/程序性/问题性内容，防止噪音写入
- **持久化存储**到本地 SQLite 数据库，跨会话保持
- **回注到上下文**，以 XML 格式注入每轮对话前缀，供 AI 使用

系统覆盖**两条写入路径**：

| 路径 | 触发方式 | 主体 |
|------|---------|------|
| **被动提取路径** | 每次会话 turn 结束后自动扫描 user/assistant 消息 | `coworkRunner` → `coworkStore.applyTurnMemoryUpdates` |
| **主动工具路径** | AI 显式调用 `memory_user_edits` MCP 工具 | Claude SDK → `coworkRunner.runMemoryUserEditsTool` |

---

## 2. 架构分层

```
┌─────────────────────────────────────────────────────────┐
│                     用户对话界面（Renderer）               │
└──────────────────────────┬──────────────────────────────┘
                           │ IPC
┌──────────────────────────▼──────────────────────────────┐
│              CoworkRunner（Main Process）                 │
│  ┌─────────────────┐    ┌──────────────────────────────┐ │
│  │ 被动提取调度队列  │    │  AI 主动工具：memory_user_edits│ │
│  │ (turnMemoryQueue)│    │  (MCP Tool)                  │ │
│  └────────┬─────────┘    └───────────────┬──────────────┘ │
└───────────┼─────────────────────────────┼───────────────┘
            │                             │
┌───────────▼─────────────────────────────▼───────────────┐
│              CoworkStore（存储+业务逻辑层）                │
│                                                         │
│  applyTurnMemoryUpdates()   createUserMemory()          │
│       │                          │                      │
│  ┌────▼─────────────────────┐    │                      │
│  │  Layer 1: 提取层          │    │                      │
│  │  coworkMemoryExtractor.ts │    │                      │
│  │  extractTurnMemoryChanges │    │                      │
│  └────────────┬─────────────┘    │                      │
│               │                  │                      │
│  ┌────────────▼─────────────┐    │                      │
│  │  Layer 2: 裁决层          │    │                      │
│  │  coworkMemoryJudge.ts     │    │                      │
│  │  judgeMemoryCandidate     │    │                      │
│  └────────────┬─────────────┘    │                      │
└───────────────┼──────────────────┼──────────────────────┘
                │                  │
┌───────────────▼──────────────────▼──────────────────────┐
│              SQLite 持久层 (sql.js / lobsterai.sqlite)    │
│   Table: user_memories       Table: user_memory_sources  │
└─────────────────────────────────────────────────────────┘
            │
┌───────────▼──────────────────────────────────────────────┐
│  回注层：buildUserMemoriesXml → 注入用户消息前缀            │
│  格式：<userMemories>\n- fact1\n- fact2\n</userMemories>  │
└──────────────────────────────────────────────────────────┘
```

---

## 3. 层 1 — 提取层

**文件**: `src/main/libs/coworkMemoryExtractor.ts`

### 3.1 提取类型

提取层输出 `ExtractedMemoryChange[]`，每个条目包含：

```typescript
interface ExtractedMemoryChange {
  action: 'add' | 'delete';
  text: string;
  confidence: number;   // 0~1
  isExplicit: boolean;  // 是否为显式指令
  reason: string;       // 分类原因标签
}
```

### 3.2 显式提取（`extractExplicit`）

通过正则匹配用户文本中的明确记忆指令：

**添加指令模式**（`EXPLICIT_ADD_RE`）：
```
记住 / 记下 / 保存到记忆 / 写入记忆
remember this / store this in memory
```

**删除指令模式**（`EXPLICIT_DELETE_RE`）：
```
删除记忆 / 从记忆中删除 / 忘掉 / 忘记这条
forget this / remove from memory
```

显式提取的条目 `confidence = 0.99`，`isExplicit = true`。

### 3.3 隐式提取（`extractImplicit`）

当 `maxImplicitAdds > 0` 时（默认 2），自动识别用户句子中的个人事实：

| 信号类型 | 正则标签 | confidence | 示例 |
|---------|---------|-----------|------|
| 个人档案 | `PERSONAL_PROFILE_SIGNAL_RE` | 0.93 | "我叫张三"、"I'm a designer" |
| 个人拥有 | `PERSONAL_OWNERSHIP_SIGNAL_RE` | 0.90 | "我养了一只猫"、"I have two dogs" |
| 个人偏好 | `PERSONAL_PREFERENCE_SIGNAL_RE` | 0.88 | "我喜欢深色主题"、"I prefer TypeScript" |
| 助手偏好 | `ASSISTANT_PREFERENCE_SIGNAL_RE` | 0.86 | "以后回复请用中文"、"always use markdown" |

**隐式提取的过滤链**（多级过滤，命中任意一条则跳过）：

1. `shouldKeepCandidate`：文本太短（<6字符）且无信号词 → 跳过
2. `SMALL_TALK_RE`：闲聊短语 → 跳过
3. `isQuestionLikeMemoryText`：疑问句检测 → 跳过
4. `NON_DURABLE_TOPIC_RE`：含"报错"/"异常"/"问题" → 跳过
5. `SOURCE_STYLE_LINE_RE` / `ATTACHMENT_STYLE_LINE_RE`："来源:"/"输入文件:" → 跳过
6. `TRANSIENT_SIGNAL_RE`：含时态词（今天/昨天/本周）且无个人档案信号 → 跳过
7. `PROCEDURAL_CANDIDATE_RE`：含命令行符号或 shell 命令 → 跳过

**置信度阈值门控**（按守护级别）：

| 守护级别 | 隐式提取阈值 |
|---------|------------|
| `strict` | 0.85 |
| `standard`（默认） | 0.65 |
| `relaxed` | 0.50 |

### 3.4 疑问句检测（`isQuestionLikeMemoryText`）

多维度检测，命中任一条则判为疑问：
- 结尾含 `？/?`
- 中文问题前缀（请问/为什么/如何/谁/什么…）
- 英文问题前缀（what/why/how/can/would/is…）
- 内嵌疑问词（是不是/能不能/有没有…）
- 结尾语气词（吗/么/呢/嘛）

### 3.5 文本清理（`sanitizeImplicitCandidate`）

通过 `REQUEST_TAIL_SPLIT_RE` 截取请求尾部，避免把"我叫张三，请你帮我写代码"整体保存，会截取为"我叫张三"。

---

## 4. 层 2 — 裁决层

**文件**: `src/main/libs/coworkMemoryJudge.ts`

### 4.1 规则打分（`scoreMemoryText`）

基础分 0.5，然后进行加减调整：

| 规则 | 分值 | 说明 |
|------|-----|------|
| `FACTUAL_PROFILE_RE` 命中 | +0.28 | 含个人事实词 |
| `ASSISTANT_STYLE_RE` 命中 | +0.10 | 含助手风格指令词 |
| `REQUEST_STYLE_RE` 命中 | -0.14 | 以请求词开头 |
| `TRANSIENT_RE` 命中 | -0.18 | 含时效词 |
| `PROCEDURAL_RE` 命中 | -0.40 | 含命令/脚本 |
| 文本长度 < 6 | -0.20 | 太短 |
| 文本长度 6~120 | +0.06 | 正常范围加分 |
| 文本长度 > 240 | -0.08 | 太长 |

最终分值 `clamp(0, 1)`。

### 4.2 接受阈值（`thresholdByGuardLevel`）

| 守护级别 | 显式记忆阈值 | 隐式记忆阈值 |
|---------|------------|------------|
| `strict` | 0.70 | 0.80 |
| `standard` | 0.60 | 0.72 |
| `relaxed` | 0.52 | 0.62 |

### 4.3 LLM 辅助裁决（`judgeWithLlm`）

**触发条件**：规则分与阈值差距 ≤ `LLM_BORDERLINE_MARGIN`（0.08），且 `llmEnabled = true`，且非"空值/疑问/程序性"类别。

**实现细节**：
- 使用当前配置的 API（`resolveCurrentApiConfig()`）调用 Anthropic Messages API
- `max_tokens: 120`，`temperature: 0`（确定性输出）
- 输入文本截断到 `LLM_INPUT_MAX_CHARS = 280` 字符
- 5 秒超时（`LLM_TIMEOUT_MS`）
- 返回格式：`{"accepted": boolean, "confidence": number, "reason": string}`

**LLM 结果缓存**：
- TTL：10 分钟（`LLM_CACHE_TTL_MS = 10 * 60 * 1000`）
- 最大条目：256（`LLM_CACHE_MAX_SIZE`）
- 缓存键：`{guardLevel}|{isExplicit}|{normalizedText}`
- LRO 淘汰：Map 插入顺序最旧的条目

**最低置信度过滤**：LLM 返回 `confidence < 0.55`（`LLM_MIN_CONFIDENCE`）则忽略，回退规则结果。

### 4.4 裁决结果接口

```typescript
interface MemoryJudgeResult {
  accepted: boolean;
  score: number;
  reason: string;
  source: 'rule' | 'llm';  // 标明判断来源
}
```

---

## 5. 层 3 — 持久层

**文件**: `src/main/coworkStore.ts` + `src/main/sqliteStore.ts`

### 5.1 数据表结构

**`user_memories`**：

| 字段 | 类型 | 说明 |
|------|-----|------|
| `id` | TEXT PK | UUID v4 |
| `text` | TEXT | 记忆内容（最长 360 字符） |
| `fingerprint` | TEXT | SHA-1(normalizeMatchKey(text)) |
| `confidence` | REAL | 置信度 0~1 |
| `is_explicit` | INTEGER | 是否显式 |
| `status` | TEXT | `created` / `stale` / `deleted` |
| `created_at` | INTEGER | 创建时间戳（ms） |
| `updated_at` | INTEGER | 更新时间戳（ms） |
| `last_used_at` | INTEGER | 最后使用时间戳（可空） |

**`user_memory_sources`**：追踪每条记忆来源的会话/消息/角色，`is_active` 用于孤立记忆标记。

**索引**：
- `(status, updated_at DESC)` — 列表查询优化
- `fingerprint` — 精确去重查询
- `(session_id, is_active)` — 来源关联查询
- `(memory_id, is_active)` — 孤立检测

### 5.2 去重机制（两级去重）

#### 第一级：指纹精确匹配

```sql
SELECT ... FROM user_memories
WHERE fingerprint = ? AND status != 'deleted'
```

指纹 = `SHA-1(normalizeMatchKey(text))`，其中 `normalizeMatchKey` 做：
- 统一空白、转小写
- 去除标点和控制字符

#### 第二级：语义近似去重（`scoreMemorySimilarity`）

当指纹未命中时，对所有 `status != 'deleted'` 的记忆进行语义扫描，计算相似度分数：

```
similarity = max(
  phraseScore,       // 包含关系得分
  tokenOverlap,      // 词元重叠（加权 Dice 系数变体）
  characterBigramDice // 字符 bigram Dice 系数
)
```

去重阈值 = `MEMORY_NEAR_DUPLICATE_MIN_SCORE = 0.82`。

命中近似条目时，会进行**记忆合并**（`createOrReviveUserMemory`）：
- `text` 取"质量分"更高者（保留 "我" 前缀 > "用户" 前缀）
- `confidence` 取两者最大值
- `is_explicit` 保守合并（只要任一显式则保持显式）
- `status` 强制重置为 `'created'`（复活软删除记忆）

### 5.3 记忆生命周期

```
created  ──── 用户或 AI 显式删除 ──────► deleted
   │                                       ▲
   │                                       │
   └──── 隐式记忆，来源全部失活 ─────► stale ─┘
                                       (不在回注中展示)
```

**孤立记忆标记**（`markOrphanImplicitMemoriesStale`）：
每次 `applyTurnMemoryUpdates` 后，将所有隐式记忆中 `user_memory_sources.is_active = 0` 的标记为 `stale`。

**自动清理**（`autoDeleteNonPersonalMemories`）：
扫描所有 `status = 'created'` 的记忆，若命中 `shouldAutoDeleteMemoryText`（含程序性/问题性内容）则软删除。

---

## 6. 层 4 — 调度与回注

**文件**: `src/main/libs/coworkRunner.ts`

### 6.1 异步队列调度

每次会话 turn 结束后（本地/沙箱模式均有触发点），调用 `applyTurnMemoryUpdatesForSession`：

```
turn 结束
    │
    ▼
取最后一条 user 消息 + 最后一条 assistant 消息（非 thinking）
    │
    ▼
计算 key = {sessionId}:{userMessageId}:{assistantMessageId}
    │
    ├── key 已在队列或上次处理过 → 跳过（幂等保护）
    │
    ▼
推入 turnMemoryQueue
    │
    ▼
drainTurnMemoryQueue（串行处理，防止并发竞争）
```

**防重机制**：
- `turnMemoryQueueKeys: Set<string>` — 队列去重
- `lastTurnMemoryKeyBySession: Map<string, string>` — 已处理记录

**错误降级**：`drainTurnMemoryQueue` 中每个 job 的错误独立捕获，不影响队列继续处理。

### 6.2 记忆回注（`buildPromptPrefix`）

记忆以 XML 格式注入**用户消息前缀**（非系统提示），理由：系统提示保持稳定可利用 API 的 prompt cache。

```xml
<userMemories>
- 我叫张三
- 我偏好使用 TypeScript
- 请始终用中文回复
</userMemories>
```

**截断限制**：
- 单条最长 200 字符（超出加 `...`）
- 总体最多 2000 字符
- 最多 `memoryUserMemoriesMaxItems` 条（默认 12，最大 60）

### 6.3 系统提示中的记忆策略声明

```
## Memory Strategy
- 历史检索工具优先……
- User memories 作为稳定个人上下文处理
- memory_user_edits 仅在用户显式要求时调用
- 不写入瞬时事实/新闻/引文来源
```

---

## 7. AI 主动工具调用路径

**工具名**: `memory_user_edits`，通过 MCP 服务器暴露。

### 支持操作

| 操作 | 参数 | 说明 |
|------|-----|------|
| `list` | `query?, limit?` | 列出记忆（含已删除） |
| `add` | `text, confidence?, is_explicit?` | 新增记忆 |
| `update` | `id, text?, confidence?, status?` | 更新记忆 |
| `delete` | `id` | 软删除记忆 |

**写入前验证**（`validateMemoryToolText`）：
1. 文本清理（截除请求尾缀）
2. 疑问句检测
3. 助手指令格式检测（`使用 XXX 技能`）
4. 程序性内容检测

注意：AI 主动添加的记忆**同样需通过验证**，但**不经过** `judgeMemoryCandidate` 裁决层（直接写库）。

---

## 8. 配置参数体系

| 配置项 | 类型 | 默认值 | 说明 |
|--------|-----|-------|------|
| `memoryEnabled` | boolean | false | 总开关 |
| `memoryImplicitUpdateEnabled` | boolean | true | 是否启用隐式提取 |
| `memoryLlmJudgeEnabled` | boolean | false | 是否启用 LLM 辅助裁决 |
| `memoryGuardLevel` | `strict/standard/relaxed` | `standard` | 守护级别 |
| `memoryUserMemoriesMaxItems` | number | 12（1~60） | 回注最大条目数 |

配置持久化在 SQLite `cowork_config` 表（KV 格式）。

---

## 9. 数据流全景图

```
用户输入: "我叫张三，帮我写一个 Python 脚本"
    │
    ▼
[turn 结束] applyTurnMemoryUpdatesForSession
    │
    ▼
extractTurnMemoryChanges(userText, assistantText, guardLevel)
    │
    ├─ 显式提取：无匹配
    │
    └─ 隐式提取：
         候选句: "我叫张三" → 命中 PERSONAL_PROFILE_SIGNAL_RE
         候选句: "帮我写一个 Python 脚本" → 命中 PROCEDURAL_CANDIDATE_RE → 过滤
         候选: {text:"我叫张三", confidence:0.93, isExplicit:false}
    │
    ▼
judgeMemoryCandidate({text:"我叫张三", isExplicit:false, guardLevel:"standard"})
    │
    ├─ scoreMemoryText → 0.5 + 0.28(FACTUAL_PROFILE) + 0.06(长度) = 0.84
    ├─ threshold = 0.72（standard 非显式）
    ├─ 0.84 >= 0.72 → accepted=true（规则直接通过，无需 LLM）
    │
    ▼
createOrReviveUserMemory({text:"我叫张三", confidence:0.93, isExplicit:false})
    │
    ├─ fingerprint = SHA-1("我叫张三")
    ├─ 查询 user_memories WHERE fingerprint=... → 无命中
    ├─ 语义近似扫描 → 无近似条目
    ├─ INSERT INTO user_memories ...
    │
    ▼
[下次 turn 开始] buildPromptPrefix
    │
    ▼
<userMemories>
- 我叫张三
</userMemories>
（注入到用户消息前缀，AI 可读取）
```

---

## 10. 问题评审

### 🔴 P0 — 严重问题

#### P0-1：测试文件缺失，CI 必然失败

**问题描述**：`package.json` 中定义了 `"test:memory": "npm run compile:electron && node --test tests/coworkMemoryExtractor.test.mjs"`，但 `tests/` 目录下**不存在** `coworkMemoryExtractor.test.mjs` 文件。

**影响**：`npm run test:memory` 命令执行必然报错，导致任何 CI pipeline 中的记忆测试步骤失败。

**关键代码位置**：`package.json:18`，`AGENTS.md:193`

**建议**：补充测试文件，或在 `package.json` 中移除失效的测试命令。

---

#### P0-2：AI 主动工具写入绕过裁决层

**问题描述**：当 AI 调用 `memory_user_edits` 工具的 `add` 操作时，文本仅经过 `validateMemoryToolText`（基于正则的简单验证），**不经过** `judgeMemoryCandidate` 裁决层。

**影响**：在对话中，AI 可能因误解用户意图而将不适宜的内容（如瞬时事实、任务上下文）通过工具直接写入长期记忆库，破坏记忆质量。

**关键代码位置**：`coworkRunner.ts:849`（`createUserMemory` 直接调用，无 `judgeMemoryCandidate`）

**建议**：在工具写入路径中引入轻量级裁决（至少规则层检查）。

---

### 🟠 P1 — 重要问题

#### P1-1：语义去重的 O(n) 全表扫描性能问题

**问题描述**：`createOrReviveUserMemory` 在指纹未命中时，会 **SELECT 全表最多 200 条记忆**逐一计算语义相似度（`scoreMemorySimilarity`），算法复杂度为 O(n)，每条比较内含三种相似度算法（phraseScore + tokenOverlap + bigramDice）。

**影响**：随着用户记忆条目增多，每次写入记忆的延迟会线性增长。当 `memoryUserMemoriesMaxItems` 接近上限（60）且总记忆远超 200 条时，可能出现明显延迟。

**关键代码位置**：`coworkStore.ts:994-1014`

**建议**：引入轻量级向量索引，或对语义 key 进行预计算并存储在 DB 列，利用 SQL 前缀过滤缩小候选集。

---

#### P1-2：LLM 缓存淘汰策略使用 Map 插入顺序，非标准 LRU

**问题描述**：`llmJudgeCache` 使用 `Map` 存储，淘汰时删除 `map.keys().next().value`（最早插入的条目）。这是 FIFO（先进先出），**不是** LRU（最近最少使用）。频繁被命中的热点条目可能在容量达到时被提前淘汰。

**关键代码位置**：`coworkMemoryJudge.ts:81-85`

**建议**：实现标准 LRU（Map + delete/set 配合实现近似 LRU），或使用 `lru-cache` 库。

---

#### P1-3：隐式记忆最大数量硬编码为 2，无法配置

**问题描述**：`extractImplicit` 中 `maxImplicitAdds` 参数虽然传入，但在函数内部强制 `Math.max(0, Math.min(2, ...))` 夹紧到最大 2，用户/配置层无法突破此上限。

**关键代码位置**：`coworkMemoryExtractor.ts:112`

**影响**：单次 turn 最多捕获 2 条隐式记忆，对信息密度较高的用户消息（如初次自我介绍）可能丢失有效记忆。

**建议**：将上限提升为可配置参数（如 `maxImplicitAddsPerTurn`），并在配置层提供合理默认值和上限。

---

#### P1-4：`last_used_at` 字段始终为 NULL，功能未实现

**问题描述**：`user_memories` 表中定义了 `last_used_at INTEGER` 字段，`CoworkUserMemory` 接口也包含 `lastUsedAt: number | null`，但**代码中从未更新此字段**（`buildUserMemoriesXml` 读取记忆时没有写回 `last_used_at`）。

**影响**：无法基于"最近使用频率"进行记忆排序或过期清理，`lastUsedAt` 字段的设计意图未兑现。

**建议**：在 `buildUserMemoriesXml` 读取并注入记忆时，批量更新 `last_used_at = NOW()`。

---

### 🟡 P2 — 一般问题

#### P2-1：删除匹配逻辑依赖短语包含关系，可能误删

**问题描述**：`scoreDeleteMatch` 中，当用户说"忘掉我叫张三"时，会对现有记忆按"短语包含"规则进行匹配。若用户有两条记忆"我叫张三"和"我叫张三李四"，两者均包含"张三"，则得分最高的会被删除，但选择逻辑不一定符合用户预期。

**关键代码位置**：`coworkStore.ts:256-268`

**建议**：优先精确匹配，模糊删除时向用户确认或返回匹配列表。

---

#### P2-2：正则表达式在多个文件中重复定义

**问题描述**：`MEMORY_REQUEST_TAIL_SPLIT_RE`、`MEMORY_PROCEDURAL_TEXT_RE`、`MEMORY_ASSISTANT_STYLE_TEXT_RE` 等正则在 `coworkRunner.ts` 中单独重新定义，与 `coworkMemoryExtractor.ts` 中的定义高度相似但不共享。同样，`MEMORY_ASSISTANT_STYLE_TEXT_RE` 也在 `coworkStore.ts` 中独立定义。

**影响**：维护时需要同步修改多处，存在行为不一致风险。

**关键代码位置**：`coworkRunner.ts:113-115`、`coworkStore.ts`（`MEMORY_ASSISTANT_STYLE_TEXT_RE`）

**建议**：将公共正则统一导出自 `coworkMemoryExtractor.ts`，各使用方引用。

---

#### P2-3：`markOrphanImplicitMemoriesStale` 语义模糊

**问题描述**：函数将"所有 `is_active=0` 来源的隐式记忆"标记为 `stale`，但 `is_active` 在会话结束时通过 `markMemorySourcesInactiveBySession` 批量设为 0，导致任何跨会话的隐式记忆在下一次 `applyTurnMemoryUpdates` 后都可能变为 `stale`。

**影响**：用户的长期隐式记忆可能在会话切换后意外降级，不展示在下一次上下文中。

**建议**：区分"会话结束后的来源失活"与"记忆本身是否应保留"的语义，引入独立的 TTL 机制而非依赖来源活跃状态。

---

#### P2-4：`buildUserMemoriesXml` 中的字符限制过于保守

**问题描述**：单条记忆截断至 200 字符，总体限制 2000 字符。对于记录了多条偏好的用户，实际上只有约 10 条记忆能完整展示，可能影响 AI 的上下文质量。

**关键代码位置**：`coworkRunner.ts:666-678`

**建议**：将总字符数上限适当提升（如 4000~6000），并允许用户自定义。

---

#### P2-5：缺乏记忆冲突检测与覆盖通知

**问题描述**：当用户先说"我叫张三"，后说"记住，我现在叫李四了"，系统会通过语义近似去重合并两条记忆，但 AI 不会收到合并通知，可能在同一会话内短暂持有旧事实。

**建议**：记忆覆盖时，可以在下轮前缀中加入 `<memoryUpdated>` 标记，帮助 AI 感知记忆变更。

---

### 🔵 P3 — 优化建议

#### P3-1：隐式提取缺少对话轮次的上下文感知

当前隐式提取仅从 `userText` 中的句子独立判断，没有利用 `assistantText` 中 AI 的确认/重复行为来提升置信度（例如 AI 回复"好的，已知道您叫张三"可以作为强烈信号）。

#### P3-2：无记忆版本历史

记忆更新时只保留最新版本，没有变更日志。对于用户维权（"AI 为什么记住了这条错误信息"）无从追溯。

#### P3-3：无跨用户隔离保护

当前所有记忆共享同一个 SQLite 数据库，无 `user_id` 字段。若将来需要支持多用户场景，需要进行结构调整。

#### P3-4：`autoDeleteNonPersonalMemories` 未被主动调用

该函数在 `coworkStore.ts` 中定义，但代码中未发现其在运行时的调用点，可能是遗留功能或文档缺失。

---

## 11. 改进建议

### 11.1 高优先级（P0/P1）

| # | 建议 | 预期收益 |
|---|-----|---------|
| 1 | **补充 `tests/coworkMemoryExtractor.test.mjs` 测试文件** | 修复 CI，保证提取逻辑正确性 |
| 2 | **工具写入路径引入裁决层** | 防止 AI 误存不适宜内容 |
| 3 | **优化语义去重为预计算 key** | 消除 O(n) 全表扫描 |
| 4 | **LLM 缓存升级为标准 LRU** | 提升热点缓存命中率 |
| 5 | **实现 `last_used_at` 字段更新** | 为记忆过期/排序提供数据基础 |

### 11.2 中优先级（P2）

| # | 建议 | 预期收益 |
|---|-----|---------|
| 6 | **正则常量统一在 `coworkMemoryExtractor.ts` 导出** | 消除重复定义，降低维护成本 |
| 7 | **重新设计孤立记忆标记语义** | 防止跨会话隐式记忆意外降级 |
| 8 | **允许配置 `maxImplicitAddsPerTurn`** | 提升信息密度场景的记忆捕获能力 |
| 9 | **`buildUserMemoriesXml` 总字符上限提升并可配置** | 改善多条偏好用户的上下文质量 |

### 11.3 架构层建议

**引入记忆质量评分周期性维护任务**：  
定期（如每日）对记忆库运行 `autoDeleteNonPersonalMemories` 并结合 `last_used_at` 清理长期未使用的低置信度隐式记忆，防止库膨胀。

**引入记忆变更事件流**：  
记忆的 create/update/delete 操作通过事件通知 Renderer，支持在 UI 中实时展示"记忆面板"，提升用户对记忆状态的感知和控制。

---

## 12. 附录：关键常量速查

### coworkMemoryExtractor.ts

| 常量 | 值 | 说明 |
|------|---|-----|
| `confidenceThreshold(strict)` | 0.85 | 隐式提取守护阈值（严格） |
| `confidenceThreshold(standard)` | 0.65 | 隐式提取守护阈值（标准） |
| `confidenceThreshold(relaxed)` | 0.50 | 隐式提取守护阈值（宽松） |
| maxImplicitAdds（硬上限） | 2 | 单 turn 最大隐式提取数 |

### coworkMemoryJudge.ts

| 常量 | 值 | 说明 |
|------|---|-----|
| `LLM_BORDERLINE_MARGIN` | 0.08 | 触发 LLM 裁决的边界宽度 |
| `LLM_MIN_CONFIDENCE` | 0.55 | LLM 结果最低可信度 |
| `LLM_TIMEOUT_MS` | 5000 | LLM 请求超时（ms） |
| `LLM_CACHE_MAX_SIZE` | 256 | LLM 结果缓存最大条目 |
| `LLM_CACHE_TTL_MS` | 600000 | LLM 缓存 TTL（10 分钟） |
| `LLM_INPUT_MAX_CHARS` | 280 | 送入 LLM 的文本截断长度 |

### coworkStore.ts

| 常量 | 值 | 说明 |
|------|---|-----|
| `MEMORY_NEAR_DUPLICATE_MIN_SCORE` | 0.82 | 语义近似去重触发阈值 |
| `DEFAULT_MEMORY_USER_MEMORIES_MAX_ITEMS` | 12 | 默认回注记忆条数 |
| `MAX_MEMORY_USER_MEMORIES_MAX_ITEMS` | 60 | 最大回注记忆条数 |
| `MAX_ITEM_CHARS`（buildUserMemoriesXml） | 200 | 单条记忆回注最大字符 |
| `MAX_TOTAL_CHARS`（buildUserMemoriesXml） | 2000 | 全部记忆回注总字符上限 |
| 记忆文本最大存储长度 | 360 | `truncate(text, 360)` |

---

*本报告基于代码静态分析生成，不包含动态运行性能数据。建议结合实际用户使用量进行性能压测。*
