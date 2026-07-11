"""Ordered, checksum-verified PostgreSQL migrations."""
from __future__ import annotations

import hashlib
from pathlib import Path

from settings import AUTH_CONFIG, MEMORY_CONFIG


MIGRATIONS_DIR = Path(__file__).with_name("migrations")


def apply_all_migrations(postgres_dsn: str | None = None) -> int:
    dsn = postgres_dsn if postgres_dsn is not None else (
        MEMORY_CONFIG.get("long_term", {}).get("postgres_dsn", "")
    )
    if not dsn:
        return 0

    import psycopg

    applied = 0
    with psycopg.connect(dsn, autocommit=False, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        conn.commit()

        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = path.stem.split("_", 1)[0]
            sql = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
            with conn.cursor() as cur:
                cur.execute("SELECT checksum FROM schema_migrations WHERE version = %s", (version,))
                row = cur.fetchone()
                if row:
                    existing = row[0] if not isinstance(row, dict) else row["checksum"]
                    if existing != checksum:
                        raise RuntimeError(f"Applied migration {version} checksum changed")
                    continue
                try:
                    cur.execute(sql)
                    cur.execute(
                        "INSERT INTO schema_migrations (version, name, checksum) VALUES (%s, %s, %s)",
                        (version, path.name, checksum),
                    )
                    conn.commit()
                    applied += 1
                except Exception:
                    conn.rollback()
                    raise
        admin_emails = AUTH_CONFIG.get("admin_emails", ())
        if admin_emails:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET role = 'admin' WHERE LOWER(email) = ANY(%s)",
                    (list(admin_emails),),
                )
            conn.commit()
    return applied
