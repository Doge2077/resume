# MixSpec 源码解析

## 前言

如果只从使用者视角看 MixSpec，很容易把它理解成一套 `/msx:*` 指令集合：`new`、`spec`、`plan`、`apply`、`verify`、`archive`，再加上一些 `sync`、`drift`、`search`、`compound` 之类的增强能力。

但当我真正去读它的本地源码之后，我对它的定位有了更明确的判断：MixSpec 的核心并不是“生成几份文档”，而是构造了一套**元数据驱动的工作流状态机**，并通过 skills 把这套状态机暴露给 agent-first 的使用方式。

更具体一点说，MixSpec 干了三件事：

1. 用 `change` 和 `meta.yaml` 定义工作边界与生命周期。
2. 用 `spec / plan / tasks / review / archive` 组织产物链与验证链。
3. 用 `Epic / lineage / link / learnings` 去触碰多人协作、多仓协作和长期复用的问题。

本文尝试从源码结构、流程控制、协作能力和横向对比几个角度，对 MixSpec 做一次系统拆解。

---

## 一、整体架构：一个以 change 为中心的 agent-first 工作流系统

### 1.1 包结构的第一印象：commands 很显眼，但 utils 才是骨架

本地安装的 MixSpec 版本是 `1.2.1`，入口包信息见 `package.json`。源码目录大体分成几层：

- `src/cli/`：CLI 入口
- `src/commands/`：工作流命令实现
- `src/utils/`：change、meta、git、epic、lineage、task-state 等基础设施
- `src/core/`：planning、learnings、policy、compound、figma 等领域能力
- `src/services/`：AI/生成/比对/编辑能力封装
- `src/skills/`：面向 IDE/agent 的 `SKILL.md`

如果只按文件夹名看，很像一个普通 CLI 工具。但细看之后会发现，MixSpec 的真正骨架其实在 `utils/` 和 `core/`：

- `commands/` 更像状态推进器
- `utils/` 才真正定义了 change、lineage、epic、rollback、tracked files、task state 这些关键概念
- `core/` 负责技术画像、经验索引、compound、policy 等“高阶能力”

这也是它和很多“命令式规范工具”的不同点：不是把业务逻辑都堆在命令里，而是把状态机和领域模型先立住。

### 1.2 CLI 很薄：它主动退出了“主工作流入口”的角色

读 `src/cli/index.ts` 时，一个非常明显的信号是：MixSpec 刻意让 CLI 变薄了。

CLI 只注册了三个命令：

- `init`
- `update`
- `migrate`

并且描述中直接写着：`init-only CLI for IDE workflows`。

这意味着开发者不再被鼓励通过传统 CLI 子命令去完成完整流程，而是先用 CLI 初始化项目，再把真正的日常工作流转交给 IDE 中的 `/msx:*` skills。

这是一种非常鲜明的产品选择：

- **CLI** 负责安装与分发
- **Skills** 负责人机交互和 agent 执行
- **本地 TS 能力** 负责状态与文件系统事实

换句话说，MixSpec 已经不再是一个“命令行工具优先”的产品，而是一个“agent-first，CLI 只做引导层”的系统。

### 1.3 init 的职责：不是初始化仓库，而是初始化一套 harness 地形

`src/commands/init.ts` 做的事情比一般脚手架要多得多。

它除了创建 `mixspec/` 的基本目录结构外，还会：

- 生成 `memory/config.yaml`
- 生成 `constitution.md`
- 初始化 `changes/`、`specs/`、`learnings/` 等目录
- 自动探测 IDE 并安装对应的 skills
- 补齐 learnings cache 等默认配置

这里很重要的一点是，`init` 并不是简单创建几个目录，而是在给 agent 准备一张“能工作的地图”：

- 记忆放哪
- 变化放哪
- 归档放哪
- 经验放哪
- agent 入口放哪

从 Harness Engineering 的视角看，这种“位置即语义”的组织方式，本身就是重要设计。

---

## 二、核心状态模型：文档只是产物，meta.yaml 才是状态机

### 2.1 change 是最核心的抽象

MixSpec 最核心的概念是 `change`。

每次变更不再只是聊天里的一个主题，或者 Git 里的一个 commit，而是 `mixspec/changes/<change-id>/` 下的一个独立工作单元。

这个工作单元至少包含：

- `meta.yaml`
- `spec.md`
- `plan.md`
- `tasks.md`
- `review.md`（可选）
- `artifacts/`

这层抽象很关键，因为它把“一个需求的一次开发生命周期”从对话和代码碎片里抽了出来，变成一个能被 agent 稳定解析、推进和归档的对象。

### 2.2 meta.yaml：MixSpec 的 system of record

真正让 MixSpec 像工作流系统而不是文档工具的，是 `meta.yaml`。

从源码和实际归档案例都能看出来，`meta.yaml` 挂载了大量核心状态：

- `status`
- `workflow.current_step`
- `workflow.steps_completed`
- `review.status`
- `spec_truth`
- `archive_truth`
- `sync_history`
- `branch / author / base_commit`
- `change_type`
- `epic`
- `claimed_modules`
- `lineage`

这意味着 MixSpec 的真实运行方式是：

- Markdown 文件负责承载“业务与方案内容”
- `meta.yaml` 负责承载“流程和治理事实”

这种分工非常聪明。因为如果把流程状态也写进 Markdown，就很难做稳定解析和状态推进；而如果完全没有结构化状态文件，整个系统又会退化成一堆会过期的说明文档。

### 2.3 “文档即状态机”的实现方式

很多工具只是“围绕文档工作”，而 MixSpec 更像是在把文档纳入状态机。

例如：

- `spec.md` 是 plan 的输入
- `plan.md` 是 tasks 的输入
- `tasks.md` 是 apply 的消费源
- `verify` 会同时查看任务状态、git 变更、tracked files 和 spec drift
- `archive` 会把归档 commit 与 artifact hash 固化为后续基线

所以这里的关键不是文档本身，而是**文档之间形成了一个被元数据驱动的输入输出协议**。

---

## 三、流程控制源码：从 new 到 archive，MixSpec 如何推动一条完整链路

### 3.1 new：创建工作单元，而不是简单生成目录

`src/commands/new.ts` 负责创建 change，但它并不是简单 `mkdir` 加模板写入。

它做了几件很关键的事情：

- 运行 `learnings`、`tech-profile`、`version` 等 preflight
- 判断 change 类型：`standard / epic-root / epic-child`
- 支持从多种输入材料解析 requirement、tech plan、design、notes
- 为 Epic 场景自动识别父子关系与模块认领
- 在某些模式下直接 fast-forward 到 `spec + plan + tasks`

这里最值得注意的一点，是 `new` 的目标不是“让用户写一句标题”，而是尽可能把 change 的上下文在入口阶段组织好。

这让后续所有步骤都不再是冷启动。

### 3.2 spec：把需求转成结构化规格，而不是继续留在聊天里

`spec` 命令会在没有 active change 时自动创建 change，并把需求转成结构化 spec。

在 `src/services/ai.ts` 里可以看到，MixSpec 的 spec 生成并不完全依赖外部模型。它有不少 `keyless` 逻辑：

- 标题提取与归一化
- FR block 解析
- 模板拼装
- risk heuristic
- section upsert

这透露出一个很重要的设计选择：**尽可能把确定性较高的部分本地化**。

这也是 harness 设计里非常值得借鉴的一点。不是所有事情都应该交给模型做，很多结构化、规则型、模板型任务完全可以在本地完成，从而降低模型耦合和不稳定性。

### 3.3 plan：plan 不是说明文，而是统一任务生产者

`src/commands/plan.ts` 的定位非常明确：

- 读取并校验当前 change 与 `spec.md`
- 运行 learnings preflight
- 运行 tech profile preflight
- 可选接管 Figma 结构化输入
- 生成 `plan.md`
- 自动生成 `tasks.md`
- 执行 plan lint 与风险软门禁

这意味着在 MixSpec 里，`plan` 不是一个“顺手写一下”的说明文档，而是整个执行阶段的统一生产者。

一个很好的设计点是：`tasks.md` 不在 `apply` 时临时拍脑袋生成，而是明确由 `plan` 阶段统一产出。这样，计划与实施之间形成了稳定协议，而不是“执行时再倒推任务”。

### 3.4 apply：按任务状态推进，而不是自由发挥

`src/commands/apply.ts` 的核心思路，是只消费 `tasks.md`。

它支持：

- 处理默认的第一个 pending task
- 指定执行某个 task
- 在 tasks 缺失但 plan 存在时自动补 tasks
- 在任务完成后更新 task 状态与 `meta.yaml`
- 所有任务完成后把当前 change 推进到 `archive`

这层设计让 `apply` 的角色很清楚：它不是再去重新理解一遍需求，而是围绕已经结构化的任务图推进实现。

这也是 agent 系统里很重要的分层原则：**越接近执行，输入就越应该稳定、明确、低歧义**。

### 3.5 verify：这是 MixSpec 真正开始像“工程系统”的地方

我认为 `src/commands/verify.ts` 是 MixSpec 最值得读的文件之一。

它做的事情远不只是“跑一下 lint 和 test”。从源码看，它会：

- 扫描归档后漂移（archived drift）
- 读取 policy profile，区分 `soft` 和 `hard`
- 统一执行 `eslint`、`tsc`、`npm test`
- 检查 tasks 完成度
- 读取 git diff
- 基于 tracked files 和 `compareSpecVsCode()` 做 spec drift 检查
- 处理 skip / override / follow-up / restore 等分支

而且它对归档文档漂移的处理非常工程化：

- 恢复归档文档到基线
- 新建 follow-up change 继续演化
- 接受当前内容并重写 baseline
- 跳过

这已经不再是“检查一下质量”，而是在做一套带治理策略的工程门禁。

### 3.6 archive：把归档变成基线固化与学习提取

`src/commands/archive.ts` 则把 MixSpec 的另一层价值做实了。

它在归档时会：

- 先调用 `verify`
- 重新对齐 spec 和代码关系
- 检查分支状态
- 记录 `archive_commit`
- 计算并保存 `artifact_hashes`
- 归档到 `mixspec/specs/<change-id>/`
- 自动生成 learnings
- 给出 artifact advisor 建议

这里面最关键的是 `archive_truth`。这使得归档不是“把目录挪走”，而是“记录一个可被未来验证的真实基线”。

这就为后续的 `drift`、`follow-up`、`patch history` 和知识沉淀，提供了可靠基础。

### 3.7 sync：不是编辑器，而是可回滚的级联同步器

`src/commands/sync.ts` 也非常值得单独拎出来说。

很多工具里的 sync 只是“改一下文档”，但 MixSpec 的 sync 是带事务感的：

- 先让用户描述修改意图
- 通过 `applyEditToFile()` 生成编辑后的候选结果
- 让用户确认
- 分析级联影响
- 自动更新下游文档
- 记录 `sync_history`
- 通过 `withFileRollback()` 支持失败回滚

而且它对 `spec -> plan -> tasks` 的联动是递归触发的。例如修改 `spec` 后，如果 `plan.md` 真发生变化，还会继续分析对 `tasks.md` 的影响。

这已经很像一个轻量版“文档事务系统”了。

---

## 四、协作能力：Epic、lineage、link 如何把单人工作流扩展到多人和多仓场景

### 4.1 Epic：MixSpec 当前最完整的协作模型

在本地源码中，协作能力里实现最扎实的是 `Epic`。

`new.ts`、`epic.ts`、`epic-state.ts` 共同构成了一套父子变更模型：

- `epic-root`：父 Epic，负责总规格、总计划、模块地图与全局约束
- `epic-child`：子变更，认领模块后独立闭环
- `claimed_modules`：每个子 change 声明自己负责哪些模块

`epic.ts` 做的事情尤其有意思。它不是简单要求用户手工维护模块地图，而是尝试从 requirement、tech plan、design、notes 等 source inputs 中抽取协作模块信号，自动推导模块候选。

这说明 MixSpec 对协作问题的理解，不是“多一个父目录”这么简单，而是试图让协作边界也结构化。

### 4.2 Epic 收口条件：ready 不是一句口头判断，而是可计算状态

`src/utils/epic-state.ts` 进一步把 Epic 的收口逻辑做成了可计算状态：

- 父 Epic 是否存在 `spec.md` 和 `plan.md`
- 是否已经生成模块地图
- 子 change 是否存在
- 是否还有未归档子 change
- 是否有未认领模块
- 是否有重复认领或无效认领

最后汇总成：

- `blockingReasons`
- `ready`

这其实是一个非常“工程系统化”的做法。很多团队里 Epic 收口全靠人脑和会议，而 MixSpec 则把它变成了仓库内可计算的状态。

### 4.3 lineage：解决“归档之后还要继续改”的现实问题

很多规范工具有个理想化假设：归档就是结束。

但真实项目里，归档之后继续修改是常态。MixSpec 对这个现实的回应，是 `lineage`。

`src/utils/lineage.ts` 定义了一套 lineage 模型：

- `root_id`
- `previous_id`
- `mode`（`follow-up` 或 `reopen`）
- `version`

它会扫描 `changes/` 与 `specs/`，计算同一演化链上的节点，并判断当前 change 是否已经落后于更高版本 head。

这就让 MixSpec 能够处理一种非常常见但很多工具都没认真解决的场景：

- 一个 change 归档了
- 后续发现需要补丁、继续演化或重开
- 系统如何知道它和原 change 的关系
- 如何避免从旧分支上盲目继续分叉

这套 lineage 设计并不复杂，但非常实用。

### 4.4 link：多仓协作主要不在 TS 命令层，而在 skill 层协议化完成

MixSpec 的多仓协作能力 `link` 很特别。

从本地源码看，它并没有主要实现在 TypeScript `commands/` 里，而是写在 `src/skills/mixspec-link/SKILL.md` 中，以 `MSX_LINK::{repo}|{branch}|{change_path}` 作为跨仓共享协议。

`share / join / update` 的核心思路是：

- 分享当前 change 的 requirement context 与 interface contracts
- 拉取远端 Markdown 产物快照
- 生成 AI summary
- 回填本地 `External Dependencies`
- 对本地 `spec / plan / tasks` 做 gap analysis

这是一种非常 agent-first 的实现方式。它说明 MixSpec 对多仓协作的理解，不是“先造一个复杂分布式状态中心”，而是先把跨仓协作压缩成一套最小共享协议。

### 4.5 workspace / monorepo：当前更多是“感知式支持”而不是统一调度器

`src/core/planning/repo-inventory.ts` 负责读取项目技术画像：

- `package.json` 依赖
- lockfile
- workspaces
- tsconfig/jsconfig alias
- module roots

它的作用主要是为 `plan`、`tech-profile`、`plan lint` 等能力提供上下文。

这说明 MixSpec 对 monorepo / workspace 的支持，目前更偏“感知式”：它能识别项目地形，但还没有发展成 DeerFlow 那种更强的运行时级多工作区调度器。

这也是 MixSpec 的一个很清晰的产品边界。

---

## 五、AI 能力实现：刻意的 keyless fallback，是一个很值得重视的设计选择

### 5.1 services/ai.ts 透露出的思路

读 `src/services/ai.ts` 时，一个非常强烈的感受是：MixSpec 并没有把“AI”这件事做成对外部模型的强依赖。

在这个文件里可以看到很多能力是本地启发式、模板式和字符串处理式实现的，例如：

- `generateSpec`
- `scoreRequirement`
- FR 提取
- 标题归一化
- spec drift 对比辅助逻辑
- section upsert

也就是说，MixSpec 的很多“智能”并不是来自远端大模型，而是来自对工程问题的结构化拆解。

### 5.2 这意味着什么

我觉得这点非常值得写进所有 agent 工程类系统的设计原则里：

> 能确定的就本地确定，必须生成的再交给模型生成。

这样做有几个直接好处：

- 降低外部模型耦合
- 降低成本与不稳定性
- 提高结果可预期性
- 让 verify、sync、archive 这类核心治理环节更容易做成可验证系统

从 Harness Engineering 的角度看，这比“把一切都扔给模型”更成熟。因为 harness 的职责本来就不是盲目信任 agent，而是构造一个既能利用 agent，又能控制 agent 的系统。

---

## 六、与 OpenSpec、compound-engineering-plugin 的对比：MixSpec 处在什么位置

### 6.1 与 OpenSpec 的对比：MixSpec 更重闭环与治理

OpenSpec 的公开定位非常明确：

- `fluid not rigid`
- `iterative not waterfall`
- `built for brownfield`
- artifact-guided workflow

它强调 proposal/spec/design/tasks 的轻量流转，避免把 SDD 做成过重流程。从理念上看，MixSpec 和 OpenSpec 的出发点其实很近，都在尝试让 spec-first 真正适应真实开发。

但源码与能力形态上的差异也很明显：

- **OpenSpec 更强调轻量 artifact workflow**
- **MixSpec 更强调闭环治理和仓库内基线**

具体来说，MixSpec 在以下几个维度明显更重：

- `verify` 的统一质量门禁
- `archive_truth` 的归档基线完整性
- `sync_history` 的过程沉淀
- `drift` 的归档后健康扫描
- `Epic / lineage` 的协作与演化模型

所以如果把两者放在同一坐标系里，我会说：

- OpenSpec 更像轻量、开放、可快速上手的 artifact-guided SDD
- MixSpec 更像把 SDD 往工程治理和 harness 方向继续推进了一层

### 6.2 与 compound-engineering-plugin 的对比：MixSpec 更聚焦仓库内 truth，compound 更聚焦 agent 生态

Every 的 `compound-engineering-plugin` 则是另一种风格。

它的 README 里直接给出了一个很完整的插件生态：

- 20+ commands
- 20+ skills
- 28 agents
- MCP servers
- 跨 Claude Code、OpenCode、Codex、Kiro、Copilot、Gemini、Windsurf 等多工具分发能力

它更像一个 agent 能力市场和复合工程操作系统，重点在：

- brainstorm / plan / work / review / compound 的复合循环
- 多 agent 并行研究和评审
- 跨工具格式转换与同步
- 团队知识不断复利

和它相比，MixSpec 更“收敛”，也更“仓库内”：

- 它没有那么重的 agent market 形态
- 也没有把重点放在多工具生态转换上
- 它把最强的能力投注在 change、meta、verify、archive、lineage、epic、link 这些与工程事实直接相关的部分

如果做个简单归纳：

- **OpenSpec**：轻量 spec workflow
- **MixSpec**：spec workflow + verification + collaboration harness
- **compound-engineering-plugin**：agent ecosystem + compounding workflow

这三者不是简单替代关系，更像是三个不同重心的设计选择。

---

## 七、我对 MixSpec 架构的总体评价

### 7.1 它最强的地方：把“规范”做成了“状态与基线”

我觉得 MixSpec 最值得肯定的地方，是它没有停留在“规范模板”层面，而是把规范真正做成了状态与基线系统。

这体现在：

- `meta.yaml` 作为工作流事实中心
- `verify` 作为统一门禁
- `archive_truth` 作为归档基线
- `sync_history` 作为过程记忆
- `lineage` 作为归档后演化关系

这几件事加起来，才使它具备了 harness 的味道。

### 7.2 它最鲜明的产品判断：CLI 极瘦，skills 极厚

这是我在源码里最喜欢的一个产品决策。

很多工具会持续给 CLI 加子命令，但 MixSpec 反过来，把 CLI 减到只负责：

- 初始化
- 更新
- 迁移

真正的工作流通过 skills 注入 IDE，由 agent-first 方式执行。

这非常符合今天 AI 工程工具的现实：命令只是分发层，工作流才是核心产品。

### 7.3 它目前还可以继续加强的地方

当然，从源码现状看，它也还有很明显的演进空间：

1. **verify 的证据类型可以更丰富**
   - 当前更多是 lint/type/test/task/spec drift
   - 后续可以更系统纳入 integration、contract、UI artifact、performance evidence

2. **多仓协作仍偏 skill 协议层**
   - `link` 已经很好地定义了最小协作协议
   - 但还可以继续增强成更强的 contract verification 和 cross-repo gate

3. **workspace 仍偏感知式**
   - 技术画像与 monorepo 感知已经有了
   - 但尚未完全发展成更强的多 repo 执行编排层

4. **AI 层可以继续保持“可替换”**
   - 当前 keyless fallback 是优点
   - 后续如果引入更强模型能力，也要保持这层工程控制，不要重新退化成 prompt-first 工具

---

## 八、结语：MixSpec 本质上是在把 AI 需要的工程轨道编码进仓库

读完源码之后，我对 MixSpec 的理解比之前更明确了一些。

它表面上当然是在做：

- `new`
- `spec`
- `plan`
- `apply`
- `verify`
- `archive`

但这些命令背后真正重要的，不是用户看到的动作，而是系统在仓库里编码进去的那套事实：

- 当前 change 是什么
- 当前处于哪个步骤
- 哪些文档是上游输入
- 哪些实现已经偏离规格
- 这次归档的基线是什么
- 这个 change 和之前版本是什么关系
- 多人协作时模块边界如何被定义

当这些东西被稳定编码进仓库之后，agent 才第一次真正拥有了一张“可读地图”，而不只是几句 prompt 和一段上下文。

这也是为什么我会把 MixSpec 看成一个正在长成中的 harness 基础设施：

- 它的起点是 practical SDD
- 它的核心能力是产物链、验证链和基线治理
- 它的演进方向是多人、多仓、长期记忆条件下的 agent legibility

从这个意义上说，MixSpec 的源码最有价值的地方，不是它做了多少命令，而是它正在尝试回答一个越来越重要的问题：

> 当“人类掌舵，智能体执行”开始成为真实的软件工程组织方式时，仓库应该如何承载意图、上下文、约束、证据与记忆？

我觉得，MixSpec 已经给出了一份相当值得研究的答案。

## 参考与源码入口

- 本地源码：`C:\Users\liys05\scoop\persist\nodejs24\bin\node_modules\@bedrock\mixspec\src\cli\index.ts`
- 本地源码：`C:\Users\liys05\scoop\persist\nodejs24\bin\node_modules\@bedrock\mixspec\src\commands\new.ts`
- 本地源码：`C:\Users\liys05\scoop\persist\nodejs24\bin\node_modules\@bedrock\mixspec\src\commands\verify.ts`
- 本地源码：`C:\Users\liys05\scoop\persist\nodejs24\bin\node_modules\@bedrock\mixspec\src\commands\archive.ts`
- 本地源码：`C:\Users\liys05\scoop\persist\nodejs24\bin\node_modules\@bedrock\mixspec\src\commands\sync.ts`
- 本地源码：`C:\Users\liys05\scoop\persist\nodejs24\bin\node_modules\@bedrock\mixspec\src\utils\epic.ts`
- 本地源码：`C:\Users\liys05\scoop\persist\nodejs24\bin\node_modules\@bedrock\mixspec\src\utils\epic-state.ts`
- 本地源码：`C:\Users\liys05\scoop\persist\nodejs24\bin\node_modules\@bedrock\mixspec\src\utils\lineage.ts`
- 本地源码：`C:\Users\liys05\scoop\persist\nodejs24\bin\node_modules\@bedrock\mixspec\src\skills\mixspec-link\SKILL.md`
- OpenSpec: https://github.com/Fission-AI/OpenSpec
- Compound Engineering Plugin: https://github.com/EveryInc/compound-engineering-plugin
- DeerFlow: https://github.com/bytedance/deer-flow
