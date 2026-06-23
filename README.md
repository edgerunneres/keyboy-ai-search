# KeyBoy AI Research 1.1

> 注意：这是基于 `keyboy-ai-search` 第一版复制出来的 1.1 升级版，不是 `keyboy-v2`。原 1.0 目录保持不变。

KeyBoy 1.1 的定位是“轻量 Deep Research 工作台 + 项目文件夹 + 独立研究历史 + 可验证证据链”。主流程仍然是输入问题后直接研究，但每次研究都会保存为一条独立任务，可恢复、删除、重跑、移动项目，并支持运行中取消。

## 快速运行

```bash
/Users/yupeilin/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m pip install -r requirements.txt
```

```bash
/Users/yupeilin/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m uvicorn keyboy.app:app --host 127.0.0.1 --port 8789
```

浏览器打开：

```text
http://127.0.0.1:8789
```

后端使用 FastAPI + Uvicorn 提供 API、静态页面和流式研究进度；核心检索、Agent 编排、在线源适配仍保留轻量 Python 实现。

## 1.1 新增能力

- SQLite 项目文件夹和研究任务历史。
- 可收起历史栏，支持恢复、删除、重跑、移动项目。
- 每次研究都是独立任务，同一问题重复研究不会自动合并。
- 任务状态：`queued`、`running`、`cancelled`、`failed`、`completed`。
- 运行中取消：后端在阶段之间检查取消状态，并保留已产生 trace。
- 证据抽屉增强：支持结论、原文片段、支持程度、读取状态、风险提示。
- 来源正文读取：网页、arXiv/DOI 页面、GitHub README、技术博客和基础 PDF 读取。
- 检索质量升级：URL/DOI/title 去重、chunk 级证据、来源多样性和轻量 rerank 指标。
- 后端生成追问，点击追问会创建新的独立研究任务。
- 30 条轻量评测集和指标定义，见 `data/eval_tasks.json` 与 `tools/run_eval_suite.py`。

## 启用真实大模型

默认情况下，系统会在没有 API Key 时使用 deterministic fallback，便于课堂现场稳定演示。要启用真正的大模型多智能体，请设置 OpenAI-compatible Chat Completions 环境变量：

```powershell
$env:KEYBOY_LLM_API_KEY="你的 API Key"
$env:KEYBOY_LLM_BASE_URL="https://api.openai.com/v1"
$env:KEYBOY_LLM_MODEL="你的模型名"
python -m uvicorn keyboy.app:app --host 127.0.0.1 --port 8789
```

### 使用阿里云百炼 / 通义千问

百炼平台兼容 OpenAI Chat Completions。只需要设置 `DASHSCOPE_API_KEY`，系统会自动使用：

- Base URL: `https://dashscope.aliyuncs.com/compatible-mode/v1`
- 默认模型：`qwen3.7-max`

```powershell
$env:DASHSCOPE_API_KEY="你的百炼 API Key"
python -m uvicorn keyboy.app:app --host 127.0.0.1 --port 8789
```

如需手动指定模型：

```powershell
$env:DASHSCOPE_API_KEY="你的百炼 API Key"
$env:KEYBOY_LLM_MODEL="qwen3.7-max"
python -m uvicorn keyboy.app:app --host 127.0.0.1 --port 8789
```

如果你更看重稳定生产能力和成本控制，也可以把 `KEYBOY_LLM_MODEL` 改为 `qwen3.6-plus`；如果需要固定复现实验结果，可以使用对应的快照版本，例如 `qwen3.7-max-2026-05-20`。

也可以使用安全启动脚本，避免把 Key 写进命令历史：

```powershell
powershell -ExecutionPolicy Bypass -File tools/start_bailian.ps1
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

```bash
# 运行测试
/Users/yupeilin/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s tests

# 运行前 5 条离线评测
/Users/yupeilin/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 tools/run_eval_suite.py --max-tasks 5

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
requirements.txt   Python Web 服务依赖
```
