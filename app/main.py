"""FastAPI后端：聊天、确认、账本视图、日志四组接口 + 静态首页。
演示模式（LEDGER_DEMO_MODE=1）下：cookie 分配访客身份、每访客独立账本、成本护栏。
本地自用不设该环境变量，行为与从前完全一致。"""
import datetime
import re
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import agent, config, db, hooks, tenancy, tools

app = FastAPI(title="AI记账助手")
db.init_db()
if config.DEMO_MODE:
    removed = tenancy.cleanup_old_tenants()
    if removed:
        print(f"[demo] 清理了 {removed} 个过期访客账本")

WEB = Path(__file__).resolve().parent.parent / "web"

_SID_RE = re.compile(r"^[0-9a-f]{32}$")


@app.middleware("http")
async def tenant_middleware(request: Request, call_next):
    """演示模式：为每个访客分配/识别 cookie 身份，并把本次请求绑定到他的独立账本"""
    if not config.DEMO_MODE:
        return await call_next(request)
    sid = request.cookies.get("ledger_sid", "")
    is_new = not _SID_RE.fullmatch(sid)
    if is_new:
        sid = uuid.uuid4().hex
    tenancy.activate(sid)
    response = await call_next(request)
    if is_new:
        response.set_cookie("ledger_sid", sid, max_age=86400 * config.TENANT_TTL_DAYS,
                            httponly=True, samesite="lax")
    return response


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _guardrail(request: Request):
    """成本护栏：只拦调用大模型的接口。返回 None=放行，dict=拒绝响应"""
    if not config.DEMO_MODE:
        return None
    ok, reason = tenancy.check_and_count(_client_ip(request))
    if ok:
        return None
    return {"type": "error", "content": reason, "events": [], "rounds": 0}


class ChatIn(BaseModel):
    message: str


class ConfirmIn(BaseModel):
    approved: bool


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/api/config")
def get_config():
    return {"demo": config.DEMO_MODE,
            "ip_daily_limit": config.IP_DAILY_LIMIT,
            "tenant_ttl_days": config.TENANT_TTL_DAYS}


@app.post("/api/chat")
def chat(body: ChatIn, request: Request):
    text = body.message.strip()
    if not text:
        return {"type": "error", "content": "说点什么吧", "events": [], "rounds": 0}
    if len(text) > 500:
        return {"type": "error", "content": "一次最多500字，拆开说吧～", "events": [], "rounds": 0}
    blocked = _guardrail(request)
    if blocked:
        return blocked
    return agent.run_turn(text)


@app.post("/api/confirm")
def confirm(body: ConfirmIn, request: Request):
    blocked = _guardrail(request)
    if blocked:
        return blocked
    return agent.resolve_confirmation(body.approved)


@app.get("/api/ledger")
def ledger(month: str = ""):
    try:
        datetime.datetime.strptime(month, "%Y-%m")
    except ValueError:
        month = datetime.date.today().strftime("%Y-%m")
    s, e = tools.month_range(month)
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT id, amount, category, date, note FROM expenses "
            "WHERE date BETWEEN ? AND ? ORDER BY date DESC, id DESC", (s, e)).fetchall()
        groups = conn.execute(
            "SELECT category, ROUND(SUM(amount),2) AS total, COUNT(*) AS cnt "
            "FROM expenses WHERE date BETWEEN ? AND ? GROUP BY category ORDER BY total DESC",
            (s, e)).fetchall()
        total = conn.execute(
            "SELECT COALESCE(SUM(amount),0) AS t, COUNT(*) AS c FROM expenses "
            "WHERE date BETWEEN ? AND ?", (s, e)).fetchone()
    return {"month": month, "total": round(total["t"], 2), "count": total["c"],
            "expenses": [dict(r) for r in rows],
            "by_category": [dict(g) for g in groups]}


@app.get("/api/logs")
def logs(n: int = 50):
    return {"logs": list(hooks.get_logs())[-n:]}


@app.post("/api/reset")
def reset():
    agent.reset_conversation()
    return {"ok": True}
