"""
长期记忆 (Long-term Memory)
支持本地 JSON 文件和 PostgreSQL 两种后端，便于本地调试与生产持久化切换。
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pathlib import Path
import json
import logging
import uuid

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FileLongTermMemory:
    """
    本地 JSON 长期记忆：适合开发调试，无需 PostgreSQL。
    数据按用户保存到 data/memory/{user_id}.json。
    """

    def __init__(self, user_id: str, storage_path: str = "data/memory", postgres_dsn: str = ""):
        self.user_id = user_id
        self.storage_path = storage_path
        self.file_path = Path(storage_path) / f"{user_id}.json"
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()
        logger.info(f"File long-term memory initialized for user: {user_id} ({self.file_path})")

    def _default_data(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "preferences": {},
            "chat_history": [],
            "trip_history": [],
            "statistics": {
                "total_trips": 0,
                "total_messages": 0,
                "total_queries": 0,
                "frequent_destinations": {},
            },
        }

    def _load(self) -> Dict[str, Any]:
        if not self.file_path.exists():
            data = self._default_data()
            self._save(data)
            return data

        try:
            with self.file_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            backup_path = self.file_path.with_suffix(f".broken-{uuid.uuid4().hex[:8]}.json")
            try:
                self.file_path.replace(backup_path)
                logger.warning(f"Broken memory file moved to {backup_path}: {exc}")
            except OSError:
                logger.warning(f"Failed to backup broken memory file: {exc}")
            data = self._default_data()
            self._save(data)
            return data

        default = self._default_data()
        for key, value in default.items():
            data.setdefault(key, value)
        data.setdefault("statistics", {}).setdefault("frequent_destinations", {})
        data["statistics"].setdefault("total_trips", len(data.get("trip_history", [])))
        data["statistics"].setdefault("total_messages", len(data.get("chat_history", [])))
        data["statistics"].setdefault("total_queries", 0)
        return data

    def _save(self, data: Optional[Dict[str, Any]] = None):
        target = data if data is not None else self.data
        tmp_path = self.file_path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(target, f, ensure_ascii=False, indent=2)
        tmp_path.replace(self.file_path)

    def save_preference(self, pref_type: str, value: Any):
        self.data.setdefault("preferences", {})[pref_type] = value
        self._save()
        logger.info(f"Saved preference: {pref_type} = {value}")

    def get_preference(self, pref_type: str = None) -> Any:
        preferences = self.data.setdefault("preferences", {})
        if pref_type is None:
            return dict(preferences)
        return preferences.get(pref_type)

    def add_hotel_brand(self, brand: str):
        brands = self.get_preference("hotel_brands")
        if not isinstance(brands, list):
            brands = [brands] if brands else []
        if brand not in brands:
            brands.append(brand)
        self.save_preference("hotel_brands", brands)
        logger.info(f"Added hotel brand preference: {brand}")

    def add_airline(self, airline: str):
        airlines = self.get_preference("airlines")
        if not isinstance(airlines, list):
            airlines = [airlines] if airlines else []
        if airline not in airlines:
            airlines.append(airline)
        self.save_preference("airlines", airlines)
        logger.info(f"Added airline preference: {airline}")

    def add_chat_message(self, role: str, content: str, session_id: str = None):
        self.data.setdefault("chat_history", []).append({
            "role": role,
            "content": content,
            "timestamp": _utc_now_iso(),
            "session_id": session_id,
        })
        stats = self.data.setdefault("statistics", {})
        stats["total_messages"] = int(stats.get("total_messages", 0)) + 1
        self._save()
        logger.debug(f"Added chat message to long-term memory: {role}")

    def get_chat_history(self, limit: int = None, session_id: str = None) -> List[Dict[str, Any]]:
        rows = self.data.setdefault("chat_history", [])
        if session_id:
            rows = [row for row in rows if row.get("session_id") == session_id]
        if limit:
            rows = rows[-limit:]
        return [dict(row) for row in rows]

    def save_trip_history(self, trip_info: Dict[str, Any]):
        trip_id = f"trip_{uuid.uuid4().hex[:12]}"
        destination = trip_info.get("destination")
        trip = {
            "trip_id": trip_id,
            "timestamp": _utc_now_iso(),
            "origin": trip_info.get("origin"),
            "destination": destination,
            "start_date": trip_info.get("start_date"),
            "end_date": trip_info.get("end_date"),
            "purpose": trip_info.get("purpose"),
        }
        self.data.setdefault("trip_history", []).append(trip)
        stats = self.data.setdefault("statistics", {})
        stats["total_trips"] = int(stats.get("total_trips", 0)) + 1
        freq = stats.setdefault("frequent_destinations", {})
        if destination:
            freq[destination] = int(freq.get(destination, 0)) + 1
        self._save()
        logger.info(f"Saved trip history: {trip_id}")

    def get_trip_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        rows = self.data.setdefault("trip_history", [])
        if limit:
            rows = rows[-limit:]
        return [dict(row) for row in rows]

    def get_frequent_destinations(self, top_n: int = 5) -> List[tuple]:
        stats = self.get_statistics()
        freq = stats.get("frequent_destinations", {})
        sorted_dest = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return sorted_dest[:top_n]

    def increment_query_count(self):
        stats = self.data.setdefault("statistics", {})
        stats["total_queries"] = int(stats.get("total_queries", 0)) + 1
        self._save()

    def get_statistics(self) -> Dict[str, Any]:
        stats = self.data.setdefault("statistics", {})
        return {
            "total_trips": int(stats.get("total_trips", 0)),
            "total_messages": int(stats.get("total_messages", 0)),
            "total_queries": int(stats.get("total_queries", 0)),
            "frequent_destinations": dict(stats.get("frequent_destinations", {})),
        }

    def clear_history(self):
        self.data["chat_history"] = []
        self.data["trip_history"] = []
        stats = self.data.setdefault("statistics", {})
        stats["total_trips"] = 0
        stats["total_messages"] = 0
        stats["frequent_destinations"] = {}
        self._save()
        logger.info("Cleared all history (chat + trips)")

    def delete_all(self):
        self.data = self._default_data()
        self._save()
        logger.warning(f"Deleted long-term memory data for user: {self.user_id}")


class DisabledLongTermMemory(FileLongTermMemory):
    """空长期记忆：完全不持久化，用于临时调试。"""

    def __init__(self, user_id: str, storage_path: str = "data/memory", postgres_dsn: str = ""):
        self.user_id = user_id
        self.storage_path = storage_path
        self.file_path = None
        self.data = self._default_data()
        logger.info(f"Disabled long-term memory initialized for user: {user_id}")

    def _save(self, data: Optional[Dict[str, Any]] = None):
        return None


class PostgresLongTermMemory:
    """
    长期记忆：持久化用户信息
    - 用户偏好（家庭地址、酒店品牌、航空公司等）
    - 历史行程记录
    - 统计信息
    """

    def __init__(self, user_id: str, storage_path: str = "data/memory", postgres_dsn: str = ""):
        """
        初始化长期记忆

        Args:
            user_id: 用户ID
            storage_path: 兼容保留参数（PostgreSQL 后端不使用）
            postgres_dsn: PostgreSQL 连接串
        """
        self.user_id = user_id
        self.storage_path = storage_path
        self.postgres_dsn = postgres_dsn

        if not self.postgres_dsn:
            raise ValueError("postgres_dsn is required when long-term memory backend is 'postgres'")
        import psycopg
        from psycopg.rows import dict_row
        from psycopg.types.json import Jsonb

        self._jsonb = Jsonb
        self.conn = psycopg.connect(self.postgres_dsn, autocommit=True, row_factory=dict_row)
        self._init_schema()
        self._ensure_user_stats_row()
        logger.info(f"PostgreSQL long-term memory initialized for user: {user_id}")

    def _init_schema(self):
        """初始化 PostgreSQL 表结构"""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id TEXT NOT NULL,
                    pref_type TEXT NOT NULL,
                    pref_value JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (user_id, pref_type)
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_history (
                    id BIGSERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    session_id TEXT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS trip_history (
                    id BIGSERIAL PRIMARY KEY,
                    trip_id TEXT NOT NULL UNIQUE,
                    user_id TEXT NOT NULL,
                    origin TEXT,
                    destination TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    purpose TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS user_statistics (
                    user_id TEXT PRIMARY KEY,
                    total_trips INTEGER NOT NULL DEFAULT 0,
                    total_messages INTEGER NOT NULL DEFAULT 0,
                    total_queries INTEGER NOT NULL DEFAULT 0,
                    frequent_destinations JSONB NOT NULL DEFAULT '{}'::jsonb,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

    def _ensure_user_stats_row(self):
        """确保用户统计行存在"""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_statistics (user_id)
                VALUES (%s)
                ON CONFLICT (user_id) DO NOTHING;
                """,
                (self.user_id,),
            )

    def save_preference(self, pref_type: str, value: Any):
        """
        保存用户偏好（列表格式）

        Args:
            pref_type: 偏好类型
            value: 偏好值
        """
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_preferences (user_id, pref_type, pref_value, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (user_id, pref_type)
                DO UPDATE SET pref_value = EXCLUDED.pref_value, updated_at = NOW();
                """,
                (self.user_id, pref_type, self._jsonb(value)),
            )
        logger.info(f"Saved preference: {pref_type} = {value}")

    def get_preference(self, pref_type: str = None) -> Any:
        """
        获取用户偏好

        Args:
            pref_type: 偏好类型，None返回字典格式的全部偏好

        Returns:
            偏好值或偏好字典
        """
        if pref_type is None:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT pref_type, pref_value
                    FROM user_preferences
                    WHERE user_id = %s;
                    """,
                    (self.user_id,),
                )
                rows = cur.fetchall()
            return {row["pref_type"]: row["pref_value"] for row in rows}

        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT pref_value
                FROM user_preferences
                WHERE user_id = %s AND pref_type = %s;
                """,
                (self.user_id, pref_type),
            )
            row = cur.fetchone()
        return row["pref_value"] if row else None

    def add_hotel_brand(self, brand: str):
        """添加酒店品牌偏好（追加到列表）"""
        brands = self.get_preference("hotel_brands")
        if not isinstance(brands, list):
            brands = [brands] if brands else []
        if brand not in brands:
            brands.append(brand)
        self.save_preference("hotel_brands", brands)
        logger.info(f"Added hotel brand preference: {brand}")

    def add_airline(self, airline: str):
        """添加航空公司偏好（追加到列表）"""
        airlines = self.get_preference("airlines")
        if not isinstance(airlines, list):
            airlines = [airlines] if airlines else []
        if airline not in airlines:
            airlines.append(airline)
        self.save_preference("airlines", airlines)
        logger.info(f"Added airline preference: {airline}")

    def add_chat_message(self, role: str, content: str, session_id: str = None):
        """
        添加聊天消息到长期记忆

        Args:
            role: 角色 (user/assistant)
            content: 消息内容
            session_id: 会话ID（可选）
        """
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO chat_history (user_id, session_id, role, content, created_at)
                VALUES (%s, %s, %s, %s, NOW());
                """,
                (self.user_id, session_id, role, content),
            )
            cur.execute(
                """
                UPDATE user_statistics
                SET total_messages = total_messages + 1, updated_at = NOW()
                WHERE user_id = %s;
                """,
                (self.user_id,),
            )
        logger.debug(f"Added chat message to long-term memory: {role}")

    def get_chat_history(self, limit: int = None, session_id: str = None) -> List[Dict[str, Any]]:
        """
        获取聊天历史

        Args:
            limit: 返回数量限制
            session_id: 会话ID（只返回特定会话的消息）

        Returns:
            消息列表
        """
        sql = """
            SELECT role, content, created_at, session_id
            FROM chat_history
            WHERE user_id = %s
        """
        params: List[Any] = [self.user_id]
        if session_id:
            sql += " AND session_id = %s"
            params.append(session_id)
        sql += " ORDER BY created_at DESC"
        if limit:
            sql += " LIMIT %s"
            params.append(limit)
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        rows.reverse()
        return [
            {
                "role": row["role"],
                "content": row["content"],
                "timestamp": row["created_at"].isoformat(),
                "session_id": row["session_id"],
            }
            for row in rows
        ]

    def save_trip_history(self, trip_info: Dict[str, Any]):
        """
        保存行程历史

        Args:
            trip_info: 行程信息
        """
        trip_id = f"trip_{uuid.uuid4().hex[:12]}"
        destination = trip_info.get("destination")
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO trip_history (
                    trip_id, user_id, origin, destination, start_date, end_date, purpose, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW());
                """,
                (
                    trip_id,
                    self.user_id,
                    trip_info.get("origin"),
                    destination,
                    trip_info.get("start_date"),
                    trip_info.get("end_date"),
                    trip_info.get("purpose"),
                ),
            )
            if destination:
                cur.execute(
                    """
                    UPDATE user_statistics
                    SET
                        total_trips = total_trips + 1,
                        frequent_destinations = jsonb_set(
                            frequent_destinations,
                            ARRAY[%s],
                            to_jsonb(COALESCE((frequent_destinations ->> %s)::int, 0) + 1),
                            true
                        ),
                        updated_at = NOW()
                    WHERE user_id = %s;
                    """,
                    (destination, destination, self.user_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE user_statistics
                    SET total_trips = total_trips + 1, updated_at = NOW()
                    WHERE user_id = %s;
                    """,
                    (self.user_id,),
                )
        logger.info(f"Saved trip history: {trip_id}")

    def get_trip_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取历史行程

        Args:
            limit: 返回数量限制

        Returns:
            行程列表
        """
        sql = """
            SELECT trip_id, origin, destination, start_date, end_date, purpose, created_at
            FROM trip_history
            WHERE user_id = %s
            ORDER BY created_at DESC
        """
        params: List[Any] = [self.user_id]
        if limit:
            sql += " LIMIT %s"
            params.append(limit)
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        rows.reverse()
        return [
            {
                "trip_id": row["trip_id"],
                "timestamp": row["created_at"].isoformat(),
                "origin": row["origin"],
                "destination": row["destination"],
                "start_date": row["start_date"],
                "end_date": row["end_date"],
                "purpose": row["purpose"],
            }
            for row in rows
        ]

    def get_frequent_destinations(self, top_n: int = 5) -> List[tuple]:
        """
        获取常去目的地

        Args:
            top_n: 返回前N个

        Returns:
            [(destination, count), ...]
        """
        stats = self.get_statistics()
        freq = stats.get("frequent_destinations", {})
        sorted_dest = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return sorted_dest[:top_n]

    def increment_query_count(self):
        """增加查询计数"""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE user_statistics
                SET total_queries = total_queries + 1, updated_at = NOW()
                WHERE user_id = %s;
                """,
                (self.user_id,),
            )

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT total_trips, total_messages, total_queries, frequent_destinations
                FROM user_statistics
                WHERE user_id = %s;
                """,
                (self.user_id,),
            )
            row = cur.fetchone()
        if not row:
            return {
                "total_trips": 0,
                "total_messages": 0,
                "total_queries": 0,
                "frequent_destinations": {},
            }
        return {
            "total_trips": row["total_trips"],
            "total_messages": row["total_messages"],
            "total_queries": row["total_queries"],
            "frequent_destinations": row["frequent_destinations"] or {},
        }

    def clear_history(self):
        """清空历史记录（保留偏好）"""
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM chat_history WHERE user_id = %s;", (self.user_id,))
            cur.execute("DELETE FROM trip_history WHERE user_id = %s;", (self.user_id,))
            cur.execute(
                """
                UPDATE user_statistics
                SET
                    total_trips = 0,
                    total_messages = 0,
                    frequent_destinations = '{}'::jsonb,
                    updated_at = NOW()
                WHERE user_id = %s;
                """,
                (self.user_id,),
            )
        logger.info("Cleared all history (chat + trips)")

        logger.warning(f"Deleted long-term memory data for user: {self.user_id}")


LongTermMemory = PostgresLongTermMemory
