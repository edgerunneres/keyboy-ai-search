# KeyBoy 智能专业搜索引擎

KeyBoy 是一个面向软件工程课程设计验收的 LLM 多智能体在线研究系统。它从原计划书中的“定向爬取 + TF-IDF + 简单总结”升级为“Agentic RAG / Deep Research 工作流 + 在线论文/开放学术源获取 + LLM 规划与证据合成 + 可解释检索 + 批判校验”的完整可运行系统。

## 快速运行

```powershell
python -m keyboy.app --host 127.0.0.1 --port 8787
```

浏览器打开：

```text
http://127.0.0.1:8787
```

如果本机没有额外 Python 依赖，也可以直接运行。本项目核心功能只使用 Python 标准库。

## 启用真实大模型

默认情况下，系统会在没有 API Key 时使用 deterministic fallback，便于课堂现场稳定演示。要启用真正的大模型多智能体，请设置 OpenAI-compatible Chat Completions 环境变量：

```powershell
$env:KEYBOY_LLM_API_KEY="你的 API Key"
$env:KEYBOY_LLM_BASE_URL="https://api.openai.com/v1"
$env:KEYBOY_LLM_MODEL="你的模型名"
python -m keyboy.app --host 127.0.0.1 --port 8787
```

## 亮点

- Agentic Research：规划、在线发现、清洗、索引、证据排序、合成、批判校验全流程。
- 在线大数据获取：接入 OpenAlex、Semantic Scholar、arXiv、Crossref 等开放学术源。
- LLM 多智能体：ResearchPlannerAgent、OnlineDiscoveryAgent、EvidenceRankerAgent、SynthesisAgent、CriticAgent 等协作。
- OpenAI-compatible 模型接口：可接入任意兼容 `/chat/completions` 的大模型服务。
- 混合检索：BM25 关键词相关性 + 哈希语义向量相似度，作为在线证据排序底座。
- RRF 融合：借鉴工业搜索系统的 Reciprocal Rank Fusion，把词法与语义排序稳定融合。
- 可信输出：答案附证据来源，CriticAgent 明确指出无模型、证据不足、来源单一等风险。
- 可评测：内置测试集，输出 Recall@5、nDCG@5 与平均查询耗时。
- 课程交付友好：包含设计文档、迭代说明、测试脚本和可直接演示前端。

## 常用命令

```powershell
# 运行测试
python -m unittest discover -s tests

# 命令行检索
python -m keyboy.cli search "混合检索 RRF 为什么比 TF-IDF 更强"

# Agentic Research，默认访问在线源
python -m keyboy.cli research "Agentic RAG GraphRAG LightRAG Self-RAG 最新研究怎么整合"

# 只使用本地证据，适合无网络演示
python -m keyboy.cli research "GraphRAG LightRAG Agentic RAG 如何整合" --offline

# 查看评测指标
python -m keyboy.cli evaluate
```

## 目录结构

```text
keyboy/             后端、检索核心、LLM 多智能体、在线源适配器
web/                前端搜索工作台
data/               演示知识库与评测集
docs/               迭代说明、设计说明、验收材料
tests/              单元测试与质量验证
tools/              文档生成工具
```
