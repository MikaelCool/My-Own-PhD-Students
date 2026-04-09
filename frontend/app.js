const DEFAULT_LANGUAGE = "zh-CN";

const I18N = {
  "zh-CN": {
    brand_subtitle: "你的 AI 博士生团队",
    start_research: "开始研究",
    usage_tutorial: "使用教程",
    projects: "项目",
    refresh: "刷新",
    workspace: "工作区",
    hint_details_first: "先看详情 判断当前运行和关键工件",
    hint_canvas_structure: "再用 Canvas 看阶段 工件和关系结构",
    hint_studio_control: "最后到 Studio 里做控制 对话和排查",
    product_eyebrow: "My Own PhD Students",
    product_layer: "研究总览",
    hero_title: "把想法 实验 写作和评审放进同一个研究工作区",
    hero_body: "这里更像一个持续研究面板 你可以像管理自己的博士生团队一样 发起课题 跟踪进度 查看结构并控制每轮运行",
    hero_card_start: "新建课题 明确目标 启动模式 研究材料和约束条件",
    hero_card_details: "先看项目现在走到哪一步 缺什么证据 下一步该做什么",
    hero_card_canvas: "从结构图看清阶段 工件 决策和回滚路径",
    hero_card_studio: "像对话一样跟踪研究进展 并结合时间线完成控制和排查",
    settings: "设置",
    continue_run: "继续",
    run: "运行",
    stop: "停止",
    details: "详情",
    files: "文件",
    start_modal_title: "发起一个新的研究课题",
    start_tab_basics: "基本信息",
    start_tab_strategy: "研究策略",
    start_tab_inputs: "资料与约束",
    project_id: "项目 ID",
    project_title: "项目标题",
    project_title_placeholder: "分布偏移下的鲁棒性研究",
    primary_request: "核心研究请求",
    primary_request_placeholder: "写清楚研究问题 成功标准和证据要求",
    research_intensity: "研究强度",
    balanced: "均衡",
    light: "轻量",
    sprint: "冲刺",
    decision_policy: "决策策略",
    autonomous: "自主",
    user_gated: "人工门控",
    launch_mode: "启动模式",
    launch_standard: "标准完整运行",
    launch_continue: "继续已有状态",
    launch_review: "只做评审",
    launch_rebuttal: "答辩 / 修稿",
    auto_approve: "自动通过 Gate",
    yes: "是",
    no: "否",
    baseline_links: "Baseline 链接",
    reference_links: "参考论文 / 仓库",
    runtime_constraints: "运行约束",
    runtime_constraints_placeholder: "硬件 模型 预算 验证规则等",
    objectives: "目标清单",
    objectives_placeholder: "每行一个目标",
    multiline_placeholder: "每行一个 URL 或本地路径",
    create_project: "创建项目",
    contract_preview: "启动合同预览",
    settings_title: "工作台设置",
    summary_status: "状态",
    summary_launch_mode: "启动模式",
    summary_stage: "当前阶段",
    summary_run: "最近运行",
    no_projects: "还没有项目",
    no_project_topic: "尚未设置主题",
    overview: "概览",
    contract: "合同",
    artifacts: "工件",
    graph: "关系图",
    nodes: "节点",
    edges: "连线",
    chat_flow: "对话流",
    timeline: "时间线",
    logs: "日志",
    workspace_files: "工作区",
    settings_ui: "界面",
    settings_research: "研究",
    settings_runtime: "运行",
    settings_quality: "质量",
    settings_server: "服务",
    settings_automation: "自动化",
    contract_section: "项目合同",
    latest_run: "最新运行",
    metrics: "指标",
    goal: "目标",
    key_artifacts: "关键工件",
    canvas_title: "研究关系图",
    canvas_empty: "还没有 Canvas 数据。",
    canvas_drawer_title: "节点详情",
    canvas_drawer_empty: "点击左侧节点查看详情、元数据和关联边。",
    related_edges: "关联边",
    message_flow_empty: "这里会显示项目合同、系统状态和最近活动。",
    timeline_empty: "还没有时间线事件。",
    log_empty: "还没有日志。",
    controls: "控制",
    current_context: "当前上下文",
    save_settings: "保存设置",
    settings_saved: "设置已保存。",
    test_feishu_notification: "测试飞书通知",
    feishu_test_sent: "测试通知已发送",
    feishu_test_failed: "测试通知发送失败",
    project_created: "项目已创建，流水线已启动。",
    pipeline_started: "流水线已启动。",
    pipeline_continued: "已从最近可恢复的运行继续。",
    pipeline_stopped: "流水线已停止。",
    no_recoverable_run: "没有找到可继续的运行。",
    select_project_first: "请先选择一个项目。",
    language: "界面语言",
    language_zh: "简体中文",
    language_en: "English",
    appearance: "外观与语言",
    interaction: "交互偏好",
    research_scope: "研究范围",
    experiment_policy: "实验策略",
    runtime_limits: "运行限制",
    quality_gate: "质量门槛",
    web_server: "Web 服务",
    dashboard: "仪表盘",
    co_pilot: "协作策略",
    multi_project: "多项目",
    notifications: "通知",
    field_project_name: "默认项目名",
    field_topic: "默认研究主题",
    field_domains: "研究领域",
    field_daily_papers: "每日论文数",
    field_quality_threshold: "质量阈值",
    field_baseline_brief: "Baseline 摘要",
    field_timezone: "时区",
    field_parallel: "并行任务数",
    field_approval_timeout: "审批超时小时",
    field_retry_limit: "重试次数",
    field_experiment_mode: "实验模式",
    field_time_budget: "时间预算秒",
    field_iterations: "最大迭代次数",
    field_metric_key: "主指标字段",
    field_target_venue: "目标 venue",
    field_target_score: "目标评分",
    field_review_rounds: "最大评审轮次",
    field_improvement: "最小提升",
    field_server_enabled: "启用 Web 服务",
    field_host: "主机地址",
    field_port: "端口",
    field_voice: "语音入口",
    field_dashboard_enabled: "启用仪表盘",
    field_refresh_interval: "刷新间隔秒",
    field_browser_notifications: "浏览器通知",
    field_pause_at_gates: "在 Gate 暂停",
    field_pause_every_stage: "每阶段暂停",
    field_allow_branching: "允许分支",
    field_max_branches: "最大分支数",
    field_notifications_channel: "通知渠道",
    field_stage_start: "阶段开始通知",
    field_stage_complete: "阶段完成通知",
    field_stage_fail: "阶段失败通知",
    field_multi_enabled: "启用多项目",
    field_projects_dir: "项目目录",
    field_max_concurrent: "最大并发项目",
    field_shared_knowledge: "共享知识",
    help_language: "",
    help_domains: "使用英文逗号分隔多个领域",
    help_baseline_brief: "用一句话说明现有 baseline 假设或已知短板",
    help_notification_channel: "例如 slack email 或 webhook",
    cloud_execution: "云服务器运行",
    field_compute_target: "运行位置",
    compute_target_local: "本地机器",
    compute_target_docker: "本地 Docker",
    compute_target_cloud: "SSH 云服务器",
    cloud_server_desc: "如果本地显存或内存不够 可以切到云服务器执行实验",
    field_cloud_host: "云服务器地址",
    field_cloud_user: "登录用户",
    field_cloud_port: "SSH 端口",
    field_cloud_key_path: "SSH 密钥路径",
    field_cloud_remote_workdir: "远程工作目录",
    field_cloud_python: "远程 Python",
    field_cloud_use_docker: "远程使用 Docker",
    not_set: "未设置",
    no_files: "还没有文件。",
    no_artifacts: "还没有关键工件。",
    no_data: "暂无数据",
    can_start: "可启动",
    can_continue: "可继续",
    can_stop: "可停止",
    type_project: "项目",
    type_run: "运行",
    type_phase: "阶段组",
    type_stage: "阶段",
    type_artifact: "工件",
    type_decision: "决策",
    type_review: "评审",
    type_quality: "质量",
    type_deliverable: "交付物",
    type_contract: "合同",
    type_objective: "目标",
    type_baseline: "基线",
    type_reference: "参考",
    type_constraint: "约束",
    status_idle: "空闲",
    status_running: "运行中",
    status_completed: "已完成",
    status_done: "已完成",
    status_failed: "失败",
    status_stopped: "已停止",
    status_unknown: "未知",
    start_time: "开始时间",
    updated_time: "更新时间",
    node_type: "节点类型",
    node_label: "节点名称",
    node_meta: "元数据",
    studio_system_hint: "这里像一个研究控制台，你可以把它当成 ChatGPT 式对话流加运行时间线。",
  },
  en: {
    brand_subtitle: "Your AI PhD student team",
    start_research: "Start Research",
    usage_tutorial: "Usage Tutorial",
    projects: "Projects",
    refresh: "Refresh",
    workspace: "Workspace",
    hint_details_first: "Start from Details to inspect the latest run",
    hint_canvas_structure: "Use Canvas to read stage and artifact structure",
    hint_studio_control: "Use Studio to control the run and review events",
    product_eyebrow: "My Own PhD Students",
    product_layer: "Research Overview",
    hero_title: "Keep ideas experiments writing and review in one workspace",
    hero_body: "This should feel like a persistent research desk where you can start topics track progress inspect structure and manage each cycle like your own PhD student team",
    hero_card_start: "Open a new topic with clear goals launch mode sources and runtime constraints",
    hero_card_details: "See where the project is now what evidence is missing and what should happen next",
    hero_card_canvas: "Read phases artifacts decisions and rollback paths from the graph view",
    hero_card_studio: "Track progress like a conversation and pair it with a run timeline and controls",
    settings: "Settings",
    continue_run: "Continue",
    run: "Run",
    stop: "Stop",
    details: "Details",
    files: "Files",
    start_modal_title: "Start a new research topic",
    start_tab_basics: "Basics",
    start_tab_strategy: "Strategy",
    start_tab_inputs: "Inputs",
    project_id: "Project ID",
    project_title: "Project title",
    project_title_placeholder: "Research on robustness under distribution shift",
    primary_request: "Primary request",
    primary_request_placeholder: "Describe the research question success criteria and evidence standard",
    research_intensity: "Research intensity",
    balanced: "Balanced",
    light: "Light",
    sprint: "Sprint",
    decision_policy: "Decision policy",
    autonomous: "Autonomous",
    user_gated: "User gated",
    launch_mode: "Launch mode",
    launch_standard: "Standard full run",
    launch_continue: "Continue existing state",
    launch_review: "Review only",
    launch_rebuttal: "Rebuttal / revision",
    auto_approve: "Auto approve gate",
    yes: "Yes",
    no: "No",
    baseline_links: "Baseline links",
    reference_links: "References / repos",
    runtime_constraints: "Runtime constraints",
    runtime_constraints_placeholder: "Hardware model budget and validation rules",
    objectives: "Objectives",
    objectives_placeholder: "One objective per line",
    multiline_placeholder: "One URL or path per line",
    create_project: "Create project",
    contract_preview: "Startup contract preview",
    settings_title: "Workspace settings",
    summary_status: "Status",
    summary_launch_mode: "Launch mode",
    summary_stage: "Current stage",
    summary_run: "Latest run",
    no_projects: "No projects yet",
    no_project_topic: "Topic not set",
    overview: "Overview",
    contract: "Contract",
    artifacts: "Artifacts",
    graph: "Graph",
    nodes: "Nodes",
    edges: "Edges",
    chat_flow: "Messages",
    timeline: "Timeline",
    logs: "Logs",
    workspace_files: "Workspace",
    settings_ui: "UI",
    settings_research: "Research",
    settings_runtime: "Runtime",
    settings_quality: "Quality",
    settings_server: "Server",
    settings_automation: "Automation",
    contract_section: "Startup contract",
    latest_run: "Latest run",
    metrics: "Metrics",
    goal: "Goal",
    key_artifacts: "Key artifacts",
    canvas_title: "Research relationship graph",
    canvas_empty: "No Canvas data yet.",
    canvas_drawer_title: "Node details",
    canvas_drawer_empty: "Click any node on the left to inspect metadata and related edges.",
    related_edges: "Related edges",
    message_flow_empty: "Project contract, system status, and recent activity will appear here.",
    timeline_empty: "No timeline events yet.",
    log_empty: "No logs yet.",
    controls: "Controls",
    current_context: "Current context",
    save_settings: "Save settings",
    settings_saved: "Settings saved.",
    test_feishu_notification: "Test Feishu notification",
    feishu_test_sent: "Test notification sent",
    feishu_test_failed: "Failed to send test notification",
    project_created: "Project created and pipeline started.",
    pipeline_started: "Pipeline started.",
    pipeline_continued: "Resumed from the latest recoverable run.",
    pipeline_stopped: "Pipeline stopped.",
    no_recoverable_run: "No recoverable run found.",
    select_project_first: "Select a project first.",
    language: "Interface language",
    language_zh: "Simplified Chinese",
    language_en: "English",
    appearance: "Appearance and language",
    interaction: "Interaction",
    research_scope: "Research scope",
    experiment_policy: "Experiment policy",
    runtime_limits: "Runtime limits",
    quality_gate: "Quality gate",
    web_server: "Web server",
    dashboard: "Dashboard",
    co_pilot: "Co-pilot",
    multi_project: "Multi-project",
    notifications: "Notifications",
    field_project_name: "Default project name",
    field_topic: "Default research topic",
    field_domains: "Domains",
    field_daily_papers: "Daily paper count",
    field_quality_threshold: "Quality threshold",
    field_baseline_brief: "Baseline brief",
    field_timezone: "Timezone",
    field_parallel: "Parallel tasks",
    field_approval_timeout: "Approval timeout hours",
    field_retry_limit: "Retry limit",
    field_experiment_mode: "Experiment mode",
    field_time_budget: "Time budget seconds",
    field_iterations: "Max iterations",
    field_metric_key: "Primary metric key",
    field_target_venue: "Target venue",
    field_target_score: "Target score",
    field_review_rounds: "Max review rounds",
    field_improvement: "Minimum improvement",
    field_server_enabled: "Enable web server",
    field_host: "Host",
    field_port: "Port",
    field_voice: "Voice entry",
    field_dashboard_enabled: "Enable dashboard",
    field_refresh_interval: "Refresh interval seconds",
    field_browser_notifications: "Browser notifications",
    field_pause_at_gates: "Pause at gates",
    field_pause_every_stage: "Pause every stage",
    field_allow_branching: "Allow branching",
    field_max_branches: "Max branches",
    field_notifications_channel: "Notification channel",
    field_stage_start: "Stage start notifications",
    field_stage_complete: "Stage complete notifications",
    field_stage_fail: "Stage fail notifications",
    field_multi_enabled: "Enable multi-project",
    field_projects_dir: "Projects directory",
    field_max_concurrent: "Max concurrent projects",
    field_shared_knowledge: "Shared knowledge",
    help_language: "",
    help_domains: "Separate multiple domains with commas",
    help_baseline_brief: "Summarize the current baseline assumption or known weakness in one sentence",
    help_notification_channel: "For example slack email or webhook",
    cloud_execution: "Cloud execution",
    field_compute_target: "Execution target",
    compute_target_local: "Local machine",
    compute_target_docker: "Local Docker",
    compute_target_cloud: "SSH cloud server",
    cloud_server_desc: "Switch to a cloud server when local GPU memory or RAM is not enough",
    field_cloud_host: "Cloud host",
    field_cloud_user: "Login user",
    field_cloud_port: "SSH port",
    field_cloud_key_path: "SSH key path",
    field_cloud_remote_workdir: "Remote work directory",
    field_cloud_python: "Remote Python",
    field_cloud_use_docker: "Use Docker remotely",
    not_set: "Not set",
    no_files: "No files yet.",
    no_artifacts: "No key artifacts yet.",
    no_data: "No data",
    can_start: "Can start",
    can_continue: "Can continue",
    can_stop: "Can stop",
    type_project: "Project",
    type_run: "Run",
    type_phase: "Phase group",
    type_stage: "Stage",
    type_artifact: "Artifact",
    type_decision: "Decision",
    type_review: "Review",
    type_quality: "Quality",
    type_deliverable: "Deliverable",
    type_contract: "Contract",
    type_objective: "Objective",
    type_baseline: "Baseline",
    type_reference: "Reference",
    type_constraint: "Constraint",
    status_idle: "Idle",
    status_running: "Running",
    status_completed: "Completed",
    status_done: "Completed",
    status_failed: "Failed",
    status_stopped: "Stopped",
    status_unknown: "Unknown",
    start_time: "Start time",
    updated_time: "Updated time",
    node_type: "Node type",
    node_label: "Node label",
    node_meta: "Metadata",
    studio_system_hint: "Treat this as a ChatGPT-like message stream plus a run timeline.",
  },
};

const state = {
  projects: [],
  selectedProjectId: null,
  selectedProject: null,
  details: null,
  canvas: null,
  studio: null,
  files: null,
  settings: null,
  settingsDraft: null,
  selectedCanvasNodeId: null,
  uiLanguage: window.localStorage.getItem("rc_ui_language") || DEFAULT_LANGUAGE,
  subtabs: {
    start: "basics",
    details: "overview",
    canvas: "graph",
    studio: "chat",
    files: "workspace",
    settings: "ui",
  },
};

const els = {
  projectList: document.getElementById("project-list"),
  emptyState: document.getElementById("empty-state"),
  workspace: document.getElementById("workspace"),
  workspaceTitle: document.getElementById("workspace-title"),
  summaryStrip: document.getElementById("summary-strip"),
  details: document.getElementById("tab-details"),
  canvas: document.getElementById("tab-canvas"),
  studio: document.getElementById("tab-studio"),
  files: document.getElementById("tab-files"),
  startModal: document.getElementById("start-modal"),
  settingsModal: document.getElementById("settings-modal"),
  startForm: document.getElementById("start-form"),
  settingsContent: document.getElementById("settings-content"),
  toast: document.getElementById("toast"),
  continueRun: document.getElementById("continue-run"),
  startRun: document.getElementById("start-run"),
  stopRun: document.getElementById("stop-run"),
};

function t(key) {
  return I18N[state.uiLanguage]?.[key] || I18N[DEFAULT_LANGUAGE][key] || key;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function deepClone(value) {
  return JSON.parse(JSON.stringify(value ?? {}));
}

function applyStaticTranslations() {
  document.documentElement.lang = state.uiLanguage;
  document.title = "My Own PhD Students";
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    const key = node.getAttribute("data-i18n");
    if (key) {
      node.textContent = t(key);
    }
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
    const key = node.getAttribute("data-i18n-placeholder");
    if (key) {
      node.setAttribute("placeholder", t(key));
    }
  });
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const payload = await response.text();
    throw new Error(payload || `HTTP ${response.status}`);
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

function toast(message) {
  els.toast.textContent = message;
  els.toast.classList.remove("hidden");
  window.clearTimeout(toast._timer);
  toast._timer = window.setTimeout(() => els.toast.classList.add("hidden"), 2600);
}

function normalizeMultiline(value) {
  return String(value || "")
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function splitCsv(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function boolLabel(value) {
  return value ? t("yes") : t("no");
}

function typeLabel(type) {
  return t(`type_${String(type || "").toLowerCase()}`) || type || t("not_set");
}

function translateStatus(status = "unknown") {
  return t(`status_${String(status).toLowerCase()}`) || status;
}

function launchModeLabel(mode) {
  const mapping = {
    standard_full_run: t("launch_standard"),
    continue_existing_state: t("launch_continue"),
    review_only: t("launch_review"),
    rebuttal_revision: t("launch_rebuttal"),
  };
  return mapping[String(mode || "")] || mode || t("not_set");
}

function formatDateTime(value) {
  if (!value) {
    return t("not_set");
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return new Intl.DateTimeFormat(state.uiLanguage === "zh-CN" ? "zh-CN" : "en-US", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function statusClass(status = "idle") {
  return `status-${String(status || "idle").toLowerCase()}`;
}

function activeSubtab(group, panel) {
  return state.subtabs[group] === panel ? "active" : "";
}

function renderSubtabBar(group, tabs) {
  return `
    <nav class="subtabbar">
      ${tabs
        .map(
          (tab) => `
            <button class="subtab ${activeSubtab(group, tab.id)}" type="button" data-subtab-group="${group}" data-subtab-panel="${tab.id}">
              ${escapeHtml(tab.label)}
            </button>
          `
        )
        .join("")}
    </nav>
  `;
}

function startupContractFromForm(form) {
  const data = new FormData(form);
  const projectId = String(data.get("project_id") || "").trim();
  const title = String(data.get("title") || "").trim();
  const topic = String(data.get("topic") || "").trim();
  const launchMode = String(data.get("launch_mode") || "standard_full_run");
  const objectives = normalizeMultiline(data.get("objectives"));
  const startupContract = {
    title,
    goal: topic,
    launch_mode: launchMode,
    research_intensity: String(data.get("research_intensity") || "balanced"),
    decision_policy: String(data.get("decision_policy") || "autonomous"),
    runtime_constraints: String(data.get("runtime_constraints") || "").trim(),
    objectives,
    baseline_urls: normalizeMultiline(data.get("baseline_urls")),
    paper_urls: normalizeMultiline(data.get("paper_urls")),
  };
  return {
    project_id: projectId,
    title,
    topic,
    launch_mode: launchMode,
    auto_approve: String(data.get("auto_approve") || "true") === "true",
    startup_contract: startupContract,
  };
}

function renderProjectList() {
  if (!state.projects.length) {
    els.projectList.innerHTML = `<div class="project-card">${escapeHtml(t("no_projects"))}</div>`;
    return;
  }

  els.projectList.innerHTML = state.projects
    .map((project) => {
      const latestRun = project.latest_run;
      const isActive = project.name === state.selectedProjectId ? "active" : "";
      return `
        <button class="project-card ${isActive}" data-project-id="${escapeHtml(project.name)}" type="button">
          <div><strong>${escapeHtml(project.title || project.name)}</strong></div>
          <div>${escapeHtml(project.topic || t("no_project_topic"))}</div>
          <div class="project-meta">
            <span class="status-badge ${statusClass(project.status)}">${escapeHtml(translateStatus(project.status))}</span>
            <span>${latestRun ? escapeHtml(String(latestRun.current_stage || 0)) : "0"}/23</span>
          </div>
        </button>
      `;
    })
    .join("");
}

function renderSummaryStrip() {
  if (!state.selectedProject) {
    els.summaryStrip.innerHTML = "";
    return;
  }

  const latestRun = state.details?.latest_run || {};
  const cards = [
    [t("summary_status"), translateStatus(state.selectedProject.status || "idle")],
    [t("summary_launch_mode"), launchModeLabel(state.selectedProject.launch_mode)],
    [t("summary_stage"), latestRun.current_stage_name || `${latestRun.current_stage || 0}/23`],
    [t("summary_run"), latestRun.run_id || t("not_set")],
  ];

  els.summaryStrip.innerHTML = cards
    .map(
      ([label, value]) => `
        <div class="summary-card">
          <div class="summary-label">${escapeHtml(label)}</div>
          <div class="summary-value">${escapeHtml(String(value || t("not_set")))}</div>
        </div>
      `
    )
    .join("");
}

function metaRows(items) {
  return items
    .map(
      ([label, value]) => `
        <div class="meta-row">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(String(value ?? t("not_set")))}</strong>
        </div>
      `
    )
    .join("");
}

function renderDetails() {
  const details = state.details;
  if (!details) {
    els.details.innerHTML = "";
    return;
  }

  const project = details.project || {};
  const contract = details.startup_contract || {};
  const latestRun = details.latest_run || {};
  const metrics = latestRun.metrics || {};
  const keyArtifacts = details.key_artifacts || [];
  const workspaceFiles = details.workspace_files || [];
  const objectives = contract.objectives || [];
  const metricMarkup = Object.keys(metrics).length
    ? Object.entries(metrics)
        .map(([key, value]) => `<div class="meta-row"><span>${escapeHtml(key)}</span><strong>${escapeHtml(JSON.stringify(value))}</strong></div>`)
        .join("")
    : `<div class="meta-row"><span>${escapeHtml(t("metrics"))}</span><strong>${escapeHtml(t("no_data"))}</strong></div>`;

  els.details.innerHTML = `
    ${renderSubtabBar("details", [
      { id: "overview", label: t("overview") },
      { id: "contract", label: t("contract") },
      { id: "artifacts", label: t("artifacts") },
    ])}
    <section class="subtab-panel ${activeSubtab("details", "overview")}">
      <div class="details-grid">
        <div class="panel-block">
          <h3>${escapeHtml(t("contract_section"))}</h3>
          <div class="meta-list">
            ${metaRows([
              [t("project_id"), project.name],
              [t("project_title"), project.title || project.name],
              [t("research_intensity"), contract.research_intensity || "balanced"],
              [t("decision_policy"), contract.decision_policy || "autonomous"],
              [t("launch_mode"), launchModeLabel(project.launch_mode)],
              [t("updated_time"), formatDateTime(project.updated_at)],
            ])}
          </div>
        </div>
        <div class="panel-block">
          <h3>${escapeHtml(t("latest_run"))}</h3>
          <div class="meta-list">
            ${metaRows([
              ["Run ID", latestRun.run_id || t("not_set")],
              [t("summary_status"), translateStatus(latestRun.status || project.status)],
              [t("summary_stage"), latestRun.current_stage_name || latestRun.current_stage || 0],
              [t("start_time"), formatDateTime(latestRun.start_time)],
            ])}
          </div>
          <div class="panel-block compact">
            <h3>${escapeHtml(t("metrics"))}</h3>
            <div class="meta-list">${metricMarkup}</div>
          </div>
        </div>
      </div>
    </section>
    <section class="subtab-panel ${activeSubtab("details", "contract")}">
      <div class="details-grid">
        <div class="panel-block">
          <h3>${escapeHtml(t("goal"))}</h3>
          <div class="rich-copy">${escapeHtml(contract.goal || t("not_set"))}</div>
        </div>
        <div class="panel-block">
          <h3>${escapeHtml(t("objectives"))}</h3>
          <div class="artifact-list">
            ${objectives.length ? objectives.map((item) => `<div class="artifact-item"><span>${escapeHtml(item)}</span></div>`).join("") : `<div class="artifact-item"><span>${escapeHtml(t("not_set"))}</span></div>`}
          </div>
        </div>
      </div>
      <div class="details-grid stacked-top">
        <div class="panel-block">
          <h3>${escapeHtml(t("baseline_links"))}</h3>
          <div class="artifact-list">
            ${(contract.baseline_urls || []).length
              ? contract.baseline_urls.map((item) => `<div class="artifact-item"><span>${escapeHtml(item)}</span></div>`).join("")
              : `<div class="artifact-item"><span>${escapeHtml(t("not_set"))}</span></div>`}
          </div>
        </div>
        <div class="panel-block">
          <h3>${escapeHtml(t("reference_links"))}</h3>
          <div class="artifact-list">
            ${(contract.paper_urls || []).length
              ? contract.paper_urls.map((item) => `<div class="artifact-item"><span>${escapeHtml(item)}</span></div>`).join("")
              : `<div class="artifact-item"><span>${escapeHtml(t("not_set"))}</span></div>`}
          </div>
        </div>
      </div>
    </section>
    <section class="subtab-panel ${activeSubtab("details", "artifacts")}">
      <div class="details-grid">
        <div class="panel-block">
          <h3>${escapeHtml(t("key_artifacts"))}</h3>
          <div class="file-list">
            ${keyArtifacts.length
              ? keyArtifacts.map((item) => `<div class="file-item"><span>${escapeHtml(item.label)}</span><strong>${escapeHtml(item.path)}</strong></div>`).join("")
              : `<div class="file-item"><span>${escapeHtml(t("no_artifacts"))}</span></div>`}
          </div>
        </div>
        <div class="panel-block">
          <h3>${escapeHtml(t("workspace_files"))}</h3>
          <div class="file-list">
            ${workspaceFiles.length
              ? workspaceFiles.slice(0, 14).map((item) => `<div class="file-item"><span>${escapeHtml(item.path)}</span><strong>${escapeHtml(`${item.size} B`)}</strong></div>`).join("")
              : `<div class="file-item"><span>${escapeHtml(t("no_files"))}</span></div>`}
          </div>
        </div>
      </div>
    </section>
  `;
}

function wrapCanvasText(text, maxChars = 22, maxLines = 3) {
  const chars = Array.from(String(text || ""));
  if (!chars.length) {
    return [t("not_set")];
  }
  const lines = [];
  for (let i = 0; i < chars.length; i += maxChars) {
    lines.push(chars.slice(i, i + maxChars).join(""));
  }
  const trimmed = lines.slice(0, maxLines);
  if (lines.length > maxLines) {
    trimmed[maxLines - 1] = `${trimmed[maxLines - 1].slice(0, Math.max(0, maxChars - 1))}…`;
  }
  return trimmed;
}

function layoutCanvasGraph(nodes) {
  const nodeWidth = 220;
  const nodeHeight = 92;
  const layerGap = 260;
  const rowGap = 126;
  const paddingX = 40;
  const paddingY = 42;
  const layers = new Map();

  nodes.forEach((node) => {
    const layer = Number(node.layer || 0);
    if (!layers.has(layer)) {
      layers.set(layer, []);
    }
    layers.get(layer).push(node);
  });

  const orderedLayers = [...layers.keys()].sort((a, b) => a - b);
  orderedLayers.forEach((layer) => {
    layers.get(layer).sort((a, b) => {
      const sortA = Number(a.sort || 0);
      const sortB = Number(b.sort || 0);
      if (sortA !== sortB) {
        return sortA - sortB;
      }
      return String(a.label || "").localeCompare(String(b.label || ""));
    });
  });

  const maxRows = Math.max(1, ...orderedLayers.map((layer) => layers.get(layer).length));
  const positions = {};

  orderedLayers.forEach((layer) => {
    const items = layers.get(layer);
    const x = paddingX + layer * layerGap;
    const offsetY = paddingY + ((maxRows - items.length) * rowGap) / 2;
    items.forEach((node, index) => {
      positions[node.id] = {
        x,
        y: offsetY + index * rowGap,
        width: nodeWidth,
        height: nodeHeight,
      };
    });
  });

  return {
    positions,
    width: paddingX * 2 + orderedLayers.length * layerGap + nodeWidth,
    height: paddingY * 2 + maxRows * rowGap + nodeHeight,
  };
}

function canvasNodeMeta(node) {
  if (node.type === "run") {
    return `${translateStatus(node.meta?.status || "unknown")} · ${node.meta?.current_stage || 0}/23`;
  }
  if (node.type === "phase") {
    return `${node.meta?.completed || 0}/${node.meta?.total || 0}`;
  }
  if (node.type === "stage") {
    return node.meta?.stage_name || "";
  }
  if (node.type === "decision") {
    return node.meta?.decision || "decision";
  }
  if (node.type === "review") {
    return node.meta?.review_outcome || node.meta?.status || "review";
  }
  return node.meta?.kind || "";
}

function renderCanvasEdge(edge, positions) {
  const source = positions[edge.source];
  const target = positions[edge.target];
  if (!source || !target) {
    return "";
  }

  const startX = source.x + source.width;
  const startY = source.y + source.height / 2;
  const endX = target.x;
  const endY = target.y + target.height / 2;
  const delta = Math.max(60, (endX - startX) / 2);
  const path = `M ${startX} ${startY} C ${startX + delta} ${startY}, ${endX - delta} ${endY}, ${endX} ${endY}`;
  return `<path class="canvas-link canvas-link-${escapeHtml(edge.kind || "flow")}" d="${path}" marker-end="url(#canvas-arrow)"></path>`;
}

function renderCanvasNode(node, box) {
  if (!box) {
    return "";
  }

  const isActive = state.selectedCanvasNodeId === node.id ? "is-active" : "";
  const lines = wrapCanvasText(node.label || "");
  const titleMarkup = lines
    .map((line, index) => `<tspan x="${box.x + 18}" dy="${index === 0 ? 0 : 18}">${escapeHtml(line)}</tspan>`)
    .join("");

  return `
    <g class="canvas-node-group ${isActive}" data-node-id="${escapeHtml(node.id)}" tabindex="0" role="button">
      <rect class="canvas-node-box type-${escapeHtml(node.type)}" x="${box.x}" y="${box.y}" rx="18" ry="18" width="${box.width}" height="${box.height}"></rect>
      <text class="canvas-node-tag" x="${box.x + 18}" y="${box.y + 24}">${escapeHtml(typeLabel(node.type))}</text>
      <text class="canvas-node-title" x="${box.x + 18}" y="${box.y + 48}">${titleMarkup}</text>
      <text class="canvas-node-subtitle" x="${box.x + 18}" y="${box.y + box.height - 14}">${escapeHtml(canvasNodeMeta(node))}</text>
    </g>
  `;
}

function renderCanvasDrawer(node, edges, nodeMap) {
  if (!node) {
    return `
      <div class="canvas-drawer-empty">
        <h3>${escapeHtml(t("canvas_drawer_title"))}</h3>
        <p>${escapeHtml(t("canvas_drawer_empty"))}</p>
      </div>
    `;
  }

  const relatedEdges = edges.filter((edge) => edge.source === node.id || edge.target === node.id);
  const metaEntries = Object.entries(node.meta || {});

  return `
    <div class="canvas-drawer-card">
      <div class="eyebrow">${escapeHtml(typeLabel(node.type))}</div>
      <h3>${escapeHtml(node.label || t("not_set"))}</h3>
      <div class="meta-list">
        ${metaRows([
          [t("node_type"), typeLabel(node.type)],
          [t("node_label"), node.label || t("not_set")],
          [t("summary_launch_mode"), node.meta?.launch_mode || ""],
        ])}
      </div>
    </div>
    <div class="canvas-drawer-card">
      <h3>${escapeHtml(t("node_meta"))}</h3>
      <div class="file-list">
        ${metaEntries.length
          ? metaEntries.map(([key, value]) => `<div class="file-item"><span>${escapeHtml(key)}</span><strong>${escapeHtml(typeof value === "object" ? JSON.stringify(value) : String(value))}</strong></div>`).join("")
          : `<div class="file-item"><span>${escapeHtml(t("no_data"))}</span></div>`}
      </div>
    </div>
    <div class="canvas-drawer-card">
      <h3>${escapeHtml(t("related_edges"))}</h3>
      <div class="file-list">
        ${relatedEdges.length
          ? relatedEdges.map((edge) => {
              const otherId = edge.source === node.id ? edge.target : edge.source;
              const otherNode = nodeMap.get(otherId);
              return `<div class="file-item"><span>${escapeHtml(`${typeLabel(otherNode?.type || "")}: ${otherNode?.label || otherId}`)}</span><strong>${escapeHtml(edge.kind || "flow")}</strong></div>`;
            }).join("")
          : `<div class="file-item"><span>${escapeHtml(t("no_data"))}</span></div>`}
      </div>
    </div>
  `;
}

function renderCanvas() {
  const canvas = state.canvas;
  if (!canvas) {
    els.canvas.innerHTML = "";
    return;
  }

  const nodes = canvas.nodes || [];
  const edges = canvas.edges || [];
  if (!nodes.length) {
    els.canvas.innerHTML = `<div class="panel-block canvas-empty">${escapeHtml(t("canvas_empty"))}</div>`;
    return;
  }

  if (!state.selectedCanvasNodeId || !nodes.some((node) => node.id === state.selectedCanvasNodeId)) {
    state.selectedCanvasNodeId = nodes[0].id;
  }

  const layout = layoutCanvasGraph(nodes);
  const nodeMap = new Map(nodes.map((node) => [node.id, node]));
  const selectedNode = nodeMap.get(state.selectedCanvasNodeId) || null;
  const edgeMarkup = edges.map((edge) => renderCanvasEdge(edge, layout.positions)).join("");
  const nodeMarkup = nodes.map((node) => renderCanvasNode(node, layout.positions[node.id])).join("");
  const phaseRail = (canvas.meta?.phases || []).map((phase) => `<span class="phase-chip">${escapeHtml(phase)}</span>`).join("");

  els.canvas.innerHTML = `
    ${renderSubtabBar("canvas", [
      { id: "graph", label: t("graph") },
      { id: "entities", label: t("nodes") },
      { id: "edges", label: t("edges") },
    ])}
    <section class="subtab-panel ${activeSubtab("canvas", "graph")}">
      <div class="canvas-layout">
        <div class="panel-block canvas-shell">
          <div class="canvas-header">
            <div>
              <h3>${escapeHtml(t("canvas_title"))}</h3>
              <div class="canvas-meta">
                <span>${escapeHtml(canvas.meta?.title || state.selectedProject?.title || "")}</span>
                <span>${escapeHtml(launchModeLabel(canvas.meta?.launch_mode))}</span>
                <span>${escapeHtml(canvas.meta?.latest_run_id || t("not_set"))}</span>
              </div>
            </div>
            <div class="canvas-legend">
              ${["project", "run", "phase", "stage", "artifact", "decision", "review"].map((type) => `
                <span class="legend-item"><span class="legend-swatch type-${escapeHtml(type)}"></span>${escapeHtml(typeLabel(type))}</span>
              `).join("")}
            </div>
          </div>
          <div class="canvas-phase-rail">${phaseRail}</div>
          <svg class="canvas-svg" viewBox="0 0 ${layout.width} ${layout.height}" role="img" aria-label="${escapeHtml(t("canvas_title"))}">
            <defs>
              <marker id="canvas-arrow" viewBox="0 0 12 12" refX="10" refY="6" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
                <path d="M 0 0 L 12 6 L 0 12 z" fill="currentColor"></path>
              </marker>
            </defs>
            ${edgeMarkup}
            ${nodeMarkup}
          </svg>
        </div>
        <aside class="canvas-drawer">
          ${renderCanvasDrawer(selectedNode, edges, nodeMap)}
        </aside>
      </div>
    </section>
    <section class="subtab-panel ${activeSubtab("canvas", "entities")}">
      <div class="panel-block">
        <h3>${escapeHtml(t("nodes"))}</h3>
        <div class="file-list">
          ${nodes.map((node) => `
            <button class="canvas-list-item ${state.selectedCanvasNodeId === node.id ? "active" : ""}" type="button" data-node-id="${escapeHtml(node.id)}">
              <span>${escapeHtml(node.label)}</span>
              <strong>${escapeHtml(typeLabel(node.type))}</strong>
            </button>
          `).join("")}
        </div>
      </div>
    </section>
    <section class="subtab-panel ${activeSubtab("canvas", "edges")}">
      <div class="panel-block">
        <h3>${escapeHtml(t("edges"))}</h3>
        <div class="file-list">
          ${edges.map((edge) => `<div class="file-item"><span>${escapeHtml(`${edge.source} -> ${edge.target}`)}</span><strong>${escapeHtml(edge.kind || "flow")}</strong></div>`).join("")}
        </div>
      </div>
    </section>
  `;
}

function renderStudioMessages(messages) {
  if (!messages.length) {
    return `<div class="message-placeholder">${escapeHtml(t("message_flow_empty"))}</div>`;
  }
  return messages
    .map((message) => `
      <article class="message-card message-${escapeHtml(message.role || "assistant")}">
        <div class="message-head">
          <strong>${escapeHtml(message.title || message.role || "assistant")}</strong>
          <span>${escapeHtml(formatDateTime(message.timestamp))}</span>
        </div>
        <div class="message-body">${escapeHtml(message.content || "").replaceAll("\n", "<br>")}</div>
      </article>
    `)
    .join("");
}

function renderTimeline(events) {
  if (!events.length) {
    return `<div class="message-placeholder">${escapeHtml(t("timeline_empty"))}</div>`;
  }
  return `
    <div class="timeline-list">
      ${events.map((event) => `
        <article class="timeline-item">
          <div class="timeline-dot status-${escapeHtml(String(event.status || "unknown").toLowerCase())}"></div>
          <div class="timeline-copy">
            <div class="timeline-head">
              <strong>${escapeHtml(event.title || t("not_set"))}</strong>
              <span>${escapeHtml(formatDateTime(event.timestamp))}</span>
            </div>
            <div class="timeline-body">${escapeHtml(event.description || "")}</div>
          </div>
        </article>
      `).join("")}
    </div>
  `;
}

function renderStudio() {
  const studio = state.studio;
  if (!studio) {
    els.studio.innerHTML = "";
    return;
  }

  const messages = studio.messages || [];
  const timeline = studio.timeline || [];
  const logs = studio.logs || [];
  const controls = studio.controls || {};

  els.studio.innerHTML = `
    ${renderSubtabBar("studio", [
      { id: "chat", label: t("chat_flow") },
      { id: "timeline", label: t("timeline") },
      { id: "logs", label: t("logs") },
    ])}
    <section class="subtab-panel ${activeSubtab("studio", "chat")}">
      <div class="studio-layout">
        <div class="panel-block">
          <div class="studio-header-copy">
            <h3>Studio</h3>
            <p>${escapeHtml(t("studio_system_hint"))}</p>
          </div>
          <div class="message-thread">
            ${renderStudioMessages(messages)}
          </div>
        </div>
        <aside class="studio-side">
          <div class="panel-block">
            <h3>${escapeHtml(t("controls"))}</h3>
            <div class="meta-list">
              ${metaRows([
                [t("can_start"), boolLabel(controls.can_start)],
                [t("can_continue"), boolLabel(controls.can_continue)],
                [t("can_stop"), boolLabel(controls.can_stop)],
                [t("launch_mode"), launchModeLabel(controls.launch_mode)],
                [t("summary_run"), controls.continue_run_id || t("not_set")],
                [t("summary_stage"), controls.continue_from_stage || t("not_set")],
              ])}
            </div>
            <div class="control-actions">
              <button class="secondary-action" type="button" data-studio-action="continue" ${controls.can_continue ? "" : "disabled"}>${escapeHtml(t("continue_run"))}</button>
              <button class="secondary-action" type="button" data-studio-action="start" ${controls.can_start ? "" : "disabled"}>${escapeHtml(t("run"))}</button>
              <button class="danger-action" type="button" data-studio-action="stop" ${controls.can_stop ? "" : "disabled"}>${escapeHtml(t("stop"))}</button>
            </div>
          </div>
          <div class="panel-block">
            <h3>${escapeHtml(t("current_context"))}</h3>
            <div class="rich-copy">${escapeHtml(studio.project?.latest_summary || t("message_flow_empty"))}</div>
          </div>
        </aside>
      </div>
    </section>
    <section class="subtab-panel ${activeSubtab("studio", "timeline")}">
      <div class="panel-block">
        <h3>${escapeHtml(t("timeline"))}</h3>
        ${renderTimeline(timeline)}
      </div>
    </section>
    <section class="subtab-panel ${activeSubtab("studio", "logs")}">
      <div class="log-panel">
        <h3>${escapeHtml(t("logs"))}</h3>
        ${logs.length ? logs.map((line) => `<div class="log-line">${escapeHtml(line)}</div>`).join("") : `<div class="log-line">${escapeHtml(t("log_empty"))}</div>`}
      </div>
    </section>
  `;
}

function renderFiles() {
  const files = state.files?.files || [];
  const artifacts = state.details?.key_artifacts || [];
  els.files.innerHTML = `
    ${renderSubtabBar("files", [
      { id: "workspace", label: t("workspace_files") },
      { id: "artifacts", label: t("artifacts") },
    ])}
    <section class="subtab-panel ${activeSubtab("files", "workspace")}">
      <div class="file-panel">
        <h3>${escapeHtml(t("workspace_files"))}</h3>
        <div class="file-list">
          ${files.length ? files.map((item) => `<div class="file-item"><span>${escapeHtml(item.path)}</span><strong>${escapeHtml(`${item.size} B`)}</strong></div>`).join("") : `<div class="file-item"><span>${escapeHtml(t("no_files"))}</span></div>`}
        </div>
      </div>
    </section>
    <section class="subtab-panel ${activeSubtab("files", "artifacts")}">
      <div class="file-panel">
        <h3>${escapeHtml(t("key_artifacts"))}</h3>
        <div class="file-list">
          ${artifacts.length ? artifacts.map((item) => `<div class="file-item"><span>${escapeHtml(item.path)}</span><strong>${escapeHtml(item.label)}</strong></div>`).join("") : `<div class="file-item"><span>${escapeHtml(t("no_artifacts"))}</span></div>`}
        </div>
      </div>
    </section>
  `;
}

function getSetting(path, fallback = "") {
  const parts = path.split(".");
  let current = state.settingsDraft || {};
  for (const part of parts) {
    if (current == null || typeof current !== "object" || !(part in current)) {
      return fallback;
    }
    current = current[part];
  }
  return current ?? fallback;
}

function setSetting(path, value) {
  const parts = path.split(".");
  let current = state.settingsDraft;
  parts.forEach((part, index) => {
    if (index === parts.length - 1) {
      current[part] = value;
      return;
    }
    if (!current[part] || typeof current[part] !== "object") {
      current[part] = {};
    }
    current = current[part];
  });
}

function renderSelectField({ label, path, value, options, help = "" }) {
  return `
    <label class="field">
      <span>${escapeHtml(label)}</span>
      <select data-setting-path="${escapeHtml(path)}" data-setting-type="string">
        ${options.map((option) => `<option value="${escapeHtml(option.value)}" ${String(option.value) === String(value) ? "selected" : ""}>${escapeHtml(option.label)}</option>`).join("")}
      </select>
      ${help ? `<small>${escapeHtml(help)}</small>` : ""}
    </label>
  `;
}

function renderBooleanField({ label, path, value }) {
  return renderSelectField({
    label,
    path,
    value: value ? "true" : "false",
    options: [
      { value: "true", label: t("yes") },
      { value: "false", label: t("no") },
    ],
  });
}

function renderInputField({ label, path, value, type = "text", help = "" }) {
  return `
    <label class="field">
      <span>${escapeHtml(label)}</span>
      <input type="${escapeHtml(type)}" value="${escapeHtml(value)}" data-setting-path="${escapeHtml(path)}" data-setting-type="${escapeHtml(type === "number" ? "number" : "string")}" />
      ${help ? `<small>${escapeHtml(help)}</small>` : ""}
    </label>
  `;
}

function renderTextAreaField({ label, path, value, help = "", rows = 3 }) {
  return `
    <label class="field span-2">
      <span>${escapeHtml(label)}</span>
      <textarea rows="${rows}" data-setting-path="${escapeHtml(path)}" data-setting-type="string">${escapeHtml(value)}</textarea>
      ${help ? `<small>${escapeHtml(help)}</small>` : ""}
    </label>
  `;
}

function renderCsvField({ label, path, value, help = "" }) {
  const text = Array.isArray(value) ? value.join(", ") : String(value || "");
  return `
    <label class="field">
      <span>${escapeHtml(label)}</span>
      <input type="text" value="${escapeHtml(text)}" data-setting-path="${escapeHtml(path)}" data-setting-type="csv" />
      ${help ? `<small>${escapeHtml(help)}</small>` : ""}
    </label>
  `;
}

function renderSettingsSection(title, body) {
  return `<section class="settings-section"><h3>${escapeHtml(title)}</h3><div class="field-grid">${body}</div></section>`;
}

function renderSettingsAction(label, id) {
  return `
    <div class="settings-action-row span-2">
      <button id="${escapeHtml(id)}" class="secondary-action" type="button">${escapeHtml(label)}</button>
    </div>
  `;
}

function renderSettings() {
  const currentMode = String(getSetting("experiment.mode", "simulated"));
  const computeTarget =
    currentMode === "ssh_remote"
      ? "cloud"
      : currentMode === "docker"
        ? "docker"
        : "local";

  els.settingsContent.innerHTML = `
    ${renderSubtabBar("settings", [
      { id: "ui", label: t("settings_ui") },
      { id: "research", label: t("settings_research") },
      { id: "runtime", label: t("settings_runtime") },
      { id: "quality", label: t("settings_quality") },
      { id: "server", label: t("settings_server") },
      { id: "automation", label: t("settings_automation") },
    ])}
    <div class="settings-layout">
      <section class="subtab-panel ${activeSubtab("settings", "ui")}">
        ${renderSettingsSection(t("appearance"), `
          <label class="field">
            <span>${escapeHtml(t("language"))}</span>
            <select id="ui-language-select">
              <option value="zh-CN" ${state.uiLanguage === "zh-CN" ? "selected" : ""}>${escapeHtml(t("language_zh"))}</option>
              <option value="en" ${state.uiLanguage === "en" ? "selected" : ""}>${escapeHtml(t("language_en"))}</option>
            </select>
          </label>
          ${renderInputField({ label: t("field_project_name"), path: "project.name", value: getSetting("project.name", "") })}
        `)}
        ${renderSettingsSection(t("interaction"), `
          ${renderBooleanField({ label: t("field_pause_at_gates"), path: "copilot.pause_at_gates", value: getSetting("copilot.pause_at_gates", true) })}
          ${renderBooleanField({ label: t("field_pause_every_stage"), path: "copilot.pause_at_every_stage", value: getSetting("copilot.pause_at_every_stage", false) })}
          ${renderBooleanField({ label: t("field_allow_branching"), path: "copilot.allow_branching", value: getSetting("copilot.allow_branching", true) })}
          ${renderInputField({ label: t("field_max_branches"), path: "copilot.max_branches", value: getSetting("copilot.max_branches", 3), type: "number" })}
        `)}
      </section>
      <section class="subtab-panel ${activeSubtab("settings", "research")}">
        ${renderSettingsSection(t("research_scope"), `
          ${renderInputField({ label: t("field_topic"), path: "research.topic", value: getSetting("research.topic", "") })}
          ${renderCsvField({ label: t("field_domains"), path: "research.domains", value: getSetting("research.domains", []), help: t("help_domains") })}
          ${renderInputField({ label: t("field_daily_papers"), path: "research.daily_paper_count", value: getSetting("research.daily_paper_count", 0), type: "number" })}
          ${renderInputField({ label: t("field_quality_threshold"), path: "research.quality_threshold", value: getSetting("research.quality_threshold", 0), type: "number" })}
          ${renderTextAreaField({ label: t("field_baseline_brief"), path: "research.baseline_brief", value: getSetting("research.baseline_brief", ""), help: t("help_baseline_brief") })}
        `)}
      </section>
      <section class="subtab-panel ${activeSubtab("settings", "runtime")}">
        ${renderSettingsSection(t("runtime_limits"), `
          ${renderInputField({ label: t("field_timezone"), path: "runtime.timezone", value: getSetting("runtime.timezone", "Asia/Shanghai") })}
          ${renderInputField({ label: t("field_parallel"), path: "runtime.max_parallel_tasks", value: getSetting("runtime.max_parallel_tasks", 1), type: "number" })}
          ${renderInputField({ label: t("field_approval_timeout"), path: "runtime.approval_timeout_hours", value: getSetting("runtime.approval_timeout_hours", 12), type: "number" })}
          ${renderInputField({ label: t("field_retry_limit"), path: "runtime.retry_limit", value: getSetting("runtime.retry_limit", 0), type: "number" })}
        `)}
        ${renderSettingsSection(t("cloud_execution"), `
          ${renderSelectField({
            label: t("field_compute_target"),
            path: "__compute_target__",
            value: computeTarget,
            options: [
              { value: "local", label: t("compute_target_local") },
              { value: "docker", label: t("compute_target_docker") },
              { value: "cloud", label: t("compute_target_cloud") },
            ],
            help: t("cloud_server_desc"),
          })}
          ${renderInputField({ label: t("field_cloud_host"), path: "experiment.ssh_remote.host", value: getSetting("experiment.ssh_remote.host", "") })}
          ${renderInputField({ label: t("field_cloud_user"), path: "experiment.ssh_remote.user", value: getSetting("experiment.ssh_remote.user", "") })}
          ${renderInputField({ label: t("field_cloud_port"), path: "experiment.ssh_remote.port", value: getSetting("experiment.ssh_remote.port", 22), type: "number" })}
          ${renderInputField({ label: t("field_cloud_key_path"), path: "experiment.ssh_remote.key_path", value: getSetting("experiment.ssh_remote.key_path", "") })}
          ${renderInputField({ label: t("field_cloud_remote_workdir"), path: "experiment.ssh_remote.remote_workdir", value: getSetting("experiment.ssh_remote.remote_workdir", "/tmp/researchclaw_experiments") })}
          ${renderInputField({ label: t("field_cloud_python"), path: "experiment.ssh_remote.remote_python", value: getSetting("experiment.ssh_remote.remote_python", "python3") })}
          ${renderBooleanField({ label: t("field_cloud_use_docker"), path: "experiment.ssh_remote.use_docker", value: getSetting("experiment.ssh_remote.use_docker", false) })}
        `)}
        ${renderSettingsSection(t("experiment_policy"), `
          ${renderSelectField({
            label: t("field_experiment_mode"),
            path: "experiment.mode",
            value: getSetting("experiment.mode", "simulated"),
            options: [
              { value: "simulated", label: "simulated" },
              { value: "sandbox", label: "sandbox" },
              { value: "docker", label: "docker" },
              { value: "ssh_remote", label: "ssh_remote" },
              { value: "colab_drive", label: "colab_drive" },
              { value: "agentic", label: "agentic" },
            ],
          })}
          ${renderInputField({ label: t("field_time_budget"), path: "experiment.time_budget_sec", value: getSetting("experiment.time_budget_sec", 300), type: "number" })}
          ${renderInputField({ label: t("field_iterations"), path: "experiment.max_iterations", value: getSetting("experiment.max_iterations", 10), type: "number" })}
          ${renderInputField({ label: t("field_metric_key"), path: "experiment.metric_key", value: getSetting("experiment.metric_key", "primary_metric") })}
        `)}
      </section>
      <section class="subtab-panel ${activeSubtab("settings", "quality")}">
        ${renderSettingsSection(t("quality_gate"), `
          ${renderInputField({ label: t("field_target_venue"), path: "quality_assessor.target_venue", value: getSetting("quality_assessor.target_venue", "CCF-A") })}
          ${renderInputField({ label: t("field_target_score"), path: "quality_assessor.review_target_score", value: getSetting("quality_assessor.review_target_score", 6), type: "number" })}
          ${renderInputField({ label: t("field_review_rounds"), path: "quality_assessor.max_review_rounds", value: getSetting("quality_assessor.max_review_rounds", 4), type: "number" })}
          ${renderInputField({ label: t("field_improvement"), path: "quality_assessor.min_score_improvement", value: getSetting("quality_assessor.min_score_improvement", 0.2), type: "number" })}
        `)}
        ${renderSettingsSection(t("notifications"), `
          ${renderInputField({ label: t("field_notifications_channel"), path: "notifications.channel", value: getSetting("notifications.channel", ""), help: t("help_notification_channel") })}
          ${renderBooleanField({ label: t("field_stage_start"), path: "notifications.on_stage_start", value: getSetting("notifications.on_stage_start", false) })}
          ${renderBooleanField({ label: t("field_stage_complete"), path: "notifications.on_stage_complete", value: getSetting("notifications.on_stage_complete", false) })}
          ${renderBooleanField({ label: t("field_stage_fail"), path: "notifications.on_stage_fail", value: getSetting("notifications.on_stage_fail", false) })}
          ${renderSettingsAction(t("test_feishu_notification"), "test-feishu-notification")}
        `)}
      </section>
      <section class="subtab-panel ${activeSubtab("settings", "server")}">
        ${renderSettingsSection(t("web_server"), `
          ${renderBooleanField({ label: t("field_server_enabled"), path: "server.enabled", value: getSetting("server.enabled", true) })}
          ${renderInputField({ label: t("field_host"), path: "server.host", value: getSetting("server.host", "127.0.0.1") })}
          ${renderInputField({ label: t("field_port"), path: "server.port", value: getSetting("server.port", 8080), type: "number" })}
          ${renderBooleanField({ label: t("field_voice"), path: "server.voice_enabled", value: getSetting("server.voice_enabled", false) })}
        `)}
        ${renderSettingsSection(t("dashboard"), `
          ${renderBooleanField({ label: t("field_dashboard_enabled"), path: "dashboard.enabled", value: getSetting("dashboard.enabled", true) })}
          ${renderInputField({ label: t("field_refresh_interval"), path: "dashboard.refresh_interval_sec", value: getSetting("dashboard.refresh_interval_sec", 5), type: "number" })}
          ${renderBooleanField({ label: t("field_browser_notifications"), path: "dashboard.browser_notifications", value: getSetting("dashboard.browser_notifications", true) })}
        `)}
      </section>
      <section class="subtab-panel ${activeSubtab("settings", "automation")}">
        ${renderSettingsSection(t("co_pilot"), `
          ${renderBooleanField({ label: t("field_pause_at_gates"), path: "copilot.pause_at_gates", value: getSetting("copilot.pause_at_gates", true) })}
          ${renderBooleanField({ label: t("field_pause_every_stage"), path: "copilot.pause_at_every_stage", value: getSetting("copilot.pause_at_every_stage", false) })}
          ${renderBooleanField({ label: t("field_allow_branching"), path: "copilot.allow_branching", value: getSetting("copilot.allow_branching", true) })}
          ${renderInputField({ label: t("field_max_branches"), path: "copilot.max_branches", value: getSetting("copilot.max_branches", 3), type: "number" })}
        `)}
        ${renderSettingsSection(t("multi_project"), `
          ${renderBooleanField({ label: t("field_multi_enabled"), path: "multi_project.enabled", value: getSetting("multi_project.enabled", true) })}
          ${renderInputField({ label: t("field_projects_dir"), path: "multi_project.projects_dir", value: getSetting("multi_project.projects_dir", ".researchclaw/projects") })}
          ${renderInputField({ label: t("field_max_concurrent"), path: "multi_project.max_concurrent", value: getSetting("multi_project.max_concurrent", 2), type: "number" })}
          ${renderBooleanField({ label: t("field_shared_knowledge"), path: "multi_project.shared_knowledge", value: getSetting("multi_project.shared_knowledge", true) })}
        `)}
      </section>
    </div>
    <div class="form-actions sticky-actions">
      <button id="save-settings" class="primary-action" type="button">${escapeHtml(t("save_settings"))}</button>
    </div>
  `;
}

function captureSettingsDraft() {
  if (!state.settingsDraft) {
    return;
  }
  els.settingsContent.querySelectorAll("[data-setting-path]").forEach((input) => {
    const path = input.getAttribute("data-setting-path");
    const type = input.getAttribute("data-setting-type");
    if (!path) {
      return;
    }
    let value = input.value;
    if (type === "number") {
      const parsed = Number(value);
      value = Number.isFinite(parsed) ? parsed : 0;
    } else if (type === "csv") {
      value = splitCsv(value);
    } else if (input.tagName === "SELECT" && (value === "true" || value === "false")) {
      value = value === "true";
    }
    if (path === "__compute_target__") {
      if (value === "local") {
        setSetting("experiment.mode", "sandbox");
      } else if (value === "cloud") {
        setSetting("experiment.mode", "ssh_remote");
      } else if (value === "docker") {
        setSetting("experiment.mode", "docker");
      }
      return;
    }
    setSetting(path, value);
  });
}

async function loadProjects() {
  const payload = await api("/api/projects");
  state.projects = payload.projects || [];
  renderProjectList();
  if (!state.projects.length) {
    state.selectedProjectId = null;
    state.selectedProject = null;
    els.workspace.classList.add("hidden");
    els.emptyState.classList.remove("hidden");
    syncPrimaryControls();
    return;
  }
  if (!state.selectedProjectId || !state.projects.some((project) => project.name === state.selectedProjectId)) {
    await selectProject(state.projects[0].name);
  }
}

async function loadProjectWorkspace(projectId) {
  const [projectPayload, details, canvas, studio, files] = await Promise.all([
    api(`/api/projects/${projectId}`),
    api(`/api/projects/${projectId}/details`),
    api(`/api/projects/${projectId}/canvas`),
    api(`/api/projects/${projectId}/studio`),
    api(`/api/projects/${projectId}/files`),
  ]);
  state.selectedProject = projectPayload.project;
  state.details = details;
  state.canvas = canvas;
  state.studio = studio;
  state.files = files;
  if (!state.selectedCanvasNodeId || !(canvas.nodes || []).some((node) => node.id === state.selectedCanvasNodeId)) {
    state.selectedCanvasNodeId = canvas.nodes?.[0]?.id || null;
  }
  els.emptyState.classList.add("hidden");
  els.workspace.classList.remove("hidden");
  els.workspaceTitle.textContent = state.selectedProject.title || state.selectedProject.name;
  renderAllWorkspace();
}

async function selectProject(projectId) {
  state.selectedProjectId = projectId;
  await loadProjectWorkspace(projectId);
}

async function createProjectAndMaybeRun(event) {
  event.preventDefault();
  const payload = startupContractFromForm(els.startForm);
  await api("/api/projects", {
    method: "POST",
    body: JSON.stringify({
      project_id: payload.project_id,
      title: payload.title,
      topic: payload.topic,
      startup_contract: payload.startup_contract,
      launch_mode: payload.launch_mode,
    }),
  });
  await api("/api/pipeline/start", {
    method: "POST",
    body: JSON.stringify({
      topic: payload.topic,
      auto_approve: payload.auto_approve,
      project_id: payload.project_id,
      startup_contract: payload.startup_contract,
      launch_mode: payload.launch_mode,
    }),
  });
  closeModal("start-modal");
  toast(t("project_created"));
  await loadProjects();
  await selectProject(payload.project_id);
}

async function startSelectedProject() {
  if (!state.selectedProjectId || !state.selectedProject) {
    toast(t("select_project_first"));
    return;
  }
  await api("/api/pipeline/start", {
    method: "POST",
    body: JSON.stringify({
      topic: state.selectedProject.topic,
      auto_approve: true,
      project_id: state.selectedProjectId,
      startup_contract: state.selectedProject.startup_contract || {},
      launch_mode: state.selectedProject.launch_mode,
    }),
  });
  toast(t("pipeline_started"));
  await loadProjectWorkspace(state.selectedProjectId);
}

async function continueSelectedProject() {
  if (!state.selectedProjectId || !state.selectedProject) {
    toast(t("select_project_first"));
    return;
  }
  const controls = state.studio?.controls || {};
  if (!controls.can_continue) {
    toast(t("no_recoverable_run"));
    return;
  }
  await api("/api/pipeline/start", {
    method: "POST",
    body: JSON.stringify({
      topic: state.selectedProject.topic,
      auto_approve: true,
      project_id: state.selectedProjectId,
      startup_contract: state.selectedProject.startup_contract || {},
      launch_mode: "continue_existing_state",
      resume: true,
    }),
  });
  toast(t("pipeline_continued"));
  await loadProjectWorkspace(state.selectedProjectId);
}

async function stopSelectedProject() {
  await api("/api/pipeline/stop", { method: "POST" });
  toast(t("pipeline_stopped"));
  if (state.selectedProjectId) {
    await loadProjectWorkspace(state.selectedProjectId);
  }
}

function openModal(id) {
  document.getElementById(id).classList.remove("hidden");
}

function closeModal(id) {
  document.getElementById(id).classList.add("hidden");
}

async function loadSettings() {
  const settingsPayload = await api("/api/settings");
  state.settings = settingsPayload;
  state.settingsDraft = deepClone(settingsPayload.config || {});
  renderSettings();
}

async function saveSettings() {
  captureSettingsDraft();
  const payload = await api("/api/settings", {
    method: "POST",
    body: JSON.stringify({ config: state.settingsDraft }),
  });
  state.settings = payload;
  state.settingsDraft = deepClone(payload.config || state.settingsDraft);
  toast(t("settings_saved"));
  renderSettings();
}

async function testFeishuNotification() {
  captureSettingsDraft();
  const payload = await api("/api/settings/test-notification", {
    method: "POST",
    body: JSON.stringify({ config: state.settingsDraft }),
  });
  if (payload?.status !== "ok") {
    throw new Error(t("feishu_test_failed"));
  }
  toast(t("feishu_test_sent"));
}

function updateContractPreview() {
  // Startup modal no longer renders a preview panel.
}

function renderStartSubtabs() {
  document.querySelectorAll('[data-subtab-group="start"]').forEach((button) => {
    if (!(button instanceof HTMLElement)) {
      return;
    }
    button.classList.toggle("active", button.dataset.subtabPanel === state.subtabs.start);
  });
  document.querySelectorAll("[data-start-panel]").forEach((panel) => {
    if (!(panel instanceof HTMLElement)) {
      return;
    }
    panel.classList.toggle("active", panel.dataset.startPanel === state.subtabs.start);
  });
}

function resetStartFormView() {
  state.subtabs.start = "basics";
  renderStartSubtabs();
  if (els.startForm instanceof HTMLFormElement) {
    els.startForm.reset();
  }
}

function bindTabs() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((item) => item.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById(`tab-${tab.dataset.tab}`).classList.add("active");
    });
  });
}

function renderAllWorkspace() {
  renderProjectList();
  renderSummaryStrip();
  renderDetails();
  renderCanvas();
  renderStudio();
  renderFiles();
  syncPrimaryControls();
}

function syncPrimaryControls() {
  const controls = state.studio?.controls || {};
  const hasProject = Boolean(state.selectedProjectId && state.selectedProject);
  if (els.startRun) {
    els.startRun.disabled = !hasProject || !controls.can_start;
  }
  if (els.continueRun) {
    els.continueRun.disabled = !hasProject || !controls.can_continue;
  }
  if (els.stopRun) {
    els.stopRun.disabled = !hasProject || !controls.can_stop;
  }
}

function renderAll() {
  applyStaticTranslations();
  renderAllWorkspace();
  if (!els.settingsModal.classList.contains("hidden") && state.settingsDraft) {
    renderSettings();
  }
  renderStartSubtabs();
}

function bindDynamicUi() {
  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }
    const projectButton = target.closest("[data-project-id]");
    if (projectButton instanceof HTMLElement) {
      const projectId = projectButton.dataset.projectId;
      if (projectId) {
        selectProject(projectId).catch((error) => {
          toast(error.message);
          console.error(error);
        });
      }
      return;
    }
    const subtab = target.closest(".subtab");
    if (subtab instanceof HTMLElement) {
      const group = subtab.dataset.subtabGroup;
      const panel = subtab.dataset.subtabPanel;
      if (group && panel) {
        if (group === "settings") {
          captureSettingsDraft();
        }
        state.subtabs[group] = panel;
        if (group === "start") renderStartSubtabs();
        if (group === "details") renderDetails();
        if (group === "canvas") renderCanvas();
        if (group === "studio") renderStudio();
        if (group === "files") renderFiles();
        if (group === "settings") renderSettings();
      }
      return;
    }
    if (target.id === "save-settings") {
      saveSettings().catch((error) => {
        toast(error.message);
        console.error(error);
      });
      return;
    }
    if (target.id === "test-feishu-notification") {
      testFeishuNotification().catch((error) => {
        toast(error.message || t("feishu_test_failed"));
        console.error(error);
      });
      return;
    }
    const canvasNode = target.closest("[data-node-id]");
    if (canvasNode instanceof HTMLElement) {
      const nodeId = canvasNode.dataset.nodeId;
      if (nodeId) {
        state.selectedCanvasNodeId = nodeId;
        state.subtabs.canvas = "graph";
        renderCanvas();
      }
      return;
    }
    const studioAction = target.closest("[data-studio-action]");
    if (studioAction instanceof HTMLElement) {
      const action = studioAction.dataset.studioAction;
      const task = action === "continue"
        ? continueSelectedProject
        : action === "start"
          ? startSelectedProject
          : stopSelectedProject;
      task().catch((error) => {
        toast(error.message);
        console.error(error);
      });
    }
  });

  document.addEventListener("change", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }
    if (target.id === "ui-language-select" && target instanceof HTMLSelectElement) {
      state.uiLanguage = target.value || DEFAULT_LANGUAGE;
      window.localStorage.setItem("rc_ui_language", state.uiLanguage);
      renderAll();
      return;
    }
    const settingPath = target.getAttribute("data-setting-path");
    if (
      !els.settingsModal.classList.contains("hidden") &&
      (settingPath === "__compute_target__" || settingPath === "experiment.mode")
    ) {
      captureSettingsDraft();
      renderSettings();
    }
  });
}

function bindUi() {
  document.getElementById("refresh-projects").addEventListener("click", () => {
    loadProjects().catch((error) => {
      toast(error.message);
      console.error(error);
    });
  });
  document.getElementById("open-start-modal").addEventListener("click", () => {
    resetStartFormView();
    openModal("start-modal");
  });
  document.getElementById("open-settings").addEventListener("click", async () => {
    await loadSettings();
    openModal("settings-modal");
  });
  document.getElementById("continue-run").addEventListener("click", () => {
    continueSelectedProject().catch((error) => {
      toast(error.message);
      console.error(error);
    });
  });
  document.getElementById("start-run").addEventListener("click", () => {
    startSelectedProject().catch((error) => {
      toast(error.message);
      console.error(error);
    });
  });
  document.getElementById("stop-run").addEventListener("click", () => {
    stopSelectedProject().catch((error) => {
      toast(error.message);
      console.error(error);
    });
  });
  document.querySelectorAll("[data-close-modal]").forEach((button) => {
    button.addEventListener("click", () => closeModal(button.dataset.closeModal));
  });
  els.startForm.addEventListener("submit", createProjectAndMaybeRun);
  bindTabs();
  bindDynamicUi();
  applyStaticTranslations();
  renderStartSubtabs();
}

async function poll() {
  if (state.selectedProjectId) {
    try {
      await loadProjectWorkspace(state.selectedProjectId);
    } catch {
      // Keep current UI on intermittent errors.
    }
  }
}

async function boot() {
  bindUi();
  await loadProjects();
  window.setInterval(poll, 5000);
}

boot().catch((error) => {
  toast(error.message);
  console.error(error);
});
