"""数据层：本地 SQLite，云端配置 DATABASE_URL 后走 Postgres（Neon）。
多租户用 owner 列隔离：'local'（本机自用）/ 'g_<sid>'（游客）/ 'u_<id>'（注册用户）。
所有业务 SQL 用 ? 占位符书写，本层负责转换方言。"""
import datetime
import sqlite3
from contextvars import ContextVar
from decimal import Decimal

from . import config

# 当前请求的数据归属者（由中间件设置；本地模式恒为 "local"）
TENANT_ID: ContextVar[str] = ContextVar("tenant_id", default="local")

IS_PG = bool(config.DATABASE_URL)

if IS_PG:
    import psycopg
    from psycopg.rows import dict_row


def owner() -> str:
    return TENANT_ID.get()


def now_str() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normalize(row: dict) -> dict:
    """Postgres 的 NUMERIC 会返回 Decimal，统一转 float，避免 json 序列化崩溃"""
    return {k: (float(v) if isinstance(v, Decimal) else v) for k, v in row.items()}


def query(sql: str, params: tuple = ()) -> list:
    if IS_PG:
        with psycopg.connect(config.DATABASE_URL, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(sql.replace("?", "%s"), params)
                return [_normalize(r) for r in cur.fetchall()]
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(config.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def query_one(sql: str, params: tuple = ()):
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple = ()):
    """写操作。SQL 含 RETURNING 时返回首行 dict，否则返回受影响行数"""
    returning = "returning" in sql.lower()
    if IS_PG:
        with psycopg.connect(config.DATABASE_URL, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(sql.replace("?", "%s"), params)
                row = cur.fetchone() if returning else None
                conn.commit()
                return _normalize(row) if row else (None if returning else cur.rowcount)
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(config.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(sql, params)
        row = cur.fetchone() if returning else None
        conn.commit()
        return (dict(row) if row else None) if returning else cur.rowcount


def init_db():
    if IS_PG:
        stmts = [
            """CREATE TABLE IF NOT EXISTS expenses (
                id BIGSERIAL PRIMARY KEY,
                owner TEXT NOT NULL DEFAULT 'local',
                amount NUMERIC(12,2) NOT NULL,
                category TEXT NOT NULL,
                date TEXT NOT NULL,
                note TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT ''
            )""",
            "CREATE INDEX IF NOT EXISTS idx_expenses_owner_date ON expenses(owner, date)",
            """CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                pw_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT ''
            )""",
            """CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                expires_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS tenants (
                owner TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                last_active TEXT NOT NULL
            )""",
        ]
    else:
        stmts = [
            """CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                date TEXT NOT NULL,
                note TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )""",
            """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                pw_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT ''
            )""",
            """CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS tenants (
                owner TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                last_active TEXT NOT NULL
            )""",
        ]
    for s in stmts:
        execute(s)
    if not IS_PG:
        # 本地老账本迁移：补 owner 列，既有数据全部归 'local'（你的真实账一条不丢）
        cols = [r["name"] for r in query("PRAGMA table_info(expenses)")]
        if "owner" not in cols:
            execute("ALTER TABLE expenses ADD COLUMN owner TEXT NOT NULL DEFAULT 'local'")
