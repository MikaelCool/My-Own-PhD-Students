# 用《工程控制论》重构 My-Own-PhD-Students 的演化计划

## 目标

把 `My-Own-PhD-Students` 从“能自动跑科研流程的系统”升级成“可观测、可诊断、可恢复、可优化的自动化科研控制系统”。

核心思想来自钱学森《工程控制论》：

- 以建模为起点。
- 以反馈闭环为核心。
- 以滤波/预测支撑决策。
- 以最优控制处理 token、时间、GPU、质量之间的折中。
- 以组织管理思想治理多组件协作。

## 当前系统的控制论诊断

### 已有基础

- 已有 23-stage 状态机，说明系统已经具备离散阶段控制骨架。
- 已有 checkpoint、heartbeat、stop request、rollback 逻辑，说明系统开始具备状态保持能力。
- 已有 stage skill map 与 skill feedback，说明系统已经出现“中层控制策略”的雏形。
- 已有 OpenClaw bridge，说明系统已经具备外部执行器与消息接口。

### 主要缺口

- 缺少统一状态空间模型。
- 缺少运行态观测器，很多判断仍然直接依赖原始日志。
- 缺少显式控制目标函数，导致质量、token、时间之间经常凭经验权衡。
- 缺少模式化控制律，尤其 Stage 9-13 对不同失败类型的响应还不够分层。
- 缺少真正的总体设计部视角，OpenClaw、skills、pipeline 还没有形成统一控制架构。

## 演化总架构

建议把系统收敛成五层：

### 第一层：受控对象层

这里是被控制的实际科研过程：

- 文献搜集与筛选
- 假设生成
- 实验设计
- 代码生成与修复
- 实验执行
- 结果分析
- 论文生成与修订

### 第二层：观测层

负责把原始运行信号转成可用于决策的状态估计：

- stage progress observer
- session health observer
- GPU/resource observer
- dataset readiness observer
- artifact integrity observer
- evidence coverage observer
- notification delivery observer

### 第三层：控制层

负责基于状态做决策：

- pipeline governor
- retry / repair / refine / pivot policy
- skill selection policy
- prompt compression policy
- resource scheduling policy

### 第四层：执行层

负责把控制动作落实：

- Codex CLI / ACP backend
- OpenClaw gateway
- 本地 shell / python / docker / sandbox
- webhook / 飞书通知
- dataset downloader / GPU allocator

### 第五层：监督层

负责高层目标与例外审批：

- 用户
- HITL gate
- quality gate
- stage review board

## 三条主演化线

## 落地到现有代码模块

为了避免这份计划停留在概念层，下面给出与当前仓库模块的直接对应关系：

### pipeline 控制骨架

- `researchclaw/pipeline/runner.py`
  - 适合落地统一 `run_control_state.json`
  - 适合统一 stop / continue / backend switch 的控制动作写入
- `researchclaw/pipeline/executor.py`
  - 适合落地 stage 级 observer 汇总
  - 适合把 retry / repair / refine / pivot 收敛成标准动作
- `researchclaw/pipeline/stages.py`
  - 适合补充模式切换规则、积分约束和控制动作枚举

### Stage 9-13 高风险区

- `researchclaw/pipeline/code_agent.py`
  - 适合落地 Stage 10/13 的块级修复、模式控制、上下文压缩输入
- `researchclaw/pipeline/stage_impls/_experiment_design.py`
  - 适合落地 experiment adequacy rubric 和 design observer
- `researchclaw/pipeline/stage_impls/_execution.py`
  - 适合落地 dataset readiness、GPU availability、runtime watchdog
- `researchclaw/pipeline/experiment_diagnosis.py`
  - 适合沉淀 failure taxonomy 和结构化诊断包
- `researchclaw/pipeline/experiment_repair.py`
  - 适合沉淀 repair taxonomy 和局部修复控制律

### 文献与证据控制

- `researchclaw/pipeline/stage_impls/_literature.py`
  - 适合落地 literature breadth / evidence coverage observer
- `researchclaw/pipeline/stage_impls/_synthesis.py`
  - 适合落地 gap quality observer 和 hypothesis support score
- `researchclaw/pipeline/stage_impls/_analysis.py`
  - 适合落地 result-analysis observer 与 evidence sufficiency 判定

### skill 中层

- `researchclaw/metaclaw_bridge/stage_skill_map.py`
  - 适合从静态映射升级到 policy mapping
- `researchclaw/metaclaw_bridge/skill_feedback.py`
  - 适合增加 token / wall time / quality_gain / rollback_risk 指标
- `researchclaw/skills/registry.py`
  - 适合引入 preconditions、conflict_skills、expected_gain 等元数据
- `researchclaw/skills/schema.py`
  - 适合作为 skill 控制论元数据的 schema 落点

### OpenClaw 与 ACP 后端

- `researchclaw/config.py`
  - 适合补充 OpenClaw/ACP 的 fallback 次序、观测参数、健康探针参数
- OpenClaw gateway 适配层
  - 适合增加结构化监督事件协议
- `researchclaw/server/routes/pipeline.py`
  - 适合暴露当前控制状态、等待原因、backend 状态、observer 结果

## A. Pipeline 进化线

### 目标

把 pipeline 从“阶段顺序机”升级成“带观测器和局部控制律的闭环系统”。

### 关键改造

1. 引入统一运行态模型

- 新增 `run_control_state.json`
- 记录：
  - current_stage
  - current_substep
  - active_session_backend
  - prompt_bundle_id
  - artifact hashes
  - dataset_state
  - gpu_state
  - notification_state
  - risk_flags

2. 引入 stage 级观测器

- `StageProgressObserver`
- `SessionHealthObserver`
- `ExperimentRuntimeObserver`
- `ArtifactIntegrityObserver`
- `EvidenceCoverageObserver`

3. 把控制动作标准化

把现有“临时分支判断”收敛成有限动作集：

- `proceed`
- `retry_same_step`
- `retry_with_smaller_context`
- `repair_local_block`
- `switch_session_backend`
- `wait_for_resource`
- `request_human_gate`
- `rollback_to_stage`
- `pivot_hypothesis`
- `terminate_run`

4. 把 Stage 9-13 改成多模式控制

- design mode
- generate mode
- block-repair mode
- deep-repair mode
- exec-diagnose mode
- refine mode

5. 建立显式代价函数

建议先定义一个简单版本：

`J = quality_gain - alpha * token_cost - beta * wallclock_cost - gamma * recovery_risk - delta * gpu_idle_cost`

后续再把各项权重从经验值升级为可学习参数。

## B. Skill 进化线

### 目标

把 skills 从“提示模板集合”升级成“技术科学层的局部控制律库”。

### 关键改造

1. skill 元数据补全

每个 skill 除了文本内容，还应记录：

- applicable_stage
- preconditions
- expected_gain
- token_cost_band
- failure_types_covered
- conflict_skills
- escalation_rule

2. skill 分类改造成控制论分类

建议从现在的任务分类，升级为：

- modeling skills
- observation skills
- diagnosis skills
- control-policy skills
- recovery skills
- evidence-quality skills
- writing-governance skills

3. skill feedback 升级

当前只统计成功率还不够，应增加：

- 生效前后 token 变化
- 生效前后 wall time 变化
- 对 artifact 质量的提升幅度
- 是否降低了回滚概率

4. 建立 skill 组合约束

某些 skill 适合串联，某些会冲突：

- prompt compression 与 deep repair 不能无脑同时拉满。
- literature breadth skill 与 paper drafting skill 不应在同一上下文里长距离混用。
- dataset fallback skill 只能在资源层决定后触发。

5. 形成四类优先增强 skill

- related-work breadth expansion
- experiment design adequacy
- block-level code repair
- paper argument tightening

## C. OpenClaw 进化线

### 目标

把 OpenClaw 从“消息入口 + session 代理”升级成“外围感知与执行协作层”。

### 关键改造

1. 让 OpenClaw 主负责外围观察

适合放到 OpenClaw 的任务：

- GPU 空闲监视
- stage 状态播报
- webhook 重试与多通道通知
- 长等待期间保活与告警
- 数据集下载进度回报
- 人工审批提醒

2. 让 OpenClaw 主负责低风险外设动作

- 读取系统资源信息
- 检测 session 是否存活
- 推送恢复建议
- 整理阶段摘要给用户

3. 不让 OpenClaw 直接承担核心科研判断

OpenClaw 适合作为执行器与感知器，不应直接替代：

- 假设选择
- 实验设计判定
- 论文论证判断

这些仍应由 pipeline governor + stage agent + 用户 gate 共同处理。

4. 建立 backend fallback 次序

建议顺序：

1. OpenClaw gateway session
2. ACP reusable session
3. ACP fresh session
4. direct CLI local execution
5. explicit fail + diagnostic

注意：

- 每次切换 backend 时必须写入 run state。
- 任何 backend 切换都不能丢失当前子步骤定位。
- 切换动作必须可追踪、可通知、可回滚。

5. OpenClaw 增加“监督员模式”

它不只是转发消息，而要输出结构化监督事件：

- `gpu_waiting`
- `gpu_ready`
- `session_unhealthy`
- `session_switched`
- `stage_stalled`
- `notification_retrying`
- `human_review_needed`

## 明确执行计划

## Phase 1：建立控制骨架

### 目标

先把“建模、观测、控制动作”三个基础件补齐。

### 任务

1. 定义统一运行态 schema。
2. 在 runner / executor / code agent 里统一写入该状态。
3. 新建 5 个 observer 的数据结构和最小实现。
4. 把 stop / continue / retry / backend switch 都写成标准控制动作。
5. 让飞书通知基于结构化事件，而不是散乱文本。

### 验收标准

- 任意时刻能回答“系统现在在哪个 stage、哪个子步骤、用哪个 backend、在等什么、下一步准备做什么”。
- 点击停止后，状态在一次轮询周期内收敛到 stopped。
- 点击继续时，能从上次子步骤而不是宽泛 stage 恢复。

## Phase 2：重构 Stage 9-13

### 目标

把最脆弱、最耗 token、最容易超时的核心段变成可控段。

### 任务

1. Stage 9 建立实验设计 adequacy rubric。
2. Stage 10 把生成/修复逻辑标准化为块级修复控制。
3. Stage 11 改为资源可行性求解，而不是静态说明文。
4. Stage 12 引入 dataset readiness observer、GPU availability observer、runtime watchdog。
5. Stage 13 只接收结构化失败诊断，不再重新消费整段大上下文。

### 验收标准

- Stage 10 超时率显著下降。
- Stage 12 因数据集/环境/GPU 等待导致的假卡死显著下降。
- Stage 13 的输入上下文可压缩到“摘要 + 诊断包 + 引用路径”。

### 当前暂挂项

- Stage 16/17 的 paper-writing 旧失败已完成一轮收敛：
  - `paper_readiness` 从硬中断改成前置告警，缺失 related work / baseline coverage / claim pruning 时仍会继续产出大纲与初稿，但会把风险写进 `paper_readiness.json` 与 prompt。
  - 与此相关的 executor/paper-writing 契约测试已补齐并通过。

## Phase 3：重构 Skill 系统

### 目标

让 skill 真正进入闭环，而不是停留在静态注入。

### 已落实进展

- `Skill` schema 已增加 `preconditions`、`expected_gain`、`token_cost_band`、`failure_types_covered`、`conflict_skills`、`escalation_rule`、`control_category`。
- `SkillRegistry` 已支持 conflict-aware bundle 解析，并能解释为什么选中某组 skill、为什么拒绝另一组 skill。
- Stage skill map 已升级为 stage skill policy，支持 `preferred_categories`、`good_combos`、`bad_combos`、`policy_focus`、`escalation_rule`。
- `research_governor` 已把 stage policy 与 bundle rationale 注入 Stage prompt，不再只有 skill 正文。
- `skill_feedback` 已开始记录 wall time、quality gain、rollback risk、artifact quality 等反馈信号。
- `runner` 已把 rollback / pivot 写入 supervisor events，并将 stage-level skill feedback 回写到演化存储。
- Stage 21 学习总结已能展示 `avg_wall_time_sec`、`avg_quality_gain`、`avg_rollback_risk_delta` 等统计。
- 已实现受控 `skill evolution loop`：
  - 现有 skill 会根据反馈统计生成 `promote / demote / keep` 建议，并对可写生产 skill 做受控 priority 调整。
  - lessons 会生成 candidate skill，先写入 `.candidates/` 沙箱而不是直接进生产库。
  - candidate skill 会被调度进 `.trials/` 做试运行；达到最小 trial 记录且指标过线后才 promotion，否则 rejection。
  - 最新演化结果会写入 `skills_dir/.evolution/skill_evolution_report.json`，并进入 Stage 21 的 learned skills summary。

### 任务

1. 给 skill 增加 precondition / expected_gain / token_cost_band。
2. 在 `skill_feedback` 里增加质量和资源指标。
3. 建立 stage-to-skill policy，而不是只做 stage-to-skill map。
4. 建立 bad combo 黑名单和 good combo 白名单。
5. 把 context compression / literature breadth / code repair / paper review 这几类 skill 做成重点策略件。

### 验收标准

- 可以回答“为什么这个 stage 选这个 skill，而不是另一个”。
- skill 的选择能够解释 token 消耗和成功率变化。
- 相关回归测试已覆盖 schema、bundle resolve、policy summary、feedback stats、runner 监督事件、executor 质量门事件。

## Phase 4：OpenClaw 收敛成外围协作层

### 目标

让 OpenClaw 真正成为外部观察-执行协作面，而不是不稳定代理。

### 已落实进展

- 已把 `run_index.json` 收敛成统一事件流，并新增 `supervisor_event` 结构化事件。
- 已把 GPU 等待、通知成功/失败、session backend 切换写入监督事件，不再只靠零散日志。
- 已为 ACP/OpenClaw 增加 backend health snapshot，状态接口可以看到当前 backend、fallback 顺序和退化状态。
- 已把状态接口与对话状态查询接上 observer summary + recent supervisor events，外围等待和退避不再是黑箱。
- 已把 supervisor events 接入 Project workspace 的 Details / Studio / Canvas，外围控制动作开始进入统一图结构。

### 任务

1. 统一 OpenClaw 结构化事件协议。
2. 统一 heartbeat 与 session health probe。
3. 为 GPU 等待、数据下载、通知重试做持续播报。
4. 做 backend fallback 状态写入和事件通知。
5. 为人工 gate 提供最小干扰式提醒。

### 验收标准

- 用户不看服务器日志，也能知道流程是在运行、等待、退避、切换还是失败。
- backend 切换不再把控制流变成黑箱。

## 建议新增的四类核心 skill

### 1. `control-state-modeling`

用途：

- 帮每个高风险 stage 明确状态、输入、输出、扰动、代价函数。

### 2. `evidence-coverage-governor`

用途：

- 专门控制文献覆盖率、baseline 覆盖率、实验对齐充分性。

### 3. `block-level-code-repair`

用途：

- Stage 10/13 的函数块、注册表块、导出块、数据块局部修复。

### 4. `openclaw-supervisor-ops`

用途：

- 管理 OpenClaw 的外围观察、等待、通知和 backend 切换动作。

## 建议新增的关键指标

### 质量指标

- related work coverage
- baseline adequacy score
- experiment alignment score
- artifact completeness score
- paper argument coherence score

### 控制指标

- resume precision
- stop convergence latency
- backend switch recovery rate
- stage timeout rate
- deep repair success rate

### 资源指标

- token per successful stage
- token per useful artifact
- gpu idle wait time
- dataset prep latency
- notification delivery latency

## 最后结论

钱学森《工程控制论》对这个项目最有价值的地方，不是“控制”两个字本身，而是它提供了一种系统进化方向：

- 把 bug 修复上升为系统建模。
- 把 prompt 调整上升为控制律设计。
- 把日志查看上升为状态观测。
- 把单次自动化上升为组织管理。
- 把 OpenClaw 从工具入口升级为外围协作层。

如果按这条路线推进，这个项目最终会从“自动化科研流水线”演化成“自动化科研控制平台”。

## 推荐的近期落地顺序

1. 先做运行态模型和 observer。
2. 再做 Stage 9-13 的模式控制改造。
3. 再做 skill 元数据与反馈闭环。
4. 最后把 OpenClaw 彻底收敛成监督-执行协作层。
