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

# ===== 公开演示模式（DEMO_MODE）=====
# 本地自用时不设置该环境变量，以下配置全部不生效，行为与从前完全一致
DEMO_MODE = os.getenv("LEDGER_DEMO_MODE", "").strip() == "1"
TENANTS_DIR = Path(os.getenv("LEDGER_TENANTS_DIR", ROOT / "data" / "tenants"))
TENANT_TTL_DAYS = int(os.getenv("LEDGER_TENANT_TTL_DAYS", "7"))     # 访客数据保留天数
IP_DAILY_LIMIT = int(os.getenv("LEDGER_IP_DAILY_LIMIT", "30"))      # 每IP每天消息数
GLOBAL_DAILY_LIMIT = int(os.getenv("LEDGER_GLOBAL_DAILY_LIMIT", "300"))  # 全站每天消息数
