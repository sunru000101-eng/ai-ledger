#!/bin/bash
# 一键验证模型Key：bash verify.sh
cd "$(dirname "$0")" || exit 1

if [ ! -x ".venv/bin/python" ]; then
  echo "首次运行，正在准备环境（约1分钟）..."
  python3 -m venv .venv || { echo "创建虚拟环境失败，请把此输出发给开发"; exit 1; }
  .venv/bin/python -m pip install -q -r requirements.txt || { echo "依赖安装失败，请把此输出发给开发"; exit 1; }
fi

.venv/bin/python verify_key.py
