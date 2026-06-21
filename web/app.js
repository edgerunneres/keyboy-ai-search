const DEFAULT_QUERY = "Agentic RAG GraphRAG LightRAG Self-RAG 最新研究怎么整合到课程项目";
const DEFAULT_SOURCE_EMAIL = "yup300737@gmail.com";

const state = {
  running: false,
  llm: null,
  sources: null,
  hasResult: false,
  typeTimer: null,
  autoFollowAnswer: true,
  currentChat: null,
  abortController: null,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const nodes = {
  form: $("#searchForm"),
  query: $("#queryInput"),
  submit: $("#submitBtn"),
  online: $("#onlineToggle"),
  docCount: $("#docCount"),
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
  nodes.submit.textContent = value ? "停止" : "研究";
  nodes.form.classList.toggle("loading", value);
  nodes.online.disabled = value;
  $$(".top-actions .ghost-btn").forEach(btn => btn.disabled = value);
  if (value) {
    document.body.classList.add("has-result");
    nodes.dockContainer.classList.add("docked");
  }
}

function setResultControlsVisible(value) {
  state.hasResult = value;
  if (state.currentChat) {
    state.currentChat.resultActions.classList.toggle("hidden", !value);
  }
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
  if (state.currentChat) state.currentChat.summary.innerHTML = html;
}

function typeAnswer(text) {
  window.clearInterval(state.typeTimer);
  state.typeTimer = null;
  state.autoFollowAnswer = true;

  nodes.chatHistory.style.scrollBehavior = 'auto';

  const cancelAutoScroll = () => { state.autoFollowAnswer = false; };
  nodes.chatHistory.addEventListener('wheel', cancelAutoScroll, { once: true });
  nodes.chatHistory.addEventListener('touchstart', cancelAutoScroll, { once: true });

  const fullText = text || "没有生成答案。";

  /* Step 1: Render with the original formatter — formatting is 100% identical */
  renderFormattedAnswer(fullText);

  /* Step 2: Collect all text nodes, store their content, then clear them */
  const el = state.currentChat.summary;
  const textNodes = [];
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (node.textContent.trim()) {
      textNodes.push({ node, full: node.textContent });
      node.textContent = '';
    }
  }

  /* Step 3: Type through text nodes at 60fps */
  let nIdx = 0, cIdx = 0;

  const tick = () => {
    if (nIdx >= textNodes.length) {
      nodes.chatHistory.style.scrollBehavior = '';
      nodes.chatHistory.removeEventListener('wheel', cancelAutoScroll);
      nodes.chatHistory.removeEventListener('touchstart', cancelAutoScroll);
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

    /* Smooth lerp scroll — keep typing position at ~70% from top */
    if (state.autoFollowAnswer && state.currentChat) {
      const containerRect = nodes.chatHistory.getBoundingClientRect();
      const elRect = el.getBoundingClientRect();
      const offset = containerRect.height * 0.3;
      const gap = elRect.bottom - containerRect.bottom + offset;
      if (gap > 0) {
        nodes.chatHistory.scrollTop += gap * 0.15;
      }
    }

    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
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

function renderFollowups(query) {
  if (!state.currentChat) return;
  state.currentChat.followupList.innerHTML = "";
  const questions = [
    `深入了解 "${query}" 的最新技术进展和论文`,
    `"${query}" 在实际工业落地中的主要痛点是什么？`,
    `是否有与 "${query}" 相关的代表性开源方案？`
  ];
  questions.forEach(q => {
    const btn = document.createElement("button");
    btn.className = "followup-btn";
    btn.textContent = q;
    btn.onclick = () => {
      nodes.query.value = q;
      nodes.form.dispatchEvent(new Event("submit"));
    };
    state.currentChat.followupList.appendChild(btn);
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
    ["规划", plan.llm_used ? "远程 LLM" : "本地规划"],
    ["子查询", (plan.subqueries || []).join(" | ")],
    ["证据", (plan.required_evidence || []).join("、")],
  ]);
  const metrics = payload.metrics || {};
  dl(nodes.quality, [
    ["模型", metrics.llm_used ? metrics.llm_model : "本地 fallback"],
    ["在线文档", metrics.online_documents],
    ["索引文档", metrics.indexed_documents],
    ["结果", metrics.result_count],
  ]);
}

function renderResearch(payload) {
  const chat = state.currentChat;
  if (!chat) return;
  chat.payload = payload;
  chat.resultCount.textContent = String((payload.citations || []).length);
  const metrics = payload.metrics || {};
  chat.latencyBadge.textContent = `${metrics.latency_ms ?? "-"} ms`;
  setResultControlsVisible(true);
  typeAnswer(payload.answer || "没有生成答案。");
  renderList(chat.insights, payload.findings);

  chat.feedbackBar.classList.remove("hidden");
  chat.followupContainer.classList.remove("hidden");
  chat.upvoteBtn.classList.remove("active");
  chat.downvoteBtn.classList.remove("active");
  renderFollowups(chat.container.querySelector('.user-query').textContent);

  chat.copyBtn.addEventListener("click", () => {
    navigator.clipboard.writeText(chat.summary.innerText);
    chat.copyText.textContent = "已复制";
    chat.copyBtn.style.color = "#0071e3";
    setTimeout(() => {
      chat.copyText.textContent = "复制";
      chat.copyBtn.style.color = "#1d1d1f";
    }, 2000);
  });

  chat.upvoteBtn.addEventListener("click", () => {
    chat.upvoteBtn.classList.toggle("active");
    chat.downvoteBtn.classList.remove("active");
  });

  chat.downvoteBtn.addEventListener("click", () => {
    chat.downvoteBtn.classList.toggle("active");
    chat.upvoteBtn.classList.remove("active");
  });
}

function createChatItem(query) {
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
  container._payloadLink = chatObj;
  return chatObj;
}

async function runResearch() {
  if (state.running) {
    if (state.abortController) state.abortController.abort();
    return;
  }

  const query = nodes.query.value.trim() || DEFAULT_QUERY;

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

  state.abortController = new AbortController();

  const dock = nodes.dockContainer;
  const first = dock.getBoundingClientRect();

  state.currentChat = createChatItem(query);
  nodes.query.value = "";

  const params = new URLSearchParams({
    q: query,
    online: nodes.online.checked ? "true" : "false",
    include_local: "true",
    limit: "8",
  });

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

  try {
    params.set("stream", "true");
    const response = await fetch(`/api/research?${params}`, { signal: state.abortController.signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let done = false;
    let payload = null;

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

              if (event.type === "status") {
                const elapsed = Math.floor((Date.now() - startTime) / 1000);
                if (state.currentChat) {
                  state.currentChat.statusText.textContent = `深度研究进行中 (${elapsed}s)`;
                  const li = document.createElement("li");
                  li.style.animation = "answerBlockIn 0.3s cubic-bezier(0.2, 0.8, 0.2, 1) forwards";
                  li.innerHTML = `<span style="color: var(--teal); margin-right: 6px;">✓</span> <span>${escapeHtml(event.message)}</span>`;
                  state.currentChat.progressSteps.appendChild(li);

                  if (state.autoFollowAnswer) {
                    nodes.chatHistory.scrollTop = nodes.chatHistory.scrollHeight;
                  }
                }
              } else if (event.type === "chunk") {
                textBuffer += event.chunk;
                const lastLine = textBuffer.split("\n").filter(l => l.trim().length > 0).pop() || "";
                const displayLine = lastLine.replace(/[#*`>{}\[\]]/g, "").trim();
                const shortDisplay = displayLine.length > 50 ? displayLine.substring(displayLine.length - 50) : displayLine;
                if (shortDisplay && state.currentChat) {
                  state.currentChat.summary.innerHTML = `<span style="color: #86868b; font-style: italic;">正在思考：${shortDisplay}</span>`;
                }
              } else if (event.type === "complete") {
                payload = event.result;
              } else if (event.type === "error") {
                throw new Error(event.message);
              }
            } catch (e) {
              // ignore parse errors for partial chunks
            }
          }
        }
      }
    }

    if (payload) {
      if (state.currentChat) state.currentChat.container._payload = payload;
      renderResearch(payload);
    }
  } catch (error) {
    if (error.name === 'AbortError') {
      if (state.currentChat) state.currentChat.statusText.textContent = "研究已终止";
    } else {
      console.error(error);
      if (state.currentChat) state.currentChat.statusText.textContent = "研究发生错误";
    }
  } finally {
    if (state.currentChat && state.currentChat.statusText.textContent !== "研究已终止" && state.currentChat.statusText.textContent !== "研究发生错误") {
      state.currentChat.thinking.classList.add("hidden");
    }
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
  } catch (error) {}
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
  nodes.drawerOverlay.click();
  runResearch();
});


nodes.online.addEventListener("change", () => {
  // Toggle doesn't need to show status text anymore
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
