#
# 本文件用于构建 csms 服务镜像：基于 Python 3.11-slim 运行 FastAPI 应用。
# 暴露端口 9000，并通过 uvicorn 启动。

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 安装 curl 用于 Docker 健康检查, postgresql-client 用于数据库初始化
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY tests ./tests
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY entrypoint.sh ./entrypoint.sh

# 确保脚本可执行
RUN chmod +x /app/entrypoint.sh /app/scripts/*.sh 2>/dev/null || true

ENV PORT=9000
EXPOSE 9000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:9000/health || exit 1

# 先等待数据库并执行初始化/迁移，再启动应用
ENTRYPOINT ["/app/entrypoint.sh"]
