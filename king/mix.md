适用范围：1.2.2
工作模式：agent-first + skills-only。CLI 仅用于 mixspec init / mixspec update，其余流程通过 IDE Skills 执行。
私货：如果想在不同项目、不同 AI 工具之间保持一致的开发规范和工作流程，可以使用https://skills.netease.com/skills/skill_99b7af2aa2de
设计与架构：MixSpec 设计与架构
KM：https://km.netease.com/v4/detail/blog/260949
多人协作开发（1.1.0以上）：Mixspec下的多人协作开发模式 Epic
多仓库协作（1.2.0以上）：实现 MixSpec 多仓库协同 Link 功能（Multi-repo Link）| https://km.netease.com/v4/detail/blog/260919
1. MixSpec 是什么
MixSpec 是一套面向日常开发的 Spec-First SDD 工作流。核心目标不是"多一层文档"，而是把以下链路稳定跑通：
需求 -> 规格(spec) -> 方案(plan) -> 任务(tasks) -> 实施(apply) -> 验证(verify) -> 归档(archive)
同时用 sync / review-plan / drift / learnings 把"迭代中反复修改"纳入同一套闭环，而不是散落在聊天记录里。
2. 安装与初始化
2.1 安装
npm install -g @bedrock/mixspec --registry=https://npm.nie.netease.com/
2.2 初始化
1.1.0版本开始，支持 -g 命令，支持全局初始化，不在需要每个文件都去init了。
init的本质是在当前仓库的.codemaker下新建一个skills目录。但是codemaker（cursor、codex等）其实可以去读全局的.claude下的skills的，所以直接全局装就好了。
// 单个仓库初始化
mixspec init

// 全局初始化，注意-g安装后，后续update也需要加 -g
mixspec init -g
初始化会完成：
创建 mixspec/ 目录结构（memory/changes/specs/learnings/...）
生成基础 constitution.md 与 config.yaml
为已选择的 IDE 安装 msx-* Skills（如 .cursor/skills/、.claude/skills/ 等）
不再分发旧的 commands 模板，所有能力统一通过 /msx:* Skills 触发
2.3 Skills 更新（可选）
当你升级 MixSpec 版本，或需要重新生成/清理 IDE Skills 时，使用：
// 单个仓库更新
mixspec update

// 全局更新
mixspec update -g
典型场景：
之前安装过旧版 commands 模板，需要迁移到 skills-only 方案
新增/更换 IDE，希望重新注入完整的 msx-* Skills 集合
2.4 openspec/speckit 迁移
/msx:migrate
执行后，agent 会引导你选择 OpenSpec 或 Speckit 作为来源，调用 CLI 完成结构迁移，并基于旧项目的上下文文件智能合并 mixspec/memory/constitution.md，一步完成迁移与规约对齐。
3. 命令触发方式
环境触发格式示例Agent/msx:<command>/msx:plan
说明：所有命令都是通过skills注入被agent识别
4. 目录结构与数据文件
your-project/
├── mixspec/
│   ├── memory/                      # 项目配置与上下文快照
│   │   ├── config.yaml              # MixSpec 项目配置（类型、语言、工具链、自定义路径）
│   │   ├── constitution.md          # 项目开发宪章与工作流约束（标准/红线）
│   │   ├── tech-profile.json        # 技术画像缓存（依赖/目录/前后端画像）
│   │   └── learnings-index-cache.json # 经验索引缓存（加速搜索，不手改）
│   ├── changes/                     # 进行中的变更（工作区）
│   │   └── <change-id>/
│   │       ├── meta.yaml            # 工作流状态、spec_truth、archive_truth 与 sync 历史
│   │       ├── spec.md              # EARS 规格（What，要做什么）
│   │       ├── plan.md              # 技术方案（How，怎么做）
│   │       ├── tasks.md             # 实施任务清单（Apply/FF 的任务图来源）
│   │       ├── review.md            # 方案/实现评审记录（可选）
│   │       └── artifacts/           # 附件产物（截图、报告、日志等）
│   ├── specs/                       # 已归档的变更（历史基线）
│   │   └── <archived-change>/       # 归档后的 spec/plan/review/meta 等快照
│   ├── learnings/                   # 知识库
│   │   ├── raw/                     # auto-compound 输出（按 change 维度，零摩擦）
│   │   ├── workflow-issues/         # 按 problem_type 分类（详见下方枚举）
│   │   ├── design-patterns/
│   │   ├── build-errors/
│   │   ├── runtime-errors/
│   │   ├── ...（共 12 个 problem_type 目录）
│   │   ├── patterns/
│   │   │   └── critical-patterns.md # 高频关键模式（检索 3x 权重）
│   │   └── schema.yaml              # 枚举定义与校验规则
│   └── audit.log                    # 审计日志（命令执行与关键决策）
关键文件职责：
meta.yaml：工作流状态、sync 历史、spec_truth、archive_truth，以及 branch/author/base_commit、workflow.environment 与每步 steps_completed[].model/duration_sec 等可观测字段
spec.md：EARS 规格（What）
plan.md：技术方案（How）
tasks.md：实施任务清单（Apply 消费源）
5. 标准开发链路（推荐）
5.1 【必须】前置：补充宪章
/msx:constitution
作用：在保留核心原则的前提下，自动更新 mixspec/memory/constitution.md 的项目上下文章节。
5.2 new：创建 change（含 Epic）并选择下一步
/msx:new "实现用户导出列表功能"
当前实现行为（v1.1）：
执行 learnings preflight、tech profile preflight
检查是否已存在同名活跃 change（幂等保护，防止重复创建）
创建 mixspec/changes/<id>/meta.yaml，写入 branch/author/base_commit/workflow.environment
通过上下文自然语言判断 change 类型（standard / epic-root / epic-child），填入 change_type
对 Epic：
父 Epic：可一次性摄入需求文档、技术方案与约束，生成 epic_root.modules[] 模块地图
子 change：可挂到父 Epic（epic.parent_id）并声明 claimed_modules[]
给出下一步选项：ff / spec / brainstorm / manual
说明：
change ID 编号基于 changes/ 与 specs/ 中最大数字自动递增，避免重用已归档编号。
你可以直接选 spec，进入标准链路；也可以选 ff 一次生成 spec+plan+tasks。
5.3 spec：生成 EARS 规格（支持自动补 new）
/msx:spec
当前实现行为：
如果无 active change，会自动创建 change（不会强制你先手动 new）
生成 spec.md
如果设计引用可桥接到宿主文件或 env，会自动接管 Figma 上下文并写入 meta.spec_truth.figma_intake、artifacts/figma/intake-report.latest.json
更新 meta.workflow.current_step = plan
5.4 plan：生成方案 + 统一生成 tasks
/msx:plan
当前实现行为（v0.9）：
校验/解析 change 目标（多 change 时列出所有选项让用户选择，不自动取第一个）
若没有标准 active change，但存在"孤立 spec"，会自动规范化：
先创建标准 change 目录
迁移该 spec
再继续生成 plan
加载 learnings preflight
执行 tech profile preflight（缓存/增量/全量）
若存在 Figma 输入：优先执行宿主接管与 intake 复用；CodeMaker 场景优先读取工作区 .codemaker/cmtmp/，可桥接时落 plan-summary.md 等结构化产物
生成 plan.md
自动生成 tasks.md（plan 是 tasks 的统一生产者）
执行 plan lint（仓库画像外依赖告警/高风险软门禁）
给出下一步建议：mixspec review-plan 或 mixspec apply
说明：
- Figma 结构化接管优先增强可桥接宿主；纯会话上下文场景仍可由 agent 直接消费，但 MixSpec 不保证一定落盘结构化 report。
- epic-child 在自身无本地设计输入时，可回退复用 parent/root 的 intake 结果，而不是只能依赖当前会话上下文。
5.5 review-plan：多专家评审
/msx:review-plan
当前实现行为：
5 位评审器：架构、安全、性能、技术深度、风险
执行策略自动探测：
可并行时走 agent-parallel
不可并行降级 agent-sequential
再降级 rule-parallel
输出 review.md
在 meta.workflow.steps_completed 记录 review
5.6 apply：按 tasks 推进实施
/msx:apply
# 或执行指定任务
/msx:apply 3
仅消费 tasks.md，不会在此阶段再生成任务
若 tasks.md 缺失但 plan.md 存在，自动从 plan 生成 tasks，不中断流程
每次处理一个 task（默认第一个 pending）
可选结果：done-validate / done-skip / skip / later
done-validate 会执行 lint/type/test（可用则跑）
所有 task 完成后自动更新 meta.yaml：status: implemented，current_step: archive
5.7 sync：修改文档并级联
/msx:sync
级联关系：
级联修改 spec 、 plan、 tasks
同时记录 sync_history（原因类型、应拦截阶段、影响范围、预防建议）。
5.8 verify：统一验证与软/硬门禁
/msx:verify
当前实现行为：
lint/type/test 检查
tasks 完成度检查
spec drift 风险检查（含 tracked_files 重叠判定）
根据 policy.mode=soft|hard 决定阻断策略
对归档漂移提供处理：restore / follow-up / keep / skip
5.9 archive：归档并自动沉淀 learnings
/msx:archive
先执行 verify（按策略）
Baseline Integrity Gate（硬门禁）：检查 archive_truth.archive_commit 与 artifact_hashes，若缺失则自动填充，填充失败则阻断归档
分支校验：若 meta.branch 与当前 git 分支不一致，会提示选择「使用当前分支 / 使用 meta.branch / 手动输入分支名 / 取消」，最终选择会写入 archive_truth.branch_at_archive
归档 change 到 mixspec/specs/<id>/
写入 archive_truth（commit/hash 基线与归档分支）
Auto-compound 写入 learnings/raw/<change-id>.md，同时按 problem_type 分类
给出 artifact advisor 建议（pattern/link/checklist/skill 提案等）
5.10 drift：归档后健康检查
/msx:drift
作用：扫描 mixspec/specs 中归档内容与 archive 基线偏移。
5.11 search：检索经验
/msx:search "关键词"
learnings/patterns/critical-patterns.md → 3x 权重
learnings/{problem_type}/ 精心整理的文档 → 2x 权重
learnings/raw/ auto-compound 输出 → 1x 权重
兼容：learnings/notes/（旧文件保持可用）、docs/solutions/
可扩展：learnings.extra_paths
6. FF 快速链路
/msx:ff "需求描述"
FF 会自动执行：
需求评分
创建 change
生成 spec.md
生成 plan.md
自动 review-plan
生成 tasks.md
构建任务依赖图并给出执行模式（auto/manual/standard）
适用：需求边界清晰、希望快速推进。
7. Epic 协作与多人开发（v1.1）
7.1 什么时候用 Epic
满足任一条件就考虑创建 Epic：
一个需求需要 2 人及以上 同时开发
已经有完整的需求文档、技术方案，希望沉淀为总规格
需要拆成多个可独立归档的 change
普通单人小需求直接：
/msx:new "需求描述"
7.2 父 Epic：作为总规格与协作锚点
示例：
/msx:new "支付中心重构二期，作为父 Epic"
推荐在父 Epic 中完成：
spec.md：目标 / 范围 / 非目标 / 模块地图 / 全局约束
plan.md：模块拆分、协作边界、分支与合并策略
meta.yaml.epic_root.modules[]：M01/M02/... 模块定义（由系统从输入材料中自动提议，可手动调整）
父 Epic 不承载大块具体实现，更像「总控」：
只做总 spec / 总 plan / 模块地图 / 全局约束
不直接拆个人任务，不直接做大范围代码改动
7.3 子 change：认领模块并独立闭环
每个开发者从父分支切自己的分支后，在自己的工作目录中创建子 change：
/msx:new "挂到 Epic 021-payment-center-phase2，认领 M01，目标是先整理路由和入口层"
当前实现会：
校验父 Epic 是否存在且未归档
在子 change 的 meta.yaml 写入：
change_type: epic-child
epic.parent_id: "021-payment-center-phase2"
claimed_modules: ["M01"]（可多个）
在父 Epic 的 status 视图中展示父子关系与认领情况
每个子 change 在自己的目录中独立跑完整链路：
/msx:spec
/msx:plan
/msx:apply
/msx:verify
/msx:archive
团队约定（推荐）：
一个子 change=一个分支或一个 worktree
子 change 先归档，父 Epic 后归档
7.4 父 Epic 看整体进度
在父 Epic 的工作目录中执行：
/msx:status
可看到：
Epic Children：所有子 change 的状态（active / implemented / archived）
Children: N total, X archived, Y active
Readiness 与 Epic blockers（例如：还有子 change 未归档、模块有人未认领/重复认领等）
通常的收口顺序：
所有子 change archive 完成
回到父 Epic：
/msx:sync
/msx:verify
/msx:archive
8. Learning 体系
8.1 problem_type 枚举
枚举目录覆盖场景build-errorbuild-errors/编译、构建、打包失败runtime-errorruntime-errors/运行时异常、崩溃test-failuretest-failures/测试不通过、回归performance-issueperformance-issues/慢、内存泄漏、资源瓶颈logic-errorlogic-errors/业务逻辑错误、条件判断integration-issueintegration-issues/API 对接、第三方服务ui-ux-issueui-ux-issues/样式、交互、布局config-issueconfig-issues/配置、环境、依赖版本workflow-issueworkflow-issues/开发流程、工具链、CI/CDdesign-patterndesign-patterns/架构、设计模式、最佳实践security-issuesecurity-issues/安全漏洞、权限、数据泄露documentation-gapdocumentation-gaps/文档缺失、误导、过时
8.2 双层 Compound 模式
Auto-compound（归档时自动）：写入 raw/，按 change 维度，零摩擦
Manual compound（手动精炼）：运行 /msx:compound，写入对应 {problem_type}/ 目录，支持一个 change 拆出多个 learning 文件，模板包含 Root Cause / What Didn't Work / Prevention 深度内容
9. 命令速查（当前版本）
命令核心作用典型产物new新建 change（含幂等保护，支持 Epic）changes/<id>/meta.yamlspec生成 EARS 规格（可自动补 new，支持 Epic 模式）spec.mdplan生成技术方案并统一产出任务plan.md + tasks.mdreview-plan多专家评审计划review.mdapply执行任务（缺 tasks 时自动补生成）tasks.md 状态更新 + meta 自动更新sync编辑并级联同步文档，归档后支持 patch/new/reopenspec/plan/tasks + sync_history + lineageverify质量检查 + 一致性门禁verify 结果 + spec_truth 更新archive归档（含基线硬门禁）+ 沉淀 learningsspecs/<id>/ + raw/ learningstatus查看当前 change/Epic 进度与风险状态摘要（含 Epic Children / Epic blockers）drift扫描归档偏移健康报告constitution补全项目宪章上下文constitution.mdbrainstorm需求澄清对话澄清结果search检索 learnings（分层权重）匹配结果compound手动深度沉淀（写入分类目录）{problem_type}/ learningmigrate迁移 openspec、speckit 历史文档change 下或者 specs 下内容，更新 constitution.mdlink多仓库接口契约共享（share / join / update）links/<repo-slug>.md + meta.yaml.links
10. 配置项（mixspec/memory/config.yaml）
常用字段：
policy:
  mode: soft # or hard

metrics:
  enabled: false
  log_file: mixspec/memory/metrics.log

learnings:
  include_legacy: true
  extra_paths: []
  cache:
    enabled: true
    file: mixspec/memory/learnings-index-cache.json
建议：
日常开发用 soft，发布前可临时切 hard
团队有项目知识库时，把路径放入 extra_paths
11. 最佳实践
复杂需求默认走：new -> plan -> review-plan -> apply
每次实现后如果需求/方案发生变化，优先 sync 再继续
归档前固定执行 verify
定期运行 drift，避免归档文档长期失真
把验收期补充项都记录为 sync_history，为后续检索和建议提供数据
auto-compound（raw/）零摩擦沉淀；重要 pattern 手动运行 compound 精炼到分类目录
12. 推荐起手顺序（新项目）
mixspec init
/msx:constitution "请补充项目背景、技术栈与团队约定"
/msx:new "你的第一个需求"
根据提示进入 spec/plan/review-plan/apply/verify/archive
13. 常见问题
1、如何修改已经归档的文档
目前没有强制禁止修改归档文档，实际开发的时候，很容易碰到了归档了之后，还有修改的情况，所以目前主要有两个建议
1、直接使用/msx:sync [change-id] "描述你的改动", 之后会进行archive patch、reopen、follow-up的推荐逻辑。2、归档时机，封板发布前进行归档~。比如周三晚上封板，周四发布，那就在周三封板的时候进行归档
2、出现实现还是没有遵循宪章等
确定下mixspec版本，1.1.1版本以上在apply的时候会强制去读取memory下的配置文件。之前的都是弱引用~
