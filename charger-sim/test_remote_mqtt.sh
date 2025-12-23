#!/bin/bash
#
# 远程 MQTT OCPP 测试启动脚本
# 使用用户提供的参数
#

cd "$(dirname "$0")"

python3 test_remote_mqtt_ocpp.py \
  --broker "47.236.134.99" \
  --port 1883 \
  --client-id "zcf&861076087029615" \
  --username "861076087029615" \
  --password "pHYtWMiW+UOa" \
  --type-code "zcf" \
  --serial-number "861076087029615" \
  --up-topic "zcf/861076087029615/user/up" \
  --down-topic "zcf/861076087029615/user/down"

