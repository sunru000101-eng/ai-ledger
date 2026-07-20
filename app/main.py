"""FastAPI后端：聊天、确认、账本、日志、账号 五组接口 + 静态首页。
云端服务模式（LEDGER_DEMO_MODE=1）：
  - 游客：cookie身份 + 演示种子数据 + TTL清理 + IP限额（面试官零门槛试玩）
  - 注册用户：邀请码注册 + 用户名密码登录 + 数据永久保存 + 账号限额
本地自用不设该环境变量，无账号无隔离，行为与从前完全一致。"""
import datetime
import re
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from . import agent, auth, config, db, hooks, tenancy, tools

app = FastAPI(title="AI记账助手")
db.init_db()
if config.DEMO_MODE:
    removed = tenancy.cleanup_old_tenants()
    if removed:
        print(f"[demo] 清理了 {removed} 个过期游客账本")

WEB = Path(__file__).resolve().parent.parent / "web"

_SID_RE = re.compile(r"^[0-9a-f]{32}$")


@app.middleware("http")
async def tenant_middleware(request: Request, call_next):
    """服务模式：优先识别登录用户，否则按游客处理"""
    if not config.DEMO_MODE:
        request.state.user = None
        return await call_next(request)
    user = auth.user_from_token(request.cookies.get("ledger_token", ""))
    request.state.user = user
    if user:
        tenancy.activate_user(user["id"])
        return await call_next(request)
    sid = request.cookies.get("ledger_sid", "")
    is_new = not _SID_RE.fullmatch(sid)
    if is_new:
        sid = uuid.uuid4().hex
    request.state.guest_sid = sid
    tenancy.activate_guest(sid)
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
    if not config.DEMO_MODE:
        return None
    user = request.state.user
    ok, reason = tenancy.check_and_count(
        _client_ip(request), user["id"] if user else None)
    if ok:
        return None
    return {"type": "error", "content": reason, "events": [], "rounds": 0}


def _set_token_cookie(resp: JSONResponse, token: str):
    resp.set_cookie("ledger_token", token, max_age=86400 * config.SESSION_DAYS,
                    httponly=True, samesite="lax")


class ChatIn(BaseModel):
    message: str


class ConfirmIn(BaseModel):
    approved: bool


class RegisterIn(BaseModel):
    username: str
    password: str
    invite_code: str


class LoginIn(BaseModel):
    username: str
    password: str


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/api/config")
def get_config():
    return {"demo": config.DEMO_MODE,
            "register_open": bool(config.INVITE_CODE),
            "ip_daily_limit": config.IP_DAILY_LIMIT,
            "account_daily_limit": config.ACCOUNT_DAILY_LIMIT,
            "tenant_ttl_days": config.TENANT_TTL_DAYS,
            "server_date": datetime.date.today().isoformat()}


@app.get("/api/me")
def me(request: Request):
    user = request.state.user
    return {"logged_in": bool(user),
            "username": user["username"] if user else None}


@app.post("/api/register")
def register(body: RegisterIn, request: Request):
    if not config.DEMO_MODE:
        return {"ok": False, "error": "本地模式无需注册"}
    token, err = auth.register(body.username, body.password, body.invite_code)
    if err:
        return {"ok": False, "error": err}
    user = auth.user_from_token(token)
    # 把游客期间记的账带进新账户
    sid = getattr(request.state, "guest_sid", "")
    if sid:
        tenancy.merge_guest_into_user(sid, user["id"])
    resp = JSONResponse({"ok": True, "username": user["username"]})
    _set_token_cookie(resp, token)
    return resp


@app.post("/api/login")
def login(body: LoginIn):
    if not config.DEMO_MODE:
        return {"ok": False, "error": "本地模式无需登录"}
    token, err = auth.login(body.username, body.password)
    if err:
        return {"ok": False, "error": err}
    user = auth.user_from_token(token)
    resp = JSONResponse({"ok": True, "username": user["username"]})
    _set_token_cookie(resp, token)
    return resp


@app.post("/api/logout")
def logout(request: Request):
    auth.logout(request.cookies.get("ledger_token", ""))
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("ledger_token")
    return resp


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
    me_owner = db.owner()
    rows = db.query(
        "SELECT id, amount, category, date, note FROM expenses "
        "WHERE owner = ? AND date BETWEEN ? AND ? ORDER BY date DESC, id DESC",
        (me_owner, s, e))
    groups = db.query(
        "SELECT category, ROUND(SUM(amount),2) AS total, COUNT(*) AS cnt "
        "FROM expenses WHERE owner = ? AND date BETWEEN ? AND ? "
        "GROUP BY category ORDER BY total DESC", (me_owner, s, e))
    total = db.query_one(
        "SELECT COALESCE(SUM(amount),0) AS t, COUNT(*) AS c FROM expenses "
        "WHERE owner = ? AND date BETWEEN ? AND ?", (me_owner, s, e))
    return {"month": month, "total": round(total["t"], 2), "count": total["c"],
            "expenses": rows, "by_category": groups}


@app.get("/api/logs")
def logs(n: int = 50):
    return {"logs": list(hooks.get_logs())[-n:]}


@app.post("/api/reset")
def reset():
    agent.reset_conversation()
    return {"ok": True}
