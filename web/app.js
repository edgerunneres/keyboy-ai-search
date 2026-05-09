const state = {
  mode: "hybrid",
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

function scorePart(label, value) {
  const width = Math.max(0, Math.min(100, value));
  return `
    <div class="score-part">
      <div class="score-label"><span>${label}</span><strong>${value.toFixed(0)}</strong></div>
      <div class="bar"><span style="width:${width}%"></span></div>
    </div>
  `;
}

function renderResults(hits) {
  $("#resultCount").textContent = `${hits.length} 条`;
  if (!hits.length) {
    $("#results").innerHTML = `<div class="empty">没有匹配结果</div>`;
    return;
  }
  $("#results").innerHTML = hits
    .map((hit) => {
      const doc = hit.document;
      const parts = hit.score_parts;
      return `
        <article class="result-card">
          <div class="result-title">
            <h3>${doc.title}</h3>
            <div class="score">${hit.score.toFixed(1)}</div>
          </div>
          <div class="meta">${doc.source} · ${doc.category} · ${doc.published_at}</div>
          <p class="snippet">${hit.snippet}</p>
          <div class="score-bars">
            ${scorePart("BM25", parts.bm25)}
            ${scorePart("语义", parts.semantic)}
            ${scorePart("RRF", parts.rrf)}
            ${scorePart("重排", parts.rerank)}
          </div>
          <div class="explain">命中解释：${hit.explanation}。关键词：${hit.matched_terms.slice(0, 8).join("、") || "综合相关"}</div>
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

function renderQuality(payload) {
  const evalMetrics = payload.metrics?.evaluation || state.health?.evaluation || {};
  dl($("#qualityList"), [
    ["Recall@5", evalMetrics.recall_at_5 ?? "-"],
    ["nDCG@5", evalMetrics.ndcg_at_5 ?? "-"],
    ["评测查询", evalMetrics.cases ?? "-"],
    ["平均耗时", `${evalMetrics.avg_latency_ms ?? "-"} ms`],
  ]);
}

async function search() {
  const params = new URLSearchParams({
    q: $("#queryInput").value.trim(),
    mode: state.mode,
    source: $("#sourceFilter").value,
    category: $("#categoryFilter").value,
    limit: "8",
  });
  $("#statusText").textContent = "正在检索...";
  const response = await fetch(`/api/search?${params}`);
  const payload = await response.json();
  $("#statusText").textContent = `当前模式：${payload.mode}`;
  $("#latencyBadge").textContent = `${payload.metrics.latency_ms} ms`;
  $("#summaryText").textContent = payload.summary;
  $("#insightList").innerHTML = payload.insights.map((item) => `<li>${item}</li>`).join("");
  renderResults(payload.hits);
  renderTrace(payload.traces);
  renderQuality(payload);
  const profile = payload.query_profile || {};
  dl($("#profileList"), [
    ["词项数", profile.token_count ?? 0],
    ["问题意图", profile.has_question_intent ? "是" : "否"],
    ["BM25 权重", profile.lexical_weight ?? "-"],
    ["语义权重", profile.semantic_weight ?? "-"],
    ["命中词", (profile.tokens || []).slice(0, 10).join("、")],
  ]);
}

async function loadHealth() {
  const response = await fetch("/api/health");
  state.health = await response.json();
  const stats = state.health.stats;
  $("#docCount").textContent = stats.documents;
  $("#vocabCount").textContent = stats.vocabulary;
  optionList($("#sourceFilter"), stats.sources, "全部来源");
  optionList($("#categoryFilter"), stats.categories, "全部主题");
  $("#statusText").textContent = "索引已就绪";
  renderQuality({ metrics: { evaluation: state.health.evaluation } });
}

$("#searchForm").addEventListener("submit", (event) => {
  event.preventDefault();
  search();
});

$$(".mode-switch button").forEach((button) => {
  button.addEventListener("click", () => {
    $$(".mode-switch button").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    state.mode = button.dataset.mode;
    search();
  });
});

$$(".example").forEach((button) => {
  button.addEventListener("click", () => {
    $("#queryInput").value = button.dataset.query;
    search();
  });
});

$("#sourceFilter").addEventListener("change", search);
$("#categoryFilter").addEventListener("change", search);

loadHealth().then(search).catch((error) => {
  $("#statusText").textContent = `初始化失败：${error}`;
});

