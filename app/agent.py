"""Agent循环：产品的心脏。
模型说 → 权限检查 → 安检门 → 执行工具 → 摄像头记录 → 结果回传模型 → 继续，
直到模型给出最终回复，或触到6轮上限。"""
import datetime
import json
import time

from . import config, db, hooks, llm, permissions, skills, tools

WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]

# 会话按租户隔离：本地模式恒为 "local" 一份；演示模式下每个访客各一份
# （短期记忆=history，挂起的确认=pending）
_SESSIONS = {}


def _session() -> dict:
    return _SESSIONS.setdefault(db.TENANT_ID.get(), {"history": [], "pending": None})


def build_system_prompt() -> str:
    """上下文组装：角色规则 + 今天日期 + 常驻Skill（每次都重新拼装）"""
    today = datetime.date.today()
    return (
        "你是一个中文AI记账助手，服务唯一的个人用户。职责：记账、查账、修改删除账目、生成消费报告。\n"
        "行为准则：\n"
        "1. 宁可反问，不可瞎记：金额缺失、指代不明、分类拿不准时，先向用户确认，绝不猜测入账。\n"
        "2. 金额必须来自用户的原话，缺少金额时绝不能编造；但用户已说清金额语义时"
        "（如'人均80，我付了自己那份'即80元）应直接采用，不要反问。\n"
        "3. 一句话包含多笔消费时，拆成多笔分别调用 add_expense。\n"
        "4. 相对时间（昨天/上周三）按今天的日期换算成 YYYY-MM-DD。\n"
        "5. 涉及金额统计的回答必须来自 query_expenses 的返回，不允许编造数字。\n"
        "6. 工具返回校验错误时，修正参数后最多重试一次，仍失败就向用户说明原因。\n"
        "7. 纯闲聊（没有消费信息）不要调用任何工具，正常聊天即可。\n"
        "8. 回复简洁口语化；记账成功后简要复述（金额/分类/日期）。\n"
        f"\n[今天] {today.isoformat()} 星期{WEEKDAYS[today.weekday()]}\n"
        f"\n[分类规则手册]\n{skills.load_skill('categories.md')}"
    )


def truncate_history(history: list) -> list:
    """上下文截断：只留最近N轮，且只在用户消息边界切——绝不切断工具调用配对"""
    user_idx = [i for i, m in enumerate(history) if m["role"] == "user"]
    if len(user_idx) <= config.MAX_HISTORY_ROUNDS:
        return history
    return history[user_idx[-config.MAX_HISTORY_ROUNDS]:]


def _assistant_to_dict(msg) -> dict:
    d = {"role": "assistant", "content": msg.content or ""}
    if msg.tool_calls:
        d["tool_calls"] = [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in msg.tool_calls
        ]
    return d


def _tool_result_msg(tc_id: str, result: dict) -> dict:
    return {"role": "tool", "tool_call_id": tc_id,
            "content": json.dumps(result, ensure_ascii=False)}


def _describe_action(name: str, args: dict) -> str:
    """给确认卡片生成人话描述"""
    eid = args.get("id")
    detail = ""
    row = db.query_one("SELECT * FROM expenses WHERE id = ? AND owner = ?",
                       (eid, db.owner()))
    if row:
        detail = f"{row['date']} {row['category']} {row['amount']}元"
        if row["note"]:
            detail += f"（{row['note']}）"
    if name == "delete_expense":
        return f"删除账目：{detail or f'id={eid}（未找到）'}"
    changes = "、".join(f"{k} 改为 {v}" for k, v in args.items() if k != "id")
    return f"修改账目 {detail or f'id={eid}'}：{changes}"


def _execute_tool(name: str, args: dict, round_no: int, events: list) -> dict:
    """安检门 → 执行 → 摄像头"""
    start = time.time()
    ok, reason = hooks.pre_tool_use(name, args)
    if not ok:
        result = {"error": f"参数校验未通过：{reason}"}
    else:
        try:
            result = tools.TOOL_HANDLERS[name](args)
        except Exception as e:  # noqa: BLE001
            result = {"error": f"工具执行出错：{e}"}
    ms = int((time.time() - start) * 1000)
    entry = hooks.post_tool_use(name, args, "error" not in result, result, round_no, ms)
    events.append(entry)
    return result


def run_turn(user_message: str) -> dict:
    if _session()["pending"]:
        return {"type": "error",
                "content": "有一个操作在等你确认，请先在确认卡片上选择。",
                "events": [], "rounds": 0}
    _session()["history"].append({"role": "user", "content": user_message})
    return _run_loop(rounds=0, events=[])


def _run_loop(rounds: int, events: list) -> dict:
    history = _session()["history"]
    while rounds < config.MAX_ROUNDS:
        rounds += 1
        try:
            resp = llm.chat(
                [{"role": "system", "content": build_system_prompt()}] + truncate_history(history),
                tools=tools.TOOL_SPECS)
        except Exception as e:  # noqa: BLE001
            return {"type": "error",
                    "content": f"模型服务暂时不可用（{type(e).__name__}），已自动重试仍失败，请稍后再试。",
                    "events": events, "rounds": rounds}
        msg = resp.choices[0].message
        if msg.tool_calls:
            history.append(_assistant_to_dict(msg))
            outcome = _process_tool_calls(history[-1]["tool_calls"], 0, rounds, events)
            if outcome is not None:  # 挂起等确认
                return outcome
            continue
        final = (msg.content or "").strip()
        history.append({"role": "assistant", "content": final})
        return {"type": "reply", "content": final, "events": events, "rounds": rounds}
    # 循环上限兜底：给自主性画硬边界
    note = "这个请求的处理轮数超过了上限（6轮），我先停下来。请换个说法，或拆成几句试试。"
    history.append({"role": "assistant", "content": note})
    return {"type": "reply", "content": note, "events": events, "rounds": rounds}


def _process_tool_calls(tcs: list, start_i: int, rounds: int, events: list):
    """依次处理一条assistant消息里的多个工具调用。
    返回 None=全部处理完（继续循环）；返回dict=挂起，等前端确认"""
    history = _session()["history"]
    for i in range(start_i, len(tcs)):
        tc = tcs[i]
        name = tc["function"]["name"]
        try:
            args = json.loads(tc["function"]["arguments"] or "{}")
        except json.JSONDecodeError:
            history.append(_tool_result_msg(tc["id"], {"error": "参数不是合法JSON，请重新生成"}))
            continue
        if permissions.check(name) == "ask":
            _session()["pending"] = {"tcs": tcs, "index": i, "name": name,
                                     "args": args, "rounds": rounds, "events": events}
            return {"type": "confirm", "summary": _describe_action(name, args),
                    "events": events, "rounds": rounds}
        result = _execute_tool(name, args, rounds, events)
        history.append(_tool_result_msg(tc["id"], result))
    return None


def resolve_confirmation(approved: bool) -> dict:
    pending = _session()["pending"]
    if not pending:
        return {"type": "error", "content": "没有待确认的操作。", "events": [], "rounds": 0}
    _session()["pending"] = None
    tc = pending["tcs"][pending["index"]]
    if approved:
        result = _execute_tool(pending["name"], pending["args"],
                               pending["rounds"], pending["events"])
    else:
        result = {"cancelled": True, "msg": "用户拒绝了该操作"}
        entry = hooks.post_tool_use(pending["name"], pending["args"], False,
                                    result, pending["rounds"], 0)
        pending["events"].append(entry)
    _session()["history"].append(_tool_result_msg(tc["id"], result))
    outcome = _process_tool_calls(pending["tcs"], pending["index"] + 1,
                                  pending["rounds"], pending["events"])
    if outcome is not None:
        return outcome
    return _run_loop(pending["rounds"], pending["events"])


def reset_conversation():
    _session()["history"] = []
    _session()["pending"] = None
