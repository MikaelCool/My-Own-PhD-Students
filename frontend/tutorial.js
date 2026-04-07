const DEFAULT_LANGUAGE = "zh-CN";
const LANGUAGE_KEY = "rc_ui_language";

const COPY = {
  "zh-CN": {
    tutorial_subtitle: "可视化工作台教程",
    back_workspace: "返回工作台",
    tutorial_eyebrow: "使用教程",
    tutorial_nav_title: "目录",
    tutorial_title: "如何使用可视化工作台",
    tutorial_intro:
      "这个页面专门说明每个区域做什么 每个选项什么时候选 应该填什么 以及本地算力不够时怎么切到云服务器",
    copy_command: "复制命令",
    copied: "已复制",
    language_zh: "中文",
    language_en: "EN",
    sections: [
      {
        id: "open",
        title: "1 打开页面",
        paragraphs: [
          "在项目根目录启动服务后 打开浏览器访问工作台地址",
          "如果你刚改过界面或语言 记得按一次 Ctrl + F5",
        ],
        subsections: [
          {
            id: "open-start",
            title: "启动服务",
            paragraphs: ["在项目根目录执行下面这条命令即可打开工作台"],
            code:
              "cd D:\\codex\\AutoResearchClaw\n.\\.venv\\Scripts\\python.exe -m researchclaw.cli serve --config .\\config.arc.yaml --host 127.0.0.1 --port 8080",
          },
          {
            id: "open-browser",
            title: "浏览器访问",
            bullets: [
              "打开 http://127.0.0.1:8080",
              "如果页面不是最新样式 先按一次 Ctrl + F5",
            ],
          },
        ],
      },
      {
        id: "layout",
        title: "2 页面区域",
        bullets: [
          "Start Research 用来新建研究课题",
          "Details 用来看当前状态 最新运行和关键工件",
          "Canvas 用来看阶段 工件 决策和回滚关系",
          "Studio 用来看消息流 时间线 日志和控制动作",
          "Settings 用来设置研究参数 运行方式和服务配置",
        ],
      },
      {
        id: "start",
        title: "3 Start Research 怎么填",
        subsections: [
          {
            id: "start-basics",
            title: "基本信息",
            bullets: [
              "Project ID 用英文 小写 数字和中横线 例如 llm-robustness-01",
              "Project title 写给人看的名字 例如 多模态鲁棒性研究",
              "Primary request 写清研究问题 成功标准和最终交付物",
            ],
          },
          {
            id: "start-strategy",
            title: "研究策略",
            bullets: [
              "Research intensity 第一次建议选 Balanced",
              "Decision policy 想让系统自己推进选 Autonomous 想手动把关选 User gated",
              "Launch mode 不确定时优先选 Standard full run",
              "Objectives 每行一个目标",
            ],
          },
          {
            id: "start-inputs",
            title: "资料与约束",
            bullets: [
              "Baseline links 和 References 每行填一个论文 仓库或本地路径",
              "Runtime constraints 写清显存 时间预算 结果验证规则",
            ],
          },
        ],
      },
      {
        id: "settings",
        title: "4 Settings 每个子页做什么",
        subsections: [
          {
            id: "settings-ui",
            title: "界面",
            bullets: ["切换中英文", "设置默认项目名"],
          },
          {
            id: "settings-research",
            title: "研究",
            bullets: ["设置默认主题 领域 每日论文数和 baseline 摘要"],
          },
          {
            id: "settings-runtime",
            title: "运行",
            bullets: ["设置时区 并行数 重试次数 运行位置和云服务器信息"],
          },
          {
            id: "settings-quality",
            title: "质量",
            bullets: ["设置目标 venue 目标分数 评审轮次和通知"],
          },
          {
            id: "settings-server",
            title: "服务",
            bullets: ["设置 Web 服务地址 端口 仪表盘和语音入口"],
          },
          {
            id: "settings-automation",
            title: "自动化",
            bullets: ["控制 Gate 暂停 分支数 多项目和共享知识"],
          },
        ],
      },
      {
        id: "cloud",
        title: "5 云服务器怎么选",
        paragraphs: [
          "如果本地显存不够 内存不够 或正式实验太慢 建议把运行位置改成 SSH 云服务器",
        ],
        subsections: [
          {
            id: "cloud-when",
            title: "什么时候切云端",
            bullets: [
              "本地显存不够",
              "本地内存不够",
              "本地机器跑正式实验太慢",
            ],
          },
          {
            id: "cloud-fields",
            title: "云服务器字段怎么填",
            bullets: [
              "云服务器地址 填公网 IP 或域名",
              "登录用户 常见是 ubuntu 或 root",
              "SSH 端口 默认 22 改过就填实际值",
              "SSH 密钥路径 填本地私钥路径",
              "远程工作目录 推荐 /tmp/researchclaw_experiments",
              "远程 Python 常见填 python3 或 Conda Python 绝对路径",
              "远程使用 Docker 适合远端环境复杂时",
            ],
          },
        ],
      },
      {
        id: "choose",
        title: "6 常见推荐组合",
        bullets: [
          "第一次试跑 Balanced + Autonomous + Standard full run + 本地机器",
          "已有旧结果 Continue existing state",
          "只想让系统评审 Review only",
          "已经有稿子要修 Rebuttal / revision",
          "本地算力不够 SSH 云服务器 + 并行任务数 1",
        ],
      },
      {
        id: "workflow",
        title: "7 最稳的起步顺序",
        ordered: [
          "先在 Settings 里确认运行位置",
          "如果本地不够 先填好云服务器信息",
          "打开 Start Research 填基本信息",
          "在研究策略里选 Balanced 和 Standard full run",
          "补 baseline 参考资料和运行约束",
          "创建项目",
          "先看 Details 再看 Canvas 最后看 Studio",
        ],
      },
    ],
  },
  en: {
    tutorial_subtitle: "Visual workspace tutorial",
    back_workspace: "Back to Workspace",
    tutorial_eyebrow: "Usage Tutorial",
    tutorial_nav_title: "Contents",
    tutorial_title: "How to use the visual workspace",
    tutorial_intro:
      "This page explains what each area does what to choose what to fill in and how to switch to a cloud server when your local machine is not enough",
    copy_command: "Copy command",
    copied: "Copied",
    language_zh: "中文",
    language_en: "EN",
    sections: [
      {
        id: "open",
        title: "1 Open the page",
        paragraphs: [
          "Start the service from the project root and open the workspace URL in your browser",
          "If you just changed the UI or language press Ctrl + F5 once",
        ],
        subsections: [
          {
            id: "open-start",
            title: "Start the service",
            paragraphs: ["Run this command from the project root to launch the workspace"],
            code:
              "cd D:\\codex\\AutoResearchClaw\n.\\.venv\\Scripts\\python.exe -m researchclaw.cli serve --config .\\config.arc.yaml --host 127.0.0.1 --port 8080",
          },
          {
            id: "open-browser",
            title: "Open the browser",
            bullets: [
              "Visit http://127.0.0.1:8080",
              "If the UI is stale press Ctrl + F5 once",
            ],
          },
        ],
      },
      {
        id: "layout",
        title: "2 Main areas",
        bullets: [
          "Start Research creates a new topic",
          "Details shows current status latest run and key artifacts",
          "Canvas shows phases artifacts decisions and rollback paths",
          "Studio shows message flow timeline logs and run controls",
          "Settings configures research runtime and service behavior",
        ],
      },
      {
        id: "start",
        title: "3 How to fill Start Research",
        subsections: [
          {
            id: "start-basics",
            title: "Basics",
            bullets: [
              "Project ID should use lowercase English letters numbers and hyphens such as llm-robustness-01",
              "Project title is the human readable project name",
              "Primary request should state the research question success criteria and expected deliverables",
            ],
          },
          {
            id: "start-strategy",
            title: "Strategy",
            bullets: [
              "For a first run choose Balanced for Research intensity",
              "Choose Autonomous if you want the system to push forward by itself or User gated if you want manual control",
              "If you are unsure choose Standard full run for Launch mode",
              "Put one objective per line",
            ],
          },
          {
            id: "start-inputs",
            title: "Inputs",
            bullets: [
              "Put one paper repo or local path per line in Baseline links and References",
              "Use Runtime constraints for GPU memory time budget and validation rules",
            ],
          },
        ],
      },
      {
        id: "settings",
        title: "4 What each Settings page does",
        subsections: [
          { id: "settings-ui", title: "UI", bullets: ["Switch language", "Set a default project name"] },
          { id: "settings-research", title: "Research", bullets: ["Set default topic domains paper count and baseline brief"] },
          { id: "settings-runtime", title: "Runtime", bullets: ["Set timezone parallelism retries execution target and cloud fields"] },
          { id: "settings-quality", title: "Quality", bullets: ["Set target venue score review rounds and notifications"] },
          { id: "settings-server", title: "Server", bullets: ["Set host port dashboard and voice entry"] },
          { id: "settings-automation", title: "Automation", bullets: ["Control gates branching multi-project and shared knowledge"] },
        ],
      },
      {
        id: "cloud",
        title: "5 When to use a cloud server",
        paragraphs: [
          "If your local GPU memory RAM or overall speed is not enough switch the execution target to SSH cloud server",
        ],
        subsections: [
          {
            id: "cloud-when",
            title: "When to switch",
            bullets: [
              "Local GPU memory is not enough",
              "Local RAM is not enough",
              "The local machine is too slow for real experiments",
            ],
          },
          {
            id: "cloud-fields",
            title: "How to fill cloud fields",
            bullets: [
              "Cloud host is the public IP or domain",
              "Login user is often ubuntu or root",
              "SSH port is usually 22 unless changed",
              "SSH key path is the path to your local private key",
              "Remote work directory can be /tmp/researchclaw_experiments",
              "Remote Python is often python3 or a Conda Python path",
              "Use remote Docker when you want a cleaner remote environment",
            ],
          },
        ],
      },
      {
        id: "choose",
        title: "6 Recommended combinations",
        bullets: [
          "First run Balanced + Autonomous + Standard full run + Local machine",
          "Continue existing work Continue existing state",
          "Review only Review only",
          "Paper revision Rebuttal / revision",
          "Local compute not enough SSH cloud server + parallel tasks set to 1",
        ],
      },
      {
        id: "workflow",
        title: "7 Safest start sequence",
        ordered: [
          "Confirm your execution target in Settings",
          "Fill cloud server settings first if local compute is not enough",
          "Open Start Research and fill the basics",
          "Choose Balanced and Standard full run in strategy",
          "Add baselines references and runtime constraints",
          "Create the project",
          "Check Details first then Canvas then Studio",
        ],
      },
    ],
  },
};

const state = {
  language: window.localStorage.getItem(LANGUAGE_KEY) || DEFAULT_LANGUAGE,
};

let tutorialObserver = null;

function text(key) {
  return COPY[state.language]?.[key] || COPY[DEFAULT_LANGUAGE][key] || key;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function anchorId(sectionId, subsectionId = "") {
  return subsectionId ? `${sectionId}__${subsectionId}` : sectionId;
}

function applyStaticText() {
  document.documentElement.lang = state.language;
  document.title =
    state.language === "zh-CN"
      ? "My Own PhD Students 使用教程"
      : "My Own PhD Students Tutorial";

  document.querySelectorAll("[data-i18n]").forEach((node) => {
    const key = node.getAttribute("data-i18n");
    if (key) {
      node.textContent = text(key);
    }
  });

  document.getElementById("tutorial-lang-zh")?.classList.toggle(
    "active",
    state.language === "zh-CN"
  );
  document.getElementById("tutorial-lang-en")?.classList.toggle(
    "active",
    state.language === "en"
  );
}

function renderNav(sections) {
  const nav = document.getElementById("tutorial-nav-links");
  nav.innerHTML = sections
    .map((section) => {
      const children = (section.subsections || [])
        .map(
          (item) => `
            <a class="tutorial-nav-child" data-anchor-link="${escapeHtml(
              anchorId(section.id, item.id)
            )}" data-parent-section="${escapeHtml(section.id)}" href="#${escapeHtml(
              anchorId(section.id, item.id)
            )}">
              ${escapeHtml(item.title)}
            </a>
          `
        )
        .join("");

      return `
        <div class="tutorial-nav-group" data-section-group="${escapeHtml(section.id)}">
          <a class="tutorial-nav-link" data-anchor-link="${escapeHtml(section.id)}" href="#${escapeHtml(section.id)}">
            ${escapeHtml(section.title)}
          </a>
          ${children ? `<div class="tutorial-nav-children">${children}</div>` : ""}
        </div>
      `;
    })
    .join("");
}

function renderCodeBlock(code) {
  if (!code) {
    return "";
  }
  return `
    <div class="tutorial-code-wrap">
      <button class="tutorial-copy-button" type="button" data-copy-code="${escapeHtml(code)}">${escapeHtml(
        text("copy_command")
      )}</button>
      <pre class="tutorial-code">${escapeHtml(code)}</pre>
    </div>
  `;
}

function renderBullets(items, ordered = false) {
  if (!items?.length) {
    return "";
  }
  const tag = ordered ? "ol" : "ul";
  const className = ordered ? "tutorial-steps" : "tutorial-list";
  return `<${tag} class="${className}">${items
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("")}</${tag}>`;
}

function renderSubsection(sectionId, subsection) {
  const id = anchorId(sectionId, subsection.id);
  const paragraphs = (subsection.paragraphs || [])
    .map((item) => `<p>${escapeHtml(item)}</p>`)
    .join("");
  return `
    <section class="tutorial-subsection" id="${escapeHtml(id)}" data-anchor-id="${escapeHtml(id)}" data-parent-section="${escapeHtml(sectionId)}">
      <h3>${escapeHtml(subsection.title)}</h3>
      ${paragraphs}
      ${renderBullets(subsection.bullets)}
      ${renderBullets(subsection.ordered, true)}
      ${renderCodeBlock(subsection.code)}
      ${subsection.note ? `<div class="tutorial-note">${escapeHtml(subsection.note)}</div>` : ""}
    </section>
  `;
}

function renderSection(section) {
  const paragraphs = (section.paragraphs || [])
    .map((item) => `<p>${escapeHtml(item)}</p>`)
    .join("");
  return `
    <section class="tutorial-section" id="${escapeHtml(section.id)}" data-anchor-id="${escapeHtml(section.id)}" data-parent-section="${escapeHtml(section.id)}">
      <h2>${escapeHtml(section.title)}</h2>
      ${paragraphs}
      ${renderBullets(section.bullets)}
      ${renderBullets(section.ordered, true)}
      ${renderCodeBlock(section.code)}
      ${section.note ? `<div class="tutorial-note">${escapeHtml(section.note)}</div>` : ""}
      ${(section.subsections || []).map((item) => renderSubsection(section.id, item)).join("")}
    </section>
  `;
}

function syncActiveNav(activeAnchorId) {
  const links = document.querySelectorAll("[data-anchor-link]");
  const groups = document.querySelectorAll("[data-section-group]");
  let activeSectionId = activeAnchorId;

  if (activeAnchorId.includes("__")) {
    activeSectionId = activeAnchorId.split("__")[0];
  }

  links.forEach((link) => {
    if (!(link instanceof HTMLElement)) {
      return;
    }
    link.classList.toggle("active", link.dataset.anchorLink === activeAnchorId);
  });

  groups.forEach((group) => {
    if (!(group instanceof HTMLElement)) {
      return;
    }
    group.classList.toggle("expanded", group.dataset.sectionGroup === activeSectionId);
  });

  const sectionLink = document.querySelector(
    `.tutorial-nav-link[data-anchor-link="${activeSectionId}"]`
  );
  if (sectionLink instanceof HTMLElement) {
    sectionLink.classList.add("active");
  }
}

function activateTutorialObserver() {
  if (tutorialObserver) {
    tutorialObserver.disconnect();
  }

  const anchors = document.querySelectorAll("[data-anchor-id]");
  if (!anchors.length) {
    return;
  }

  tutorialObserver = new IntersectionObserver(
    (entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
      if (visible.length) {
        syncActiveNav(visible[0].target.id);
      }
    },
    {
      rootMargin: "-12% 0px -66% 0px",
      threshold: [0.2, 0.45, 0.7],
    }
  );

  anchors.forEach((anchor) => tutorialObserver.observe(anchor));
  syncActiveNav(anchors[0].id);
}

function render() {
  applyStaticText();
  const sections = COPY[state.language].sections;
  renderNav(sections);
  document.getElementById("tutorial-content").innerHTML = sections
    .map((section) => renderSection(section))
    .join("");
  activateTutorialObserver();
}

async function copyCommand(button) {
  const code = button.getAttribute("data-copy-code") || "";
  try {
    await navigator.clipboard.writeText(code);
    const original = text("copy_command");
    button.textContent = text("copied");
    window.setTimeout(() => {
      button.textContent = original;
    }, 1400);
  } catch {
    button.textContent = text("copy_command");
  }
}

document.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }

  const copyButton = target.closest("[data-copy-code]");
  if (copyButton instanceof HTMLButtonElement) {
    copyCommand(copyButton);
    return;
  }

  if (target.id === "tutorial-lang-zh") {
    state.language = "zh-CN";
    window.localStorage.setItem(LANGUAGE_KEY, state.language);
    render();
    return;
  }

  if (target.id === "tutorial-lang-en") {
    state.language = "en";
    window.localStorage.setItem(LANGUAGE_KEY, state.language);
    render();
  }
});

window.addEventListener("storage", (event) => {
  if (event.key === LANGUAGE_KEY && event.newValue) {
    state.language = event.newValue;
    render();
  }
});

render();
