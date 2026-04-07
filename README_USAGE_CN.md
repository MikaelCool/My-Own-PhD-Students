# AutoResearchClaw 使用 README

详细版教程见：

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
