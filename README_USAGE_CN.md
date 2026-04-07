# My Own PhD Students 使用 README

详细教程见：
- [docs/USAGE_TUTORIAL_CN.md](D:/codex/AutoResearchClaw/docs/USAGE_TUTORIAL_CN.md)

如果你只想先跑通一遍，按下面做。

## 1. 安装

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

## 2. 初始化

```powershell
researchclaw setup
researchclaw init
researchclaw doctor --config config.arc.yaml
researchclaw validate --config config.arc.yaml
```

## 3. 配置

至少检查这几项：
- `research.topic`
- `research.baseline_brief`
- `research.zotero_library_path`
- `knowledge_base.obsidian_vault`
- `experiment.mode`
- `experiment.sandbox.python_path`
- `quality_assessor.target_venue`

## 4. 运行

```powershell
researchclaw run --config config.arc.yaml --topic "Your research idea" --auto-approve
```

## 4.1 阶段通知

本地已经支持把阶段进度推送到 `飞书/Feishu/Lark` 或 `企业微信/WeCom`。

每个阶段完成后，通知里会带 3 类信息：
- 这一阶段做了什么
- 这一阶段形成了什么创新点，或强化了什么创新约束
- 这一阶段对后续流程的优势是什么

你需要准备：
- 飞书：机器人 webhook URL；如果启用签名，再提供 `secret`
- 企业微信：群机器人 webhook URL

配置示例：

```yaml
notifications:
  channel: "lark"   # 或 "wecom"
  target: "https://open.feishu.cn/open-apis/bot/v2/hook/..."
  secret: ""        # 飞书签名机器人可选
  on_stage_start: true
  on_stage_complete: true
  on_stage_fail: true
  on_gate_required: true
```

## 5. 看结果

重点看：
- `artifacts/.../stage-09/claims_evidence_matrix.md`
- `artifacts/.../stage-15/claims_from_results.md`
- `artifacts/.../stage-18/review_state.json`
- `artifacts/.../stage-18/paper_score.json`
- `artifacts/.../deliverables/`

## 6. 恢复运行

```powershell
researchclaw run --config config.arc.yaml --resume
```
