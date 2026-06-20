const DEFAULT_QUERY = "Agentic RAG GraphRAG LightRAG Self-RAG 最新研究怎么整合到课程项目";
const DEFAULT_SOURCE_EMAIL = "yup300737@gmail.com";

const state = {
  running: false,
  llm: null,
  sources: null,
  hasResult: false,
  typeTimer: null,
  autoFollowAnswer: true,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const nodes = {
  form: $("#searchForm"),
  query: $("#queryInput"),
  submit: $("#submitBtn"),
  online: $("#onlineToggle"),
  status: $("#statusText"),
  docCount: $("#docCount"),
  modelState: $("#modelState"),
  loading: $("#loadingState"),
  answerStage: $(".answer-stage"),
  latency: $("#latencyBadge"),
  summary: $("#summaryText"),
  insights: $("#insightList"),
  resultActions: $("#resultActions"),
  results: $("#results"),
  resultCount: $("#resultCount"),
  drawerOverlay: $("#drawerOverlay"),
  drawerTitle: $("#drawerTitle"),
  drawerClose: $("#drawerClose"),
  modelView: $("#drawerModel"),
  sourcesView: $("#drawerSources"),
  evidenceView: $("#drawerEvidence"),
  planView: $("#drawerPlan"),
  traceView: $("#drawerTrace"),
  qualityView: $("#drawerQuality"),
  profile: $("#profileList"),
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
};

nodes.query.placeholder = DEFAULT_QUERY;

function setBusy(value) {
  state.running = value;
  nodes.submit.disabled = value;
  nodes.loading.classList.toggle("hidden", !value);
}

function setResultControlsVisible(value) {
  state.hasResult = value;
  document.body.classList.toggle("has-result", value);
  nodes.resultActions.classList.toggle("hidden", !value);
}

function dl(container, pairs) {
  container.innerHTML = "";
  pairs.forEach(([key, value]) => {
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = key;
    dd.textContent = value ?? "-";
    container.append(dt, dd);
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

function renderFormattedAnswer(text) {
  const source = String(text || "").replace(/\r\n/g, "\n").trim();
  if (!source) {
    nodes.summary.innerHTML = "";
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
  nodes.summary.innerHTML = html;
}

function typeAnswer(text) {
  window.clearInterval(state.typeTimer);
  nodes.summary.innerHTML = "";
  state.typeTimer = null;
  state.autoFollowAnswer = false;
  nodes.answerStage.scrollTop = 0;
  renderFormattedAnswer(text || "没有生成答案。");
  window.requestAnimationFrame(() => {
    nodes.answerStage.scrollTop = 0;
  });
}

function renderCitations(citations) {
  nodes.resultCount.textContent = String(citations.length);
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
    snippet.textContent = item.evidence || "暂无摘要。";

    const isWebUrl = /^https?:\/\//i.test(item.url || "");
    const source = document.createElement(isWebUrl ? "a" : "span");
    source.className = isWebUrl ? "citation-link" : "source-text";
    source.textContent = isWebUrl ? "打开来源" : item.url || "本地资料";
    if (isWebUrl) {
      source.href = item.url;
      source.target = "_blank";
      source.rel = "noreferrer";
    }

    article.append(titleRow, meta, snippet, source);
    nodes.results.appendChild(article);
  });
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

function renderResearch(payload) {
  const metrics = payload.metrics || {};
  const onlineDocs = metrics.online_documents ?? 0;
  nodes.status.textContent = nodes.online.checked ? `在线资料 · ${onlineDocs} 篇` : "仅本地资料";
  nodes.latency.textContent = `${metrics.latency_ms ?? "-"} ms`;
  setResultControlsVisible(true);
  typeAnswer(payload.answer || "没有生成答案。");
  renderList(nodes.insights, payload.findings);
  renderCitations(payload.citations || []);
  renderTrace(payload.traces);
  renderRisks(payload.risks);

  const plan = payload.plan || {};
  dl(nodes.profile, [
    ["意图", plan.intent],
    ["规划", plan.llm_used ? "远程 LLM" : "本地规划"],
    ["子查询", (plan.subqueries || []).join(" | ")],
    ["证据", (plan.required_evidence || []).join("、")],
  ]);

  dl(nodes.quality, [
    ["模型", metrics.llm_used ? metrics.llm_model : "本地 fallback"],
    ["在线文档", metrics.online_documents],
    ["索引文档", metrics.indexed_documents],
    ["结果", metrics.result_count],
  ]);
}

async function runResearch() {
  if (state.running) return;
  const query = nodes.query.value.trim() || DEFAULT_QUERY;
  nodes.query.value = query;
  const params = new URLSearchParams({
    q: query,
    online: nodes.online.checked ? "true" : "false",
    include_local: "true",
    limit: "8",
  });

  nodes.status.textContent = nodes.online.checked ? "正在研究在线资料" : "正在研究本地资料";
  setBusy(true);
  try {
    const response = await fetch(`/api/research?${params}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderResearch(await response.json());
  } catch (error) {
    nodes.status.textContent = `请求失败：${error.message}`;
  } finally {
    setBusy(false);
  }
}

function renderModelState(config) {
  state.llm = config;
  if (!config) return;
  if (config.enabled) {
    nodes.modelState.textContent = `远程模型 · ${config.model}`;
    nodes.modelMessage.textContent = `已配置 ${config.model}`;
  } else {
    nodes.modelState.textContent = "本地 fallback";
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
  const resultOnly = new Set(["evidence", "plan", "trace", "quality"]);
  if (resultOnly.has(name) && !state.hasResult) return;
  const titles = {
    model: "模型连接",
    sources: "在线源配置",
    evidence: "证据来源",
    plan: "研究计划",
    trace: "Agent Trace",
    quality: "质量状态",
  };
  nodes.drawerTitle.textContent = titles[name] || "详情";
  [nodes.modelView, nodes.sourcesView, nodes.evidenceView, nodes.planView, nodes.traceView, nodes.qualityView].forEach((view) => {
    view.classList.add("hidden");
  });
  const target = {
    model: nodes.modelView,
    sources: nodes.sourcesView,
    evidence: nodes.evidenceView,
    plan: nodes.planView,
    trace: nodes.traceView,
    quality: nodes.qualityView,
  }[name];
  if (target) target.classList.remove("hidden");
  nodes.drawerOverlay.classList.remove("hidden");
}

function hideDrawer() {
  nodes.drawerOverlay.classList.add("hidden");
}

async function loadHealth() {
  try {
    const response = await fetch("/api/health");
    const payload = await response.json();
    const stats = payload.stats || {};
    nodes.docCount.textContent = `${stats.documents ?? "-"} docs · ${stats.vocabulary ?? "-"} terms`;
    renderModelState(payload.llm);
    nodes.status.textContent = "系统就绪";
  } catch (error) {
    nodes.status.textContent = "后端未连接";
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

nodes.form.addEventListener("submit", (event) => {
  event.preventDefault();
  runResearch();
});

nodes.answerStage.addEventListener("wheel", () => {
  state.autoFollowAnswer = false;
}, { passive: true });

nodes.answerStage.addEventListener("touchmove", () => {
  state.autoFollowAnswer = false;
}, { passive: true });

nodes.online.addEventListener("change", () => {
  nodes.status.textContent = nodes.online.checked ? "在线资料已打开" : "在线资料已关闭";
});

nodes.provider.addEventListener("change", applyProviderDefaults);
nodes.saveModel.addEventListener("click", saveModelConfig);
nodes.saveSources.addEventListener("click", saveSourceConfig);
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
