import unittest
import tempfile
from unittest.mock import patch

from fastapi.testclient import TestClient

import keyboy.app as app_module
from keyboy.agentic import AgenticKeyBoySystem, ResearchPlannerAgent
from keyboy.app import app
from keyboy.agents import KeyBoySystem
from keyboy.evaluator import evaluate
from keyboy.eval_suite import load_eval_tasks
from keyboy.llm import LLMProvider
from keyboy.online_sources import OnlineSourceClient
from keyboy.storage import load_eval_queries
from keyboy.task_store import TaskStore


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
        self.assertEqual(result.metrics["online_documents"], 0)
        self.assertGreaterEqual(result.metrics["indexed_documents"], 10)
        self.assertIn("ResearchPlannerAgent", [trace.name for trace in result.traces])
        self.assertIn("CriticAgent", [trace.name for trace in result.traces])
        self.assertFalse(result.metrics["llm_used"])

    def test_agentic_research_generates_decision_layer(self):
        agentic = AgenticKeyBoySystem()
        result = agentic.research("为什么用户会选择 KeyBoy 做前沿项目研究", online=False, include_local=True, limit=5)
        payload = result.to_dict()
        strategy_traces = [trace for trace in result.traces if trace.name == "StrategyAgent"]
        self.assertTrue(strategy_traces)
        self.assertEqual(strategy_traces[-1].status, "ok")
        self.assertTrue(payload["decision_brief"]["recommended_path"])
        self.assertGreaterEqual(payload["trust_score"]["score"], 1)
        self.assertTrue(payload["knowledge_map"]["concepts"])
        self.assertTrue(payload["next_questions"])
        self.assertGreaterEqual(len(payload["frontier_patterns"]), 5)

    def test_trace_error_is_visible_in_quality_risks(self):
        class BrokenStrategy:
            def advise(self, *args, **kwargs):
                from keyboy.agents import AgentResult
                from keyboy.models import AgentTrace
                return None, AgentTrace(name="StrategyAgent", status="error", message="失败：boom", duration_ms=1.0)

        agentic = AgenticKeyBoySystem()
        agentic.strategy_agent = BrokenStrategy()
        result = agentic.research("KeyBoy 课程设计如何答辩", online=False, include_local=True, limit=5)
        payload = result.to_dict()
        self.assertTrue(any(trace.status == "error" and trace.name == "StrategyAgent" for trace in result.traces))
        self.assertTrue(any("StrategyAgent" in risk for risk in payload["risks"]))
        self.assertTrue(payload["decision_brief"]["recommended_path"])

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
            self.assertEqual(provider.model, "qwen3.7-max")
            self.assertTrue(provider.enabled)

    def test_llm_source_plan_normalizes_to_online_sources(self):
        fallback = ["openalex", "semanticscholar", "arxiv", "crossref"]
        raw_sources = [
            "peer-reviewed papers from ACL and NeurIPS",
            "Microsoft Research publications and GitHub repositories for GraphRAG",
            "Crossref DOI metadata",
        ]
        sources = ResearchPlannerAgent._normalize_source_plan(raw_sources, fallback)
        self.assertEqual(sources, fallback)

    def test_online_source_default_mailto(self):
        with patch.dict("os.environ", {"OPENALEX_MAILTO": "", "CROSSREF_MAILTO": ""}, clear=False):
            client = OnlineSourceClient()
            self.assertEqual(client.openalex_mailto, "yup300737@gmail.com")
            self.assertEqual(client.crossref_mailto, "yup300737@gmail.com")

    def test_task_store_projects_move_and_cancel(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TaskStore(f"{tmpdir}/tasks.db")
            project = store.create_project("临时项目")
            task = store.create_task(project_id="default", query="同一个问题", source_config={"online": False})
            moved = store.move_task(task["id"], project["id"])
            self.assertEqual(moved["project_id"], project["id"])
            cancelled = store.cancel_task(task["id"])
            self.assertEqual(cancelled["status"], "cancelled")

    def test_task_store_archives_conversations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TaskStore(f"{tmpdir}/tasks.db")
            task = store.create_task(project_id="default", query="归档对话", source_config={"online": False})
            self.assertFalse(task["archived"])
            self.assertEqual(len(store.list_tasks(archived=False)), 1)
            self.assertEqual(len(store.list_tasks(archived=True)), 0)
            archived = store.archive_task(task["id"], archived=True)
            self.assertTrue(archived["archived"])
            self.assertEqual(len(store.list_tasks(archived=False)), 0)
            self.assertEqual(len(store.list_tasks(archived=True)), 1)
            restored = store.archive_task(task["id"], archived=False)
            self.assertFalse(restored["archived"])
            self.assertEqual(len(store.list_tasks(archived=False)), 1)

    def test_task_api_keeps_same_query_as_independent_tasks(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(app_module, "TASK_STORE", TaskStore(f"{tmpdir}/tasks.db")):
            client = TestClient(app)
            payload = {"query": "GraphRAG 课程设计验收要点", "project_id": "default", "online": False, "include_local": True, "limit": 3}
            first = client.post("/api/tasks", json=payload)
            second = client.post("/api/tasks", json=payload)
            self.assertEqual(first.status_code, 200)
            self.assertEqual(second.status_code, 200)
            first_task = first.json()["task"]
            second_task = second.json()["task"]
            self.assertNotEqual(first_task["id"], second_task["id"])
            self.assertEqual(first_task["status"], "completed")
            self.assertEqual(second_task["status"], "completed")
            self.assertTrue(first.json()["result"]["answer"])

    def test_conversation_archive_api(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(app_module, "TASK_STORE", TaskStore(f"{tmpdir}/tasks.db")):
            client = TestClient(app)
            response = client.post(
                "/api/tasks",
                json={"query": "对话归档接口", "project_id": "default", "online": False, "include_local": True, "limit": 3},
            )
            self.assertEqual(response.status_code, 200)
            task_id = response.json()["task"]["id"]
            self.assertEqual(len(client.get("/api/conversations").json()["conversations"]), 1)
            archived = client.patch(f"/api/conversations/{task_id}/archive", json={"archived": True})
            self.assertEqual(archived.status_code, 200)
            self.assertTrue(archived.json()["conversation"]["archived"])
            self.assertEqual(len(client.get("/api/conversations").json()["conversations"]), 0)
            self.assertEqual(len(client.get("/api/conversations?archived=true").json()["conversations"]), 1)
            unarchived = client.patch(f"/api/conversations/{task_id}/archive", json={"archived": False})
            self.assertEqual(unarchived.status_code, 200)
            self.assertFalse(unarchived.json()["conversation"]["archived"])

    def test_conversation_can_hold_multiple_research_tasks_and_rename(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(app_module, "TASK_STORE", TaskStore(f"{tmpdir}/tasks.db")):
            client = TestClient(app)
            first = client.post(
                "/api/tasks",
                json={"query": "GraphRAG 对话窗口第一问", "project_id": "default", "online": False, "include_local": True, "limit": 2},
            )
            self.assertEqual(first.status_code, 200)
            conversation_id = first.json()["task"]["conversation_id"]
            second = client.post(
                "/api/tasks",
                json={
                    "query": "GraphRAG 对话窗口第二问",
                    "project_id": "default",
                    "conversation_id": conversation_id,
                    "online": False,
                    "include_local": True,
                    "limit": 2,
                },
            )
            self.assertEqual(second.status_code, 200)
            restored = client.get(f"/api/conversations/{conversation_id}")
            self.assertEqual(restored.status_code, 200)
            self.assertEqual(len(restored.json()["conversation"]["tasks"]), 2)
            renamed = client.patch(f"/api/conversations/{conversation_id}", json={"title": "GraphRAG 连续研究"})
            self.assertEqual(renamed.status_code, 200)
            self.assertEqual(renamed.json()["conversation"]["title"], "GraphRAG 连续研究")

    def test_eval_suite_has_30_tasks(self):
        tasks = load_eval_tasks()
        counts = {}
        for task in tasks:
            counts[task["category"]] = counts.get(task["category"], 0) + 1
        self.assertEqual(len(tasks), 30)
        self.assertEqual(counts["技术选型"], 10)
        self.assertEqual(counts["论文/技术综述"], 10)
        self.assertEqual(counts["GitHub 项目调研"], 5)
        self.assertEqual(counts["课程设计/答辩问题"], 5)


if __name__ == "__main__":
    unittest.main()
