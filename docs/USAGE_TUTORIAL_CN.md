# My Own PhD Students 使用教程

如果你主要使用可视化工作台，请优先看：
- [docs/WORKSPACE_TUTORIAL_CN.md](D:/codex/AutoResearchClaw/docs/WORKSPACE_TUTORIAL_CN.md)

这份文档面向第一次真正跑通 `My Own PhD Students` 的用户，不讲宣传，只讲怎么在本地把流程跑起来，以及每一步应该准备什么。

## 1. 这套系统会做什么

给它一个研究主题，或者一个 baseline 家族，它会按 23 个阶段完成：
- 文献检索与筛选
- 问题拆解与创新点生成
- 实验设计、代码生成、实验执行
- 结果分析、论文写作、同行评审
- 质量门控、导出和归档

如果你启用了当前仓库里的增强流程，它还会：
- 优先读取 `Zotero -> Obsidian -> 本地 seed`
- 使用 `claims_evidence_matrix` 约束创新点
- 按 `target_venue` 做主编式 review score loop
- 在每个阶段完成后给飞书或企业微信推送摘要

## 2. 环境要求

- Python `3.11+`
- 建议先创建虚拟环境 `.venv`
- 如果要跑 `docker` 模式实验，需要 Docker
- 如果要启用 `OpenCode Beast Mode`，需要 `node` 和 `npm`
- 如果用 API 模型，需要对应的 API Key
- 如果用 ACP agent 模式，需要本地可用的 ACP agent

## 3. 安装

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

Linux / macOS：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 4. 初始化配置

先执行环境检查和可选工具安装：

```powershell
researchclaw setup
```

然后生成配置文件：

```powershell
researchclaw init
```

这会在项目根目录生成 `config.arc.yaml`。如果已经有配置文件，想强制重建：

```powershell
researchclaw init --force
```

配置写完后，先做一次体检：

```powershell
researchclaw doctor --config config.arc.yaml
researchclaw validate --config config.arc.yaml
```

## 5. 最小可运行配置

下面是一份适合本地第一次跑通的最小配置思路。你可以直接在 [config.arc.yaml](D:/codex/AutoResearchClaw/config.arc.yaml) 里改。

```yaml
project:
  name: "my-research"
  mode: "docs-first"

research:
  topic: "Your research topic here"
  baseline_brief: "baseline_briefing.md"
  zotero_library_path: ""
  zotero_attachment_root: ""
  zotero_collection_filters: []
  literature_seed_paths: []
  note_seed_paths: []
  max_seed_docs: 12
  max_obsidian_notes: 16

knowledge_base:
  backend: "markdown"
  root: "docs/kb"
  obsidian_vault: ""

llm:
  provider: "acp"
  primary_model: "gpt-4o"
  acp:
    agent: "codex"
    cwd: "."
    acpx_command: "C:/Users/yourname/AppData/Roaming/npm/acpx.cmd"

experiment:
  mode: "sandbox"
  time_budget_sec: 1800
  max_iterations: 10
  metric_key: "primary_metric"
  metric_direction: "minimize"
  sandbox:
    python_path: ".venv/Scripts/python.exe"

quality_assessor:
  enabled: true
  target_venue: "CCF-A"
  review_target_score: 8.0
  max_review_rounds: 4
  min_score_improvement: 0.2

prompts:
  custom_file: "prompts.high_impact_baseline.yaml"

skills:
  enabled: true
  custom_dirs:
    - "researchclaw/skills/custom"
```

## 6. 运行前你要准备什么

### 6.1 baseline briefing

如果你想让系统围绕已有 baseline 做创新，不要只给 topic，最好准备 [baseline_briefing.md](D:/codex/AutoResearchClaw/baseline_briefing.md)。

建议至少写这些项：
- baseline 论文标题
- baseline 核心创新
- baseline 实验设置
- baseline 明显弱点
- 哪些实验协议必须复现
- 你不接受哪些“伪创新”

如果你走的是 baseline 驱动路线，再看一眼 [docs/BASELINE_WORKFLOW_CN.md](D:/codex/AutoResearchClaw/docs/BASELINE_WORKFLOW_CN.md)。

### 6.2 Zotero

如果你有自己的文献库，建议直接接入 Zotero。

支持两种输入：
- Zotero JSON export
- Zotero sqlite library

配置示例：

```yaml
research:
  zotero_library_path: "D:/data/zotero/export.json"
  zotero_attachment_root: "D:/data/zotero/storage"
  zotero_collection_filters:
    - "my-topic"
```

### 6.3 Obsidian

如果你有自己整理过的笔记库，可以接入 Obsidian vault：

```yaml
knowledge_base:
  obsidian_vault: "D:/notes/MyVault"
```

### 6.4 本地 seed

如果你还有本地 PDF / md / txt seed，可以继续配，但现在优先级应该理解为：

`Zotero -> Obsidian -> 本地 seed`

配置示例：

```yaml
research:
  literature_seed_paths:
    - "D:/papers"
  note_seed_paths:
    - "D:/notes/topic_seeds"
```

## 7. 如何运行

最直接的命令：

```powershell
researchclaw run --config config.arc.yaml --topic "Your research idea" --auto-approve
```

常见变体：

```powershell
researchclaw run --config config.arc.yaml --topic "Your research idea"
researchclaw run --config config.arc.yaml --resume
researchclaw run --config config.arc.yaml --from-stage PAPER_REVISION
researchclaw run --config config.arc.yaml --topic "Your research idea" --skip-preflight
```

说明：
- `--auto-approve`：自动通过 gate stages
- 不加 `--auto-approve` 时，`docs-first` / `semi-auto` 会在 gate 处停住
- `--resume`：从最近 checkpoint 恢复
- `--from-stage`：从指定阶段继续

## 7.1 接入飞书或企业微信通知

如果你希望每完成一个阶段，就在聊天工具里收到“做了什么、创新点、优势”摘要，现在可以直接用本地 webhook。

支持：
- `lark` / `feishu`
- `wecom` / `wechat_work`

你需要提供：
- 飞书机器人 webhook URL
- 飞书签名 secret，可选
- 或企业微信群机器人 webhook URL

配置示例：

```yaml
notifications:
  channel: "lark"   # 或 "wecom"
  target: "https://open.feishu.cn/open-apis/bot/v2/hook/..."
  secret: ""        # 飞书签名机器人时再填
  on_stage_start: true
  on_stage_complete: true
  on_stage_fail: true
  on_gate_required: true
```

说明：
- `target` 留空时，不会真的发消息
- `on_stage_complete: true` 时，每个阶段完成后都会推送阶段摘要
- webhook 短暂失败不会打断主流程

## 8. 推荐的第一次跑法

第一次不要直接上最复杂配置，建议按下面顺序：

1. 用 `sandbox` 模式跑一个你熟悉、可快速验证的 topic。
2. 准备 `baseline_briefing.md`，不要只给一句 topic。
3. 如果有自己的文献体系，接入 Zotero 和 Obsidian。
4. 把 `quality_assessor.target_venue` 设成你真正对标的 venue。
5. 先跑通一轮，再看 artifacts，不要盲目加大预算。

## 9. 结果会输出到哪里

默认输出目录在：

```text
artifacts/rc-YYYYMMDD-HHMMSS-<hash>/
```

重点看这些文件：
- `stage-09/claims_evidence_matrix.md`
- `stage-15/claims_from_results.md`
- `stage-18/review_state.json`
- `stage-18/paper_score.json`
- `stage-19/review_comment_audit.md`
- `stage-21/learned_skills_summary.md`
- `deliverables/`

如果你按当前增强流程来用，建议优先读：
1. `phase1_handoff.md`
2. `phase2_handoff.md`
3. `review_state.json`
4. `paper_score.json`
5. `learned_skills_summary.md`

## 10. 怎么判断这一轮跑得值不值

不要只看是不是生成了论文，要看下面几个判断点：
- `claims_evidence_matrix.md` 里的 claim 是否真的对应到实验
- `claims_from_results.md` 里是否有大量 `Unsupported or Rejected Claims`
- `review_state.json` 里的 `editorial_action` 是 `revise_paper` 还是 `supplement_experiments` / `rework_innovation`
- `paper_score.json` 是否接近或达到目标 venue 的门槛
- `review_comment_audit.md` 是否真的在判断 reviewer comments 合不合理，而不是机械改写

## 11. 常用命令

```powershell
researchclaw init
researchclaw setup
researchclaw doctor --config config.arc.yaml
researchclaw validate --config config.arc.yaml
researchclaw run --config config.arc.yaml --topic "Your topic"
researchclaw run --config config.arc.yaml --resume
```

如果你想开 Web 界面：

```powershell
researchclaw serve --config config.arc.yaml
```

## 12. 常见问题

### 12.1 `config` 找不到

先确认当前目录下有 `config.arc.yaml`，或者显式传：

```powershell
researchclaw run --config config.arc.yaml --topic "..."
```

### 12.2 ACP agent 跑不起来

检查：
- `llm.provider` 是否是 `acp`
- `llm.acp.agent` 是否填对
- `llm.acp.acpx_command` 是否存在
- `researchclaw doctor --config config.arc.yaml` 是否通过

### 12.3 sandbox 模式跑实验失败

优先检查：
- `.venv` 是否装好了依赖
- `experiment.sandbox.python_path` 是否指向正确 Python
- 题目是不是太大，超出本地时间或算力预算
- 先从更小的 baseline 或更短的 budget 开始

## 13. 推荐继续读的文档

- [docs/AUTOMATION_PROCESS_CN.md](D:/codex/AutoResearchClaw/docs/AUTOMATION_PROCESS_CN.md)
- [docs/BASELINE_WORKFLOW_CN.md](D:/codex/AutoResearchClaw/docs/BASELINE_WORKFLOW_CN.md)
- [docs/integration-guide.md](D:/codex/AutoResearchClaw/docs/integration-guide.md)
- [docs/TESTER_GUIDE_CN.md](D:/codex/AutoResearchClaw/docs/TESTER_GUIDE_CN.md)
