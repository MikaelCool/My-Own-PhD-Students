# Baseline 驱动工作流

## 目的

把 AutoResearchClaw 从“给定 topic 自动写论文”，收紧到“参考你提供的 baseline，提炼创新空间，做 2-3 个理论/算法创新，并按 baseline 实验协议进行验证”。

## 使用方法

1. 编辑根目录的 `baseline_briefing.md`
   - 填入每篇 baseline 的题目、链接、核心创新、关键公式、实验协议、最强结果和不足。
   - 最后补上跨论文的共性假设、必须复现的实验设置、可扩展的评价维度。

2. 检查 `config.arc.yaml`
   - `research.baseline_brief: "baseline_briefing.md"`
   - `prompts.custom_file: "prompts.high_impact_baseline.yaml"`

3. 运行环境检查
   - `.\.venv\Scripts\researchclaw.exe doctor --config config.arc.yaml`

4. 启动研究
   - `.\.venv\Scripts\researchclaw.exe run --config config.arc.yaml --topic "你的研究主题" --auto-approve`

## 当前改动点

- 关键阶段会自动读取 `baseline_briefing.md`。
- Prompt 已强化为：
  - 只接受理论/算法创新，不接受纯工程优化。
  - 强制围绕 2-3 个创新点组织全文。
  - baseline 对比要公平，先复现实验逻辑，再宣称超越。
  - 结果不够强时自动收缩 claim，而不是硬写 SOTA。
- 图表默认风格更偏简洁科研出版风格。

## 需要明确的现实约束

- “达到 CCF-A 要求”只能作为优化目标，不能靠 prompt 保证。
- “达到 SOTA”必须由真实实验支持，系统不会诚实地预先承诺。
- 如果 baseline 本身需要 GPU、大数据集或长时间训练，当前本机 sandbox 预算可能不够，需要切到更强算力环境。
