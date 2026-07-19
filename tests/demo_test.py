"""演示模式冒烟：访客账本隔离 + 成本护栏（纯离线，不调用模型）。
运行：.venv/bin/python tests/demo_test.py"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

tmp = tempfile.mkdtemp()
os.environ["LEDGER_DEMO_MODE"] = "1"
os.environ["LEDGER_DB_PATH"] = os.path.join(tmp, "local.db")
os.environ["LEDGER_TENANTS_DIR"] = os.path.join(tmp, "tenants")
os.environ["LEDGER_IP_DAILY_LIMIT"] = "0"  # 限额设0：第一条就拦截，保证测试不调模型

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("✅" if cond else "❌"), name, ("—— " + str(detail)[:60] if detail else ""))
    if not cond:
        fails.append(name)


A = TestClient(app)
B = TestClient(app)

r = A.get("/api/config").json()
check("演示模式开启", r["demo"] is True)

ra = A.get("/api/ledger").json()
rb = B.get("/api/ledger").json()
check("访客A自动获得种子账本", ra["count"] >= 3, f"A={ra['count']}笔")
check("访客B自动获得种子账本", rb["count"] >= 3, f"B={rb['count']}笔")

tenants = list(Path(os.environ["LEDGER_TENANTS_DIR"]).glob("*.db"))
check("两个访客=两个独立账本文件", len(tenants) == 2, f"实际{len(tenants)}个")

# 直接往A的账本插一笔，验证B完全不可见
sid_a = A.cookies.get("ledger_sid")
db_a = Path(os.environ["LEDGER_TENANTS_DIR"]) / f"{sid_a}.db"
conn = sqlite3.connect(db_a)
conn.execute("INSERT INTO expenses(amount, category, date, note) "
             "VALUES (999, '其他-未分类', date('now'), '隔离测试')")
conn.commit()
conn.close()
ra2 = A.get("/api/ledger").json()
rb2 = B.get("/api/ledger").json()
check("A新增后A可见", ra2["count"] == ra["count"] + 1)
check("B完全不受影响（账本隔离生效）", rb2["count"] == rb["count"])

# 成本护栏
r = A.post("/api/chat", json={"message": "午饭20"}).json()
check("护栏拦截并返回友好提示", r["type"] == "error" and "额度" in r["content"], r["content"][:40])

# 超长输入拦截
r = B.post("/api/chat", json={"message": "好" * 501}).json()
check("超长输入被拦截", r["type"] == "error" and "500" in r["content"])

print("-" * 44)
if fails:
    print(f"❌ 失败 {len(fails)} 项：{fails}")
    sys.exit(1)
print("🎉 演示模式冒烟全部通过")
