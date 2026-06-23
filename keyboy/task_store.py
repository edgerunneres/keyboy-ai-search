from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DEFAULT_DB_PATH = DATA_DIR / "keyboy_tasks.db"

DEFAULT_PROJECTS = [
    ("default", "默认项目"),
    ("course-defense", "课程设计答辩"),
    ("graphrag-research", "GraphRAG 调研"),
    ("competitor-analysis", "竞品分析"),
    ("custom", "自定义项目"),
]

TASK_STATUSES = {"queued", "running", "cancelled", "failed", "completed"}
TERMINAL_STATUSES = {"cancelled", "failed", "completed"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def task_id() -> str:
    return uuid.uuid4().hex


def conversation_title(query: str) -> str:
    title = " ".join((query or "").strip().split())
    if not title:
        return "新研究对话"
    return title[:28] + ("..." if len(title) > 28 else "")


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


class TaskStore:
    def __init__(self, db_path: Path | str | None = None) -> None:
        configured = os.getenv("KEYBOY_TASK_DB_PATH")
        self.db_path = Path(db_path or configured or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def ensure_schema(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    archived_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS research_tasks (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    conversation_id TEXT,
                    query TEXT NOT NULL,
                    answer TEXT NOT NULL DEFAULT '',
                    citations_json TEXT NOT NULL DEFAULT '[]',
                    traces_json TEXT NOT NULL DEFAULT '[]',
                    risks_json TEXT NOT NULL DEFAULT '[]',
                    metrics_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL,
                    model TEXT NOT NULL DEFAULT '',
                    source_config_json TEXT NOT NULL DEFAULT '{}',
                    origin_task_id TEXT,
                    error_message TEXT NOT NULL DEFAULT '',
                    archived_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
                """
            )
            self._migrate_schema(conn)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_project_created ON research_tasks(project_id, created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_conversation_created ON research_tasks(conversation_id, created_at ASC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON research_tasks(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at DESC)")
            self._seed_projects(conn)

    def _migrate_schema(self, conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(research_tasks)").fetchall()}
        if "archived_at" not in columns:
            conn.execute("ALTER TABLE research_tasks ADD COLUMN archived_at TEXT")
        if "conversation_id" not in columns:
            conn.execute("ALTER TABLE research_tasks ADD COLUMN conversation_id TEXT")
        self._migrate_conversations(conn)

    def _migrate_conversations(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            """
            SELECT *
            FROM research_tasks
            WHERE conversation_id IS NULL OR conversation_id = ''
            ORDER BY created_at ASC
            """
        ).fetchall()
        for row in rows:
            conn.execute(
                """
                INSERT OR IGNORE INTO conversations(id, title, archived_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    conversation_title(row["query"]),
                    row["archived_at"],
                    row["created_at"],
                    row["updated_at"],
                ),
            )
            conn.execute("UPDATE research_tasks SET conversation_id = ? WHERE id = ?", (row["id"], row["id"]))

        missing = conn.execute(
            """
            SELECT t.conversation_id, MIN(t.query) AS query, MIN(t.created_at) AS created_at, MAX(t.updated_at) AS updated_at
            FROM research_tasks t
            LEFT JOIN conversations c ON c.id = t.conversation_id
            WHERE t.conversation_id IS NOT NULL AND t.conversation_id != '' AND c.id IS NULL
            GROUP BY t.conversation_id
            """
        ).fetchall()
        for row in missing:
            conn.execute(
                """
                INSERT OR IGNORE INTO conversations(id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    row["conversation_id"],
                    conversation_title(row["query"]),
                    row["created_at"] or now_iso(),
                    row["updated_at"] or now_iso(),
                ),
            )

    def _seed_projects(self, conn: sqlite3.Connection) -> None:
        stamp = now_iso()
        for project_id, name in DEFAULT_PROJECTS:
            conn.execute(
                """
                INSERT OR IGNORE INTO projects(id, name, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (project_id, name, stamp, stamp),
            )

    @staticmethod
    def project_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_projects(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY created_at ASC").fetchall()
        return [self.project_row(row) for row in rows]

    def create_project(self, name: str) -> dict[str, Any]:
        name = name.strip() or "新项目"
        stamp = now_iso()
        project_id = task_id()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO projects(id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (project_id, name, stamp, stamp),
            )
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return self.project_row(row)

    def update_project(self, project_id: str, name: str) -> dict[str, Any] | None:
        name = name.strip()
        if not name:
            return self.get_project(project_id)
        with self.connect() as conn:
            conn.execute("UPDATE projects SET name = ?, updated_at = ? WHERE id = ?", (name, now_iso(), project_id))
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return self.project_row(row) if row else None

    def delete_project(self, project_id: str) -> bool:
        if project_id == "default":
            return False
        with self.connect() as conn:
            existing = conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
            if not existing:
                return False
            conn.execute("UPDATE research_tasks SET project_id = ?, updated_at = ? WHERE project_id = ?", ("default", now_iso(), project_id))
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        return True

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return self.project_row(row) if row else None

    @staticmethod
    def conversation_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "title": row["title"],
            "archived_at": row["archived_at"],
            "archived": bool(row["archived_at"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def create_conversation(self, title: str = "", *, first_query: str = "") -> dict[str, Any]:
        stamp = now_iso()
        conversation_id = task_id()
        name = title.strip() or conversation_title(first_query)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO conversations(id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (conversation_id, name, stamp, stamp),
            )
            row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        return self.conversation_row(row)

    def get_conversation(self, conversation_id: str, *, include_tasks: bool = False) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        if not row:
            return None
        conversation = self.conversation_row(row)
        if include_tasks:
            conversation["tasks"] = self.list_tasks(conversation_id=conversation_id, archived=None, include_result=True)
        return conversation

    def list_conversations(self, *, archived: bool | None = False) -> list[dict[str, Any]]:
        sql = "SELECT * FROM conversations"
        clauses: list[str] = []
        if archived is True:
            clauses.append("archived_at IS NOT NULL")
        elif archived is False:
            clauses.append("archived_at IS NULL")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY updated_at DESC"
        with self.connect() as conn:
            rows = conn.execute(sql).fetchall()
            conversations = [self.conversation_row(row) for row in rows]
            for item in conversations:
                task_rows = conn.execute(
                    """
                    SELECT *
                    FROM research_tasks
                    WHERE conversation_id = ?
                    ORDER BY created_at DESC
                    """,
                    (item["id"],),
                ).fetchall()
                tasks = [self.task_row(row, include_result=False) for row in task_rows]
                item["task_count"] = len(tasks)
                item["latest_task"] = tasks[0] if tasks else None
                item["evidence_count"] = sum(task.get("evidence_count", 0) for task in tasks)
                statuses = {task.get("status") for task in tasks}
                if "running" in statuses:
                    item["status"] = "running"
                elif "queued" in statuses:
                    item["status"] = "queued"
                elif "failed" in statuses:
                    item["status"] = "failed"
                elif "cancelled" in statuses and "completed" not in statuses:
                    item["status"] = "cancelled"
                elif tasks:
                    item["status"] = "completed"
                else:
                    item["status"] = "empty"
                item["running_task_ids"] = [task["id"] for task in tasks if task.get("status") in {"queued", "running"}]
        return conversations

    def update_conversation(self, conversation_id: str, *, title: str | None = None) -> dict[str, Any] | None:
        updates = ["updated_at = ?"]
        params: list[Any] = [now_iso()]
        if title is not None:
            name = title.strip()
            if name:
                updates.append("title = ?")
                params.append(name[:80])
        params.append(conversation_id)
        with self.connect() as conn:
            conn.execute(f"UPDATE conversations SET {', '.join(updates)} WHERE id = ?", params)
            row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        return self.conversation_row(row) if row else None

    def touch_conversation(self, conversation_id: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now_iso(), conversation_id))

    def archive_conversation(self, conversation_id: str, archived: bool = True) -> dict[str, Any] | None:
        archived_at = now_iso() if archived else None
        stamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                "UPDATE conversations SET archived_at = ?, updated_at = ? WHERE id = ?",
                (archived_at, stamp, conversation_id),
            )
            row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        return self.conversation_row(row) if row else None

    def delete_conversation(self, conversation_id: str) -> bool:
        with self.connect() as conn:
            existing = conn.execute("SELECT id FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
            if not existing:
                return False
            conn.execute("DELETE FROM research_tasks WHERE conversation_id = ?", (conversation_id,))
            cur = conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        return cur.rowcount > 0

    def create_task(
        self,
        *,
        project_id: str,
        query: str,
        source_config: dict[str, Any] | None = None,
        origin_task_id: str | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        if not self.get_project(project_id):
            project_id = "default"
        stamp = now_iso()
        new_id = task_id()
        if conversation_id:
            conversation = self.get_conversation(conversation_id)
            if not conversation:
                conversation = self.create_conversation(first_query=query)
                conversation_id = conversation["id"]
        else:
            conversation = self.create_conversation(first_query=query)
            conversation_id = conversation["id"]
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO research_tasks(
                    id, project_id, conversation_id, query, status, source_config_json,
                    origin_task_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 'queued', ?, ?, ?, ?)
                """,
                (new_id, project_id, conversation_id, query.strip(), _json_dumps(source_config or {}), origin_task_id, stamp, stamp),
            )
            conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (stamp, conversation_id))
            row = conn.execute("SELECT * FROM research_tasks WHERE id = ?", (new_id,)).fetchone()
        return self.task_row(row, include_result=True)

    def list_tasks(
        self,
        project_id: str | None = None,
        *,
        archived: bool | None = False,
        conversation_id: str | None = None,
        include_result: bool = False,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM research_tasks"
        params: list[Any] = []
        clauses: list[str] = []
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        if conversation_id:
            clauses.append("conversation_id = ?")
            params.append(conversation_id)
        if archived is True:
            clauses.append("archived_at IS NOT NULL")
        elif archived is False:
            clauses.append("archived_at IS NULL")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at ASC" if conversation_id else " ORDER BY created_at DESC"
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self.task_row(row, include_result=include_result) for row in rows]

    def get_task(self, research_task_id: str, *, include_result: bool = True) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM research_tasks WHERE id = ?", (research_task_id,)).fetchone()
        return self.task_row(row, include_result=include_result) if row else None

    def update_status(self, research_task_id: str, status: str, *, error_message: str = "") -> dict[str, Any] | None:
        if status not in TASK_STATUSES:
            raise ValueError(f"Unknown task status: {status}")
        completed_at = now_iso() if status in TERMINAL_STATUSES else None
        stamp = now_iso()
        where = "id = ?"
        params: list[Any] = [status, error_message, stamp, completed_at, research_task_id]
        if status == "running":
            where += " AND status = 'queued'"
        elif status == "cancelled":
            where += " AND status IN ('queued', 'running')"
        elif status in {"completed", "failed"}:
            where += " AND status != 'cancelled'"
        with self.connect() as conn:
            conn.execute(
                f"""
                UPDATE research_tasks
                SET status = ?, error_message = ?, updated_at = ?, completed_at = COALESCE(?, completed_at)
                WHERE {where}
                """,
                params,
            )
            row = conn.execute("SELECT * FROM research_tasks WHERE id = ?", (research_task_id,)).fetchone()
            if row and row["conversation_id"]:
                conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (stamp, row["conversation_id"]))
        return self.task_row(row, include_result=True) if row else None

    def save_partial(self, research_task_id: str, *, traces: list[dict[str, Any]] | None = None, metrics: dict[str, Any] | None = None) -> None:
        updates: list[str] = ["updated_at = ?"]
        params: list[Any] = [now_iso()]
        if traces is not None:
            updates.append("traces_json = ?")
            params.append(_json_dumps(traces))
        if metrics is not None:
            updates.append("metrics_json = ?")
            params.append(_json_dumps(metrics))
        params.append(research_task_id)
        with self.connect() as conn:
            conn.execute(f"UPDATE research_tasks SET {', '.join(updates)} WHERE id = ?", params)
            row = conn.execute("SELECT conversation_id FROM research_tasks WHERE id = ?", (research_task_id,)).fetchone()
            if row and row["conversation_id"]:
                conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now_iso(), row["conversation_id"]))

    def save_result(self, research_task_id: str, result: dict[str, Any], *, status: str = "completed") -> dict[str, Any] | None:
        metrics = result.get("metrics") or {}
        citations = result.get("citations") or []
        traces = result.get("traces") or []
        risks = result.get("risks") or []
        model = metrics.get("llm_model") or ("deterministic-fallback" if not metrics.get("llm_used") else "")
        if status not in TASK_STATUSES:
            raise ValueError(f"Unknown task status: {status}")
        completed_at = now_iso() if status in TERMINAL_STATUSES else None
        stamp = now_iso()
        where = "id = ?"
        if status == "cancelled":
            where += " AND status IN ('queued', 'running', 'cancelled')"
        elif status in {"completed", "failed"}:
            where += " AND status != 'cancelled'"
        with self.connect() as conn:
            conn.execute(
                f"""
                UPDATE research_tasks
                SET answer = ?, citations_json = ?, traces_json = ?, risks_json = ?,
                    metrics_json = ?, result_json = ?, status = ?, model = ?,
                    updated_at = ?, completed_at = COALESCE(?, completed_at)
                WHERE {where}
                """,
                (
                    str(result.get("answer") or ""),
                    _json_dumps(citations),
                    _json_dumps(traces),
                    _json_dumps(risks),
                    _json_dumps(metrics),
                    _json_dumps(result),
                    status,
                    str(model or ""),
                    stamp,
                    completed_at,
                    research_task_id,
                ),
            )
            row = conn.execute("SELECT * FROM research_tasks WHERE id = ?", (research_task_id,)).fetchone()
            if row and row["conversation_id"]:
                conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (stamp, row["conversation_id"]))
        return self.task_row(row, include_result=True) if row else None

    def delete_task(self, research_task_id: str) -> bool:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM research_tasks WHERE id = ?", (research_task_id,))
        return cur.rowcount > 0

    def move_task(self, research_task_id: str, project_id: str) -> dict[str, Any] | None:
        if not self.get_project(project_id):
            return None
        with self.connect() as conn:
            conn.execute(
                "UPDATE research_tasks SET project_id = ?, updated_at = ? WHERE id = ?",
                (project_id, now_iso(), research_task_id),
            )
            row = conn.execute("SELECT * FROM research_tasks WHERE id = ?", (research_task_id,)).fetchone()
        return self.task_row(row, include_result=True) if row else None

    def archive_task(self, research_task_id: str, archived: bool = True) -> dict[str, Any] | None:
        archived_at = now_iso() if archived else None
        with self.connect() as conn:
            conn.execute(
                "UPDATE research_tasks SET archived_at = ?, updated_at = ? WHERE id = ?",
                (archived_at, now_iso(), research_task_id),
            )
            row = conn.execute("SELECT * FROM research_tasks WHERE id = ?", (research_task_id,)).fetchone()
        return self.task_row(row, include_result=True) if row else None

    def cancel_task(self, research_task_id: str) -> dict[str, Any] | None:
        return self.update_status(research_task_id, "cancelled", error_message="用户已取消研究。")

    def create_rerun_task(self, research_task_id: str) -> dict[str, Any] | None:
        task = self.get_task(research_task_id, include_result=True)
        if not task:
            return None
        return self.create_task(
            project_id=task["project_id"],
            query=task["query"],
            source_config=task.get("source_config") or {},
            origin_task_id=task["id"],
            conversation_id=task.get("conversation_id"),
        )

    @staticmethod
    def task_row(row: sqlite3.Row, *, include_result: bool) -> dict[str, Any]:
        citations = _json_loads(row["citations_json"], [])
        traces = _json_loads(row["traces_json"], [])
        risks = _json_loads(row["risks_json"], [])
        metrics = _json_loads(row["metrics_json"], {})
        source_config = _json_loads(row["source_config_json"], {})
        result = _json_loads(row["result_json"], {})
        if not result and (row["answer"] or citations or traces or metrics):
            result = {
                "query": row["query"],
                "answer": row["answer"],
                "citations": citations,
                "traces": traces,
                "risks": risks,
                "metrics": metrics,
            }
        public = {
            "id": row["id"],
            "project_id": row["project_id"],
            "conversation_id": row["conversation_id"],
            "query": row["query"],
            "status": row["status"],
            "model": row["model"] or metrics.get("llm_model") or "",
            "evidence_count": len(citations),
            "source_config": source_config,
            "origin_task_id": row["origin_task_id"],
            "error_message": row["error_message"],
            "archived_at": row["archived_at"],
            "archived": bool(row["archived_at"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "completed_at": row["completed_at"],
        }
        if include_result:
            public["result"] = result
        return public
