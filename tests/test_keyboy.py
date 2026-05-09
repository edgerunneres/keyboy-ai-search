import unittest

from keyboy.agents import KeyBoySystem
from keyboy.evaluator import evaluate
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


if __name__ == "__main__":
    unittest.main()

