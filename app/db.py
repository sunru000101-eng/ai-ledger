"""SQLite账本：产品的长期记忆。
演示模式下每个访客一本独立账（contextvar 指向各自的数据库文件），
本地自用时 contextvar 为空，走默认的 data/ledger.db——行为与从前一致。"""
import sqlite3
from contextvars import ContextVar

from . import config

# 当前请求的租户身份与数据库路径（由 tenancy.activate 设置；本地模式恒为默认值）
TENANT_ID: ContextVar[str] = ContextVar("tenant_id", default="local")
DB_PATH_OVERRIDE: ContextVar = ContextVar("db_path_override", default=None)


def current_db_path():
    return DB_PATH_OVERRIDE.get() or config.DB_PATH


def get_conn():
    path = current_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                date TEXT NOT NULL,
                note TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
        """)
