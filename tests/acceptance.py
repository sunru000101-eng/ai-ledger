"""验收清单自动化：设计文档§5的11项，全过才算完成。
走真实模型 + HTTP层（TestClient），用临时数据库。
运行：.venv/bin/python tests/acceptance.py"""
import datetime
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["LEDGER_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "acc.db")

from fastapi.testclient import TestClient  # noqa: E402

from app import agent, config, db, llm, tools  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)
today = datetime.date.today()
month = today.strftime("%Y-%m")
fails = []


def check(name, cond, detail=""):
    print(("✅" if cond else "❌"), name, ("—— " + str(detail)[:100] if detail else ""))
    if not cond:
        fails.append(name)


def chat(text):
    return client.post("/api/chat", json={"message": text}).json()


def confirm(approved):
    return client.post("/api/confirm", json={"approved": approved}).json()


def ledger():
    return client.get(f"/api/ledger?month={month}").json()


def db_rows():
    with db.get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM expenses ORDER BY id").fetchall()]


def wipe():
    with db.get_conn() as conn:
        conn.execute("DELETE FROM expenses")
    agent.reset_conversation()


print("== 记账功能 ==")
wipe()
r = chat("午饭30")
check("1. 单笔记账，账本视图立刻出现", ledger()["count"] == 1, r["content"][:40])

r = chat("咖啡10，外卖20")
check("2. 一句多笔全部入账", ledger()["count"] == 3)

r = chat("昨天奶茶8")
yesterday = (today - datetime.timedelta(days=1)).isoformat()
check("3. '昨天'日期换算正确", any(x["date"] == yesterday and x["amount"] == 8 for x in db_rows()))

print("== 查账功能 ==")
r = chat("今天吃饭一共花了多少？")
check("4. 查账结果与手算一致（今天餐饮=60，不含昨天）", "60" in r["content"], r["content"][:60])

r = chat("这个月娱乐花了多少？")
ok5 = ("0" in r["content"]) or ("没" in r["content"])
check("5. 查无记录分类不编数字", ok5, r["content"][:60])

print("== 删改与安全 ==")
# 模型可能先在对话层口头核对（正常行为）；安全不变量是：真正删除必须经harness确认卡
r = chat("把昨天奶茶那笔删掉")
for _ in range(2):
    if r["type"] != "reply":
        break
    r = chat("对，就是那笔，删吧")
check("6a. 删除动作必经确认卡，且确认前未预先执行",
      r["type"] == "confirm" and ledger()["count"] == 4, r.get("summary", r.get("content", ""))[:50])
if r["type"] == "confirm":
    r = confirm(False)
check("6b. 取消后账目还在", ledger()["count"] == 4)
r = chat("还是删掉吧，昨天那笔奶茶")
for _ in range(2):
    if r["type"] != "reply":
        break
    r = chat("确定，删")
if r["type"] == "confirm":
    r = confirm(True)
check("6c. 确认后删除成功", ledger()["count"] == 3, r.get("content", "")[:40])

n_before = ledger()["count"]
r = chat("记一笔-20的支出")
neg = [x for x in db_rows() if x["amount"] <= 0]
check("7. 负数金额被拦截，不入账", ledger()["count"] == n_before and not neg, r["content"][:50])

print("== 报告与Skill ==")
r = chat("生成这个月的消费报告")
ok8 = len(r.get("content", "")) > 80 and ("元" in r["content"] or "¥" in r["content"])
check("8. 月报生成且含真实数字", ok8, f"{len(r.get('content', ''))}字")

cat_file = config.SKILLS_DIR / "categories.md"
orig = cat_file.read_text(encoding="utf-8")
try:
    cat_file.write_text(orig + "\n- 「小蓝杯」指瑞幸咖啡 → 餐饮-饮品\n", encoding="utf-8")
    r = chat("小蓝杯9块9")
    hit = any(abs(x["amount"] - 9.9) < 0.01 and x["category"] == "餐饮-饮品" for x in db_rows())
    check("9. categories.md加新规则，下一句立刻生效", hit, r["content"][:50])
finally:
    cat_file.write_text(orig, encoding="utf-8")

print("== 系统 ==")
orig_url = config.LLM_BASE_URL
try:
    config.LLM_BASE_URL = "http://127.0.0.1:9"  # 不可达地址模拟断网
    llm._client = None
    r = chat("午饭12")
    ok10 = r["type"] == "error" and "稍后" in r["content"] and "Traceback" not in r["content"]
    check("10. 断网时提示友好、不崩溃", ok10, r["content"][:60])
finally:
    config.LLM_BASE_URL = orig_url
    llm._client = None

r = client.get("/api/logs").json()
check("11. 每次工具调用日志可查", len(r["logs"]) > 0, f"{len(r['logs'])}条日志")

print("-" * 48)
if fails:
    print(f"❌ 未通过 {len(fails)} 项：{fails}")
    sys.exit(1)
print("🎉 11项验收全部通过")
