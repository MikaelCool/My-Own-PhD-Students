# AutoResearchClaw 自动化流程总览

## 总体结构

整套系统现在按 3 个大阶段组织，而不是把 23 个 stage 当成 23 个独立黑盒。

1. Discovery Council
- 目标：定义问题、吸收 baseline、锁定研究缺口。
- 性格：谨慎、怀疑、重问题定义。
- 范围：Stage 1-8。
- 关键产物：`problem_anchor.md`、`baseline_digest.md`、`literature_shortlist.md`、`phase1_handoff.md`。

2. Innovation Forge
- 目标：把创新点变成可以被实验验证的算法与证据链。
- 性格：强硬、务实、结果导向。
- 范围：Stage 9-15。
- 关键规则：创新点必须对应 claim-evidence matrix；实验跑不过 baseline 时，创新默认不成立。
- 关键产物：`claims_evidence_matrix.md`、`experiment_log.md`、`claims_from_results.md`、`phase2_handoff.md`。

3. Editorial Board
- 目标：按 CCF-A / venue 标准审稿、修稿、回滚。
- 性格：主编视角，严谨、公正、一针见血。
- 范围：Stage 16-23。
- 关键规则：区分三类动作：纯写作修订、补实验、补创新。
- 关键产物：`auto_review.md`、`paper_score.json`、`review_state.json`、`review_comment_audit.md`、`learned_skills_summary.md`。

## 三阶段内部循环

### 第一阶段：问题与文献循环
- 先冻结 `problem_anchor.md`。
- 文献输入优先级：`Zotero -> Obsidian -> 本地 seed -> 学术 API / web`。
- 如果筛完文献仍然得不到清晰缺口，就继续收缩问题，而不是直接进入方法设计。

### 第二阶段：创新与实验循环
- 先写 `claims_evidence_matrix`，后写代码。
- `iterative_refine` 负责代码和实验层面的循环优化。
- `result_to_claim` 决定 claim 能否保留。
- 如果方法没有超过 baseline，或者创新点没有被 ablation / 对比实验支撑，就回到创新或实验设计阶段。

### 第三阶段：主编式审稿循环
- `peer_review` 不只是给点评，还会生成分数、最弱维度、editorial action。
- `paper_revision` 会判断评论是否合理，不能机械照单全收。
- `quality_gate` 现在会区分：
  - `review_revise`：只需要继续修稿
  - `editorial_experiment_refine`：缺实验，回滚到实验设计
  - `editorial_pivot`：缺创新，回滚到假设生成

## 关键新增机制

### 1. Zotero / Obsidian 真接入
- `research.zotero_library_path`
- `research.zotero_attachment_root`
- `research.zotero_collection_filters`
- `knowledge_base.obsidian_vault`

支持：
- Zotero JSON export
- Zotero sqlite library
- Obsidian vault markdown notes

### 2. CCF-A / venue-aware 审稿
- `quality_assessor.target_venue`
- 当前内置 profile：`CCF-A`、`NeurIPS`、`ICML`、`ACL`、`CVPR`
- 审稿与质量门控会读取 venue profile，而不是统一标准。

### 3. Skills 真进入流程
- 仓库内 custom skills 会注入关键阶段 prompt。
- 当前新增：
  - `knowledge-intake-zotero-obsidian`
  - `innovation-validity-loop`
  - `ccf-a-editorial-review`

### 4. 自我进化
- 运行后会记录技能有效性。
- 归档阶段会输出 `learned_skills_summary.md`。
- 如果启用 MetaClaw bridge，失败 lesson 还能继续转成 `arc-*` skills。

## 运行时的核心判断

### 什么时候补实验
- baseline fairness 不足
- ablation 不足
- empirical adequacy / rigor 分数低
- reviewer 明确指出缺对比、缺统计、缺验证

### 什么时候补创新
- novelty 分数低于 venue floor
- reviewer 认为贡献不清楚、创新点弱、过于 incremental
- `claims_from_results` 显示主要 claim 站不住

### 什么时候只修稿
- 创新与实验基本成立，但表达、结构、claim calibration 还不够稳

## 推荐使用方式

1. 准备 baseline briefing。
2. 配置 Zotero 和 Obsidian 路径。
3. 运行整套流程。
4. 优先读：
- `phase1_handoff.md`
- `phase2_handoff.md`
- `paper_score.json`
- `review_state.json`
- `learned_skills_summary.md`

