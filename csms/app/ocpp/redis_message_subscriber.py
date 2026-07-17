"""Redis Streams 消费者：跨节点 OCPP 命令不再依赖易丢失的 Pub/Sub。"""

import json
import threading
import redis

from app.core.config import get_settings
from app.core.logging_config import get_logger
from app.ocpp.message_router import MessageRouter
from app.ocpp.distributed_connection_manager import distributed_connection_manager

logger = get_logger("ocpp_csms")
settings = get_settings()


class RedisMessageSubscriber:
    def __init__(self):
        self.redis_client = redis.from_url(settings.redis_url, decode_responses=True)
        self.running = False
        self.consumer = distributed_connection_manager.server_id
        self.group = "ocpp-route-workers"
        self.stream = distributed_connection_manager.ROUTE_STREAM

    def start(self):
        if self.running:
            return
        try:
            self.redis_client.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except redis.exceptions.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        self.running = True
        threading.Thread(target=self._message_loop, daemon=True, name="redis-ocpp-stream").start()
        logger.info("Redis Streams OCPP 路由消费者已启动")

    def stop(self):
        self.running = False
        logger.info("Redis Streams OCPP 路由消费者已停止")

    def _message_loop(self):
        while self.running:
            try:
                batches = self.redis_client.xreadgroup(
                    self.group, self.consumer, {self.stream: ">"}, count=20, block=1000
                )
                for _, entries in batches or []:
                    for entry_id, fields in entries:
                        try:
                            message = json.loads(fields["message"])
                            charger_id = message.get("charger_id")
                            if charger_id and distributed_connection_manager.is_connected_locally(charger_id):
                                MessageRouter.handle_routed_message(charger_id, message)
                            self.redis_client.xack(self.stream, self.group, entry_id)
                        except Exception:
                            logger.exception("处理 Redis Stream 路由消息失败: entry=%s", entry_id)
            except Exception:
                logger.exception("Redis Stream 消费循环失败")


redis_message_subscriber = RedisMessageSubscriber()
