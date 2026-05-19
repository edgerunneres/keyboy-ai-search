import unittest
from unittest.mock import patch

from keyboy.agentic import AgenticKeyBoySystem
from keyboy.agents import KeyBoySystem
from keyboy.evaluator import evaluate
from keyboy.llm import LLMProvider
from keyboy.storage import load_eval_queries


class KeyBoyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.system = KeyBoySystem()
        cls.system.bootstrap()

    def test_index_bootstrap(self):
        self.assertIsNotNone(self.system.index)
        stats = self.system.index.stats()
        self.assertGreaterEqual(stats["documents"], 15)
        self.assertGreater(stats["vocabulary"], 100)

    def test_hybrid_search_finds_rrf(self):
        response = self.system.search("混合检索 BM25 RRF", mode="hybrid", limit=5)
        titles = [hit.document.title for hit in response.hits]
        self.assertIn("混合检索架构：BM25 与轻量语义向量的互补", titles[:3])
        self.assertTrue(response.summary)

    def test_semantic_query(self):
        response = self.system.search("怎么让课程设计搜索结果更准确", mode="hybrid", limit=5)
        joined = " ".join(hit.document.title for hit in response.hits[:5])
        self.assertTrue("检索" in joined or "评测" in joined or "重排" in joined)

    def test_evaluation_metrics(self):
        metrics = evaluate(self.system.index, load_eval_queries())
        self.assertGreaterEqual(metrics["recall_at_5"], 0.7)
        self.assertGreaterEqual(metrics["ndcg_at_5"], 0.6)

    def test_agentic_research_offline_pipeline(self):
        agentic = AgenticKeyBoySystem()
        result = agentic.research("GraphRAG LightRAG Agentic RAG 如何整合", online=False, include_local=True, limit=5)
        self.assertTrue(result.answer)
        self.assertGreaterEqual(result.metrics["indexed_documents"], 10)
        self.assertIn("ResearchPlannerAgent", [trace.name for trace in result.traces])
        self.assertIn("CriticAgent", [trace.name for trace in result.traces])
        self.assertFalse(result.metrics["llm_used"])

    def test_dashscope_defaults(self):
        with patch.dict(
            "os.environ",
            {
                "DASHSCOPE_API_KEY": "test-only",
                "KEYBOY_LLM_BASE_URL": "",
                "KEYBOY_LLM_MODEL": "",
                "KEYBOY_LLM_API_KEY": "",
                "OPENAI_API_KEY": "",
            },
            clear=False,
        ):
            provider = LLMProvider()
            self.assertEqual(provider.base_url, "https://dashscope.aliyuncs.com/compatible-mode/v1")
            self.assertEqual(provider.model, "qwen3.6-max-preview")
            self.assertTrue(provider.enabled)


if __name__ == "__main__":
    unittest.main()
