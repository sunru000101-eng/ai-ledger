"""评测跑分：20条真实口语 → 逐条走真实Agent → 对照标准答案 → 输出准确率。
用途：①量化解析质量 ②改提示词/Skill后重跑，防止改崩（回归测试）。
运行：.venv/bin/python eval/run_eval.py（用临时数据库，不碰真实账本）"""
import datetime
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["LEDGER_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "eval.db")

from app import agent, db  # noqa: E402


def resolve_date(expr: str, today: datetime.date) -> str:
    if expr == "today":
        return today.isoformat()
    if expr.startswith("today-"):
        return (today - datetime.timedelta(days=int(expr.split("-")[1]))).isoformat()
    return expr


def all_records():
    with db.get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT amount, category, date, note FROM expenses ORDER BY id").fetchall()]


def wipe():
    with db.get_conn() as conn:
        conn.execute("DELETE FROM expenses")
    agent.reset_conversation()


def match(expected: list, actual: list, today: datetime.date):
    """全对才算对：笔数一致，且每笔的 金额(精确)+日期(精确)+分类(在可接受集合内) 都匹配"""
    if len(expected) != len(actual):
        return False, f"笔数期望{len(expected)}实际{len(actual)}：{[(a['amount'], a['category'], a['date']) for a in actual]}"
    rest = list(actual)
    for exp in expected:
        want_date = resolve_date(exp["date"], today)
        hit = next((a for a in rest
                    if abs(a["amount"] - exp["amount"]) < 0.001
                    and a["date"] == want_date
                    and a["category"] in exp["category"]), None)
        if hit is None:
            return False, (f"没找到匹配 {exp['amount']}元/{'或'.join(exp['category'])}/{want_date}；"
                           f"实际={[(a['amount'], a['category'], a['date']) for a in actual]}")
        rest.remove(hit)
    return True, ""


def main():
    cases = json.loads((ROOT / "eval" / "cases.json").read_text(encoding="utf-8"))
    today = datetime.date.today()
    db.init_db()
    results = []
    print(f"评测开始：{len(cases)}条，今天={today}")
    print("-" * 60)
    for c in cases:
        wipe()
        t0 = time.time()
        r = agent.run_turn(c["input"])
        if r["type"] == "confirm":  # 评测语句不应触发确认，拒绝并按失败处理留痕
            r = agent.resolve_confirmation(False)
        secs = time.time() - t0
        ok, why = match(c["expect"], all_records(), today)
        results.append({"case": c, "ok": ok, "why": why,
                        "reply": (r.get("content") or "")[:80],
                        "rounds": r.get("rounds", 0), "secs": round(secs, 1)})
        print(("✅" if ok else "❌"), f"[{c['type']}] #{c['id']} {c['input']}")
        if not ok:
            print(f"      ↳ {why}")
    print("-" * 60)

    total = len(results)
    passed = sum(1 for x in results if x["ok"])
    by_type = {}
    for x in results:
        t = x["case"]["type"]
        by_type.setdefault(t, [0, 0])
        by_type[t][1] += 1
        by_type[t][0] += x["ok"]
    acc = passed / total * 100
    print(f"总准确率：{passed}/{total} = {acc:.0f}%")
    for t, (p, n) in by_type.items():
        print(f"  {t}: {p}/{n}")

    # 生成报告
    lines = [
        "# 评测报告（自动生成）", "",
        f"- 日期：{datetime.datetime.now():%Y-%m-%d %H:%M}",
        f"- 模型：{os.getenv('LLM_MODEL', '见.env')}",
        f"- **总准确率：{passed}/{total} = {acc:.0f}%**",
        "- 分类型：" + "，".join(f"{t} {p}/{n}" for t, (p, n) in by_type.items()),
        "", "| # | 类型 | 输入 | 结果 | 说明 | 轮数 | 耗时 |", "|---|---|---|---|---|---|---|",
    ]
    for x in results:
        c = x["case"]
        lines.append(f"| {c['id']} | {c['type']} | {c['input']} | {'✅' if x['ok'] else '❌'} "
                     f"| {x['why'] or x['reply'][:40]} | {x['rounds']} | {x['secs']}s |")
    fail_types = [t for t, (p, n) in by_type.items() if p < n]
    lines += ["", "## 失败模式分析",
              ("全部通过，无失败模式。" if not fail_types else
               "失败集中在：" + "、".join(fail_types) + "。详见上表❌行。")]
    (ROOT / "eval" / "results.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"报告已写入 eval/results.md")
    sys.exit(0 if acc >= 80 else 1)


if __name__ == "__main__":
    main()
