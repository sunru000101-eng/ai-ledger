"""离线冒烟测试：不调模型，直接测 Harness 各部件（工具/钩子/权限/截断/Skill解析）。
运行：.venv/bin/python tests/smoke.py"""
import datetime
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["LEDGER_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")

from app import agent, db, hooks, permissions, skills, tools  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("✅" if cond else "❌"), name, detail)
    if not cond:
        fails.append(name)


db.init_db()
today = datetime.date.today().isoformat()

# Skill解析
cats = skills.valid_categories()
check("Skill解析出分类集合", "餐饮-饮品" in cats and "交通-打车" in cats, f"共{len(cats)}个")

# 安检门
ok, why = hooks.pre_tool_use("add_expense", {"amount": -5, "category": "餐饮-正餐", "date": today})
check("拦截负数金额", not ok, why or "")
ok, _ = hooks.pre_tool_use("add_expense", {"amount": 20, "category": "不存在的分类", "date": today})
check("拦截非法分类", not ok)
future = (datetime.date.today() + datetime.timedelta(days=3)).isoformat()
ok, _ = hooks.pre_tool_use("add_expense", {"amount": 20, "category": "餐饮-正餐", "date": future})
check("拦截未来日期", not ok)
ok, _ = hooks.pre_tool_use("add_expense", {"amount": 35, "category": "餐饮-正餐", "date": today})
check("合法参数放行", ok)
ok, _ = hooks.pre_tool_use("query_expenses", {"start_date": today, "end_date": today, "mode": "瞎填"})
check("拦截非法查询mode", not ok)

# 工具
r = tools.TOOL_HANDLERS["add_expense"]({"amount": 35, "category": "餐饮-正餐", "date": today, "note": "午饭"})
check("记账成功", r.get("ok") and r.get("id") == 1)
tools.TOOL_HANDLERS["add_expense"]({"amount": 19, "category": "餐饮-饮品", "date": today, "note": "咖啡"})
r = tools.TOOL_HANDLERS["query_expenses"]({"start_date": today, "end_date": today, "mode": "sum"})
check("查账求和=54", r.get("total") == 54, str(r))
r = tools.TOOL_HANDLERS["query_expenses"]({"start_date": today, "end_date": today,
                                           "category": "餐饮", "mode": "by_category"})
check("一级分类前缀匹配+分组", len(r.get("groups", [])) == 2)
r = tools.TOOL_HANDLERS["update_expense"]({"id": 2, "amount": 21})
check("改账成功", r.get("ok") and r["after"]["amount"] == 21)
r = tools.TOOL_HANDLERS["delete_expense"]({"id": 1})
check("删账成功", r.get("ok"))
r = tools.TOOL_HANDLERS["delete_expense"]({"id": 99})
check("删除不存在账目返回错误", not r.get("ok"))

# 权限
check("删账需确认", permissions.check("delete_expense") == "ask")
check("记账自动放行", permissions.check("add_expense") == "allow")
check("未注册工具默认要确认", permissions.check("unknown_tool") == "ask")

# 截断
hist = []
for i in range(15):
    hist.append({"role": "user", "content": f"记一笔{i}"})
    hist.append({"role": "assistant", "content": "",
                 "tool_calls": [{"id": f"c{i}", "type": "function",
                                 "function": {"name": "add_expense", "arguments": "{}"}}]})
    hist.append({"role": "tool", "tool_call_id": f"c{i}", "content": "{}"})
    hist.append({"role": "assistant", "content": "好了"})
t = agent.truncate_history(hist)
check("截断到10轮", sum(1 for m in t if m["role"] == "user") == 10)
check("截断点在用户消息边界（不切断工具配对）", t[0]["role"] == "user")

# 报告
r = tools.TOOL_HANDLERS["generate_report"]({"month": today[:7]})
check("报告返回统计+按需注入的风格指南", "stats" in r and "style_guide" in r)
check("报告统计正确", r["stats"]["count"] == 1 and r["stats"]["total"] == 21, str(r["stats"])[:80])

print("-" * 44)
if fails:
    print(f"❌ 失败 {len(fails)} 项：{fails}")
    sys.exit(1)
print("🎉 冒烟测试全部通过")
