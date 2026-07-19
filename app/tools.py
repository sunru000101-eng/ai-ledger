"""5个工具：模型只能按按钮，按钮背后是确定性的程序。
工具边界设计：query_expenses 是参数化查询，不让模型写SQL——安全、可控、可测。"""
import datetime

from . import db, skills

TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "add_expense",
            "description": "记录一笔消费",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "description": "金额（元），必须来自用户原话"},
                    "category": {"type": "string", "description": "分类，必须是分类手册中的完整分类，如 餐饮-正餐"},
                    "date": {"type": "string", "description": "消费日期 YYYY-MM-DD"},
                    "note": {"type": "string", "description": "简短备注，如 火锅、打车去机场"},
                },
                "required": ["amount", "category", "date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_expenses",
            "description": "查询账目（参数化查询）。用户问花了多少钱、有哪些消费时使用",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "起始日期 YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "结束日期 YYYY-MM-DD"},
                    "category": {"type": "string", "description": "可选。一级分类（如 餐饮）或完整分类（如 餐饮-饮品），不填=全部"},
                    "mode": {"type": "string", "enum": ["list", "sum", "by_category"],
                             "description": "list=列明细，sum=求总和，by_category=按分类汇总"},
                },
                "required": ["start_date", "end_date", "mode"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_expense",
            "description": "删除一笔账目。删除前如不确定是哪笔，先用 query_expenses 查出id向用户确认",
            "parameters": {
                "type": "object",
                "properties": {"id": {"type": "integer", "description": "账目id"}},
                "required": ["id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_expense",
            "description": "修改一笔账目的金额/分类/日期/备注",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "description": "账目id"},
                    "amount": {"type": "number"},
                    "category": {"type": "string"},
                    "date": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_report",
            "description": "生成某月的消费统计数据和报告写作指南，用于撰写消费月报",
            "parameters": {
                "type": "object",
                "properties": {"month": {"type": "string", "description": "月份 YYYY-MM"}},
                "required": ["month"],
            },
        },
    },
]


def _category_filter(cat):
    if not cat:
        return "", []
    return " AND (category = ? OR category LIKE ?)", [cat, f"{cat}-%"]


def month_range(month: str):
    y, m = map(int, month.split("-"))
    start = datetime.date(y, m, 1)
    end = datetime.date(y + (m == 12), (m % 12) + 1, 1) - datetime.timedelta(days=1)
    return start.isoformat(), end.isoformat()


def _prev_month(month: str) -> str:
    y, m = map(int, month.split("-"))
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def handle_add(args):
    with db.get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO expenses(amount, category, date, note) VALUES (?,?,?,?)",
            (round(float(args["amount"]), 2), args["category"], args["date"], args.get("note", "")))
        return {"ok": True, "id": cur.lastrowid, "msg": "已入账"}


def handle_query(args):
    where = "date BETWEEN ? AND ?"
    params = [args["start_date"], args["end_date"]]
    extra, p2 = _category_filter(args.get("category"))
    where += extra
    params += p2
    mode = args["mode"]
    with db.get_conn() as conn:
        if mode == "sum":
            row = conn.execute(
                f"SELECT COALESCE(SUM(amount),0) AS total, COUNT(*) AS cnt FROM expenses WHERE {where}",
                params).fetchone()
            return {"total": round(row["total"], 2), "count": row["cnt"]}
        if mode == "by_category":
            rows = conn.execute(
                f"SELECT category, ROUND(SUM(amount),2) AS total, COUNT(*) AS cnt "
                f"FROM expenses WHERE {where} GROUP BY category ORDER BY total DESC",
                params).fetchall()
            return {"groups": [dict(r) for r in rows]}
        rows = conn.execute(
            f"SELECT id, amount, category, date, note FROM expenses WHERE {where} "
            f"ORDER BY date DESC, id DESC LIMIT 100", params).fetchall()
        return {"expenses": [dict(r) for r in rows], "note": "最多返回100条"}


def handle_delete(args):
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM expenses WHERE id=?", (args["id"],)).fetchone()
        if not row:
            return {"ok": False, "error": f"没有 id={args['id']} 的账目"}
        conn.execute("DELETE FROM expenses WHERE id=?", (args["id"],))
        return {"ok": True, "deleted": dict(row)}


def handle_update(args):
    fields = {k: args[k] for k in ("amount", "category", "date", "note") if k in args}
    if not fields:
        return {"ok": False, "error": "没有提供要修改的字段"}
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM expenses WHERE id=?", (args["id"],)).fetchone()
        if not row:
            return {"ok": False, "error": f"没有 id={args['id']} 的账目"}
        sets = ", ".join(f"{k}=?" for k in fields)
        conn.execute(f"UPDATE expenses SET {sets} WHERE id=?", [*fields.values(), args["id"]])
        new = conn.execute("SELECT * FROM expenses WHERE id=?", (args["id"],)).fetchone()
        return {"ok": True, "before": dict(row), "after": dict(new)}


def handle_report(args):
    month = args["month"]
    s, e = month_range(month)
    ps, pe = month_range(_prev_month(month))
    with db.get_conn() as conn:
        total = conn.execute(
            "SELECT COALESCE(SUM(amount),0) t, COUNT(*) c FROM expenses WHERE date BETWEEN ? AND ?",
            (s, e)).fetchone()
        prev = conn.execute(
            "SELECT COALESCE(SUM(amount),0) t FROM expenses WHERE date BETWEEN ? AND ?",
            (ps, pe)).fetchone()
        groups = conn.execute(
            "SELECT category, ROUND(SUM(amount),2) total, COUNT(*) cnt "
            "FROM expenses WHERE date BETWEEN ? AND ? GROUP BY category ORDER BY total DESC",
            (s, e)).fetchall()
        top = conn.execute(
            "SELECT amount, category, date, note FROM expenses WHERE date BETWEEN ? AND ? "
            "ORDER BY amount DESC LIMIT 1", (s, e)).fetchone()
    stats = {
        "month": month,
        "total": round(total["t"], 2),
        "count": total["c"],
        "prev_month_total": round(prev["t"], 2),
        "by_category": [dict(g) for g in groups],
        "biggest_single": dict(top) if top else None,
    }
    # report_style.md 在这里按需注入：只有生成报告时才递给模型
    return {"stats": stats,
            "style_guide": skills.load_skill("report_style.md"),
            "instruction": "请严格按 style_guide 的结构和语气，基于 stats 撰写月度报告；不要编造 stats 之外的数字。"}


# dispatch map：加新工具=注册一个新handler，主循环一行不改
TOOL_HANDLERS = {
    "add_expense": handle_add,
    "query_expenses": handle_query,
    "delete_expense": handle_delete,
    "update_expense": handle_update,
    "generate_report": handle_report,
}
