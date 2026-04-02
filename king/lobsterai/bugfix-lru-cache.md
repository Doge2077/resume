**技术报告**

# LLM 缓存淘汰策略偏离 LRU 的问题分析与修复报告

## 1. 背景

在 `LobsterAI` 的全局记忆治理链路中，`src/main/libs/coworkMemoryJudge.ts` 负责对候选记忆做二次裁决。对于规则分数接近阈值的边界案例，系统会触发一次 LLM 辅助判断，以降低误判率。

为了避免同一类边界输入反复请求模型，这里实现了一层本地缓存，文档中将其描述为：

- TTL：10 分钟
- 最大条目数：256
- 淘汰策略：LRU

但 issue `#1299` 指出，这里的实现实际上并不是标准 LRU，而是依赖 `Map` 的插入顺序来淘汰。这个差异会导致“热点缓存项”在缓存打满后仍被错误淘汰。

---

## 2. 问题定位

问题代码位于：

- `src/main/libs/coworkMemoryJudge.ts`

修复前缓存相关实现的核心逻辑可以概括为：

```ts
const llmJudgeCache = new Map<string, CachedLlmJudgeResult>();

function getCachedLlmResult(key: string): MemoryJudgeResult | null {
  const cached = llmJudgeCache.get(key);
  if (!cached) return null;
  if (Date.now() - cached.createdAt > LLM_CACHE_TTL_MS) {
    llmJudgeCache.delete(key);
    return null;
  }
  return cached.value;
}

function setCachedLlmResult(key: string, value: MemoryJudgeResult): void {
  llmJudgeCache.set(key, { value, createdAt: Date.now() });
  while (llmJudgeCache.size > LLM_CACHE_MAX_SIZE) {
    const oldestKey = llmJudgeCache.keys().next().value;
    llmJudgeCache.delete(oldestKey);
  }
}
```

### 2.1 表面上看起来像 LRU

实现中确实有：

- 固定上限 `LLM_CACHE_MAX_SIZE`
- 超限时删除 `Map` 的第一个键

如果只看淘汰动作，很容易误以为这已经是 LRU。

### 2.2 实际上只是“按插入顺序淘汰”

关键问题在于：

- `Map` 维护的是**插入顺序**
- `getCachedLlmResult()` 在命中缓存后，**没有刷新该 key 的顺序**
- 因此即使某个缓存项刚刚被访问过，它仍然保留在原来的旧位置
- 一旦容量超限，最早插入的项仍会被删除

所以它的行为更接近：

- FIFO by insertion order
- 或者“带 TTL 的插入序淘汰缓存”

而不是标准 LRU。

---

## 3. Issue 复现过程

这个问题的复现条件非常清晰：需要让缓存容量达到上限，并且验证“最近访问过的最老条目”是否仍被淘汰。

### 3.1 复现目标

验证以下场景：

1. 先写满 256 个缓存项
2. 再访问第 1 个缓存项，使它在逻辑上成为“最近使用”
3. 插入第 257 个缓存项，触发淘汰
4. 再次访问第 1 个缓存项

### 3.2 预期行为

如果缓存是真正的 LRU，那么：

- 第 1 个缓存项因为刚被访问过，应该保留下来
- 第 2 个缓存项才应该被淘汰

### 3.3 实际行为（修复前）

修复前会出现：

- 第 1 个缓存项仍被淘汰
- 再次访问第 1 项时，会重新触发一次 LLM 请求
- 这说明缓存并没有把“最近访问”纳入淘汰顺序

### 3.4 为什么这个复现成立

因为修复前的逻辑中：

- 第 1 项虽然被读取了
- 但它在 `Map` 中的位置没有更新
- 它仍然是最早插入的元素
- 当第 257 项写入时，`Map.keys().next().value` 仍然返回第 1 项

这正是 issue 中提到的“非标准 LRU”问题。

---

## 4. 影响分析

这个问题不会导致功能完全错误，但会带来明显的行为偏差和性能损耗。

### 4.1 热点缓存项被误淘汰

对于一些反复出现的边界候选记忆：

- 它们本应长期保留在缓存中
- 但由于只按插入时间排序
- 在缓存打满时仍会被优先删除

### 4.2 增加不必要的 LLM 请求

被错误淘汰后，系统会：

- 对相同候选再次调用 LLM
- 增加外部请求次数
- 增加判断延迟
- 增加配额和成本消耗

### 4.3 实现与文档不一致

文档和分析都把它视作 LRU：

- 这会误导后续维护者
- 也会让基于缓存语义的性能分析出现偏差

---

## 5. 解决方案设计

修复目标很明确：

- 保留现有 TTL 机制
- 保留现有最大容量控制
- 在不扩大改动范围的前提下，让 `Map` 真正承载 LRU 语义

### 5.1 设计原则

采用最小改动方案：

- 不引入新的缓存结构
- 不引入额外依赖
- 继续使用现有 `Map`
- 通过“删除再插入”刷新最近使用顺序

这是 JavaScript/TypeScript 中基于 `Map` 实现轻量 LRU 的常见做法。

### 5.2 核心思路

#### 读缓存时

如果缓存命中且未过期：

1. 先 `delete(key)`
2. 再 `set(key, cached)`

这样该 key 会被移动到 `Map` 的尾部，表示“最近使用”。

#### 写缓存时

如果当前 key 已存在：

1. 先删除旧 key
2. 再插入新值

这样可以保证：

- 更新后的 key 也被视为最近使用
- `Map` 顺序始终与最近访问顺序一致

---

## 6. 代码实现说明

### 6.1 `getCachedLlmResult()` 的修改

修复后：

```ts
function getCachedLlmResult(key: string): MemoryJudgeResult | null {
  const cached = llmJudgeCache.get(key);
  if (!cached) return null;
  if (Date.now() - cached.createdAt > LLM_CACHE_TTL_MS) {
    llmJudgeCache.delete(key);
    return null;
  }
  llmJudgeCache.delete(key);
  llmJudgeCache.set(key, cached);
  return cached.value;
}
```

### 6.1.1 改动意义

新增的两行：

```ts
llmJudgeCache.delete(key);
llmJudgeCache.set(key, cached);
```

作用是：

- 在“命中且未过期”时，刷新 recency
- 使该条目不再被视为旧项
- 从而参与正确的 LRU 淘汰

### 6.2 `setCachedLlmResult()` 的修改

修复后：

```ts
function setCachedLlmResult(key: string, value: MemoryJudgeResult): void {
  if (llmJudgeCache.has(key)) {
    llmJudgeCache.delete(key);
  }
  llmJudgeCache.set(key, { value, createdAt: Date.now() });
  while (llmJudgeCache.size > LLM_CACHE_MAX_SIZE) {
    const oldestKey = llmJudgeCache.keys().next().value;
    if (!oldestKey || typeof oldestKey !== 'string') break;
    llmJudgeCache.delete(oldestKey);
  }
}
```

### 6.2.1 改动意义

这部分主要解决“更新已有 key”时的顺序一致性问题：

- 如果 key 已存在，直接 `set()` 虽然会覆盖值，但不会显式表达“刷新 recency”
- 通过先删后插，语义更稳定
- 这样无论是读命中还是写更新，都会统一把该 key 移到队尾

---

## 7. 回归测试设计

为确保问题被真实复现并永久受保护，这次新增了测试文件：

- `src/main/libs/coworkMemoryJudge.test.ts`

### 7.1 测试思路

测试使用 mocked `fetch` 来模拟 LLM 响应，不依赖真实网络。

核心步骤：

1. 构造 256 个不同的边界输入
2. 逐个调用 `judgeMemoryCandidate()`，填满缓存
3. 再次访问第 0 个输入，确认命中缓存，不产生额外请求
4. 插入第 256 个新输入，触发淘汰
5. 再访问第 0 个输入，确认仍然命中缓存
6. 再访问第 1 个输入，确认它才是被淘汰并重新请求的项

### 7.2 关键断言

测试里用 `fetchMock` 的调用次数来判断缓存是否生效：

- 前 256 次输入后：`fetch` 被调用 256 次
- 重新访问第 0 项后：调用次数仍为 256
- 插入第 257 项后：调用次数变为 257
- 再访问第 0 项后：调用次数仍为 257
- 再访问第 1 项后：调用次数变为 258

这个断言链完整覆盖了：

- 问题复现
- 修复生效
- LRU 顺序正确

---

## 8. 验证结果

### 8.1 单元测试

执行：

```powershell
.\node_modules\.bin\vitest.cmd run src/main/libs/coworkMemoryJudge.test.ts
```

结果：

- 通过

### 8.2 静态检查

执行：

```powershell
.\node_modules\.bin\eslint.cmd src/main/libs/coworkMemoryJudge.ts src/main/libs/coworkMemoryJudge.test.ts
```

结果：

- 通过

---

## 9. 方案优点与边界

### 9.1 优点

这次修复的优点是：

- 改动范围小
- 不影响外部接口
- 不改变 TTL 逻辑
- 不改变缓存容量上限
- 不引入新依赖
- 直接让现有实现与文档语义对齐

### 9.2 边界

这次修复只解决：

- “最近使用顺序未更新”导致的非标准 LRU 问题

没有改变的部分包括：

- TTL 的定义和过期策略
- 缓存键构造方式
- 是否触发 LLM 的边界判定逻辑
- LLM 返回值置信度过滤逻辑

因此这是一次非常聚焦的行为修正，不会扩大影响面。

---

## 10. 结论

issue `#1299` 的本质，是一个典型的“文档声明为 LRU，但实现只做了插入序淘汰”的缓存语义偏差问题。

### 10.1 问题本质

- 使用了 `Map`
- 用首键做淘汰
- 但没有在读取时刷新顺序

因此缓存并不是真正的 LRU。

### 10.2 修复核心

通过在缓存命中和更新时统一执行：

- `delete(key)`
- `set(key, value)`

让 `Map` 顺序真正表示“最近使用顺序”。

### 10.3 最终结果

修复后：

- 热点缓存项不会再被错误优先淘汰
- LLM 边界判定缓存行为与文档一致
- 重复 LLM 请求减少
- 系统性能和可维护性更符合预期