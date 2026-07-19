#!/usr/bin/env python3
"""终端版聊天（开发自测用）：.venv/bin/python cli.py"""
from app import agent, db

db.init_db()
print("AI记账助手（终端版）。输入 exit 退出。")
while True:
    try:
        text = input("\n你：").strip()
    except (EOFError, KeyboardInterrupt):
        break
    if not text or text == "exit":
        break
    r = agent.run_turn(text)
    while r["type"] == "confirm":
        ans = input(f"⚠️ 需要确认：{r['summary']} [y/n]：").strip().lower()
        r = agent.resolve_confirmation(ans == "y")
    print(f"助手（{r.get('rounds', '-')}轮）：{r['content']}")
