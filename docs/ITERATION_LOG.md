# KeyBoy 3.0 修改迭代说明

## 1. 为什么重构

上一版 KeyBoy 已经比原计划书更强，但本质仍然是本地混合检索原型：本地 JSON 语料、BM25、轻量语义向量、抽取式摘要。它适合课程演示，却不符合“真正的大模型多智能体系统”和“在线大数据获取”的目标。

KeyBoy 3.0 因此进行了架构重构：主链路从 `/api/search` 切换为 `/api/research`，系统从本地搜索升级为 Agentic RAG / Deep Research。

## 2. 核心架构变化

| 维度 | 旧版本 | KeyBoy 3.0 |
| --- | --- | --- |
| 数据来源 | 本地 JSON 为主 | OpenAlex、Semantic Scholar、arXiv、Crossref 在线源 + 本地兜底 |
| 智能体 | 工程模块化 Agent | ResearchPlanner、OnlineDiscovery、EvidenceRanker、Synthesis、Critic 等研究 Agent |
| LLM | 未调用真实大模型 | OpenAI-compatible Chat Completions 抽象，可接入任意兼容模型 |
| 输出 | 搜索结果 + 摘要 | 研究计划 + 在线证据 + 带引用答案 + 风险校验 |
| 前端 | 搜索工作台 | Agentic Deep Research 控制台 |
| 可信度 | 分数解释 | 引用、来源多样性、CriticAgent 风险提示 |

## 3. 新增文件

- `keyboy/llm.py`：OpenAI-compatible LLM Provider。
- `keyboy/online_sources.py`：OpenAlex、Semantic Scholar、arXiv、Crossref 适配器。
- `keyboy/agentic.py`：多智能体研究流水线。

## 4. 新增智能体

- `ResearchPlannerAgent`：问题规划和子查询拆分。
- `OnlineDiscoveryAgent`：访问在线开放研究源。
- `EvidenceRankerAgent`：对在线证据建立索引并排序。
- `SynthesisAgent`：基于证据生成答案；有 API Key 时调用真实 LLM。
- `CriticAgent`：检查 LLM 状态、证据数量、来源多样性和风险。

## 5. 模型说明

当前仓库不内置任何商业模型，也不会假装已经调用了大模型。真实 LLM 通过环境变量配置：

```powershell
$env:KEYBOY_LLM_API_KEY="你的 API Key"
$env:KEYBOY_LLM_BASE_URL="https://api.openai.com/v1"
$env:KEYBOY_LLM_MODEL="你的模型名"
```

没有 API Key 时，系统自动 fallback，并在前端和 API 返回中标明 `llm_used=false`。

## 6. 前沿参考

- GraphRAG: From Local to Global, Microsoft Research, 2024。
- LightRAG: Simple and Fast Retrieval-Augmented Generation, 2024。
- Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection, 2023。
- Agentic RAG / Deep Research 系列开源实践：强调规划、搜索、阅读、合成、引用和可追踪。
- AutoGen / LangGraph：代表性多智能体编排框架，启发本项目的 Agent Trace 和模块化工作流。

## 7. 当前边界

- 真实 LLM 需要用户提供 API Key。
- 当前在线源聚焦开放学术数据，不直接调用商业搜索引擎。
- 图谱能力已在设计中预留，但尚未实现完整实体图和社区摘要。
- 本地 fallback 是演示稳定性的保障，不代表最终形态。

