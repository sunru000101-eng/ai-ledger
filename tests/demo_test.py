"""服务模式冒烟：游客隔离 + 成本护栏 + 账号体系（纯离线，不调用模型）。
运行：.venv/bin/python tests/demo_test.py"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

tmp = tempfile.mkdtemp()
os.environ["LEDGER_DEMO_MODE"] = "1"
os.environ["LEDGER_DB_PATH"] = os.path.join(tmp, "svc.db")
os.environ["LEDGER_IP_DAILY_LIMIT"] = "0"  # 游客限额0：护栏测试不调模型
os.environ["LEDGER_INVITE_CODE"] = "test-invite-123"

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("✅" if cond else "❌"), name, ("—— " + str(detail)[:70] if detail else ""))
    if not cond:
        fails.append(name)


A = TestClient(app)
B = TestClient(app)

# ---- 游客体验 ----
r = A.get("/api/config").json()
check("服务模式开启且注册开放", r["demo"] and r["register_open"])

ra = A.get("/api/ledger").json()
rb = B.get("/api/ledger").json()
check("游客A自动获得种子账本", ra["count"] == 5, f"A={ra['count']}笔")
check("游客B独立种子账本", rb["count"] == 5)

sid_a = A.cookies.get("ledger_sid")
db.execute("INSERT INTO expenses(owner, amount, category, date, note, created_at) "
           "VALUES (?,?,?,?,?,?)",
           (f"g_{sid_a}", 999, "其他-未分类", "2026-07-19", "隔离测试", db.now_str()))
check("A新增后A可见", A.get("/api/ledger").json()["count"] == 6)
check("B完全不受影响（游客隔离）", B.get("/api/ledger").json()["count"] == 5)

r = A.post("/api/chat", json={"message": "午饭20"}).json()
check("游客护栏拦截并提示注册", r["type"] == "error" and "注册" in r["content"], r["content"][:50])

# ---- 注册与数据合并 ----
r = A.post("/api/register", json={"username": "小儒", "password": "123456",
                                  "invite_code": "错误的码"}).json()
check("错误邀请码被拒", not r.get("ok"))
r = A.post("/api/register", json={"username": "小儒", "password": "123456",
                                  "invite_code": "test-invite-123"}).json()
check("正确邀请码注册成功", r.get("ok"), str(r)[:50])
check("注册后身份生效", A.get("/api/me").json()["username"] == "小儒")
check("游客数据自动带入账户", A.get("/api/ledger").json()["count"] == 6)

# ---- 换设备登录（持久身份的核心验证）----
C = TestClient(app)  # 模拟新手机：没有任何cookie
check("新设备未登录是游客", C.get("/api/me").json()["logged_in"] is False)
r = C.post("/api/login", json={"username": "小儒", "password": "错密码"}).json()
check("错密码被拒", not r.get("ok"))
r = C.post("/api/login", json={"username": "小儒", "password": "123456"}).json()
check("正确密码登录成功", r.get("ok"))
check("换设备后账本完整找回", C.get("/api/ledger").json()["count"] == 6)

# ---- 用户间隔离 ----
r = B.post("/api/register", json={"username": "朋友甲", "password": "654321",
                                  "invite_code": "test-invite-123"}).json()
check("第二个用户注册成功", r.get("ok"))
check("用户乙看不到用户甲的账", B.get("/api/ledger").json()["count"] == 5)

# ---- 注册用户的护栏（账号限额独立于IP限额）----
r = C.post("/api/chat", json={"message": "晚饭30"}).json()
ok_user_quota = (r["type"] != "error") or ("额度" in r.get("content", ""))
check("注册用户不受游客IP限额约束（走账号限额）",
      r["type"] == "reply" or r["type"] == "confirm" or "模型服务" in r.get("content", ""),
      f"type={r['type']}")

# ---- 退出登录 ----
r = C.post("/api/logout").json()
check("退出成功", r.get("ok"))
check("退出后回到游客身份", C.get("/api/me").json()["logged_in"] is False)

print("-" * 44)
if fails:
    print(f"❌ 失败 {len(fails)} 项：{fails}")
    sys.exit(1)
print("🎉 服务模式冒烟全部通过")
