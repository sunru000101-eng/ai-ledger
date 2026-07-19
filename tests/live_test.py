"""在线链路测试：走真实模型，验证完整Agent循环（用临时数据库，不碰真实账本）。
运行：.venv/bin/python tests/live_test.py"""
import datetime
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["LEDGER_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "live.db")

from app import agent, db, tools  # noqa: E402

db.init_db()
today = datetime.date.today().isoformat()
fails = []


def check(name, cond, detail=""):
    print(("✅" if cond else "❌"), name, ("—— " + str(detail)[:120] if detail else ""))
    if not cond:
        fails.append(name)


def rows():
    return tools.TOOL_HANDLERS["query_expenses"](
        {"start_date": "2000-01-01", "end_date": today, "mode": "list"})["expenses"]


print("场景1：一句话记两笔")
r = agent.run_turn("早上瑞幸咖啡19，中午外卖35")
print("   回复：", r["content"][:80], f"（{r['rounds']}轮，{len(r['events'])}次工具调用）")
es = rows()
check("入账2笔", len(es) == 2, [(e["amount"], e["category"]) for e in es])
check("金额正确", {e["amount"] for e in es} == {19, 35})
check("咖啡归入餐饮-饮品", any(e["category"] == "餐饮-饮品" and e["amount"] == 19 for e in es))

print("\n场景2：查账")
r = agent.run_turn("这个月吃饭一共花了多少？")
print("   回复：", r["content"][:80], f"（{r['rounds']}轮）")
check("查账回复包含正确总额54", "54" in r["content"])
check("查账用了query工具", any(e["tool"] == "query_expenses" for e in r["events"]))

print("\n场景3：坑题——没有金额")
r = agent.run_turn("今天买了个东西")
print("   回复：", r["content"][:80])
check("没金额时不入账", len(rows()) == 2)
check("没调用add工具", not any(e["tool"] == "add_expense" for e in r["events"]))

print("\n场景4：删除要走确认闸门")
r = agent.run_turn("把咖啡那笔删掉")
if r["type"] == "confirm":
    print("   确认卡片：", r["summary"])
    check("删除触发确认", True)
    r = agent.resolve_confirmation(True)
    print("   确认后回复：", r["content"][:80])
    check("确认后删除成功", len(rows()) == 1, [(e["amount"], e["category"]) for e in rows()])
else:
    check("删除触发确认", False, f"实际type={r['type']}：{r['content'][:80]}")

print("\n场景5：拒绝删除")
r = agent.run_turn("把外卖那笔也删了")
if r["type"] == "confirm":
    r = agent.resolve_confirmation(False)
    print("   拒绝后回复：", r["content"][:80])
    check("拒绝后账目还在", len(rows()) == 1)
else:
    check("第二次删除也触发确认", False, r["content"][:80])

print("-" * 44)
if fails:
    print(f"❌ 失败 {len(fails)} 项：{fails}")
    sys.exit(1)
print("🎉 在线链路测试全部通过")
