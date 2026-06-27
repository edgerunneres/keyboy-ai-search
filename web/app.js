const DEFAULT_QUERY = "Agentic RAG GraphRAG LightRAG Self-RAG 最新研究怎么整合到课程项目";
const DEFAULT_SOURCE_EMAIL = "yup300737@gmail.com";

const state = {
  llm: null,
  sources: null,
  hasResult: false,
  typeTimer: null,
  autoFollowAnswer: true,
  currentChat: null,
  currentTaskId: null,
  activeTaskId: null,
  currentConversationId: null,
  currentConversationTitle: "",
  runningTaskIds: new Set(),
  taskRuns: new Map(),
  chatByTaskId: new Map(),
  conversations: [],
  tasks: [],
  showArchived: false,
  restoringHistory: false,
};

let historyMotionTimer = null;

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const nodes = {
  form: $("#searchForm"),
  query: $("#queryInput"),
  submit: $("#submitBtn"),
  online: $("#onlineToggle"),
  docCount: $("#docCount"),
  localDocInput: $("#localDocInput"),
  modelState: $("#modelState"),
  results: $("#results"),
  dockContainer: $("#dockContainer"),
  chatHistory: $("#chatHistory"),
  chatItemTemplate: $("#chatItemTemplate"),
  drawerOverlay: $("#drawerOverlay"),
  drawerTitle: $("#drawerTitle"),
  drawerClose: $("#drawerClose"),
  modelView: $("#drawerModel"),
  sourcesView: $("#drawerSources"),
  evidenceView: $("#drawerEvidence"),
  traceView: $("#drawerTrace"),
  qualityView: $("#drawerQuality"),
  profile: $("#profileList"),
  qualityBrief: $("#qualityBrief"),
  quality: $("#qualityList"),
  traces: $("#traceList"),
  risks: $("#riskList"),
  riskBadge: $("#riskBadge"),
  provider: $("#providerSelect"),
  apiKey: $("#apiKeyInput"),
  baseUrl: $("#baseUrlInput"),
  model: $("#modelInput"),
  timeout: $("#timeoutInput"),
  thinking: $("#thinkingToggle"),
  saveModel: $("#saveModelBtn"),
  modelMessage: $("#modelMessage"),
  semanticScholarKey: $("#semanticScholarKeyInput"),
  openAlexKey: $("#openAlexKeyInput"),
  openAlexMailto: $("#openAlexMailtoInput"),
  crossrefMailto: $("#crossrefMailtoInput"),
  sourceTimeout: $("#sourceTimeoutInput"),
  perSourceLimit: $("#perSourceLimitInput"),
  saveSources: $("#saveSourcesBtn"),
  sourcesMessage: $("#sourcesMessage"),
  historyPanel: $("#historyPanel"),
  historyToggle: $("#historyToggle"),
  historyCollapse: $("#historyCollapse"),
  taskList: $("#taskList"),
  activeProjectName: $("#activeProjectName"),
  newConversation: $("#newConversationBtn"),
  archiveToggle: $("#archiveToggleBtn"),
  historyModeLabel: $("#historyModeLabel"),
  refreshHistory: $("#refreshHistoryBtn"),
};

nodes.query.placeholder = DEFAULT_QUERY;

function setBusy(value) {
  refreshRunningUi();
  $$(".top-actions .ghost-btn[data-drawer]").forEach(btn => btn.disabled = false);
  if (value) {
    document.body.classList.add("has-result");
    nodes.dockContainer.classList.add("docked");
  }
}

function getCurrentConversationRunningIds() {
  const ids = [];
  for (const [id, run] of state.taskRuns) {
    if (run.conversationId === state.currentConversationId) {
      ids.push(id);
    }
  }
  return ids;
}

function refreshRunningUi() {
  const currentRunning = getCurrentConversationRunningIds();
  const isCurrentRunning = currentRunning.length > 0;
  if (isCurrentRunning) {
    nodes.submit.textContent = "停止";
    nodes.submit.classList.add("stop-btn-active");
  } else {
    nodes.submit.textContent = "研究";
    nodes.submit.classList.remove("stop-btn-active");
  }
  nodes.submit.disabled = false;
  nodes.online.disabled = false;
  nodes.form.classList.toggle("loading", isCurrentRunning);
}

function setResultControlsVisible(value, chat = state.currentChat) {
  state.hasResult = value;
  if (chat) {
    chat.resultActions.classList.toggle("hidden", !value);
  }
}

function dl(container, pairs) {
  container.innerHTML = "";
  pairs.forEach(([key, value]) => {
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = key;
    renderDlValue(dd, value);
    container.append(dt, dd);
  });
}

function renderDlValue(container, value) {
  if (Array.isArray(value)) {
    const items = normalizeDlItems(value);
    if (!items.length) {
      container.textContent = "-";
      return;
    }
    const list = document.createElement("ol");
    list.className = "compact-dl-list";
    items.forEach((item) => {
      const li = document.createElement("li");
      li.textContent = item;
      list.appendChild(li);
    });
    container.appendChild(list);
    return;
  }
  container.textContent = value ?? "-";
}

function normalizeDlItems(items) {
  const seen = new Set();
  return (items || [])
    .map(item => String(item ?? "").replace(/\s+/g, " ").trim())
    .filter(Boolean)
    .filter(item => {
      const key = item.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, 6);
}

function setHistoryPanelOpen(open) {
  const panel = nodes.historyPanel;
  const stage = $(".stage");
  const openPadding = window.matchMedia("(max-width: 860px)").matches ? "14px" : "338px";
  const nextFrame = (callback) => {
    let applied = false;
    const run = () => {
      if (applied) return;
      applied = true;
      callback();
    };
    requestAnimationFrame(run);
    setTimeout(run, 24);
  };
  clearTimeout(historyMotionTimer);
  panel.style.transition = "transform 0.36s cubic-bezier(0.22, 1, 0.36, 1), opacity 0.28s ease";
  stage.style.transition = "padding-left 0.36s cubic-bezier(0.22, 1, 0.36, 1), max-width 0.36s cubic-bezier(0.22, 1, 0.36, 1)";

  if (open) {
    panel.classList.remove("collapsed");
    panel.classList.add("is-open");
    panel.style.pointerEvents = "auto";
    panel.style.transform = "translateX(calc(-100% - 28px)) scale(0.98)";
    panel.style.opacity = "0";
    stage.style.paddingLeft = "22px";
    stage.style.maxWidth = "1380px";
    panel.offsetHeight;
    nextFrame(() => {
      panel.style.transform = "translateX(0) scale(1)";
      panel.style.opacity = "1";
      stage.style.paddingLeft = openPadding;
      stage.style.maxWidth = "1680px";
    });
    return;
  }

  panel.classList.remove("is-open");
  panel.classList.add("collapsed");
  panel.style.pointerEvents = "none";
  panel.style.transform = "translateX(0) scale(1)";
  panel.style.opacity = "1";
  stage.style.paddingLeft = openPadding;
  stage.style.maxWidth = "1680px";
  panel.offsetHeight;
  nextFrame(() => {
    panel.style.transform = "translateX(calc(-100% - 28px)) scale(0.98)";
    panel.style.opacity = "0";
    stage.style.paddingLeft = "22px";
    stage.style.maxWidth = "1380px";
  });
}

function renderList(container, items) {
  container.innerHTML = "";
  (items || []).forEach((item) => {
    const li = document.createElement("li");
    li.textContent = item;
    container.appendChild(li);
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatInline(value) {
  let html = escapeHtml(value).trim();
  html = html
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(/\[(\d+)\]/g, '<span class="cite-ref">[$1]</span>')
    .replace(/（来源[:：]([^）]+)）/g, '<span class="source-chip">来源：$1</span>');
  return html.replace(/\*\*/g, "").replace(/(^|\s)#{1,6}\s*/g, "$1");
}

function renderEvidenceSummary(value) {
  const items = String(value || "")
    .split(/、(?=\[\d+\])|；(?=\[\d+\])|;(?=\[\d+\])/)
    .map((item) => item.trim())
    .filter(Boolean);
  if (!items.length) return "";
  return `<ol class="answer-source-list">${items.map((item) => `<li>${formatInline(item)}</li>`).join("")}</ol>`;
}

function renderFormattedAnswer(text, chat = state.currentChat) {
  const source = String(text || "").replace(/\r\n/g, "\n").trim();
  if (!source) {
    if (chat) chat.summary.innerHTML = "";
    return;
  }

  const lines = source.split("\n");
  let html = '<article class="answer-doc">';
  let paragraph = [];
  let listItems = [];
  let paragraphCount = 0;

  const flushParagraph = () => {
    if (!paragraph.length) return;
    const content = formatInline(paragraph.join(" "));
    const className = paragraphCount === 0 ? "answer-lead" : "answer-body";
    html += `<p class="${className}">${content}</p>`;
    paragraph = [];
    paragraphCount += 1;
  };

  const flushList = () => {
    if (!listItems.length) return;
    html += `<ul class="answer-list">${listItems.map((item) => `<li>${item}</li>`).join("")}</ul>`;
    listItems = [];
  };

  lines.forEach((line) => {
    const raw = line.trim();
    if (!raw) {
      flushList();
      flushParagraph();
      return;
    }

    const sourceMatch = raw.match(/^证据(?:来源|引用)?[:：]\s*(.*)$/);
    if (sourceMatch) {
      flushList();
      flushParagraph();
      html += '<h2 class="answer-heading">证据引用</h2>';
      html += renderEvidenceSummary(sourceMatch[1]);
      return;
    }

    const headingMatch = raw.match(/^(#{1,4})\s+(.+)$/);
    if (headingMatch) {
      flushList();
      flushParagraph();
      const depth = headingMatch[1].length;
      const tag = depth <= 2 ? "h2" : "h3";
      const className = depth <= 2 ? "answer-heading" : "answer-section";
      const title = headingMatch[2].replace(/^\d+[.、]\s*/, "");
      html += `<${tag} class="${className}">${formatInline(title)}</${tag}>`;
      return;
    }

    const bulletMatch = raw.match(/^[-*•]\s+(.+)$/) || raw.match(/^\d+[.)、]\s+(.+)$/);
    if (bulletMatch) {
      flushParagraph();
      listItems.push(formatInline(bulletMatch[1]));
      return;
    }

    paragraph.push(raw);
  });

  flushList();
  flushParagraph();
  html += "</article>";
  if (chat) chat.summary.innerHTML = html;
}

function scrollWithAnswer(chat, force = false, anchorNode = null) {
  if (!chat || state.currentChat !== chat) return;
  if (!force && !state.autoFollowAnswer) return;
  if (anchorNode) {
    const el = anchorNode.nodeType === Node.TEXT_NODE ? anchorNode.parentElement : anchorNode;
    if (el) {
      const containerRect = nodes.chatHistory.getBoundingClientRect();
      const elRect = el.getBoundingClientRect();
      if (elRect.bottom > containerRect.bottom - 120) {
        nodes.chatHistory.scrollTop += elRect.bottom - containerRect.bottom + 160;
      }
    }
  } else {
    nodes.chatHistory.scrollTop = nodes.chatHistory.scrollHeight;
  }
}

function typeAnswer(text, chat = state.currentChat) {
  return new Promise((resolve) => {
    if (!chat) return resolve();
    window.clearInterval(state.typeTimer);
    state.typeTimer = null;
    state.autoFollowAnswer = true;

    nodes.chatHistory.style.scrollBehavior = 'auto';

    const cancelAutoScroll = () => { state.autoFollowAnswer = false; };
    nodes.chatHistory.addEventListener('wheel', cancelAutoScroll, { once: true });
    nodes.chatHistory.addEventListener('touchstart', cancelAutoScroll, { once: true });

    const fullText = text || "没有生成答案。";

  renderFormattedAnswer(fullText, chat);

  const el = chat.summary;
  const textNodes = [];
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (node.textContent.trim()) {
      textNodes.push({ node, full: node.textContent });
      node.textContent = '';
    }
  }

  let nIdx = 0, cIdx = 0;

  const tick = () => {
    if (nIdx >= textNodes.length) {
      nodes.chatHistory.style.scrollBehavior = '';
      nodes.chatHistory.removeEventListener('wheel', cancelAutoScroll);
      nodes.chatHistory.removeEventListener('touchstart', cancelAutoScroll);
      resolve();
      return;
    }

    const item = textNodes[nIdx];
    const speed = item.full.length > 50 ? 3 : 1;
    cIdx += speed;

    if (cIdx >= item.full.length) {
      item.node.textContent = item.full;
      cIdx = 0;
      nIdx++;
    } else {
      item.node.textContent = item.full.substring(0, cIdx);
    }

    scrollWithAnswer(chat, false, item.node);

    requestAnimationFrame(tick);
  };
  scrollWithAnswer(chat, true, chat.summary);
  requestAnimationFrame(tick);
  });
}

function renderCitations(citations) {
  nodes.results.innerHTML = "";
  if (!citations.length) {
    nodes.results.innerHTML = `<div class="empty">没有获得证据来源</div>`;
    return;
  }

  citations.forEach((item) => {
    const article = document.createElement("article");
    article.className = "evidence-item";

    const titleRow = document.createElement("div");
    titleRow.className = "evidence-title";
    const title = document.createElement("h3");
    title.textContent = item.title || "未命名资料";
    const score = document.createElement("span");
    score.className = "score";
    score.textContent = Number(item.score || 0).toFixed(1);
    titleRow.append(title, score);

    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = `${item.source || "未知来源"} · ${item.published_at || "未知日期"}`;

    const snippet = document.createElement("p");
    snippet.className = "snippet";
    snippet.textContent = item.original_excerpt || item.evidence || "暂无摘要。";

    const support = document.createElement("div");
    support.className = "evidence-support";
    support.innerHTML = `
      <span>支持程度：${escapeHtml(item.support_level || "中")}</span>
      <span>${escapeHtml(item.read_status || "仅摘要")}</span>
    `;

    const claim = document.createElement("p");
    claim.className = "evidence-claim";
    claim.textContent = item.supporting_claim || "支撑答案中的相关判断。";

    const risks = document.createElement("div");
    risks.className = "evidence-risks";
    (item.risk_flags || []).forEach((risk) => {
      const badge = document.createElement("span");
      badge.textContent = risk;
      risks.appendChild(badge);
    });

    const isWebUrl = /^https?:\/\//i.test(item.url || "");
    const source = document.createElement(isWebUrl ? "a" : "span");
    source.className = isWebUrl ? "citation-link" : "source-text";
    source.textContent = isWebUrl ? "打开来源" : item.url || "本地资料";
    if (isWebUrl) {
      source.href = item.url;
      source.target = "_blank";
      source.rel = "noreferrer";
    }

    article.append(titleRow, meta, support, claim, snippet);
    if ((item.risk_flags || []).length) article.appendChild(risks);
    article.appendChild(source);
    nodes.results.appendChild(article);
  });
}

function resetConversationView(message = "输入问题后开始研究。") {
  window.clearInterval(state.typeTimer);
  state.typeTimer = null;
  state.currentChat = null;
  state.hasResult = false;
  state.hasResultBefore = false;
  state.currentTaskId = null;
  state.activeTaskId = null;
  state.currentConversationId = null;
  state.currentConversationTitle = "";
  state.chatByTaskId.clear();
  nodes.chatHistory.innerHTML = `
    <div id="initialHero" class="initial-hero">
      <div class="answer-text">${escapeHtml(message)}</div>
    </div>
  `;
  document.body.classList.remove("has-result");
  nodes.dockContainer.classList.remove("docked");
  setResultControlsVisible(false);
  refreshRunningUi();
}

function renderTrace(traces) {
  nodes.traces.innerHTML = "";
  (traces || []).forEach((trace) => {
    const item = document.createElement("div");
    item.className = "trace-item";
    const title = document.createElement("strong");
    title.textContent = `${trace.name} · ${trace.status}`;
    const detail = document.createElement("span");
    detail.textContent = `${trace.message} · ${Number(trace.duration_ms || 0).toFixed(2)} ms`;
    item.append(title, detail);
    nodes.traces.appendChild(item);
  });
}

function renderRisks(risks) {
  nodes.riskBadge.textContent = `${(risks || []).length} 条风险`;
  nodes.risks.innerHTML = "";
  if (!risks || !risks.length) {
    nodes.risks.innerHTML = `<div class="empty">暂无风险提示</div>`;
    return;
  }
  risks.forEach((risk) => {
    const item = document.createElement("div");
    item.className = "risk-item";
    item.textContent = risk;
    nodes.risks.appendChild(item);
  });
}

function renderFollowups(query, questions, originTaskId, chat = state.currentChat) {
  if (!chat) return;
  chat.followupList.innerHTML = "";
  const fallbackQuestions = [
    `深入了解 "${query}" 的最新技术进展和论文`,
    `"${query}" 在实际工业落地中的主要痛点是什么？`,
    `是否有与 "${query}" 相关的代表性开源方案？`
  ];
  (questions && questions.length ? questions : fallbackQuestions).forEach(q => {
    const btn = document.createElement("button");
    btn.className = "followup-btn";
    btn.textContent = q;
    btn.onclick = () => {
      nodes.query.value = q;
      runResearch({ originTaskId, conversationId: chat.task?.conversation_id || state.currentConversationId });
    };
    chat.followupList.appendChild(btn);
  });
}

function populateDrawers(payload) {
  if (!payload) return;
  renderCitations(payload.citations || []);
  renderTrace(payload.traces);
  renderRisks(payload.risks);
  const plan = payload.plan || {};
  dl(nodes.profile, [
    ["意图", plan.intent],
    ["规划", plan.llm_used ? "远程大模型" : "本地规划"],
    ["检索拆解", plan.subqueries || []],
    ["证据", plan.required_evidence || []],
  ]);
  const metrics = payload.metrics || {};
  const failedAgents = (metrics.failed_agents || []).map(item => `${item.name}: ${item.message}`).join("；");
  const brief = payload.decision_brief || {};
  const trust = payload.trust_score || {};
  const trustValue = trust.overall ?? trust.score ?? trust.total ?? "-";
  nodes.qualityBrief.innerHTML = `<h3>可信决策简报</h3><dl class="brief-dl"></dl>`;
  dl(nodes.qualityBrief.querySelector("dl"), [
    ["适用判断", brief.verdict || "暂无"],
    ["证据依据", brief.evidence_basis || "暂无"],
    ["可信度", trust.level ? `${trust.level}（${trustValue}）` : String(trustValue)],
    ["使用建议", brief.recommended_path || "暂无"],
    ["关键取舍", brief.tradeoffs || "暂无"],
  ]);
  dl(nodes.quality, [
    ["模型", metrics.llm_used ? metrics.llm_model : "本地兜底模式"],
    ["在线文档", metrics.online_documents],
    ["正文读取", `${metrics.source_read_success ?? 0}/${metrics.source_read_attempted ?? 0}`],
    ["来源多样性", metrics.source_diversity ?? "-"],
    ["引用支持率", metrics.citation_support_rate != null ? `${Math.round(metrics.citation_support_rate * 100)}%` : "-"],
    ["索引文档", metrics.indexed_documents],
    ["结果", metrics.result_count],
    ["失败智能体", failedAgents || "无"],
  ]);
}

async function renderResearch(payload, options = {}) {
  const chat = options.chat || state.currentChat;
  if (!chat) return;
  chat.payload = payload;
  chat.task = options.task || chat.task || null;
  if (chat.task?.id) chat.container.dataset.taskId = chat.task.id;
  chat.container._payload = payload;
  chat.resultCount.textContent = String((payload.citations || []).length);
  const metrics = payload.metrics || {};
  chat.latencyBadge.textContent = `${metrics.latency_ms ?? "-"} ms`;
  setResultControlsVisible(true, chat);
  if (options.animate === false) {
    renderFormattedAnswer(payload.answer || "没有生成答案。", chat);
  } else {
    await typeAnswer(payload.answer || "没有生成答案。", chat);
  }
  renderList(chat.insights, payload.findings);

  chat.feedbackBar.classList.remove("hidden");
  chat.followupContainer.classList.remove("hidden");
  chat.upvoteBtn.classList.remove("active");
  chat.downvoteBtn.classList.remove("active");
  renderFollowups(chat.container.querySelector('.user-query').textContent, payload.next_questions, chat.task?.id, chat);
}

function createChatItem(query, options = {}) {
  const append = options.append !== false;
  if (!append) {
    nodes.chatHistory.innerHTML = "";
  } else {
    const initialHero = document.querySelector("#initialHero");
    if (initialHero) initialHero.remove();
  }
  const clone = nodes.chatItemTemplate.content.cloneNode(true);
  const container = clone.querySelector('.chat-item');
  clone.querySelector('.user-query').textContent = query;
  nodes.chatHistory.appendChild(clone);

  const drawerBtns = container.querySelectorAll("[data-drawer]");
  drawerBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const payload = container._payload || (state.currentChat && state.currentChat.container === container ? state.currentChat.payload : null);
      if (payload) populateDrawers(payload);
      showDrawer(btn.dataset.drawer);
    });
  });

  const progressToggle = container.querySelector('.progress-toggle');
  const progressSteps = container.querySelector('.progress-steps');
  progressToggle.addEventListener("click", () => {
    const isHidden = progressSteps.classList.toggle("hidden");
    progressToggle.textContent = isHidden ? "展开" : "收起";
    container.querySelector(".thinking").classList.toggle("expanded", !isHidden);
  });

  setTimeout(() => {
    nodes.chatHistory.scrollTo({
      top: nodes.chatHistory.scrollHeight,
      behavior: 'smooth'
    });
  }, 50);

  const chatObj = {
    container,
    payload: null,
    thinking: container.querySelector('.thinking'),
    statusText: container.querySelector('.status-text'),
    progressSteps: container.querySelector('.progress-steps'),
    progressToggle,
    summary: container.querySelector('.answer-text'),
    insights: container.querySelector('.insight-list'),
    feedbackBar: container.querySelector('.feedback-toolbar'),
    copyBtn: container.querySelector('.copy-btn'),
    copyText: container.querySelector('.copy-text'),
    upvoteBtn: container.querySelector('.upvote-btn'),
    downvoteBtn: container.querySelector('.downvote-btn'),
    followupContainer: container.querySelector('.followup-container'),
    followupList: container.querySelector('.followup-list'),
    resultActions: container.querySelector('.result-actions'),
    resultCount: container.querySelector('.result-count'),
    latencyBadge: container.querySelector('.latency')
  };
  chatObj.copyBtn.addEventListener("click", () => {
    navigator.clipboard.writeText(chatObj.summary.innerText);
    chatObj.copyText.textContent = "已复制";
    chatObj.copyBtn.style.color = "#0071e3";
    setTimeout(() => {
      chatObj.copyText.textContent = "复制";
      chatObj.copyBtn.style.color = "#1d1d1f";
    }, 2000);
  });
  chatObj.upvoteBtn.addEventListener("click", () => {
    chatObj.upvoteBtn.classList.toggle("active");
    chatObj.downvoteBtn.classList.remove("active");
  });
  chatObj.downvoteBtn.addEventListener("click", () => {
    chatObj.downvoteBtn.classList.toggle("active");
    chatObj.upvoteBtn.classList.remove("active");
  });
  container._payloadLink = chatObj;
  return chatObj;
}

function isChatVisible(chat) {
  return Boolean(chat?.container && document.body.contains(chat.container));
}

function createTaskRun({ controller, chat, task = null, conversationId = null }) {
  return {
    controller,
    chat,
    task,
    conversationId,
    startedAt: Date.now(),
    progress: {
      statusText: "初始化研究流程...",
      steps: [],
      streamText: "",
    },
  };
}

function ensureRunProgress(run) {
  if (!run.progress) {
    run.progress = { statusText: "研究进行中", steps: [], streamText: "" };
  }
  if (!Array.isArray(run.progress.steps)) run.progress.steps = [];
  return run.progress;
}

function renderProgressStep(chat, step, animate = false) {
  if (!chat) return;
  const message = typeof step === "string" ? step : step?.message;
  if (!message) return;
  const li = document.createElement("li");
  if (animate) li.style.animation = "answerBlockIn 0.3s cubic-bezier(0.2, 0.8, 0.2, 1) forwards";
  li.innerHTML = `<span class="step-mark">✓</span><span>${escapeHtml(message)}</span>`;
  chat.progressSteps.appendChild(li);
}

function applyRunProgress(chat, run, task = null) {
  if (!chat || !run) return;
  const progress = ensureRunProgress(run);
  const fallbackStatus = task?.status === "queued" ? "排队中" : "研究进行中";
  chat.statusText.textContent = progress.statusText || fallbackStatus;
  chat.progressSteps.innerHTML = "";
  progress.steps.forEach((step) => renderProgressStep(chat, step));
  chat.thinking.classList.remove("hidden");
}

function bindRunChat(run, chat, task = null) {
  if (!run || !chat) return;
  run.chat = chat;
  if (task) run.task = task;
  chat.task = run.task || task || chat.task;
  applyRunProgress(chat, run, run.task || task);
}

function updateRunStatus(runId, statusText, options = {}) {
  const run = state.taskRuns.get(runId);
  if (!run) return null;
  const progress = ensureRunProgress(run);
  progress.statusText = statusText;
  if (options.stepMessage) {
    const lastStep = progress.steps[progress.steps.length - 1];
    if (!lastStep || lastStep.message !== options.stepMessage) {
      progress.steps.push({ message: options.stepMessage, at: Date.now() });
    }
  }
  if (isChatVisible(run.chat)) {
    run.chat.statusText.textContent = progress.statusText;
    if (options.stepMessage) {
      renderProgressStep(run.chat, { message: options.stepMessage }, true);
    }
  }
  return run;
}

function fallbackRunningStatus(task) {
  if (task.status === "queued") return "排队中";
  const traces = task.result?.traces || [];
  const latestTrace = traces[traces.length - 1];
  return latestTrace?.message ? `${latestTrace.message}（已保存进度）` : "研究进行中";
}

function setCurrentConversation(conversation) {
  state.currentConversationId = conversation?.id || null;
  state.currentConversationTitle = conversation?.title || "";
  nodes.activeProjectName.textContent = conversation?.title
    ? `当前：${conversation.title}`
    : "新对话，发送后保存";
}

async function runResearch(options = {}) {
  const query = nodes.query.value.trim() || DEFAULT_QUERY;
  const conversationId = options.conversationId || state.currentConversationId || null;

  if (!state.hasResult) {
    nodes.query.disabled = true;
    nodes.submit.disabled = true;
    const heroText = document.querySelector('.initial-hero .answer-text');
    if (heroText) {
      let text = heroText.textContent;
      await new Promise(resolve => {
        const deleteTimer = setInterval(() => {
          if (text.length > 0) {
            text = text.slice(0, -1);
            heroText.textContent = text;
          } else {
            clearInterval(deleteTimer);
            nodes.query.disabled = false;
            nodes.submit.disabled = false;
            resolve();
          }
        }, 30);
      });
    }
  }

  const controller = new AbortController();
  let taskId = null;

  const dock = nodes.dockContainer;
  const first = dock.getBoundingClientRect();

  const chat = createChatItem(query, { append: true });
  let finalChat = chat;
  state.currentChat = chat;

  const tempId = "pending_" + Date.now();
  chat.container.dataset.taskId = tempId;
  state.taskRuns.set(tempId, createTaskRun({ controller, chat, task: null, conversationId }));
  if (!state.currentConversationId) {
    nodes.activeProjectName.textContent = "新对话，发送后保存";
  }
  chat.thinking.classList.remove("hidden");
  nodes.query.value = "";

  setBusy(true);

  if (!state.hasResultBefore) {
    state.hasResultBefore = true;
    const last = dock.getBoundingClientRect();
    const invertX = first.left - last.left;
    const invertY = first.top - last.top;

    dock.style.transform = `translate(${invertX}px, ${invertY}px)`;
    dock.style.transition = "none";

    requestAnimationFrame(() => {
      dock.style.transform = "";
      dock.style.transition = "transform 0.6s cubic-bezier(0.2, 0.8, 0.2, 1)";
    });
  }

  const startTime = Date.now();
  let textBuffer = "";
  let payload = null;
  let task = null;
  let cancelledByUser = false;
  let streamError = null;

  try {
    const response = await fetch("/api/tasks?stream=true", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      body: JSON.stringify({
        query,
        project_id: "default",
        conversation_id: conversationId,
        online: nodes.online.checked,
        include_local: true,
        limit: 8,
        origin_task_id: options.originTaskId || null,
      }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let done = false;

    while (!done) {
      const { value, done: readerDone } = await reader.read();
      done = readerDone;
      if (value) {
        const chunkStr = decoder.decode(value, { stream: true });
        const lines = chunkStr.split("\n");
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const event = JSON.parse(line.substring(6));

              if (event.type === "task") {
                task = event.task;
                taskId = task?.id || null;
	                state.currentTaskId = taskId;
	                state.activeTaskId = taskId;
	                chat.task = task;
	                chat.container.dataset.taskId = taskId || "";
	                if (task?.conversation_id && !state.currentConversationId) {
	                  state.currentConversationId = task.conversation_id;
	                  state.currentConversationTitle = query.length > 28 ? `${query.slice(0, 28)}...` : query;
	                  nodes.activeProjectName.textContent = `当前：${state.currentConversationTitle}`;
	                }
	                if (taskId) {
	                  state.runningTaskIds.add(taskId);
	                  state.chatByTaskId.set(taskId, chat);

                      const run = state.taskRuns.get(tempId);
                      if (run) {
                        state.taskRuns.delete(tempId);
                        run.task = task;
                        run.conversationId = task?.conversation_id || conversationId;
                        bindRunChat(run, chat, task);
                        state.taskRuns.set(taskId, run);
                      } else {
	                    state.taskRuns.set(taskId, createTaskRun({ controller, chat, task, conversationId: task?.conversation_id || conversationId }));
                      }

	                  refreshRunningUi();
	                }
	                loadTasks();
	              } else if (event.type === "status") {
	                const elapsed = Math.floor((Date.now() - startTime) / 1000);
	                updateRunStatus(taskId || tempId, `${event.message} · ${elapsed}s`, { stepMessage: event.message });
	              } else if (event.type === "chunk") {
                textBuffer += event.chunk;
                const lastLine = textBuffer.split("\n").filter(l => l.trim().length > 0).pop() || "";
                const displayLine = lastLine.replace(/[#*`>{}\[\]]/g, "").trim();
	                const shortDisplay = displayLine.length > 50 ? displayLine.substring(displayLine.length - 50) : displayLine;
	                if (shortDisplay) {
	                  const run = updateRunStatus(taskId || tempId, `正在组织答案：${shortDisplay}`);
	                  if (run) ensureRunProgress(run).streamText = textBuffer;
	                }
              } else if (event.type === "complete") {
                payload = event.result;
                task = event.task || task;
                if (task?.id) {
                  finalChat = state.taskRuns.get(task.id)?.chat || chat;
                  state.runningTaskIds.delete(task.id);
                  state.taskRuns.delete(task.id);
                  refreshRunningUi();
                }
              } else if (event.type === "cancelled") {
                cancelledByUser = true;
                task = event.task || task;
                if (task?.id) {
                  finalChat = state.taskRuns.get(task.id)?.chat || chat;
                  state.runningTaskIds.delete(task.id);
                  state.taskRuns.delete(task.id);
                  refreshRunningUi();
                }
	                const targetChat = task?.id ? (state.taskRuns.get(task.id)?.chat || finalChat) : finalChat;
	                if (isChatVisible(targetChat)) {
	                  renderFormattedAnswer(event.message || "研究已终止。", targetChat);
	                  targetChat.thinking.classList.add("hidden");
	                }
              } else if (event.type === "error") {
                task = event.task || task;
                streamError = new Error(event.message);
                done = true;
                try { await reader.cancel(); } catch {}
              }
            } catch (e) {
              // ignore parse errors for partial chunks
            }
          }
        }
      }
    }

    if (streamError) throw streamError;
	    if (payload) {
	      const targetChat = finalChat;
	      targetChat.container._payload = payload;
	      if (isChatVisible(targetChat)) {
	        renderResearch(payload, { task, chat: targetChat });
	      }
	    }
  } catch (error) {
	    if (error.name === 'AbortError') {
	      const targetChat = finalChat;
	      if (isChatVisible(targetChat)) {
	        targetChat.statusText.textContent = cancelledByUser ? "研究已终止" : "研究已中断";
	      }
	    } else {
	      console.error(error);
	      const targetChat = finalChat;
	      if (isChatVisible(targetChat)) {
	        targetChat.statusText.textContent = "研究发生错误";
	        renderFormattedAnswer(error.message || "研究发生错误", targetChat);
	      }
    }
  } finally {
    if (taskId) {
      state.runningTaskIds.delete(taskId);
      state.taskRuns.delete(taskId);
    }
    state.taskRuns.delete(tempId);
    const targetChat = finalChat;
	    if (isChatVisible(targetChat) && targetChat.statusText.textContent !== "研究已终止" && targetChat.statusText.textContent !== "研究发生错误") {
	      targetChat.thinking.classList.add("hidden");
	    }
    setBusy(false);
    if (state.currentTaskId === taskId) state.currentTaskId = null;
    refreshRunningUi();
    await loadTasks();
  }
}

async function cancelTask(taskId) {
  if (taskId && !taskId.startsWith("pending_")) {
    try {
      await fetch(`/api/tasks/${taskId}/cancel`, { method: "POST" });
    } catch (error) {
      console.error(error);
    }
  }
  const run = state.taskRuns.get(taskId);
  if (run?.controller) run.controller.abort();
  state.runningTaskIds.delete(taskId);
  state.taskRuns.delete(taskId);
  const chat = run?.chat || state.chatByTaskId.get(taskId);
  if (isChatVisible(chat)) {
    renderFormattedAnswer("研究已取消。", chat);
    chat.thinking.classList.add("hidden");
    chat.feedbackBar.classList.add("hidden");
    chat.followupContainer.classList.add("hidden");
    setResultControlsVisible(false, chat);
  }
  refreshRunningUi();
  await loadTasks();
}

async function cancelCurrentTask() {
  if (state.activeTaskId) await cancelTask(state.activeTaskId);
}

function formatTime(value) {
  if (!value) return "-";
  try {
    return new Date(value).toLocaleString("zh-CN", { hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  } catch {
    return value;
  }
}

function statusText(status) {
  return {
    queued: "排队",
    running: "运行中",
    cancelled: "已取消",
    failed: "失败",
    completed: "完成",
    empty: "未开始",
  }[status] || status || "-";
}

async function loadTasks() {
  try {
    const params = new URLSearchParams({
      archived: state.showArchived ? "true" : "false",
    });
    const response = await fetch(`/api/conversations?${params}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    state.conversations = payload.conversations || [];
    renderTasks();
  } catch (error) {
    console.error(error);
  }
}

function renderTasks() {
  nodes.taskList.innerHTML = "";
  nodes.historyModeLabel.textContent = state.showArchived ? "已归档对话" : "最近对话";
  nodes.archiveToggle.textContent = state.showArchived ? "返回" : "归档";
  if (!state.conversations.length) {
    nodes.taskList.innerHTML = `<div class="empty compact">${state.showArchived ? "没有归档对话" : "还没有对话历史"}</div>`;
    return;
  }
  state.conversations.forEach((conversation) => {
    const latest = conversation.latest_task || {};
    const runningIds = conversation.running_task_ids || [];
    const item = document.createElement("article");
    item.className = `task-item status-${conversation.status}${state.currentConversationId === conversation.id ? " active" : ""}`;
    item.onclick = () => restoreConversation(conversation.id);

    const title = document.createElement("h3");
    title.textContent = conversation.title || latest.query || "未命名对话";

    const meta = document.createElement("div");
    meta.className = "task-meta";
    const countText = conversation.task_count ? `${conversation.task_count} 条研究` : "空对话";
    meta.textContent = `${formatTime(conversation.updated_at)} · ${statusText(conversation.status)} · ${countText}`;

    const main = document.createElement("div");
    main.className = "task-main";
    main.append(title, meta);

    const actions = document.createElement("div");
    actions.className = "task-actions";

    if (runningIds.length) {
      const stop = document.createElement("button");
      stop.type = "button";
      stop.textContent = "停止";
      stop.className = "danger-action";
      stop.onclick = async (event) => {
        event.stopPropagation();
        await Promise.all(runningIds.map(id => cancelTask(id)));
      };
      actions.appendChild(stop);
    }

    const rename = document.createElement("button");
    rename.type = "button";
    rename.textContent = "命名";
    rename.onclick = async (event) => {
      event.stopPropagation();
      await renameConversation(conversation.id, conversation.title || latest.query || "");
    };

    const archive = document.createElement("button");
    archive.type = "button";
    archive.textContent = state.showArchived ? "取消归档" : "归档";
    archive.onclick = async (event) => {
      event.stopPropagation();
      await archiveConversation(conversation.id, !state.showArchived);
    };

    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "删除";
    remove.onclick = async (event) => {
      event.stopPropagation();
      await deleteConversation(conversation.id, runningIds);
    };

    actions.append(rename, archive, remove);
    item.append(main, actions);
    nodes.taskList.appendChild(item);
  });
}

async function newConversation() {
  if (state.showArchived) {
    state.showArchived = false;
  }
  resetConversationView();
  setCurrentConversation(null);
  await loadTasks();
  nodes.query.focus();
}

function normalizeTaskResult(task) {
  const result = task.result || {};
  if (result.answer || result.traces || result.metrics) return result;
  const isCancelled = task.status === "cancelled";
  const isRunning = task.status === "running" || task.status === "queued";
  return {
    query: task.query,
    answer: isCancelled ? "研究已取消。" : isRunning ? "" : (task.error_message || `任务状态：${statusText(task.status)}`),
    plan: { intent: "", subqueries: [], source_plan: [], required_evidence: [], llm_used: false },
    citations: [],
    findings: [],
    risks: task.error_message ? [task.error_message] : [],
    decision_brief: {},
    trust_score: {},
    knowledge_map: {},
    next_questions: [],
    frontier_patterns: [],
    metrics: { task_status: task.status },
    traces: [],
  };
}

async function restoreConversation(conversationId) {
  const response = await fetch(`/api/conversations/${conversationId}`);
  if (!response.ok) return;
  const payload = await response.json();
  const conversation = payload.conversation;
  const tasks = conversation.tasks || [];
  window.clearInterval(state.typeTimer);
  state.typeTimer = null;
  resetConversationView(tasks.length ? "" : "这个对话还没有研究。");
  setCurrentConversation(conversation);
  state.chatByTaskId.clear();
  if (!tasks.length) {
    renderTasks();
    return;
  }
  document.body.classList.add("has-result");
  nodes.dockContainer.classList.add("docked");
  state.hasResult = true;
  state.hasResultBefore = true;
  nodes.chatHistory.innerHTML = "";
  tasks.forEach((task) => {
    const chat = createChatItem(task.query, { append: true });
    chat.task = task;
    chat.container.dataset.taskId = task.id;
    state.chatByTaskId.set(task.id, chat);
    state.currentChat = chat;
    state.activeTaskId = task.id;
    const run = state.taskRuns.get(task.id);
    if (run) {
      run.task = task;
      run.conversationId = task.conversation_id;
      bindRunChat(run, chat, task);
      state.taskRuns.set(task.id, run);
    }
    const isActive = task.status === "running" || task.status === "queued";
    if (isActive) {
      if (run) {
        applyRunProgress(chat, run, task);
      } else {
        chat.statusText.textContent = fallbackRunningStatus(task);
        chat.progressSteps.innerHTML = "";
        (task.result?.traces || []).forEach((trace) => {
          renderProgressStep(chat, { message: `${trace.name}: ${trace.message}` });
        });
        chat.thinking.classList.remove("hidden");
      }
    } else {
      const result = normalizeTaskResult(task);
      renderResearch(result, { task, chat, animate: false });
      if (task.status === "cancelled") {
        chat.thinking.classList.add("hidden");
      } else {
        chat.thinking.classList.add("hidden");
      }
    }
  });
  renderTasks();
  refreshRunningUi();
  requestAnimationFrame(() => {
    nodes.chatHistory.scrollTop = nodes.chatHistory.scrollHeight;
  });
}

async function renameConversation(conversationId, currentTitle) {
  const title = window.prompt("重命名对话", currentTitle || "");
  if (!title || !title.trim()) return;
  const response = await fetch(`/api/conversations/${conversationId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: title.trim() }),
  });
  if (response.ok) {
    if (state.currentConversationId === conversationId) {
      const payload = await response.json();
      setCurrentConversation(payload.conversation);
    }
    await loadTasks();
  }
}

async function deleteConversation(conversationId, runningIds = []) {
  await Promise.all((runningIds || []).map(id => cancelTask(id)));
  const response = await fetch(`/api/conversations/${conversationId}`, { method: "DELETE" });
  if (response.ok) {
    if (state.currentConversationId === conversationId) {
      await newConversation();
    } else {
      await loadTasks();
    }
  }
}

async function archiveConversation(conversationId, archived) {
  const response = await fetch(`/api/conversations/${conversationId}/archive`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ archived }),
  });
  if (response.ok) {
    if (state.currentConversationId === conversationId && archived) await newConversation();
    await loadTasks();
  }
}

function renderModelState(config) {
  state.llm = config;
  if (!config) return;
  if (config.enabled) {
    nodes.modelState.textContent = `远程模型 · ${config.model}`;
    nodes.modelMessage.textContent = `已配置 ${config.model}`;
  } else {
    nodes.modelState.textContent = "本地兜底模式";
    nodes.modelMessage.textContent = config.has_api_key ? "模型名未配置" : "未配置远程模型";
  }
  if (config.enabled || config.has_api_key) {
    if (config.base_url) nodes.baseUrl.value = config.base_url;
    if (config.model && config.model !== "openai-compatible-model") nodes.model.value = config.model;
  }
  if (config.timeout) nodes.timeout.value = config.timeout;
}

function renderSourceState(config) {
  state.sources = config;
  if (!config) return;
  nodes.openAlexMailto.value = config.openalex?.mailto || DEFAULT_SOURCE_EMAIL;
  nodes.crossrefMailto.value = config.crossref?.mailto || DEFAULT_SOURCE_EMAIL;
  nodes.sourceTimeout.value = config.timeout || 15;
  nodes.perSourceLimit.value = config.per_source_limit || 5;
  const semantic = config.semantic_scholar?.has_api_key ? "Semantic Scholar Key 已配置" : "Semantic Scholar Key 未配置";
  const openalex = config.openalex?.has_api_key ? "OpenAlex Key 已配置" : "OpenAlex Key 未配置";
  nodes.sourcesMessage.textContent = `${semantic} · ${openalex}`;
}

async function saveModelConfig() {
  nodes.saveModel.disabled = true;
  nodes.modelMessage.textContent = "保存中";
  try {
    const response = await fetch("/api/config/llm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: nodes.provider.value,
        api_key: nodes.apiKey.value,
        base_url: nodes.baseUrl.value,
        model: nodes.model.value,
        timeout: nodes.timeout.value,
        enable_thinking: nodes.thinking.checked,
      }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    localStorage.setItem("keyboy_llm_provider", nodes.provider.value);
    localStorage.setItem("keyboy_llm_base_url", nodes.baseUrl.value);
    localStorage.setItem("keyboy_llm_model", nodes.model.value);
    renderModelState(payload.llm);
    nodes.apiKey.value = "";
  } catch (error) {
    nodes.modelMessage.textContent = `保存失败：${error.message}`;
  } finally {
    nodes.saveModel.disabled = false;
  }
}

async function saveSourceConfig() {
  nodes.saveSources.disabled = true;
  nodes.sourcesMessage.textContent = "保存中";
  try {
    const response = await fetch("/api/config/sources", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        semantic_scholar_api_key: nodes.semanticScholarKey.value,
        openalex_api_key: nodes.openAlexKey.value,
        openalex_mailto: nodes.openAlexMailto.value,
        crossref_mailto: nodes.crossrefMailto.value,
        timeout: nodes.sourceTimeout.value,
        per_source_limit: nodes.perSourceLimit.value,
      }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    localStorage.setItem("keyboy_openalex_mailto", nodes.openAlexMailto.value);
    localStorage.setItem("keyboy_crossref_mailto", nodes.crossrefMailto.value);
    localStorage.setItem("keyboy_source_timeout", nodes.sourceTimeout.value);
    localStorage.setItem("keyboy_per_source_limit", nodes.perSourceLimit.value);
    renderSourceState(payload.sources);
    nodes.semanticScholarKey.value = "";
    nodes.openAlexKey.value = "";
  } catch (error) {
    nodes.sourcesMessage.textContent = `保存失败：${error.message}`;
  } finally {
    nodes.saveSources.disabled = false;
  }
}

function applyProviderDefaults() {
  if (nodes.provider.value === "bailian") {
    nodes.baseUrl.value = "https://dashscope.aliyuncs.com/compatible-mode/v1";
    if (!nodes.model.value || nodes.model.value === "openai-compatible-model") {
      nodes.model.value = "qwen-plus";
    }
  }
}

function showDrawer(name) {
  const resultOnly = new Set(["evidence", "trace", "quality"]);
  if (resultOnly.has(name) && !state.hasResult) return;
  const titles = {
    model: "模型连接",
    sources: "在线源配置",
    evidence: "证据来源",
    trace: "Agent Trace",
    quality: "质量状态",
  };
  nodes.drawerTitle.textContent = titles[name] || "详情";
  [nodes.modelView, nodes.sourcesView, nodes.evidenceView, nodes.traceView, nodes.qualityView].forEach((view) => {
    if (view) view.classList.add("hidden");
  });
  const target = {
    model: nodes.modelView,
    sources: nodes.sourcesView,
    evidence: nodes.evidenceView,
    trace: nodes.traceView,
    quality: nodes.qualityView,
  }[name];
  if (target) target.classList.remove("hidden");
  nodes.drawerOverlay.classList.remove("hidden");
  const drawerEl = nodes.drawerOverlay.querySelector('.drawer');
  if (drawerEl) drawerEl.scrollTop = 0;
}

function hideDrawer() {
  nodes.drawerOverlay.classList.add("hidden");
}

function setLocalDocCount(count) {
  nodes.docCount.textContent = `本地资料 ${count ?? "-"} 篇`;
}

async function loadHealth() {
  try {
    const response = await fetch("/api/health");
    const payload = await response.json();
    const stats = payload.stats || {};
    setLocalDocCount(stats.documents);
    renderModelState(payload.llm);
  } catch (error) {}
}

async function uploadLocalDocuments() {
  const files = Array.from(nodes.localDocInput?.files || []);
  if (!files.length) return;

  const previousLabel = nodes.docCount.textContent;
  const payload = new FormData();
  files.forEach((file) => payload.append("files", file));
  nodes.docCount.disabled = true;
  nodes.docCount.classList.remove("upload-ok", "upload-warn", "upload-error");
  nodes.docCount.classList.add("uploading");
  nodes.docCount.textContent = `正在上传 ${files.length} 篇...`;
  nodes.docCount.title = "正在把本地资料加入索引";

  try {
    const response = await fetch("/api/local-documents", {
      method: "POST",
      body: payload,
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(result.detail || "上传失败。");
    }
    const skipped = result.skipped || [];
    const added = Number(result.added || 0);
    nodes.docCount.classList.add(added > 0 ? "upload-ok" : "upload-warn");
    nodes.docCount.textContent = added > 0 ? `已加入 ${added} 篇` : "未加入新资料";
    nodes.docCount.title = skipped.length
      ? `已加入 ${added} 篇，跳过 ${skipped.length} 个文件：${skipped.map(item => `${item.file}：${item.reason}`).join("；")}`
      : `已加入 ${added} 篇本地资料`;
    setTimeout(() => {
      nodes.docCount.classList.remove("upload-ok", "upload-warn");
      loadHealth();
    }, 1200);
  } catch (error) {
    nodes.docCount.classList.add("upload-error");
    nodes.docCount.textContent = "上传失败";
    nodes.docCount.title = error.message || "上传失败，请检查文件格式。";
    setTimeout(() => {
      nodes.docCount.classList.remove("upload-error");
      nodes.docCount.textContent = previousLabel;
    }, 1600);
  } finally {
    nodes.docCount.classList.remove("uploading");
    nodes.docCount.disabled = false;
    nodes.localDocInput.value = "";
  }
}

async function loadSources() {
  try {
    const response = await fetch("/api/config/sources");
    if (response.ok) renderSourceState(await response.json());
  } catch {
    nodes.sourcesMessage.textContent = "在线源配置未加载";
  }
}

function restoreLocalSettings() {
  nodes.provider.value = localStorage.getItem("keyboy_llm_provider") || "bailian";
  nodes.baseUrl.value = localStorage.getItem("keyboy_llm_base_url") || nodes.baseUrl.value;
  nodes.model.value = localStorage.getItem("keyboy_llm_model") || nodes.model.value;
  nodes.openAlexMailto.value = localStorage.getItem("keyboy_openalex_mailto") || nodes.openAlexMailto.value;
  nodes.crossrefMailto.value = localStorage.getItem("keyboy_crossref_mailto") || nodes.crossrefMailto.value;
  nodes.sourceTimeout.value = localStorage.getItem("keyboy_source_timeout") || nodes.sourceTimeout.value;
  nodes.perSourceLimit.value = localStorage.getItem("keyboy_per_source_limit") || nodes.perSourceLimit.value;
  applyProviderDefaults();
}

nodes.form.addEventListener("submit", (e) => {
  e.preventDefault();
  const currentRunning = getCurrentConversationRunningIds();
  if (currentRunning.length > 0) {
    for (const id of currentRunning) {
      cancelTask(id);
    }
    return;
  }
  nodes.drawerOverlay.click();
  runResearch();
});


nodes.online.addEventListener("change", () => {
  // Toggle doesn't need to show status text anymore
});

nodes.docCount.addEventListener("click", () => nodes.localDocInput.click());
nodes.localDocInput.addEventListener("change", uploadLocalDocuments);
nodes.provider.addEventListener("change", applyProviderDefaults);
nodes.saveModel.addEventListener("click", saveModelConfig);
nodes.saveSources.addEventListener("click", saveSourceConfig);
nodes.historyToggle.addEventListener("click", () => setHistoryPanelOpen(!nodes.historyPanel.classList.contains("is-open")));
nodes.historyCollapse.addEventListener("click", () => setHistoryPanelOpen(false));
window.addEventListener("resize", () => {
  if (!nodes.historyPanel.classList.contains("is-open")) return;
  $(".stage").style.paddingLeft = window.matchMedia("(max-width: 860px)").matches ? "14px" : "338px";
});
nodes.newConversation.addEventListener("click", newConversation);
nodes.archiveToggle.addEventListener("click", async () => {
  state.showArchived = !state.showArchived;
  if (state.showArchived && state.currentConversationId) {
    const active = state.conversations.find(conversation => conversation.id === state.currentConversationId);
    if (!active?.archived) {
      resetConversationView();
      setCurrentConversation(null);
    }
  }
  await loadTasks();
});
nodes.refreshHistory.addEventListener("click", loadTasks);
nodes.drawerClose.addEventListener("click", hideDrawer);
nodes.drawerOverlay.addEventListener("click", (event) => {
  if (event.target === nodes.drawerOverlay) hideDrawer();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") hideDrawer();
});

$$("[data-drawer]").forEach((button) => {
  button.addEventListener("click", () => showDrawer(button.dataset.drawer));
});

setResultControlsVisible(false);
restoreLocalSettings();
loadHealth();
loadSources();
loadTasks();
