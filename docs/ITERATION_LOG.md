# KeyBoy 修改迭代说明

本文记录相对原《KeyBoy搜索引擎软件项目开发计划.docx》的升级内容。原文档强调“定向爬取 + 多智能体 + TF-IDF + 本地 JSON”，增强版保留课程设计可控、可演示、低部署成本的优点，同时把算法、工程、质量和验收表达全部提升一档。

## 1. 产品定位升级

原定位：单机本地运行的专业领域搜索工具，满足课程实训基本要求。

升级后定位：面向软件工程、人工智能、信息检索等专业知识的智能搜索工作台，具备数据采集、清洗、索引、混合检索、智能摘要、可解释评分、质量评测和演示指标闭环。

改动理由：课程验收不只看功能“能不能跑”，还看是否体现软件工程思维、技术先进性和可验证成果。

## 2. 检索算法迭代

原方案：倒排索引 + TF-IDF。

升级方案：

- BM25 替代基础 TF-IDF，提升长短文档归一化能力。
- 轻量哈希语义向量用于同义表达、长问题和概念相似召回。
- RRF 融合 BM25 与语义排序，避免不同检索器分数不可比。
- 查询画像自适应权重：短技术词偏关键词，长问句偏语义。
- 二阶段重排：综合标题覆盖、正文覆盖、新鲜度等信号。
- 每条结果输出 BM25、语义、RRF、重排分数，形成可解释证据。

参考经验：Elasticsearch 文档指出 RRF 可将具有不同相关性指标的多个结果集合并为单一结果集，并且不同指标无需同尺度；OpenSearch 的混合检索方案也强调将关键词检索与神经/语义检索结合并进行分数归一化；BEIR 论文表明 BM25 是强基线，重排与 late-interaction 方法在零样本检索中表现突出但成本更高，因此本项目采用低成本可落地的混合召回与轻量重排。

## 3. 多智能体体系升级

原方案：CrawlAgent、CleanAgent、IndexAgent、SearchAgent 四个智能体。

升级方案：

- CrawlAgent：合规采集、本地语料加载、可选网页抓取。
- CleanAgent：文本标准化、去重、低质量内容过滤。
- IndexAgent：构建 BM25 索引、语义向量索引、元数据索引。
- SearchAgent：执行检索、融合排序、过滤与解释。
- InsightAgent：生成抽取式摘要和查询洞察。
- EvalAgent：运行离线评测，输出 Recall@5、nDCG@5、平均耗时。

改动理由：新增 InsightAgent 和 EvalAgent 后，系统从“能搜”升级为“能解释、能证明质量、能验收”。

## 4. 前端体验升级

原方案：搜索框 + 结果列表 + 简单摘要。

升级方案：

- 左侧显示知识库规模、来源过滤、主题过滤和演示查询。
- 中间显示搜索模式切换、智能摘要、结果列表和分数解释。
- 右侧显示查询画像、Agent Trace 和质量指标。
- 支持 Hybrid、BM25、Semantic 三种模式即时对比。

改动理由：验收现场要让老师快速看到系统能力边界，前端需要把算法、指标和流水线透明展示出来。

## 5. 数据与部署升级

原方案：依赖爬取指定 3 到 5 个网站。

升级方案：

- 内置可演示专业知识库，避免现场网络、反爬、网站结构变化导致演示失败。
- 保留合规爬虫模块，支持 robots.txt、User-Agent、请求间隔、HTML 文本抽取。
- 核心代码仅依赖 Python 标准库，老师电脑可直接运行。
- 数据使用 JSON，便于检查、修改和扩展。

改动理由：课程设计应展示真实工程风险控制。演示稳定性优先于现场实时爬网。

## 6. 质量保证升级

原方案：人工测试为主，要求响应时间小于 3 秒。

升级方案：

- 使用 `unittest` 覆盖索引构建、混合检索、语义查询、摘要和评测。
- 内置评测集，自动计算 Recall@5、nDCG@5、平均查询耗时。
- API 提供 `/api/health`、`/api/search`、`/api/metrics`，便于接口测试。
- 前端展示响应时间和评测指标，形成质量闭环。

## 7. 文档交付升级

新增交付物：

- `README.md`：运行说明与亮点。
- `docs/ITERATION_LOG.md`：修改迭代说明。
- `docs/SYSTEM_DESIGN.md`：系统架构、接口、算法与测试设计。
- `docs/ACCEPTANCE_GUIDE.md`：验收演示脚本与评分要点。
- `KeyBoy搜索引擎课程设计增强版说明.docx`：可提交给老师的增强版说明文档。

## 8. 后续可扩展方向

- 接入真实 embedding 模型和 FAISS、Milvus、Elasticsearch、OpenSearch 等向量/全文检索组件。
- 增加主题包机制：每个领域维护独立站点配置、清洗规则、评测查询。
- 增加用户反馈学习：将点击、收藏、纠错作为排序优化信号。
- 增加文档导入：支持 PDF、DOCX、Markdown 批量入库。
- 增加报告生成：把查询结果和摘要一键导出为课程报告。

## 参考来源

- Elasticsearch Reciprocal Rank Fusion: https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion
- OpenSearch Hybrid Search: https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/index/
- Faiss Documentation: https://faiss.ai/
- BEIR: A Heterogeneous Benchmark for Zero-shot Evaluation of Information Retrieval Models: https://arxiv.org/abs/2104.08663
