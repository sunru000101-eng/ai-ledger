"""Postgres(Neon) 真实联调：建表 → 游客种子 → 注册合并 → 跨设备找回 → 清理测试数据。
不调用大模型。运行：.venv/bin/python tests/pg_test.py（需 .env 已配 DATABASE_URL）"""
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["LEDGER_DEMO_MODE"] = "1"
os.environ["LEDGER_INVITE_CODE"] = "pg-test-invite"
os.environ["LEDGER_IP_DAILY_LIMIT"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from app import config, db  # noqa: E402
from app.main import app  # noqa: E402

if not db.IS_PG:
    print("❌ 未处于Postgres模式：检查 .env 的 DATABASE_URL")
    sys.exit(1)
print(f"连接目标：{config.DATABASE_URL.split('@')[-1].split('/')[0]}")

fails = []


def check(name, cond, detail=""):
    print(("✅" if cond else "❌"), name, ("—— " + str(detail)[:70] if detail else ""))
    if not cond:
        fails.append(name)


suffix = secrets.token_hex(3)
u1, u2 = f"测试甲{suffix}", f"测试乙{suffix}"
cleanup_owners = []

try:
    A, B, C = TestClient(app), TestClient(app), TestClient(app)

    ra = A.get("/api/ledger").json()
    rb = B.get("/api/ledger").json()
    check("游客A获得种子账本(PG)", ra["count"] == 5, f"A={ra['count']}笔")
    check("游客B独立账本(PG)", rb["count"] == 5)
    cleanup_owners += [f"g_{A.cookies.get('ledger_sid')}", f"g_{B.cookies.get('ledger_sid')}"]

    r = A.post("/api/register", json={"username": u1, "password": "test123",
                                      "invite_code": "pg-test-invite"}).json()
    check("注册成功(PG)", r.get("ok"), str(r)[:60])
    check("游客数据带入账户", A.get("/api/ledger").json()["count"] == 5)

    db.execute("INSERT INTO expenses(owner, amount, category, date, note, created_at) "
               "VALUES (?,?,?,?,?,?)",
               (db.query_one("SELECT id FROM users WHERE username=?", (u1,)) and
                f"u_{db.query_one('SELECT id FROM users WHERE username=?', (u1,))['id']}",
                66, "餐饮-正餐", "2026-07-20", "PG联调", db.now_str()))
    check("直接写入一笔(PG)", A.get("/api/ledger").json()["count"] == 6)

    r = C.post("/api/login", json={"username": u1, "password": "test123"}).json()
    check("换设备登录成功(PG)", r.get("ok"))
    if C.cookies.get("ledger_sid"):
        cleanup_owners.append(f"g_{C.cookies.get('ledger_sid')}")
    check("换设备账本完整找回(PG)", C.get("/api/ledger").json()["count"] == 6)

    r = B.post("/api/register", json={"username": u2, "password": "test456",
                                      "invite_code": "pg-test-invite"}).json()
    check("第二用户注册(PG)", r.get("ok"))
    check("用户间隔离(PG)", B.get("/api/ledger").json()["count"] == 5)

finally:
    # 清理测试数据，把干净的库留给真实用户
    for name in (u1, u2):
        row = db.query_one("SELECT id FROM users WHERE username = ?", (name,))
        if row:
            cleanup_owners.append(f"u_{row['id']}")
            db.execute("DELETE FROM sessions WHERE user_id = ?", (row["id"],))
            db.execute("DELETE FROM users WHERE id = ?", (row["id"],))
    for owner in cleanup_owners:
        db.execute("DELETE FROM expenses WHERE owner = ?", (owner,))
        db.execute("DELETE FROM tenants WHERE owner = ?", (owner,))
    left = db.query_one("SELECT COUNT(*) AS c FROM expenses")
    print(f"🧹 测试数据已清理，库内剩余 {left['c']} 笔（应为0）")

print("-" * 44)
if fails:
    print(f"❌ 失败 {len(fails)} 项：{fails}")
    sys.exit(1)
print("🎉 Neon Postgres 真实联调全部通过")
