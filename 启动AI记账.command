#!/bin/bash
# 双击这个文件即可启动 AI 记账助手（会自动打开浏览器）
# 想停：Ctrl+C 或直接关闭这个终端窗口

cd "$(dirname "$0")"

# 如果服务已在跑，直接打开浏览器就好
if lsof -ti :8000 >/dev/null 2>&1; then
  echo "AI 记账助手已经在运行，正在打开浏览器..."
  open "http://127.0.0.1:8000"
  sleep 2
  exit 0
fi

echo "─────────────────────────────────────────"
echo "  AI 记账助手启动中... 浏览器会自动打开"
echo "  停止方法：Ctrl+C 或直接关闭此窗口"
echo "─────────────────────────────────────────"
echo ""

# 启动前自动备份账本（失败也不阻塞启动）
bash backup.sh 2>/dev/null || true

(sleep 2 && open "http://127.0.0.1:8000") &
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
