#!/bin/bash
# 启动 AI记账助手：bash run.sh，然后浏览器打开 http://127.0.0.1:8000
cd "$(dirname "$0")" || exit 1
[ -x .venv/bin/python ] || { echo "环境未就绪，请先运行：bash verify.sh"; exit 1; }
# 启动前自动备份账本（失败也不阻塞启动）
bash backup.sh 2>/dev/null || true
echo "AI记账助手启动中 → http://127.0.0.1:8000  （按 Ctrl+C 停止）"
# 用 python -m 方式启动：文件夹挪到任何位置都能跑（不受venv内脚本路径影响）
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
