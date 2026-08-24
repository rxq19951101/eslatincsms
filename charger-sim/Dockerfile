FROM python:3.11-slim AS dependencies

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

FROM dependencies AS test

COPY requirements-test.txt .
RUN python -m pip install --no-cache-dir -r requirements-test.txt

COPY . .
COPY --from=repository docker-compose.yml /docker-compose.yml

CMD ["python", "-m", "pytest", "-q", "tests", "smoke_test.py"]

FROM dependencies AS runtime

COPY . .

# 默认由 docker-compose 传入 command
CMD ["python", "cli.py", "run-one", "--ws", "ws://csms:9000/ocpp", "--ocpp-identity", "CP-DOCKER-1", "--connector-id", "1"]
