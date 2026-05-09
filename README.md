# KeyBoy 智能专业搜索引擎

KeyBoy 是一个面向软件工程课程设计验收的垂直领域搜索引擎原型。它从原计划书中的“定向爬取 + TF-IDF + 简单总结”升级为“多智能体流水线 + BM25 + 轻量语义向量 + RRF 融合排序 + 可解释摘要 + 评测面板”的完整可运行系统。

## 快速运行

```powershell
python -m keyboy.app --host 127.0.0.1 --port 8787
```

浏览器打开：

```text
http://127.0.0.1:8787
```

如果本机没有额外 Python 依赖，也可以直接运行。本项目核心功能只使用 Python 标准库。

## 亮点

- 混合检索：BM25 关键词相关性 + 哈希语义向量相似度。
- RRF 融合：借鉴工业搜索系统的 Reciprocal Rank Fusion，把词法与语义排序稳定融合。
- 查询意图自适应：长问题偏语义检索，短技术词偏精确匹配。
- 二阶段重排：综合标题覆盖、关键词覆盖、时间新鲜度和来源质量。
- 可解释搜索：每条结果展示 BM25、语义、融合、重排分数及命中原因。
- 智能摘要：基于 Top-K 结果生成面向查询的抽取式总结，并保留来源线索。
- 多智能体：CrawlAgent、CleanAgent、IndexAgent、SearchAgent、InsightAgent、EvalAgent 协同运行。
- 可评测：内置测试集，输出 Recall@5、nDCG@5 与平均查询耗时。
- 课程交付友好：包含设计文档、迭代说明、测试脚本和可直接演示前端。

## 常用命令

```powershell
# 运行测试
python -m unittest discover -s tests

# 命令行检索
python -m keyboy.cli search "混合检索 RRF 为什么比 TF-IDF 更强"

# 查看评测指标
python -m keyboy.cli evaluate
```

## 目录结构

```text
keyboy/             后端、检索核心、多智能体
web/                前端搜索工作台
data/               演示知识库与评测集
docs/               迭代说明、设计说明、验收材料
tests/              单元测试与质量验证
tools/              文档生成工具
```

