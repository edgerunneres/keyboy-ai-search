const state = {
  mode: "research",
  health: null,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

function optionList(select, values, label) {
  select.innerHTML = "";
  const all = document.createElement("option");
  all.value = "";
  all.textContent = label;
  select.appendChild(all);
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  });
}

function dl(container, pairs) {
  container.innerHTML = "";
  pairs.forEach(([key, value]) => {
    const dt = document.createElement("dt");
    dt.textContent = key;
    const dd = document.createElement("dd");
    dd.textContent = value;
    container.append(dt, dd);
  });
}

function renderCitations(citations) {
  $("#resultCount").textContent = `${citations.length} 条`;
  if (!citations.length) {
    $("#results").innerHTML = `<div class="empty">没有获得证据来源</div>`;
    return;
  }

  $("#results").innerHTML = citations
    .map((item) => {
      const url = item.url || "#";
      return `
        <article class="result-card">
          <div class="result-title">
            <h3>[${item.id}] ${item.title}</h3>
            <div class="score">${Number(item.score || 0).toFixed(1)}</div>
          </div>
          <div class="meta">${item.source} · ${item.published_at || "未知日期"}</div>
          <p class="snippet">${item.evidence || "暂无摘要。"}</p>
          <a class="citation-link" href="${url}" target="_blank" rel="noreferrer">打开来源</a>
        </article>
      `;
    })
    .join("");
}

function renderTrace(traces) {
  $("#traceList").innerHTML = traces
    .map(
      (trace) => `
        <div class="trace-item">
          <strong>${trace.name} · ${trace.status}</strong>
          <span>${trace.message} · ${trace.duration_ms.toFixed(2)} ms</span>
        </div>
      `
    )
    .join("");
}

function renderRisks(risks) {
  $("#riskList").innerHTML = (risks || [])
    .map((risk) => `<div class="risk-item">${risk}</div>`)
    .join("");
}

function renderResearch(payload) {
  $("#statusText").textContent = `当前模式：${state.mode === "local" ? "本地证据" : "在线 Agentic Research"}`;
  $("#latencyBadge").textContent = `${payload.metrics.latency_ms} ms`;
  $("#summaryText").textContent = payload.answer;
  $("#insightList").innerHTML = payload.findings.map((item) => `<li>${item}</li>`).join("");
  renderCitations(payload.citations);
  renderTrace(payload.traces);
  renderRisks(payload.risks);

  const plan = payload.plan || {};
  dl($("#profileList"), [
    ["意图", plan.intent || "-"],
    ["LLM 规划", plan.llm_used ? "已启用" : "本地规划"],
    ["子查询", (plan.subqueries || []).join(" | ")],
    ["在线源", (plan.source_plan || []).join("、")],
    ["证据要求", (plan.required_evidence || []).join("、")],
  ]);

  const metrics = payload.metrics || {};
  dl($("#qualityList"), [
    ["LLM 状态", metrics.llm_used ? "远程模型" : "本地 fallback"],
    ["模型", metrics.llm_model || "-"],
    ["在线文档", metrics.online_documents ?? "-"],
    ["索引文档", metrics.indexed_documents ?? "-"],
    ["结果数量", metrics.result_count ?? "-"],
  ]);
}

async function research() {
  const query = $("#queryInput").value.trim();
  if (!query) return;
  const online = state.mode !== "local" && $("#onlineToggle").checked;
  const params = new URLSearchParams({
    q: query,
    online: online ? "true" : "false",
    include_local: "true",
    limit: "10",
  });
  $("#statusText").textContent = online ? "正在规划并访问在线研究源..." : "正在使用本地证据运行...";
  const response = await fetch(`/api/research?${params}`);
  const payload = await response.json();
  renderResearch(payload);
}

async function classicSearch() {
  const params = new URLSearchParams({
    q: $("#queryInput").value.trim(),
    mode: "hybrid",
    source: $("#sourceFilter").value,
    category: $("#categoryFilter").value,
    limit: "8",
  });
  const response = await fetch(`/api/search?${params}`);
  const payload = await response.json();
  renderResearch({
    query: payload.query,
    answer: payload.summary,
    plan: {
      intent: "传统混合检索",
      llm_used: false,
      subqueries: [payload.query],
      source_plan: ["local"],
      required_evidence: ["本地知识库"],
    },
    citations: payload.hits.map((hit, index) => ({
      id: index + 1,
      title: hit.document.title,
      source: hit.document.source,
      url: hit.document.url,
      published_at: hit.document.published_at,
      score: hit.score,
      evidence: hit.snippet.replaceAll("<mark>", "").replaceAll("</mark>", ""),
    })),
    findings: payload.insights,
    risks: ["当前为兼容旧版本的本地混合检索链路。"],
    metrics: {
      latency_ms: payload.metrics.latency_ms,
      llm_used: false,
      llm_model: "none",
      online_documents: 0,
      indexed_documents: payload.metrics.index.documents,
      result_count: payload.hits.length,
    },
    traces: payload.traces,
  });
}

function runCurrentMode() {
  if (state.mode === "search") {
    classicSearch();
  } else {
    research();
  }
}

async function loadHealth() {
  const response = await fetch("/api/health");
  state.health = await response.json();
  const stats = state.health.stats;
  $("#docCount").textContent = stats.documents;
  $("#vocabCount").textContent = stats.vocabulary;
  optionList($("#sourceFilter"), stats.sources, "全部来源");
  optionList($("#categoryFilter"), stats.categories, "全部主题");
  $("#statusText").textContent = "多智能体研究系统已就绪";
}

$("#searchForm").addEventListener("submit", (event) => {
  event.preventDefault();
  runCurrentMode();
});

$$(".mode-switch button").forEach((button) => {
  button.addEventListener("click", () => {
    $$(".mode-switch button").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    state.mode = button.dataset.mode;
    runCurrentMode();
  });
});

$$(".example").forEach((button) => {
  button.addEventListener("click", () => {
    $("#queryInput").value = button.dataset.query;
    runCurrentMode();
  });
});

$("#sourceFilter").addEventListener("change", runCurrentMode);
$("#categoryFilter").addEventListener("change", runCurrentMode);
$("#onlineToggle").addEventListener("change", runCurrentMode);

loadHealth().then(runCurrentMode).catch((error) => {
  $("#statusText").textContent = `初始化失败：${error}`;
});

