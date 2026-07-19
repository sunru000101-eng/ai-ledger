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
