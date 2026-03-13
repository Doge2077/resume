# 基于 MixSpec 落地 Harness Engineering 实战

## 前言

随着大模型的发展，模型 Coding 的能力越来越强。为了更好得“驾驶” AI 编码，我开始关注 SDD 驱动开发范式，尝试将开发的流程进行规范。初期是效果显著的，但很快我陷入了另一层陷阱——我需要花费大量时间来规划和重整 AI 给我的每一次 Plan，且每次的需求产生到 AI 编码，似乎都变成了一个随用随抛的垃圾过程。

最近，我基于 SDD 来完成了我的 Markdown 翻译服务的 MCP 接口支持，并且将这次改造的经验沉淀出了一篇文章，方便团队能够快速借鉴，完成对服务的 MCP 接口支持。我猛然发现，仅靠 SDD 是无法实现代码的复利效应的，无法将 AI 的生产经验快速辐射到整个团队，仍然依赖于个人的团队意识驱动，于是我便关注到了复合工程，并基于 MixSpec 进行实践，给出一些我的思考。

---

## 一、从 SDD 到复合工程：为什么代码已经不是最稀缺的东西

### 1.1 SDD 的价值，不是“多写几份文档”

Spec-Driven Development（SDD）最容易被误解成“在开发前多补几份 Markdown”。

但如果只把 SDD 理解成文档规范，那它当然很容易沦为形式主义。真正重要的不是文档数量，而是把一次开发从松散对话里抽出来，变成一条可追踪、可验证、可回放的产物链：

`需求 -> 规格(spec) -> 方案(plan) -> 任务(tasks) -> 实施(apply) -> 验证(verify) -> 归档(archive)`

这条链真正解决的是三个问题：

1. **意图显式化**：先把“要做什么”冻结下来，而不是边写边猜。
2. **约束结构化**：把实现方向、风险、非目标、验收标准写成后续步骤可消费的输入。
3. **执行可验证**：不是“代码写完就算结束”，而是“验证完成、证据可追踪、结果可沉淀”。

在 AI 时代，**代码越来越像结果，而不是能力本身**。真正让代码产生复利价值的，是让代码走出 IDE，将每一次的生产变成规范、设计、约束和可验证的经验。

### 1.2 复合工程：每一次工作都应该让下一次更容易

如果说 SDD 解决的是“如何把一次开发组织起来”，那么复合工程（Compounding Engineering）解决的就是“如何让这套组织方式随着时间变得更强”。

复合工程的核心命题很简单：

> 每一单元工程工作，都应该让后续工作更容易，而不是更难。

传统开发中，新增一个功能往往意味着：

- 代码库复杂一点
- 隐性规则再多一点
- 老人脑内知识再多一点
- 下一次类似开发再重复踩一遍坑

而复合工程追求的是相反方向：

- 这次踩过的坑，变成下次的提示
- 这次评审发现的风险，变成之后的检查项
- 这次解决的复杂问题，变成团队知识库的一部分
- 这次的工作流，变成下一次更低摩擦的默认路径

Every 的 `compound-engineering-plugin` 对这件事的表达非常直接：`Brainstorm -> Plan -> Work -> Review -> Compound`。其中最关键的不是执行，而是最后的 `Compound`——把过程知识结构化沉淀，让团队能力持续复利。

### 1.3 Harness Engineering：人类掌舵，智能体执行

如果继续往前走，就会发现问题已经不只是“要不要写 spec”，而是“怎么为 agent 设计一条稳定轨道”，怎么把复合工程真正落地到现有的工作流中。

这也是我理解的 Harness Engineering 的起点：

- 人类负责定义目标、边界、优先级与接受标准
- 智能体负责执行、迭代、调用工具、产出中间结果
- 系统负责提供上下文、约束、验证回路和可复用记忆

Claude Code 对这种范式已经给了非常清晰的能力模型：它不只是“聊天写代码”，而是读代码库、编辑文件、运行命令、接 MCP、使用 `CLAUDE.md`、skills、hooks、sub-agents，并在不同表面之间共享同一套 engine。换句话说，工程重点已经不是“怎么让模型多说几句对的话”，而是“怎么让模型在一条可控轨道上稳定做对事”。

从这个角度看，Harness Engineering 至少包含四个核心问题：

1. **边界**：agent 在哪个工作单元里工作。
2. **上下文**：agent 在当前步骤能看到哪些高信号信息。
3. **约束**：哪些规则、契约、红线和非目标必须被守住。
4. **验证**：什么时候算真正完成，失败时如何阻断、回退、修正。

我关注到了 [MixSpec](https://km.netease.com/v4/detail/blog/260949)，一个基于复合工程思想的 Harness 框架，它实现了真正把这些抽象问题尽量压成了项目内可版本化、可追踪、可被 agent 直接消费的产物。

---

## 二、MixSpec 的设计理念：它不是在“加文档”，而是在搭工作轨道

### 2.1 MixSpec 的出发点，是 practical SDD

MixSpec 第一眼看上去像一个 spec 工具，这个判断并没有错。

它最开始要解决的，不是“多 agent 平台”，也不是“超级工作流调度器”，而是一个很朴素的问题：**怎么让 SDD 在真实项目里跑起来**。

这意味着它必须降低两类成本：

- **记忆成本**：不要要求每个人都记住一长串流程和规范。
- **操作成本**：不要让团队为了遵守 SDD 额外执行大量手工步骤。

所以 MixSpec 做了几个很关键的选择：

- 用 `change` 作为统一工作单元，而不是让开发行为散落在聊天与零碎提交里。
- 用 `spec.md / plan.md / tasks.md / meta.yaml` 组成固定产物链，而不是靠人脑记住“现在做到哪一步”。
- 用 `sync / verify / archive / drift` 把一致性、门禁、归档、健康检查做成默认能力，而不是靠人自觉补。

### 2.2 agent-first + skills-only：CLI 变薄，工作流变厚

MixSpec 一个特别有意思的设计，是它把 CLI 主动做薄了。

在本地源码里，`src/cli/index.ts` 注册的只有 `init / update / migrate` 三个入口，描述也明确写着：`init-only CLI for IDE workflows`。真正的日常开发工作流，不再通过传统 CLI 子命令驱动，而是通过注入 IDE 的 `/msx:*` skills 来执行。

这意味着它的产品分层很清晰：

- **CLI**：负责初始化、升级、迁移，把框架注入到项目或全局环境里。
- **Skills**：负责真正的人机交互和 agent-first 工作流执行。
- **TypeScript commands / utils / core**：负责本地状态机、元数据管理、级联同步、验证、归档和沉淀。

这不是一个小改动，而是一种方向判断：AI 工程工具的重点，不再是“提供多少命令”，而是“让 agent 和人围绕同一套产物协议协同工作”。

### 2.3 change 是工作边界，meta.yaml 是状态机中心

MixSpec 最核心的抽象是 `change`。

每个 change 都对应一个目录，里面有固定产物：

- `meta.yaml`
- `spec.md`
- `plan.md`
- `tasks.md`
- `review.md`（可选）
- `artifacts/`

其中最关键的不是 Markdown，而是 `meta.yaml`。它记录的不只是标题和状态，而是整个工作流的事实来源，例如：

- `workflow.current_step`
- `steps_completed`
- `review.status`
- `archive_truth`
- `sync_history`
- `lineage`
- `epic` / `claimed_modules`

这使得 MixSpec 不是“围绕文档的工具”，而是“围绕元数据驱动工作流的工具”。文档是产物，`meta.yaml` 才是状态机。

### 2.4 闭环能力：sync、verify、archive、drift、learnings

很多 spec 工具最大的问题不是起步，而是过期。

spec 改了 plan 没改，plan 改了 tasks 没改，代码变了 spec 没回写，归档后文档又被人手工改了——最后整个系统只剩下一堆看似结构化、实则已经失真的文件。

MixSpec 的闭环能力，主要就是为了解这个问题：

- `sync`：修改上游文档时分析级联影响，自动或半自动更新下游文档，并记录 `sync_history`
- `verify`：统一执行 lint / type / test / task 完成度 / spec drift 检查，支持 `soft` 和 `hard` gate
- `archive`：归档时记录 `archive_commit` 和 `artifact_hashes`，并自动生成 learnings
- `drift`：扫描归档基线之后的偏移，发现归档后的文档健康问题

走到这一步，MixSpec 的重心其实已经从“写文档”变成了“让文档链与实现链保持闭环”。而这，正是 harness 的雏形。

---

## 三、实战案例：从经验沉淀，到经验复用

接下来用一个我最近的真实案例，具体说明 MixSpec 是怎么把“经验 -> change -> 规格 -> 实施 -> 归档”串起来的。

### 3.1 背景：先在 Markdown 翻译服务 沉淀 MCP 服务改造经验

在 `Markdown 翻译服务` 服务里，我先完成了一次面向 Spring Boot 服务的 MCP 改造实践，并且沉淀了一份改造经验文档。

那份经验文档最核心的结论并不复杂：

- 不要重写业务逻辑，而是复用已有 Service
- 把 MCP 改造收敛成 `Tool -> Mapper -> Service`
- 把参数校验、默认值和返回结构稳定在协议适配层
- 首批就把开关、鉴权、观测、测试补齐

如果只把这份文档当作“经验总结”，它当然有价值；但如果没有一个更强的工程载体，它依然很容易停留在“写过、看过、下次未必记得”的状态。而且，对于团队成员来说，真正落地到自己的服务中也需要做相应的调整和适配，这变相中加重了团队成员的学习和工作负担。

### 3.2 用 `/msx:new` 把经验文档变成 change 输入

在我的另一个服务中，我安装 MixSpec 后，直接用 `/msx:new` 配合 `mcp-dev.md`（经验文档） 作为输入，创建了一个变更：

`001-add-mcp-support-for-convert`

归档后的产物目录在：

`\mixspec\specs\001-add-mcp-support-for-convert`

这个目录下的 change 中包含了一份 `meta.yaml` 文件，它不是简单记录“谁创建了一个需求”，而是把整次工作流的信息完整挂住了：

- `source_inputs` 明确记下了 `mcp-dev.md` 是这次 change 的输入材料
- `steps_completed` 记录了 `spec -> plan -> tasks -> review-plan -> apply -> archive` 的完成时间
- `sync_history` 记录了过程中的两次关键修正
- `archive_truth` 记录了归档时的 commit 与 artifact hash

这里最重要的变化是：**经验不再只是被引用，而是被结构化接管进本次 change 的生命周期**。

### 3.3 spec：先冻结需求的外部契约

在这次改造里，`spec.md` 做的第一件事不是解释内部代码怎么改，而是把对外契约冻结下来。

例如，规格里明确了几个关键点：

- 必须暴露一个 MCP 工具，而不是改造现有 HTTP 入口语义
- 必须复用现有文档转换能力，而不是重写一套业务逻辑
- 输入只接受最小必要字段
- 成功时必须返回可直接消费的字段
- MCP 路径必须支持独立开关和 Bearer 鉴权，但不影响原有接口

这一步非常关键，因为它把“经验里的一般原则”真正收敛成了当前 change 的外部 contract。

如果没有这一步，MCP 服务化改造最容易出现的问题就是：

- 输入字段边写边定
- 输出结构在 review 和实现阶段来回摇摆
- 内部业务对象被直接泄漏到对外接口
- 安全和兼容边界被放到实现后期再修

### 3.4 plan：把经验翻译成协议适配层架构

进入 `plan.md` 之后，抽象开始落地成技术结构。

这份 plan 非常典型地采用了“协议适配层 + 业务能力复用”的思路：

1. **协议与业务解耦**：MCP 改造只是新增协议入口，不污染既有 HTTP 控制器。
2. **复用已有能力**：核心业务仍然走已有的 Service 实现。
3. **对外契约稳定**：把参数校验、默认值、大小限制、返回整形都收敛到 mapper 层。

这和 `mcp-dev.md` 的经验完全一致，但不同的是，这次不再只是“参考一篇文章”，而是被强制编码进了当前变更的 plan。

### 3.5 review-plan：在编码前把关键边界前移

我觉得这次案例里很有代表性的一步，是 `review-plan`。

归档目录里的 `review.md` 显示，MixSpec 在方案阶段拉起了 5 类专家视角评审：

- Architecture Strategist
- Security Sentinel
- Performance Oracle
- Technical Depth Specialist
- Risk Analyst

最后结论是 `With Concerns`，原因不是方向错，而是几个边界还没有冻结：

- 输入载荷的具体形态
- 最大文件大小与同步调用边界
- 鉴权契约的具体实现
- Spring AI 版本兼容与启动级验证要不要前移

这一步特别像 harness 里的“预执行约束检查”：不是等代码写完以后再靠测试和事故兜底，而是在 plan 阶段就尽量把实现会踩的坑显式化。

### 3.6 sync：把过程中的修正变成可检索的工程记忆

这次 change 里最值得注意的，其实是两次 `sync_history`。

第一次 sync 记录的是：

- 原因类型：`acceptance_defect`
- 影响范围：`spec+plan+tasks`
- 结论：必须明确 MCP 成功时向调用方返回完整 markdown

第二次 sync 记录的是：

- 原因类型：`upstream_change`
- 影响范围：`spec+plan`
- 结论：根据已完成实现回写 base64 输入、payload 大小限制、固定 bearer token 鉴权和验证场景

这两次记录特别有价值，因为它们不是“事后写总结”，而是在工作流里即时沉淀。

这意味着以后做类似 MCP 化需求时，团队不只是能看到最后代码，还能知道：

- 哪些问题是 spec 阶段就应该冻结的
- 哪些问题是在评审或实现中暴露出来的
- 下一次应该提前在哪一步拦截

这已经非常接近复合工程的目标了：**过程知识不再丢失，而是回流到系统里**。

### 3.7 archive：让一次改造从“完成”变成“可复用”

最后，`archive` 把这次 change 变成了真正可复用的资产。

在 `meta.yaml` 里，归档不仅标记了 `status: archived`，还留下了：

- `archive_commit`
- `artifact_hashes`
- `patch_history`

在 MixSpec 的实现里，`archive` 还会联动 `verify`，并触发 auto-compound 生成 learnings。这一点非常关键：它让工作流的结束，不是“把文件挪到 specs 目录”，而是“把本次 change 的结果固定成未来可被检索、比对、演化的基线”。

所以回头看，这次 `multidoc-md` 的 MCP 服务化改造，真正有价值的并不只是完成了一个功能，而是完整跑通了这样一条链：

`已有经验文档 -> MixSpec intake -> spec 冻结契约 -> plan 固化结构 -> review 前移风险 -> apply 实施 -> sync 记录修正 -> verify/archive 形成基线`

而这条链，本质上就是一条 harness。

---

## 四、从 MixSpec 延伸到 Harness Engineering：它解决了什么，还缺什么

### 4.1 Harness 不只是“多 agent”，而是把工程现实编码进系统

一提到 harness，很多人第一反应会想到 DeerFlow 这样的 super agent runtime：

- sub-agents
- memory
- sandbox
- skills
- context engineering
- 长任务执行

DeerFlow 把自己定义成 `super agent harness`，这个定位很有代表性。它强调的是运行时层面的基础设施：给 agent 一台“真正的电脑”、独立上下文、长期记忆、技能按需加载、并行子代理。

但对大多数服务研发团队来说，harness 不一定必须先从“重运行时”开始。

MixSpec 提供的是另一条路线：先从**仓库内的 truth system** 开始，把以下东西版本化、结构化、流程化：

- 当前 change 的工作边界
- 当前阶段该读什么文档
- 当前方案有哪些约束和非目标
- 当前实现的完成标准是什么
- 当前变更的归档基线和后续演化如何追踪

这类 harness 不是替代 super agent，而是在更贴近日常服务开发的层面，把 AI 稳定接进工程现场。

### 4.2 MixSpec 现在最像什么样的 harness

如果用一句话概括，我会把 MixSpec 定义成：

> 一套以 `change + artifact chain + verification gates + learnings` 为核心的 harness 框架。

它已经解决了很多很难靠 prompt 单独解决的问题：

1. **工作单元清晰**：通过 `change` 避免任务漂浮在对话里。
2. **阶段产物稳定**：`spec / plan / tasks` 变成固定输入输出协议。
3. **一致性可治理**：`sync / verify / archive / drift` 让文档链和实现链尽量闭环。
4. **经验开始复利**：review、sync history、archive learnings 不再只是一次性输出。
5. **协作能力开始成形**：Epic、lineage、link 已经在向多人、多仓、多变更场景扩展。

### 4.3 但它也有明确边界

如果把 MixSpec 和 DeerFlow、Claude Code 这类更重的 harness 放在一起看，也能看到它当前的边界：

- 它更强在仓库内产物协议，不强在运行时调度。
- 它更强在工作流闭环，不强在长会话任务编排。
- 它更强在版本化工程资产，不强在通用执行环境和沙箱隔离。
- 它更强在“为 AI 准备轨道”，不强在“替 AI 构建完整操作系统”。

但这并不是缺点，反而恰恰说明它很适合日常服务开发：不需要先搭一个复杂 super-agent 平台，也能先把 SDD、验证和沉淀真正落地。

### 4.4 我对当前服务开发流程的几个思考

结合这次 MCP 改造实践，我对 MixSpec 在服务开发中的角色有几个更具体的判断。

#### 第一，MixSpec 最有价值的地方，不是生成文档，而是强化规范

对于服务研发来说，最难的通常不是“写代码”，而是：

- 需求边界什么时候锁定
- 外部接口主返回结构什么时候冻结
- 安全、容量、兼容性约束什么时候前移

MixSpec 的最大价值，是强迫这些信息在 spec 和 plan 阶段显式化，而不是等到 apply 才边写边补。

#### 第二，真实 ROI 来自 sync、verify、archive，而不只是 new、plan、apply

很多工具的演示都喜欢展示“几步生成代码”，但长期来看，真正决定体系成熟度的不是起步速度，而是闭环质量。

这也是为什么我越来越看重：

- `sync_history` 能不能形成工程记忆
- `verify` 能不能成为默认门禁
- `archive_truth` 能不能形成真实基线
- learnings 能不能在后续 change 里真正复用

#### 第三，下一步值得补的是 evidence，而不是更多“自动化幻觉”

如果继续沿着 harness 的方向演进，我觉得比“多加几个 agent”更重要的是补强 evidence：

- 在 plan 里显式写验证策略
- 在 tasks 里产出更清晰的测试与回归项
- 在 verify 里纳入更多构建、契约、联调证据
- 在多 repo 场景里增加接口契约一致性校验
- 在 archive 时沉淀更高质量的 learning 与 artifact 建议

真正的工程可控，不来自“模型看起来很聪明”，而来自“系统能持续证明它做的是对的”。

---

## 五、结语：MixSpec 的价值，不只是把 SDD 做起来，而是把 AI 接进真实工程链路

回头看，MixSpec 最初解决的是一个 practical SDD 的问题：如何把 `需求 -> 规格 -> 方案 -> 任务 -> 实施` 这条链跑顺。

但当这条链真的被 AI 执行起来之后，它自然会进入更深一层的问题域：

- 文档和实现如何保持一致
- 多次修正如何沉淀为过程记忆
- 归档后的真理源如何维护
- 多人、多仓、多 change 如何围绕同一个 truth 协作
- 如何让 agent 读懂项目，而不是只看聊天记录

这时候，MixSpec 就已经不再只是一个 spec 工具，而是在逐步长成一套 harness 基础设施。

对我来说，这也是它最有意思的地方：

- 它的起点是 practical SDD
- 它中途补齐的是执行闭环和一致性治理
- 它接下来要长成的，是多 agent、多 repo 条件下，把意图、上下文、约束和证据稳定组织起来的工程 harness

如果说过去软件工程最重要的资产是代码，那么在 AI 时代，更稀缺、也更能产生复利的，可能会越来越像是另外一组东西：

- 结构化的 spec
- 可执行的 workflow
- 明确的约束
- 可靠的验证链
- 可持续复用的工程记忆

代码当然仍然重要，但它越来越像结果，而不是全部。

而 MixSpec 真正让我觉得有价值的地方，正是在于它开始把这些东西，稳定地装进仓库、装进流程、装进团队的日常开发链路里。

## 参考&延伸阅读

- [复合工程(Compounding Engineering)](https://km.netease.com/v4/detail/blog/258277)
- [从可落地 SDD，到 Harness Engineer：我是如何重新理解 MixSpec 的](https://km.netease.com/v4/detail/blog/260949)
- [MixSpec：让 AI 时代的 SDD 真正跑起来](https://km.netease.com/v4/detail/blog/260230)
- Claude Code Overview: https://docs.anthropic.com/en/docs/claude-code/overview
- DeerFlow: https://github.com/bytedance/deer-flow
- OpenSpec: https://github.com/Fission-AI/OpenSpec
- Compound Engineering Plugin: https://github.com/EveryInc/compound-engineering-plugin
