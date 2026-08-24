"""Redis Streams 消费者：跨节点 OCPP 命令不再依赖易丢失的 Pub/Sub。"""

import json
import threading
import asyncio
import redis

from app.core.config import get_settings
from app.core.logging_config import get_logger
from app.ocpp.message_router import MessageRouter
from app.ocpp.distributed_connection_manager import distributed_connection_manager

logger = get_logger("ocpp_csms")
settings = get_settings()


class RedisMessageSubscriber:
    CLAIM_IDLE_MS = 30_000
    MAX_ATTEMPTS = 5
    DEAD_LETTER_STREAM = "ocpp:route:dead-letter"

    def __init__(self):
        self.redis_client = redis.from_url(settings.redis_url, decode_responses=True)
        self.running = False
        self.consumer = distributed_connection_manager.server_id
        self.group = "ocpp-route-workers"
        self.stream = distributed_connection_manager.ROUTE_STREAM
        self.loop = None

    def start(self, loop=None):
        if self.running:
            return
        try:
            self.redis_client.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except redis.exceptions.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        self.loop = loop or asyncio.get_event_loop()
        self.running = True
        threading.Thread(target=self._message_loop, daemon=True, name="redis-ocpp-stream").start()
        logger.info("Redis Streams OCPP 路由消费者已启动")

    def stop(self):
        self.running = False
        self.loop = None
        logger.info("Redis Streams OCPP 路由消费者已停止")

    def _claim_pending(self):
        """回收故障消费者的 Pending 消息，避免消息永久卡在旧 consumer 上。"""
        try:
            result = self.redis_client.xautoclaim(
                self.stream,
                self.group,
                self.consumer,
                min_idle_time=self.CLAIM_IDLE_MS,
                start_id="0-0",
                count=20,
            )
            # redis-py 返回 (next_start_id, entries, deleted_ids)
            return result[1] if result else []
        except (AttributeError, redis.exceptions.ResponseError) as exc:
            logger.warning("Redis XAUTOCLAIM 不可用，暂时跳过 Pending 回收: %s", exc)
            return []

    def _read_owned_pending(self):
        """读取已经转交给当前 consumer 的消息，避免依赖 XAUTOCLAIM 的空闲时间。"""
        return self.redis_client.xreadgroup(
            self.group,
            self.consumer,
            {self.stream: "0-0"},
            count=20,
            block=1,
        )

    def _attempt_key(self, entry_id):
        return f"ocpp:route:attempts:{entry_id}"

    def _dead_letter(self, entry_id, fields, error, attempts):
        self.redis_client.xadd(
            self.DEAD_LETTER_STREAM,
            {
                "entry_id": entry_id,
                "message": fields.get("message", ""),
                "error": str(error)[:1000],
                "attempts": str(attempts),
            },
            maxlen=100000,
            approximate=True,
        )
        self.redis_client.xack(self.stream, self.group, entry_id)
        self.redis_client.delete(self._attempt_key(entry_id))
        logger.error("OCPP 路由消息进入死信队列: entry=%s attempts=%s", entry_id, attempts)

    def _handoff_to_owner(self, entry_id, target_server):
        """把误分配给当前消费者的消息交给实际持有 WebSocket 的服务器。"""
        if target_server and target_server != self.consumer:
            self.redis_client.xclaim(
                self.stream,
                self.group,
                target_server,
                min_idle_time=0,
                message_ids=[entry_id],
            )
            return True
        return False

    def _dispatch(self, entry_id, fields):
        try:
            message = json.loads(fields["message"])
            charger_id = message.get("charger_id")
            if not charger_id:
                raise ValueError("route message missing charger_id")

            target_server = message.get("target_server")
            current_owner = distributed_connection_manager.get_connection_server(charger_id)
            if current_owner:
                target_server = current_owner

            if self._handoff_to_owner(entry_id, target_server):
                return

            # 没有本地连接时不能 ACK，否则跨节点命令会直接丢失。
            if not distributed_connection_manager.is_connected_locally(charger_id):
                return

            if not self.loop or self.loop.is_closed():
                raise RuntimeError("main asyncio loop is not available")

            future = asyncio.run_coroutine_threadsafe(
                MessageRouter.handle_routed_message_async(charger_id, message),
                self.loop,
            )
            future.add_done_callback(
                lambda completed: completed.exception()
                if not completed.cancelled()
                else None
            )
            self.redis_client.xack(self.stream, self.group, entry_id)
        except Exception as exc:
            attempts = int(self.redis_client.incr(self._attempt_key(entry_id)))
            self.redis_client.expire(self._attempt_key(entry_id), 86400)
            if attempts >= self.MAX_ATTEMPTS:
                self._dead_letter(entry_id, fields, exc, attempts)
            else:
                logger.exception(
                    "处理 Redis Stream 路由消息失败，将重试: entry=%s attempts=%s",
                    entry_id,
                    attempts,
                )

    def _message_loop(self):
        while self.running:
            try:
                for _, entries in self._read_owned_pending() or []:
                    self._process_entries(entries)
                self._process_entries(self._claim_pending())
                batches = self.redis_client.xreadgroup(
                    self.group, self.consumer, {self.stream: ">"}, count=20, block=1000
                )
                for _, entries in batches or []:
                    self._process_entries(entries)
            except Exception:
                logger.exception("Redis Stream 消费循环失败")

    def _process_entries(self, entries):
        for entry_id, fields in entries or []:
            self._dispatch(entry_id, fields)


redis_message_subscriber = RedisMessageSubscriber()
