const state = {
  mode: "research",
  health: null,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

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
            <h3>[${escapeHtml(item.id)}] ${escapeHtml(item.title)}</h3>
            <div class="score">${Number(item.score || 0).toFixed(1)}</div>
          </div>
          <div class="meta">${escapeHtml(item.source)} · ${escapeHtml(item.published_at || "未知日期")}</div>
          <p class="snippet">${escapeHtml(item.evidence || "暂无摘要。")}</p>
          <a class="citation-link" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">打开来源</a>
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
          <strong>${escapeHtml(trace.name)} · ${escapeHtml(trace.status)}</strong>
          <span>${escapeHtml(trace.message)} · ${trace.duration_ms.toFixed(2)} ms</span>
        </div>
      `
    )
    .join("");
}

function renderRisks(risks) {
  $("#riskList").innerHTML = (risks || [])
    .map((risk) => `<div class="risk-item">${escapeHtml(risk)}</div>`)
    .join("");
}

function renderDecisionBrief(brief) {
  const data = brief || {};
  $("#needText").textContent = data.user_need || "-";
  $("#pathText").textContent = data.recommended_path || "-";
  $("#whyList").innerHTML = (data.why_keyboy || [])
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");
  $("#tradeoffList").innerHTML = (data.tradeoffs || [])
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");
}

function renderTrust(score) {
  const data = score || {};
  $("#trustScore").textContent = data.score ?? "-";
  $("#trustLevel").textContent = data.level ? `可信度：${data.level}` : "可信度：-";
  $("#trustSignals").innerHTML = (data.signals || [])
    .map((signal) => {
      const max = Number(signal.max || 1);
      const raw = Number(signal.score || 0);
      const percent = max > 0 ? Math.max(0, Math.min(100, (raw / max) * 100)) : 0;
      return `
        <div class="signal-item">
          <div class="signal-head">
            <strong>${escapeHtml(signal.name)}</strong>
            <span>${escapeHtml(signal.score)} / ${escapeHtml(signal.max)}</span>
          </div>
          <div class="bar"><span style="width:${percent}%"></span></div>
          <small>${escapeHtml(signal.detail)}</small>
        </div>
      `;
    })
    .join("");
}

function renderKnowledgeMap(map) {
  const data = map || {};
  const concepts = data.concepts || [];
  $("#conceptCloud").innerHTML = concepts.length
    ? concepts.map((item) => `<span>${escapeHtml(item.name)}</span>`).join("")
    : `<span>暂无概念</span>`;
  $("#sourceCoverage").innerHTML = (data.source_coverage || [])
    .map((item) => `<div><strong>${escapeHtml(item.name)}</strong><span>${escapeHtml(item.count)} 条</span></div>`)
    .join("");
}

function renderFrontier(patterns) {
  $("#frontierList").innerHTML = (patterns || [])
    .map(
      (item) => `
        <div class="frontier-item">
          <strong>${escapeHtml(item.name)}</strong>
          <span>${escapeHtml(item.strength)}</span>
          <small>已融合：${escapeHtml(item.integrated_as)}</small>
        </div>
      `
    )
    .join("");
}

function renderNextQuestions(questions) {
  $("#nextQuestionList").innerHTML = (questions || [])
    .map((item) => `<button class="next-question" type="button">${escapeHtml(item)}</button>`)
    .join("");
  $$(".next-question").forEach((button) => {
    button.addEventListener("click", () => {
      $("#queryInput").value = button.textContent;
      runCurrentMode();
    });
  });
}

function renderResearch(payload) {
  $("#statusText").textContent = `当前模式：${state.mode === "local" ? "本地证据" : "在线 Agentic Research"}`;
  $("#latencyBadge").textContent = `${payload.metrics.latency_ms} ms`;
  $("#summaryText").textContent = payload.answer;
  $("#insightList").innerHTML = payload.findings.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  renderCitations(payload.citations);
  renderTrace(payload.traces);
  renderRisks(payload.risks);
  renderDecisionBrief(payload.decision_brief);
  renderTrust(payload.trust_score);
  renderKnowledgeMap(payload.knowledge_map);
  renderFrontier(payload.frontier_patterns);
  renderNextQuestions(payload.next_questions);

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
    decision_brief: {
      user_need: "快速查清本地知识库中的课程设计证据。",
      recommended_path: "本地 Search 适合做快速定位；需要前沿资料、风险校验和行动建议时切换到 Research。",
      why_keyboy: ["搜索结果带评分解释。", "本地知识库可离线稳定演示。"],
      tradeoffs: ["本地 Search 速度快，但不会访问在线源，也不会生成完整决策简报。"],
    },
    trust_score: {
      score: Math.min(80, 30 + payload.hits.length * 6),
      level: "本地",
      signals: [
        { name: "本地命中", score: payload.hits.length, max: 8, detail: `${payload.hits.length} 条本地结果` },
        { name: "离线稳定", score: 10, max: 10, detail: "无需网络和模型 API" },
      ],
    },
    knowledge_map: {
      concepts: payload.hits.slice(0, 6).flatMap((hit) => (hit.matched_terms || []).slice(0, 2)).map((term) => ({ name: term, weight: 1 })),
      source_coverage: Object.entries(payload.hits.reduce((acc, hit) => {
        acc[hit.document.source] = (acc[hit.document.source] || 0) + 1;
        return acc;
      }, {})).map(([name, count]) => ({ name, count })),
    },
    frontier_patterns: [],
    next_questions: [
      `${payload.query} 的下一步工程实现是什么？`,
      `${payload.query} 需要哪些验收指标？`,
    ],
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

