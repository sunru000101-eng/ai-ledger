#!/usr/bin/env python3
"""验证 .env 中配置的大模型 Key 是否可用、工具调用能力是否过关。

运行方式（在 ai-ledger 目录下）：bash verify.sh
共4项测试：
  T1 基础连通    —— Key/地址/模型名配置是否正确
  T2 工具调用    —— 模型会不会主动调用工具（产品的命脉）
  T3 结果跟进    —— 工具结果喂回去后能否继续对话（Agent循环的关键）
  T4 解析质量    —— "昨天午饭花了35"能否解析出正确的金额/日期/分类
"""
import datetime
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

try:
    from dotenv import load_dotenv
    from openai import OpenAI
except ImportError:
    print("❌ 依赖未安装。请在终端运行：bash verify.sh（它会自动装依赖）")
    sys.exit(1)

load_dotenv(ROOT / ".env")

API_KEY = os.getenv("LLM_API_KEY", "").strip()
BASE_URL = os.getenv("LLM_BASE_URL", "").strip()
MODEL = os.getenv("LLM_MODEL", "").strip()


def die(msg: str):
    print(msg)
    sys.exit(1)


if not API_KEY or "在这里" in API_KEY:
    die("❌ 还没填Key：用文本编辑器打开 ai-ledger/.env，"
        "把 LLM_API_KEY= 后面换成你的真实Key，保存后重跑 bash verify.sh")
if not BASE_URL:
    die("❌ .env 里 LLM_BASE_URL 是空的，参考 .env 文件底部的填法说明。")
if not MODEL or "以控制台" in MODEL:
    die("❌ .env 里 LLM_MODEL 还没填好，参考 .env 文件底部的填法说明。")

client = OpenAI(api_key=API_KEY, base_url=BASE_URL, timeout=60, max_retries=0)

today = datetime.date.today()
yesterday = today - datetime.timedelta(days=1)
WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]

TOOLS = [{
    "type": "function",
    "function": {
        "name": "add_expense",
        "description": "记录一笔消费",
        "parameters": {
            "type": "object",
            "properties": {
                "amount": {"type": "number", "description": "金额（元）"},
                "category": {"type": "string",
                             "enum": ["餐饮", "交通", "娱乐", "日用", "其他"],
                             "description": "消费分类"},
                "date": {"type": "string", "description": "消费日期，格式 YYYY-MM-DD"},
                "note": {"type": "string", "description": "备注"},
            },
            "required": ["amount", "category", "date"],
        },
    },
}]

passed, failed = [], []


def report(name: str, ok: bool, detail: str = ""):
    mark = "✅ 通过" if ok else "❌ 失败"
    print(f"  {mark}  {name}" + (f" —— {detail}" if detail else ""))
    (passed if ok else failed).append(name)


print(f"\n开始验证：{BASE_URL} / {MODEL}")
print("-" * 56)

# ---------- T1 基础连通 ----------
t1_error = None
try:
    r = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": "请只回复四个字：连接成功"}],
    )
    content = (r.choices[0].message.content or "").strip()
    report("T1 基础连通", bool(content), f"模型回复：{content[:20]}")
except Exception as e:  # noqa: BLE001
    t1_error = e
    report("T1 基础连通", False, str(e)[:120])

if t1_error is not None:
    print("-" * 56)
    msg = str(t1_error).lower()
    if "401" in msg or "authentication" in msg or "api key" in msg:
        print("诊断：Key 不对或没生效 → 检查 .env 的 LLM_API_KEY 是否复制完整（前后别带空格）。")
    elif "404" in msg or "model" in msg:
        print("诊断：模型名不对 → 登录平台控制台查'模型列表'，把准确模型名填进 LLM_MODEL。")
    else:
        print("诊断：多半是 LLM_BASE_URL 不对或网络不通 → 对照 .env 底部的填法检查。")
    sys.exit(1)

# ---------- T2/T3/T4 工具调用全链路 ----------
sys_prompt = (
    f"你是记账助手。今天是{today.isoformat()}（星期{WEEKDAYS[today.weekday()]}）。"
    "用户描述消费时，调用 add_expense 工具记账，日期一律换算成 YYYY-MM-DD 格式。"
)
messages = [
    {"role": "system", "content": sys_prompt},
    {"role": "user", "content": "昨天午饭花了35"},
]

m1 = None
tc = None
args = {}
try:
    r1 = client.chat.completions.create(
        model=MODEL, messages=messages, tools=TOOLS, tool_choice="auto")
    m1 = r1.choices[0].message
    if m1.tool_calls:
        tc = m1.tool_calls[0]
        try:
            args = json.loads(tc.function.arguments)
            report("T2 会主动调用工具", True,
                   f"调用 {tc.function.name}，参数 {json.dumps(args, ensure_ascii=False)}")
        except json.JSONDecodeError:
            tc = None
            report("T2 会主动调用工具", False,
                   f"调了工具但参数不是合法JSON：{tc.function.arguments[:80]}")
    else:
        report("T2 会主动调用工具", False,
               f"模型没调工具，只回了文字：{(m1.content or '')[:60]}")
except Exception as e:  # noqa: BLE001
    report("T2 会主动调用工具", False, str(e)[:120])

if args:
    ok_amount = args.get("amount") == 35
    ok_date = args.get("date") == yesterday.isoformat()
    ok_cat = "餐" in str(args.get("category", ""))
    detail = (f"金额{'✓' if ok_amount else '✗'} "
              f"日期{'✓' if ok_date else '✗'}(期望{yesterday.isoformat()}，实际{args.get('date')}) "
              f"分类{'✓' if ok_cat else '✗'}({args.get('category')})")
    report("T4 中文解析质量", ok_amount and ok_date and ok_cat, detail)
else:
    report("T4 中文解析质量", False, "T2没通过，无从验证")

if tc is not None:
    try:
        messages.append({
            "role": "assistant",
            "content": m1.content or "",
            "tool_calls": [{
                "id": tc.id, "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }],
        })
        messages.append({
            "role": "tool", "tool_call_id": tc.id,
            "content": json.dumps({"ok": True, "id": 1}, ensure_ascii=False),
        })
        r2 = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
        final = (r2.choices[0].message.content or "").strip()
        report("T3 工具结果能接得住", bool(final), f"最终回复：{final[:40]}")
    except Exception as e:  # noqa: BLE001
        report("T3 工具结果能接得住", False, str(e)[:120])
else:
    report("T3 工具结果能接得住", False, "T2没通过，无从验证")

# ---------- 结论 ----------
print("-" * 56)
if not failed:
    print(f"🎉 4项全过！{MODEL} 的工具调用过关，可以开干了。")
elif any(f.startswith("T2") for f in failed):
    print("结论：这个模型的工具调用不过关（T2失败是硬伤）。\n"
          "建议：换成 DeepSeek（.env 改成 deepseek-chat 那组配置）后重跑本测试。")
else:
    print(f"结论：{len(passed)}/4 通过。把上面的完整输出发给你的开发（我），我来判断能不能用。")
