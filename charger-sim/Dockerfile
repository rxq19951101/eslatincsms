FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 默认由 docker-compose 传入 command
CMD ["python", "cli.py", "run-one", "--ws", "ws://csms:9000/ocpp", "--ocpp-identity", "CP-DOCKER-1", "--connector-id", "1"]
