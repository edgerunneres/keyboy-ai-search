# test_search_refactored.py
# =========================================================================
# KeyBoy AI-Search 系统集成测试
# 覆盖范围：服务连通 → 配置管理 → 基础检索 → 深度研究 → 状态流 → 异常边界
# 测试框架：pytest
# 运行方式：pytest test_search_refactored.py -v
# =========================================================================
import pytest
import requests
import time
import os
import threading

# ---------- 全局配置 ----------
BASE_URL = "http://127.0.0.1:8787"
TIMEOUT = 10         # 普通接口超时
RESEARCH_TIMEOUT = 120  # 深度研究最长等待（涉及多轮 Agent + LLM）


# ==========================================================================
# 工具函数
# ==========================================================================

def get(path, params=None, timeout=TIMEOUT):
    """发起 GET 请求并返回 (response, json_data)"""
    resp = requests.get(f"{BASE_URL}{path}", params=params, timeout=timeout)
    return resp, resp.json() if resp.headers.get("Content-Type", "").startswith("application/json") else None


def post(path, payload=None, timeout=TIMEOUT):
    """发起 POST 请求并返回 (response, json_data)"""
    resp = requests.post(f"{BASE_URL}{path}", json=payload or {}, timeout=timeout)
    return resp, resp.json() if resp.headers.get("Content-Type", "").startswith("application/json") else None


# ==========================================================================
# 第一部分：服务连通性与基础设施 (S001)
# ==========================================================================

class TestServiceInfrastructure:
    """验证服务启动状态、健康检查与静态资源"""

    def test_s001_01_root_serves_html(self):
        """S001-01: 根路径应返回前端页面 (HTTP 200 + HTML)"""
        resp = requests.get(f"{BASE_URL}/", timeout=3)
        assert resp.status_code == 200, f"根路径返回 {resp.status_code}"
        assert "text/html" in resp.headers.get("Content-Type", ""), "根路径应返回 HTML"
        assert "KeyBoy" in resp.text, "页面内容缺少 KeyBoy 标识"

    def test_s001_02_health_check(self):
        """S001-02: /api/health 健康检查完整性"""
        resp, data = get("/api/health")
        assert resp.status_code == 200
        # 必须包含系统状态、索引统计、LLM 配置
        assert data.get("status") == "ok", "健康状态应为 ok"
        assert "stats" in data, "缺少索引统计 (stats)"
        stats = data["stats"]
        assert "documents" in stats, "stats 缺少 documents 字段"
        assert "vocabulary" in stats, "stats 缺少 vocabulary 字段"
        assert isinstance(stats["documents"], int) and stats["documents"] >= 0
        assert isinstance(stats["vocabulary"], int) and stats["vocabulary"] >= 0
        assert "llm" in data, "缺少 LLM 配置信息"
        assert "evaluation" in data, "缺少评测指标 (evaluation)"

    def test_s001_03_cors_preflight(self):
        """S001-03: OPTIONS 预检请求应返回正确的 CORS 头"""
        resp = requests.options(f"{BASE_URL}/api/health", timeout=3)
        assert resp.status_code == 204, f"OPTIONS 返回 {resp.status_code}，期望 204"
        assert resp.headers.get("Access-Control-Allow-Origin") == "*"
        allow_methods = resp.headers.get("Access-Control-Allow-Methods", "")
        assert "GET" in allow_methods and "POST" in allow_methods

    def test_s001_04_static_js_css(self):
        """S001-04: 静态资源 (JS/CSS) 可正常访问"""
        for path in ["/app.js", "/style.css"]:
            resp = requests.get(f"{BASE_URL}{path}", timeout=3)
            assert resp.status_code == 200, f"静态文件 {path} 返回 {resp.status_code}"
            assert len(resp.content) > 100, f"静态文件 {path} 内容过短，可能为空"

    def test_s001_05_nonexistent_path_404(self):
        """S001-05: 不存在的路径应返回 404"""
        resp = requests.get(f"{BASE_URL}/api/this_does_not_exist", timeout=3)
        assert resp.status_code == 404, f"不存在路径返回 {resp.status_code}，期望 404"


# ==========================================================================
# 第二部分：配置管理接口 (S002)
# ==========================================================================

class TestConfigManagement:
    """验证 LLM 模型配置与在线源配置的读写能力"""

    def test_s002_01_get_llm_config(self):
        """S002-01: 读取 LLM 配置"""
        resp, data = get("/api/config/llm")
        assert resp.status_code == 200
        # safe_config 应包含基本字段但不泄露完整 API Key
        assert "model" in data, "LLM 配置缺少 model"
        assert "base_url" in data, "LLM 配置缺少 base_url"

    def test_s002_02_post_llm_config(self):
        """S002-02: 写入 LLM 配置（百炼默认）"""
        payload = {
            "provider": "bailian",
            "api_key": "",
            "model": "qwen-plus",
            "base_url": "",
            "timeout": 30,
            "enable_thinking": False,
        }
        resp, data = post("/api/config/llm", payload)
        assert resp.status_code == 200
        assert data.get("status") == "ok", f"配置写入失败: {data}"
        assert "llm" in data, "返回缺少 llm 字段"
        # 验证回写的配置是否生效
        assert data["llm"]["model"] == "qwen-plus", "模型未正确设置为 qwen-plus"

    def test_s002_03_post_llm_config_custom_provider(self):
        """S002-03: 写入自定义 Provider 配置"""
        payload = {
            "provider": "custom",
            "base_url": "https://example.com/v1",
            "model": "my-custom-model",
            "api_key": "sk-test-key",
            "timeout": 60,
            "enable_thinking": True,
        }
        resp, data = post("/api/config/llm", payload)
        assert resp.status_code == 200
        assert data.get("status") == "ok"
        llm = data["llm"]
        assert llm["model"] == "my-custom-model"
        assert llm["base_url"] == "https://example.com/v1"

    def test_s002_04_get_sources_config(self):
        """S002-04: 读取在线源配置"""
        resp, data = get("/api/config/sources")
        assert resp.status_code == 200
        # 在线源配置应包含各学术源的设置
        assert isinstance(data, dict), "在线源配置应为字典"

    def test_s002_05_post_sources_config(self):
        """S002-05: 写入在线源配置"""
        payload = {
            "openalex_mailto": "test@example.com",
            "crossref_mailto": "test@example.com",
            "openalex_api_key": "test_key",
            "timeout": 10,
            "per_source_limit": 5,
        }
        resp, data = post("/api/config/sources", payload)
        assert resp.status_code == 200
        assert data.get("status") == "ok", f"在线源配置写入失败: {data}"
        assert "sources" in data, "返回缺少 sources 字段"

    def test_s002_06_post_unknown_endpoint_404(self):
        """S002-06: POST 到不存在的接口应返回 404"""
        resp = requests.post(f"{BASE_URL}/api/nonexistent", json={}, timeout=3)
        assert resp.status_code == 404

    def test_s002_07_post_llm_config_invalid_timeout(self):
        """S002-07: 超时参数为非数字时不应崩溃"""
        payload = {
            "provider": "bailian",
            "timeout": "not_a_number",
        }
        resp, data = post("/api/config/llm", payload)
        assert resp.status_code == 200, "非法超时参数导致服务崩溃"
        assert data.get("status") == "ok"

    def test_s002_08_post_llm_config_empty_body(self):
        """S002-08: 空 JSON body 不应导致异常"""
        resp, data = post("/api/config/llm", {})
        assert resp.status_code == 200
        assert data.get("status") == "ok"


# ==========================================================================
# 第三部分：基础检索接口 (S003)
# ==========================================================================

class TestBasicSearch:
    """验证 /api/search 基础检索（非 Agentic 模式）"""

    def test_s003_01_hybrid_search(self):
        """S003-01: 混合检索基本功能"""
        resp, data = get("/api/search", params={"q": "information retrieval", "limit": "3"})
        assert resp.status_code == 200
        assert "query" in data, "返回缺少 query 字段"
        assert data["query"] == "information retrieval"
        assert "hits" in data, "返回缺少 hits 字段"
        assert isinstance(data["hits"], list)
        assert "summary" in data, "返回缺少 summary 字段"
        assert "insights" in data, "返回缺少 insights 字段"
        assert "metrics" in data, "返回缺少 metrics 字段"
        assert "traces" in data, "返回缺少 traces 字段"

    def test_s003_02_search_result_structure(self):
        """S003-02: 检索结果单条结构完整性"""
        resp, data = get("/api/search", params={"q": "test query", "limit": "5"})
        assert resp.status_code == 200
        hits = data.get("hits", [])
        if len(hits) > 0:
            hit = hits[0]
            # 每条 hit 应包含核心字段
            assert "document" in hit, "hit 缺少 document"
            assert "score" in hit, "hit 缺少 score"
            assert "snippet" in hit, "hit 缺少 snippet"
            doc = hit["document"]
            assert "title" in doc, "document 缺少 title"
            assert "content" in doc, "document 缺少 content"
            assert "source" in doc, "document 缺少 source"
            assert "url" in doc, "document 缺少 url"
            # 分数应为非负数
            assert isinstance(hit["score"], (int, float)) and hit["score"] >= 0

    def test_s003_03_search_with_mode(self):
        """S003-03: 指定检索模式 (bm25/vector/hybrid)"""
        for mode in ["bm25", "hybrid"]:
            resp, data = get("/api/search", params={"q": "search", "mode": mode, "limit": "2"})
            assert resp.status_code == 200, f"模式 {mode} 请求失败"
            assert data["mode"] == mode, f"返回模式应为 {mode}"

    def test_s003_04_search_metrics(self):
        """S003-04: 检索指标字段校验"""
        resp, data = get("/api/search", params={"q": "metrics test"})
        metrics = data.get("metrics", {})
        assert "latency_ms" in metrics, "metrics 缺少 latency_ms"
        assert "result_count" in metrics, "metrics 缺少 result_count"
        assert isinstance(metrics["latency_ms"], (int, float))
        assert metrics["latency_ms"] >= 0, "延迟不能为负"

    def test_s003_05_search_traces(self):
        """S003-05: Agent 执行轨迹 (traces) 结构"""
        resp, data = get("/api/search", params={"q": "trace test"})
        traces = data.get("traces", [])
        assert isinstance(traces, list)
        if len(traces) > 0:
            t = traces[0]
            assert "name" in t, "trace 缺少 name"
            assert "status" in t, "trace 缺少 status"
            assert "message" in t, "trace 缺少 message"
            assert "duration_ms" in t, "trace 缺少 duration_ms"
            assert t["status"] in ("ok", "error"), f"未知 trace 状态: {t['status']}"


# ==========================================================================
# 第四部分：深度研究接口 (S004)
# ==========================================================================

class TestDeepResearch:
    """验证 /api/research Agentic 深度研究功能"""

    def test_s004_01_research_offline(self):
        """S004-01: 离线深度研究（仅本地知识）"""
        params = {"q": "test offline research", "online": "false", "include_local": "true", "limit": "3"}
        resp, data = get("/api/research", params=params, timeout=RESEARCH_TIMEOUT)
        assert resp.status_code == 200

        # ---- 核心字段完整性 ----
        assert "query" in data and data["query"] == "test offline research"
        assert "answer" in data, "缺少 answer 字段"
        assert isinstance(data["answer"], str)
        assert "plan" in data, "缺少研究计划 (plan)"
        assert "citations" in data, "缺少引用列表 (citations)"
        assert "findings" in data, "缺少发现列表 (findings)"
        assert "risks" in data, "缺少风险列表 (risks)"
        assert "metrics" in data, "缺少指标 (metrics)"
        assert "traces" in data, "缺少执行轨迹 (traces)"
        assert "decision_brief" in data, "缺少决策简报 (decision_brief)"
        assert "trust_score" in data, "缺少可信度评分 (trust_score)"
        assert "knowledge_map" in data, "缺少知识地图 (knowledge_map)"
        assert "next_questions" in data, "缺少追问推荐 (next_questions)"
        assert "frontier_patterns" in data, "缺少前沿模式 (frontier_patterns)"

        # ---- 离线限制校验 ----
        metrics = data["metrics"]
        assert metrics.get("online_documents", 0) == 0, "离线模式不应有在线文档"

    def test_s004_02_research_plan_structure(self):
        """S004-02: 研究计划字段结构"""
        params = {"q": "plan structure test", "online": "false", "limit": "2"}
        resp, data = get("/api/research", params=params, timeout=RESEARCH_TIMEOUT)
        plan = data.get("plan", {})
        assert "intent" in plan, "plan 缺少 intent（意图）"
        assert "subqueries" in plan, "plan 缺少 subqueries（子查询）"
        assert "source_plan" in plan, "plan 缺少 source_plan（源规划）"
        assert "required_evidence" in plan, "plan 缺少 required_evidence（所需证据）"
        assert "llm_used" in plan, "plan 缺少 llm_used 标记"
        assert isinstance(plan["subqueries"], list)
        assert isinstance(plan["required_evidence"], list)

    def test_s004_03_research_traces_multi_agent(self):
        """S004-03: 深度研究应产生多个 Agent 的执行轨迹"""
        params = {"q": "multi agent trace test", "online": "false", "limit": "2"}
        resp, data = get("/api/research", params=params, timeout=RESEARCH_TIMEOUT)
        traces = data.get("traces", [])
        assert len(traces) >= 5, f"深度研究至少需要5个Agent阶段，实际只有 {len(traces)} 个"

        agent_names = [t["name"] for t in traces]
        # 核心 Agent 必须出现
        expected_agents = ["ResearchPlannerAgent", "OnlineDiscoveryAgent", "CleanAgent", "IndexAgent"]
        for name in expected_agents:
            assert name in agent_names, f"缺少关键 Agent: {name}"

    def test_s004_04_research_metrics_completeness(self):
        """S004-04: 深度研究指标完整性"""
        params = {"q": "metrics completeness", "online": "false", "limit": "2"}
        resp, data = get("/api/research", params=params, timeout=RESEARCH_TIMEOUT)
        metrics = data.get("metrics", {})

        required_fields = ["latency_ms", "online_documents", "indexed_documents",
                           "result_count", "llm_used", "llm_model"]
        for f in required_fields:
            assert f in metrics, f"metrics 缺少 {f}"

        assert isinstance(metrics["latency_ms"], (int, float)) and metrics["latency_ms"] > 0
        assert isinstance(metrics["online_documents"], int)
        assert isinstance(metrics["indexed_documents"], int)

    def test_s004_05_research_frontier_patterns(self):
        """S004-05: 前沿技术模式列表应非空且结构正确"""
        params = {"q": "frontier test", "online": "false", "limit": "2"}
        resp, data = get("/api/research", params=params, timeout=RESEARCH_TIMEOUT)
        patterns = data.get("frontier_patterns", [])
        assert len(patterns) > 0, "前沿模式列表为空"
        for p in patterns:
            assert "name" in p, "前沿模式缺少 name"
            assert "strength" in p, "前沿模式缺少 strength"
            assert "integrated_as" in p, "前沿模式缺少 integrated_as"


# ==========================================================================
# 第五部分：实时状态与指标接口 (S005)
# ==========================================================================

class TestStatusAndMetrics:
    """验证研究过程中的状态流和系统指标"""

    def test_s005_01_status_endpoint(self):
        """S005-01: /api/status 基本可用性"""
        resp, data = get("/api/status")
        assert resp.status_code == 200
        assert "status" in data, "状态接口缺少 status 字段"
        assert "stream_buffer" in data, "状态接口缺少 stream_buffer 字段"

    def test_s005_02_status_during_research(self):
        """S005-02: 研究进行期间 /api/status 应返回非空状态"""
        statuses_seen = []

        def poll_status():
            """后台线程持续轮询状态"""
            end_time = time.time() + 15
            while time.time() < end_time:
                try:
                    r = requests.get(f"{BASE_URL}/api/status", timeout=2)
                    if r.status_code == 200:
                        s = r.json().get("status", "")
                        if s:
                            statuses_seen.append(s)
                except Exception:
                    pass
                time.sleep(0.3)

        # 在后台线程轮询，主线程发起研究
        poller = threading.Thread(target=poll_status, daemon=True)
        poller.start()
        try:
            requests.get(
                f"{BASE_URL}/api/research",
                params={"q": "status polling test", "online": "false", "limit": "2"},
                timeout=RESEARCH_TIMEOUT
            )
        except Exception:
            pass
        poller.join(timeout=3)

        # 研究期间至少应看到一些状态更新
        assert len(statuses_seen) > 0, "研究期间未观测到任何状态更新"

    def test_s005_03_metrics_endpoint(self):
        """S005-03: /api/metrics 系统指标"""
        resp, data = get("/api/metrics")
        assert resp.status_code == 200
        assert "stats" in data, "metrics 缺少 stats"
        assert "evaluation" in data, "metrics 缺少 evaluation"
        assert "traces" in data, "metrics 缺少 traces"
        assert isinstance(data["traces"], list)


# ==========================================================================
# 第六部分：异常与边界测试 (S006)
# ==========================================================================

class TestEdgeCases:
    """验证系统的健壮性与边界处理"""

    def test_s006_01_empty_query_search(self):
        """S006-01: 空查询检索不应崩溃"""
        resp, data = get("/api/search", params={"q": ""})
        assert resp.status_code == 200, "空查询导致服务崩溃"
        assert "hits" in data

    def test_s006_02_empty_query_research(self):
        """S006-02: 空查询深度研究不应崩溃"""
        resp, data = get("/api/research", params={"q": "", "online": "false", "limit": "2"},
                         timeout=RESEARCH_TIMEOUT)
        assert resp.status_code == 200, "空查询深度研究导致服务崩溃"
        assert "answer" in data

    def test_s006_03_very_long_query(self):
        """S006-03: 超长查询 (1500+ 字符) 不应崩溃"""
        long_query = "artificial intelligence " * 100  # ~2400 字符
        resp, data = get("/api/search", params={"q": long_query, "limit": "2"})
        assert resp.status_code == 200, "超长查询导致服务崩溃"
        assert "hits" in data

    def test_s006_04_special_characters_query(self):
        """S006-04: 特殊字符查询"""
        for q in ["@#$%^&*()", "SELECT * FROM users", "<script>alert(1)</script>", "中文测试查询"]:
            resp, data = get("/api/search", params={"q": q, "limit": "2"})
            assert resp.status_code == 200, f"特殊字符 '{q[:20]}' 导致服务崩溃"

    def test_s006_05_invalid_limit(self):
        """S006-05: 非法 limit 参数"""
        # limit 为 0
        resp, data = get("/api/search", params={"q": "test", "limit": "0"})
        assert resp.status_code == 200

    def test_s006_06_concurrent_requests(self):
        """S006-06: 并发请求压力测试 (5 个并发)"""
        results = []
        errors = []

        def do_request(i):
            try:
                r = requests.get(
                    f"{BASE_URL}/api/search",
                    params={"q": f"concurrent test {i}", "limit": "2"},
                    timeout=TIMEOUT
                )
                results.append(r.status_code)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=do_request, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=TIMEOUT + 5)

        assert len(errors) == 0, f"并发请求出现错误: {errors}"
        assert all(s == 200 for s in results), f"部分请求失败: {results}"

    def test_s006_07_research_online_false_string_variants(self):
        """S006-07: online 参数的各种 falsy 写法均应生效"""
        for val in ["false", "False", "0", "no"]:
            resp, data = get("/api/research",
                             params={"q": "falsy test", "online": val, "limit": "2"},
                             timeout=RESEARCH_TIMEOUT)
            assert resp.status_code == 200
            assert data["metrics"]["online_documents"] == 0, \
                f"online={val} 但仍查到在线文档"


# ==========================================================================
# 第七部分：响应性能基准 (S007)
# ==========================================================================

class TestPerformanceBenchmarks:
    """验证关键接口的响应时间在合理范围内"""

    def test_s007_01_health_latency(self):
        """S007-01: /api/health 响应时间应 < 2s"""
        start = time.time()
        resp = requests.get(f"{BASE_URL}/api/health", timeout=5)
        elapsed = time.time() - start
        assert resp.status_code == 200
        assert elapsed < 2.0, f"健康检查耗时 {elapsed:.2f}s，超过 2s 基准"

    def test_s007_02_search_latency(self):
        """S007-02: 基础检索响应时间应 < 3s"""
        start = time.time()
        resp = requests.get(
            f"{BASE_URL}/api/search",
            params={"q": "latency benchmark", "limit": "5"},
            timeout=5
        )
        elapsed = time.time() - start
        assert resp.status_code == 200
        assert elapsed < 3.0, f"基础检索耗时 {elapsed:.2f}s，超过 3s 基准"

    def test_s007_03_static_file_latency(self):
        """S007-03: 静态文件响应时间应 < 500ms"""
        start = time.time()
        resp = requests.get(f"{BASE_URL}/style.css", timeout=3)
        elapsed = time.time() - start
        assert resp.status_code == 200
        assert elapsed < 0.5, f"静态文件耗时 {elapsed:.3f}s，超过 500ms 基准"