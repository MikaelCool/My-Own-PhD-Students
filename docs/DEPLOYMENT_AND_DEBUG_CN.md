# AutoResearchClaw 部署与排错说明

这份文档只解决三个问题：

1. 本机如何正确启动。
2. Docker 模式应该怎么配。
3. 运行失败时去哪里看日志和根因。

## 1. 先确认当前项目实际上怎么在跑

以当前仓库里的 [config.arc.yaml](D:/codex/AutoResearchClaw/config.arc.yaml) 为准：

- `llm.provider: acp`
- `llm.acp.agent: codex`
- `experiment.mode: sandbox`
- `experiment.opencode.enabled: false`

这意味着当前默认不是走 OpenAI API 直连，也不是默认走 OpenCode Beast Mode。
当前默认路径是：

`ResearchClaw -> ACPClient -> acpx -> codex agent`

如果你想让 Codex 侧实际使用 `GPT-5.4`，要在 Codex/ACP agent 自己的配置里切模型，不是改 `llm.primary_model`。

## 2. Windows 本机最小可运行部署

在 PowerShell 里执行：

```powershell
cd D:\codex\AutoResearchClaw
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[web,pdf,dev]"
```

说明：

- `[web]` 负责 Web 界面和文献检索相关依赖。
- `[pdf]` 负责 PDF 解析。
- `[dev]` 方便跑测试。

然后做环境检查：

```powershell
.\.venv\Scripts\python.exe -m researchclaw.cli doctor --config .\config.arc.yaml
.\.venv\Scripts\python.exe -m researchclaw.cli validate --config .\config.arc.yaml
```

如果你是 ACP + Codex 路线，还要确认：

- `codex` 可执行程序能被找到。
- `acpx` 可执行程序能被找到，或者 `llm.acp.acpx_command` 已写死。

最后启动 Web：

```powershell
.\.venv\Scripts\python.exe -m researchclaw.cli serve --config .\config.arc.yaml --host 127.0.0.1 --port 8080
```

浏览器打开：

```text
http://127.0.0.1:8080/
```

## 3. Docker 模式正确步骤

先确认 Docker Desktop 已安装并已启动。只安装命令行不够， Docker Engine 也必须在运行。

构建实验镜像：

```powershell
cd D:\codex\AutoResearchClaw
docker build -t researchclaw/experiment:latest .\researchclaw\docker
```

然后把 [config.arc.yaml](D:/codex/AutoResearchClaw/config.arc.yaml) 改成至少这样：

```yaml
experiment:
  mode: docker
  docker:
    image: researchclaw/experiment:latest
    network_policy: setup_only
    gpu_enabled: true
```

再检查：

```powershell
docker image inspect researchclaw/experiment:latest | Out-Null
.\.venv\Scripts\python.exe -m researchclaw.cli doctor --config .\config.arc.yaml
```

如果你的机器根本没有 Docker，或者 Docker Desktop 没启动，`docker` 模式一定会失败。当前这台机器上我实际检查到的状态就是 `docker` 命令不可用。

## 4. OpenCode 应该怎么启用

OpenCode 不是默认开启的。要用它，需要先安装：

```powershell
npm i -g opencode-ai@latest
```

再在配置里启用：

```yaml
experiment:
  opencode:
    enabled: true
```

代码里它主要用于复杂代码生成和实验修复，不是整个 23 阶段流程的总控。

## 5. PAPER_OUTLINE 失败怎么定位

`PAPER_OUTLINE` 不是第一现场。它依赖前面已经产出：

- `analysis.md`
- `decision.md`

也就是说，常见链路是：

1. 实验阶段失败。
2. 分析阶段没产出完整结论。
3. 到 `PAPER_OUTLINE` 时缺输入，所以报错。

当前代码里 `PAPER_DRAFT` 甚至会直接拒绝“没有真实实验指标却硬写论文”。

先看这几个目录：

- `stage-12`
- `stage-13`
- `stage-14`
- `stage-15`

再看总日志：

- `artifacts/.../<run_id>/pipeline.log`

## 6. 现在怎么查看详细运行过程

当前前端不是实时流式 WebSocket 展示，而是每 5 秒轮询一次项目状态。

前端主要读的是：

- `pipeline.log`
- 最新阶段工件

所以最直接的查看方式有两种：

1. Web 的 `Studio` 面板看最近日志。
2. 直接打开运行目录下的 `pipeline.log`。

飞书通知只是附加通知渠道，不是唯一观察方式。

## 7. 这次我已经修掉的两个问题

### 7.1 Windows 下 Docker 命令构造会崩

原来 `docker_sandbox.py` 直接调用 `os.getuid()` / `os.getgid()`。
Windows 没这两个函数，所以会在真正启动 Docker 之前就报错。

现在已经修成：

- 只有在系统支持 `getuid/getgid` 时才加 `--user`
- Windows 下不再因为这个原因直接崩掉

### 7.2 Web 工作台之前不一定能读到详细日志

`Studio` 会去读 `pipeline.log`，但之前主流程没有可靠地把日志接到这个文件。
现在已经在 pipeline 启动时把根日志路由到每次运行的 `pipeline.log`。

## 8. 推荐排错顺序

1. 先跑 `doctor`
2. 再跑 `validate`
3. 先用 `experiment.mode: sandbox` 跑通
4. 确认 `pipeline.log` 有内容
5. 再切到 `docker`
6. `PAPER_OUTLINE` 报错时，优先回看 `stage-12` 到 `stage-15`
