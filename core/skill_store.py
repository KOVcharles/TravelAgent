"""Optional PostgreSQL persistence for skill settings and execution traces."""
from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from settings import MEMORY_CONFIG


class SkillPlatformStore:
    def __init__(self, postgres_dsn: Optional[str] = None):
        backend = MEMORY_CONFIG.get("long_term", {}).get("backend", "file")
        self.postgres_dsn = postgres_dsn if postgres_dsn is not None else (
            MEMORY_CONFIG.get("long_term", {}).get("postgres_dsn", "")
        )
        self._enabled = bool(self.postgres_dsn) and (postgres_dsn is not None or backend == "postgres")

    @property
    def configured(self) -> bool:
        return self._enabled

    @contextmanager
    def _conn(self):
        if not self.configured:
            yield None
            return
        import psycopg
        from psycopg.rows import dict_row

        conn = psycopg.connect(
            self.postgres_dsn,
            autocommit=True,
            row_factory=dict_row,
            connect_timeout=5,
        )
        try:
            yield conn
        finally:
            conn.close()

    def is_enabled(self, skill_name: str, default: bool = True) -> bool:
        if not self.configured:
            return default
        try:
            with self._conn() as conn, conn.cursor() as cur:
                cur.execute("SELECT enabled FROM skill_settings WHERE skill_name = %s", (skill_name,))
                row = cur.fetchone()
            return bool(row["enabled"]) if row else default
        except Exception:
            return default

    def settings(self) -> Dict[str, Dict[str, Any]]:
        if not self.configured:
            return {}
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT skill_name, enabled, config_overrides, updated_by, updated_at FROM skill_settings")
            rows = cur.fetchall() or []
        return {row["skill_name"]: dict(row) for row in rows}

    def set_enabled(self, skill_name: str, enabled: bool, updated_by: str) -> None:
        if not self.configured:
            raise RuntimeError("Skill settings require PostgreSQL")
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO skill_settings (skill_name, enabled, updated_by, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (skill_name) DO UPDATE SET
                    enabled = EXCLUDED.enabled,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = NOW()
                """,
                (skill_name, enabled, updated_by),
            )

    def record_run(
        self,
        *,
        request_id: str,
        user_id: str,
        skill_name: str,
        skill_version: str,
        status: str,
        duration_ms: int,
        input_summary: Dict[str, Any],
        output_summary: Dict[str, Any],
        evidence_count: int = 0,
        error_code: Optional[str] = None,
        parent_run_id: Optional[str] = None,
    ) -> Optional[str]:
        if not self.configured:
            return None
        run_id = str(uuid.uuid4())
        try:
            with self._conn() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO skill_execution_runs (
                        id, request_id, user_id, skill_name, skill_version, status,
                        duration_ms, input_summary, output_summary, evidence_count,
                        error_code, parent_run_id, started_at, finished_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb,
                        %s, %s, %s, NOW(), NOW()
                    )
                    """,
                    (
                        run_id, request_id, user_id, skill_name, skill_version, status,
                        duration_ms, json.dumps(input_summary, ensure_ascii=False),
                        json.dumps(output_summary, ensure_ascii=False), evidence_count,
                        error_code, parent_run_id,
                    ),
                )
            return run_id
        except Exception:
            return None

    def recent_runs(self, limit: int = 100, skill_name: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self.configured:
            return []
        sql = """
            SELECT id, request_id, user_id, skill_name, skill_version, status,
                   duration_ms, input_summary, output_summary, evidence_count,
                   error_code, parent_run_id, started_at, finished_at
            FROM skill_execution_runs
        """
        params: List[Any] = []
        if skill_name:
            sql += " WHERE skill_name = %s"
            params.append(skill_name)
        sql += " ORDER BY started_at DESC LIMIT %s"
        params.append(max(1, min(limit, 500)))
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall() or []
        return [dict(row) for row in rows]
