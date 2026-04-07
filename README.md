<p align="center">
  <img src="image/logo.png" width="700" alt="My Own PhD Students Logo">
</p>

<h1 align="center">My Own PhD Students</h1>
<p align="center"><b>An autonomous research workbench for topic framing, experimentation, paper writing, review, and revision</b></p>

<p align="center">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License">
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/Web-Workspace-0f766e" alt="Web Workspace">
  <img src="https://img.shields.io/badge/Research-23--Stage%20Pipeline-111827" alt="23 Stage Pipeline">
</p>

## Overview

My Own PhD Students is the product-facing layer on top of the `ResearchClaw` pipeline.

It turns a strict 23-stage autonomous research engine into a usable project workspace:

- start a topic with a structured `startup_contract`
- run full research cycles or revision-only cycles
- inspect progress through `Details`, `Canvas`, `Studio`, and `Files`
- track claims against evidence instead of generating paper text blindly
- route heavy experiments to a cloud server when local compute is not enough

This project is built for practical iteration, not demo-only paper generation.

## What It Does

At a high level, the system can:

- ingest literature from `Zotero -> Obsidian -> local seed files`
- frame a problem and generate testable research directions
- design experiments and generate execution artifacts
- run experiment-analysis-review loops with rollback and refinement
- draft papers, revise them, and export conference-style deliverables
- expose the whole process in a visual workspace instead of flat logs

## Why It Is Different

Most AI research generators optimize for text output. This project optimizes for research process quality.

Core advantages:

- `Claims-Evidence discipline`
  Novelty is expected to map to evidence through `claims_evidence_matrix.md`
- `Venue-aware review`
  Review loops target concrete quality bars such as `CCF-A`
- `Revision-first operation`
  The pipeline supports `standard_full_run`, `continue_existing_state`, `review_only`, and `rebuttal_revision`
- `Project workspace model`
  Research is organized as persistent projects with multiple runs, not one-off scripts
- `Visual workbench`
  Users can inspect graph structure, messages, timeline, settings, and artifacts from the browser
- `Cloud execution path`
  Experiments can move from local execution to `SSH` cloud servers when local GPU or RAM is insufficient

## Workspace

The web workspace is designed around 4 working surfaces:

- `Start Research`
  Create a project and fill a structured startup contract
- `Details`
  Inspect current status, latest run, key artifacts, metrics, and contract goals
- `Canvas`
  Explore stages, artifacts, decisions, and rollback paths through a graph
- `Studio`
  Follow a ChatGPT-style message flow, timeline, logs, and control actions

### Workspace Walkthrough

Open the web workspace locally to inspect the live UI:

- Home: `http://127.0.0.1:8080/`
- Tutorial: `http://127.0.0.1:8080/static/tutorial.html`

### Pipeline View

<p align="center">
  <img src="image/framework_v2.png" width="100%" alt="Pipeline Framework">
</p>

## Feature Summary

### Research engine

- 23-stage pipeline with rollback-aware execution
- startup contracts and per-project run history
- evidence-aware analysis and review loops
- markdown-first writing and export to LaTeX deliverables

### Product layer

- browser workspace with project list and multi-run context
- structured settings form in Chinese and English
- one-click Feishu notification test from workspace settings
- visual canvas with right-side node details
- tutorial page with synchronized language switching

### Execution modes

- local machine
- local Docker
- `SSH` remote cloud server
- resume and revision-oriented launch modes

## Setup

### 1. Requirements

- Python `3.11+`
- a virtual environment such as `.venv`
- optional: Docker for isolated execution
- optional: Node.js if you use external coding agents
- optional: cloud Linux server with `SSH` access for heavy experiments

### 2. Install

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 3. Initialize configuration

```powershell
researchclaw setup
researchclaw init
researchclaw doctor --config config.arc.yaml
researchclaw validate --config config.arc.yaml
```

### 4. Minimum configuration focus

Before the first real run, check these fields in `config.arc.yaml`:

- `research.topic`
- `research.baseline_brief`
- `knowledge_base.obsidian_vault`
- `experiment.mode`
- `experiment.sandbox.python_path`
- `experiment.ssh_remote.*` if you use a cloud server
- `quality_assessor.target_venue`

## Quick Start

### CLI run

```powershell
researchclaw run --config config.arc.yaml --topic "Your research idea" --auto-approve
```

Resume the latest run:

```powershell
researchclaw run --config config.arc.yaml --resume
```

### Launch the visual workspace

```powershell
.\.venv\Scripts\python.exe -m researchclaw.cli serve --config .\config.arc.yaml --host 127.0.0.1 --port 8080
```

Open:

```text
http://127.0.0.1:8080/
```

## Cloud Server Workflow

If local compute is not enough, switch to cloud execution in the workspace:

`Settings -> 运行 / Runtime -> 云服务器运行 / Cloud execution`

Recommended fields:

- `运行位置 / Execution target`: `SSH cloud server`
- `云服务器地址 / Cloud host`: public IP or domain
- `登录用户 / Login user`: often `ubuntu`
- `SSH 端口 / SSH port`: usually `22`
- `SSH 密钥路径 / SSH key path`: your local private key path
- `远程工作目录 / Remote work directory`: for example `/tmp/researchclaw_experiments`
- `远程 Python / Remote Python`: for example `python3`

## Typical Outputs

A successful run usually produces:

- `paper_draft.md`
- `paper.tex`
- `references.bib`
- `deliverables/`
- `stage-09/claims_evidence_matrix.md`
- `stage-18/review_state.json`
- `stage-18/paper_score.json`

## Documentation

Chinese documentation:

- [README_USAGE_CN.md](README_USAGE_CN.md)
- [docs/USAGE_TUTORIAL_CN.md](docs/USAGE_TUTORIAL_CN.md)
- [docs/WORKSPACE_TUTORIAL_CN.md](docs/WORKSPACE_TUTORIAL_CN.md)
- [docs/AUTOMATION_PROCESS_CN.md](docs/AUTOMATION_PROCESS_CN.md)
- [docs/BASELINE_WORKFLOW_CN.md](docs/BASELINE_WORKFLOW_CN.md)

## Repository Layout

- `researchclaw/`
  Main Python package
- `researchclaw/pipeline/`
  Stage orchestration and execution logic
- `researchclaw/project/`
  Project workspace model and materialized views
- `researchclaw/server/`
  FastAPI app and web routes
- `frontend/`
  Visual workspace and tutorial page
- `docs/`
  Documentation and guides
- `tests/`
  Regression and integration tests

## Development

Useful commands:

```powershell
researchclaw doctor --config config.arc.yaml
researchclaw validate --config config.arc.yaml
pytest -q
```

If you are debugging the pipeline, inspect artifacts under `artifacts/rc-*/` instead of judging success only by whether a paper file exists.

## License

This project is released under the [MIT License](LICENSE).
