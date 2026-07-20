"""全局配置：模型、路径、Harness参数"""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()

# LEDGER_DB_PATH 环境变量用于测试时指向临时数据库
DB_PATH = Path(os.getenv("LEDGER_DB_PATH", ROOT / "data" / "ledger.db"))
LOG_PATH = ROOT / "logs" / "agent.log"
SKILLS_DIR = ROOT / "skills"

MAX_ROUNDS = 6           # Agent循环上限（防失控）
MAX_HISTORY_ROUNDS = 10  # 上下文只保留最近N轮对话

# ===== 公开演示/服务模式（DEMO_MODE）=====
# 本地自用时不设置该环境变量，以下配置全部不生效，行为与从前完全一致
DEMO_MODE = os.getenv("LEDGER_DEMO_MODE", "").strip() == "1"
TENANT_TTL_DAYS = int(os.getenv("LEDGER_TENANT_TTL_DAYS", "7"))     # 游客数据保留天数
IP_DAILY_LIMIT = int(os.getenv("LEDGER_IP_DAILY_LIMIT", "30"))      # 游客：每IP每天消息数
ACCOUNT_DAILY_LIMIT = int(os.getenv("LEDGER_ACCOUNT_DAILY_LIMIT", "60"))  # 注册用户：每账号每天
GLOBAL_DAILY_LIMIT = int(os.getenv("LEDGER_GLOBAL_DAILY_LIMIT", "1000"))  # 全站每天消息数

# ===== 持久化与账号（云端）=====
# DATABASE_URL 配置后使用 Postgres（Neon），不配置则本地 SQLite
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
# 邀请码：注册的门票，发给朋友；不配置则注册功能关闭
INVITE_CODE = os.getenv("LEDGER_INVITE_CODE", "").strip()
SESSION_DAYS = 180  # 登录有效期
