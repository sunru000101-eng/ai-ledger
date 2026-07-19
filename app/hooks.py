"""Hooks扩展点：所有工具调用都要穿过这两个钩子。
pre_tool_use = 安检门（模型输出是概率性的，真实世界入口必须有检查站）
post_tool_use = 监控摄像头（每次调用一行结构化日志）"""
import datetime
import json
from collections import defaultdict, deque

from . import config, db, skills

# 每个租户一条独立日志流（演示模式下访客互相看不到对方的调用记录）
_LOGS = defaultdict(lambda: deque(maxlen=500))
LOGS = _LOGS["local"]  # 本地模式的向后兼容别名


def get_logs():
    return _LOGS[db.TENANT_ID.get()]


def _parse_date(s):
    try:
        return datetime.date.fromisoformat(str(s))
    except (ValueError, TypeError):
        return None


def pre_tool_use(name: str, args: dict):
    """返回 (是否放行, 拦截原因)"""
    today = datetime.date.today()

    if name in ("add_expense", "update_expense"):
        if "amount" in args or name == "add_expense":
            amount = args.get("amount")
            if isinstance(amount, bool) or not isinstance(amount, (int, float)):
                return False, "amount 必须是数字"
            if amount <= 0:
                return False, "金额必须大于0"
            if amount > 1_000_000:
                return False, "单笔金额超过100万，疑似解析错误，请与用户确认"
        if "date" in args or name == "add_expense":
            d = _parse_date(args.get("date"))
            if d is None:
                return False, "date 格式必须是 YYYY-MM-DD"
            if d > today:
                return False, f"日期 {d} 在未来（今天是 {today}），请与用户确认"
        if "category" in args or name == "add_expense":
            cats = skills.valid_categories()
            if args.get("category") not in cats:
                return False, (f"分类 '{args.get('category')}' 不在分类手册中，"
                               f"可选分类：{'、'.join(sorted(cats))}")

    if name in ("delete_expense", "update_expense"):
        eid = args.get("id")
        if isinstance(eid, bool) or not isinstance(eid, int) or eid <= 0:
            return False, "id 必须是正整数"

    if name == "query_expenses":
        for key in ("start_date", "end_date"):
            if _parse_date(args.get(key)) is None:
                return False, f"{key} 格式必须是 YYYY-MM-DD"
        if args["start_date"] > args["end_date"]:
            return False, "start_date 不能晚于 end_date"
        if args.get("mode") not in ("list", "sum", "by_category"):
            return False, "mode 只能是 list / sum / by_category"
        cat = args.get("category")
        if cat:
            cats = skills.valid_categories()
            tops = {c.split("-")[0] for c in cats}
            if cat not in cats and cat not in tops:
                return False, f"分类 '{cat}' 不存在，可用一级分类：{'、'.join(sorted(tops))}"

    if name == "generate_report":
        try:
            datetime.datetime.strptime(str(args.get("month", "")), "%Y-%m")
        except ValueError:
            return False, "month 格式必须是 YYYY-MM"

    return True, None


def post_tool_use(name: str, args: dict, ok: bool, result, round_no: int, ms: int) -> dict:
    entry = {
        "time": datetime.datetime.now().strftime("%H:%M:%S"),
        "round": round_no,
        "tool": name,
        "args": args,
        "ok": ok,
        "result": str(result)[:200],
        "ms": ms,
    }
    get_logs().append(entry)
    config.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(config.LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry
