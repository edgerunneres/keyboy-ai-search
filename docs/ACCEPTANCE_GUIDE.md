# KeyBoy 3.0 验收演示指南

## 1. 启动

```powershell
python -m keyboy.app --host 127.0.0.1 --port 8787
```

打开 `http://127.0.0.1:8787`。

## 2. 启用真实大模型

如果已经有大模型 API Key，先设置：

```powershell
$env:KEYBOY_LLM_API_KEY="你的 API Key"
$env:KEYBOY_LLM_BASE_URL="https://api.openai.com/v1"
$env:KEYBOY_LLM_MODEL="你的模型名"
```

没有 API Key 也能演示，但系统会明确显示本地 fallback。这一点在答辩时要说明：我们没有伪装调用大模型，而是做了真实可接入的 LLM Provider。

### 使用百炼平台

```powershell
$env:DASHSCOPE_API_KEY="你的百炼 API Key"
python -m keyboy.app --host 127.0.0.1 --port 8787
```

设置 `DASHSCOPE_API_KEY` 后，系统默认使用百炼 OpenAI 兼容接口和 `qwen3.6-max-preview`。如果更看重稳定生产能力、超长上下文和完整工具能力，可以手动切换到 `qwen3.6-plus`。不要把 API Key 写进仓库。

## 3. 推荐演示查询

### 查询一

`Agentic RAG GraphRAG LightRAG Self-RAG 最新研究怎么整合到课程项目`

展示重点：

- ResearchPlannerAgent 会拆解问题。
- OnlineDiscoveryAgent 会访问开放研究源。
- SynthesisAgent 输出研究答案。
- CriticAgent 输出风险提示。

### 查询二

`大模型多智能体在线研究系统应该如何设计`

展示重点：

- 系统不再是本地小数据库。
- 前端显示在线文档数、索引文档数、LLM 状态和 Agent Trace。
- 可以解释架构从本地搜索升级为 Deep Research。

### 查询三

`GraphRAG 和 LightRAG 相比普通 RAG 强在哪里`

展示重点：

- 说明 GraphRAG/LightRAG 的图结构思想。
- 说明当前项目已经预留图谱扩展方向。

## 4. 答辩表述

可以这样说：

> 第一版只是本地搜索原型。我们后来发现真正前沿的方向是 Agentic RAG 和 Deep Research，所以把系统重构为 LLM 多智能体在线研究架构。现在系统包含 ResearchPlanner、OnlineDiscovery、EvidenceRanker、Synthesis、Critic 等智能体，能访问 OpenAlex、Semantic Scholar、arXiv、Crossref 等在线开放数据源，并通过 OpenAI-compatible 接口接入真实大模型。没有 API Key 时系统会进入本地 fallback 并明确提示，不会伪装模型调用。这个设计既保证课堂演示稳定，也具备继续扩展为真实前沿系统的架构基础。

## 5. 验收看点

- 是否能运行。
- 是否有真实多智能体流程，而不是一个函数假装 Agent。
- 是否能在线获取数据。
- 是否能接入真实大模型。
- 是否有引用和证据。
- 是否有 CriticAgent 校验风险。
- 是否有清晰架构文档和测试。
