"""FastAPI后端：聊天、确认、账本视图、日志四组接口 + 静态首页"""
import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import agent, db, hooks, tools

app = FastAPI(title="AI记账助手")
db.init_db()

WEB = Path(__file__).resolve().parent.parent / "web"


class ChatIn(BaseModel):
    message: str


class ConfirmIn(BaseModel):
    approved: bool


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.post("/api/chat")
def chat(body: ChatIn):
    text = body.message.strip()
    if not text:
        return {"type": "error", "content": "说点什么吧", "events": [], "rounds": 0}
    return agent.run_turn(text)


@app.post("/api/confirm")
def confirm(body: ConfirmIn):
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
    return {"logs": list(hooks.LOGS)[-n:]}


@app.post("/api/reset")
def reset():
    agent.reset_conversation()
    return {"ok": True}
