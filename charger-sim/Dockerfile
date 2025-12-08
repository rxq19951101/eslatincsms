#
# 本文件用于构建 charger-sim 模拟器镜像：运行 Python 脚本。
# 默认命令发送一轮标准消息序列。

FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY simulator.py interactive.py __init__.py ./

CMD ["python", "simulator.py", "--id", "CP-DOCKER-1", "--url", "ws://csms:9000/ocpp"]


