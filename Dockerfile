FROM python:3.12-slim

# 时区固定为中国：真实用户凌晨记账时"今天"不能按UTC算
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*
ENV TZ=Asia/Shanghai

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 公开服务模式：游客隔离 + 账号体系 + 成本护栏
ENV LEDGER_DEMO_MODE=1

CMD python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
