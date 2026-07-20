"""5个工具：模型只能按按钮，按钮背后是确定性的程序。
工具边界设计：query_expenses 是参数化查询，不让模型写SQL——安全、可控、可测。
所有查询带 owner 过滤：谁的数据谁可见，跨账户的 id 也够不着别人的账。"""
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
    row = db.execute(
        "INSERT INTO expenses(owner, amount, category, date, note, created_at) "
        "VALUES (?,?,?,?,?,?) RETURNING id",
        (db.owner(), round(float(args["amount"]), 2), args["category"],
         args["date"], args.get("note", ""), db.now_str()))
    return {"ok": True, "id": row["id"], "msg": "已入账"}


def handle_query(args):
    where = "owner = ? AND date BETWEEN ? AND ?"
    params = [db.owner(), args["start_date"], args["end_date"]]
    extra, p2 = _category_filter(args.get("category"))
    where += extra
    params += p2
    mode = args["mode"]
    if mode == "sum":
        row = db.query_one(
            f"SELECT COALESCE(SUM(amount),0) AS total, COUNT(*) AS cnt "
            f"FROM expenses WHERE {where}", tuple(params))
        return {"total": round(row["total"], 2), "count": row["cnt"]}
    if mode == "by_category":
        rows = db.query(
            f"SELECT category, ROUND(SUM(amount),2) AS total, COUNT(*) AS cnt "
            f"FROM expenses WHERE {where} GROUP BY category ORDER BY total DESC",
            tuple(params))
        return {"groups": rows}
    rows = db.query(
        f"SELECT id, amount, category, date, note FROM expenses WHERE {where} "
        f"ORDER BY date DESC, id DESC LIMIT 100", tuple(params))
    return {"expenses": rows, "note": "最多返回100条"}


def handle_delete(args):
    row = db.query_one("SELECT * FROM expenses WHERE id = ? AND owner = ?",
                       (args["id"], db.owner()))
    if not row:
        return {"ok": False, "error": f"没有 id={args['id']} 的账目"}
    db.execute("DELETE FROM expenses WHERE id = ? AND owner = ?",
               (args["id"], db.owner()))
    return {"ok": True, "deleted": row}


def handle_update(args):
    fields = {k: args[k] for k in ("amount", "category", "date", "note") if k in args}
    if not fields:
        return {"ok": False, "error": "没有提供要修改的字段"}
    row = db.query_one("SELECT * FROM expenses WHERE id = ? AND owner = ?",
                       (args["id"], db.owner()))
    if not row:
        return {"ok": False, "error": f"没有 id={args['id']} 的账目"}
    sets = ", ".join(f"{k} = ?" for k in fields)
    db.execute(f"UPDATE expenses SET {sets} WHERE id = ? AND owner = ?",
               (*fields.values(), args["id"], db.owner()))
    new = db.query_one("SELECT * FROM expenses WHERE id = ? AND owner = ?",
                       (args["id"], db.owner()))
    return {"ok": True, "before": row, "after": new}


def handle_report(args):
    month = args["month"]
    s, e = month_range(month)
    ps, pe = month_range(_prev_month(month))
    me = db.owner()
    total = db.query_one(
        "SELECT COALESCE(SUM(amount),0) AS t, COUNT(*) AS c FROM expenses "
        "WHERE owner = ? AND date BETWEEN ? AND ?", (me, s, e))
    prev = db.query_one(
        "SELECT COALESCE(SUM(amount),0) AS t FROM expenses "
        "WHERE owner = ? AND date BETWEEN ? AND ?", (me, ps, pe))
    groups = db.query(
        "SELECT category, ROUND(SUM(amount),2) AS total, COUNT(*) AS cnt "
        "FROM expenses WHERE owner = ? AND date BETWEEN ? AND ? "
        "GROUP BY category ORDER BY total DESC", (me, s, e))
    top = db.query_one(
        "SELECT amount, category, date, note FROM expenses "
        "WHERE owner = ? AND date BETWEEN ? AND ? ORDER BY amount DESC LIMIT 1",
        (me, s, e))
    stats = {
        "month": month,
        "total": round(total["t"], 2),
        "count": total["c"],
        "prev_month_total": round(prev["t"], 2),
        "by_category": groups,
        "biggest_single": top,
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
