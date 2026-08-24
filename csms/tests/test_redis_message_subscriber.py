import json

from app.ocpp import redis_message_subscriber as subscriber_module


class FakeRedis:
    def __init__(self):
        self.claims = []
        self.acks = []
        self.dead_letters = []
        self.counters = {}

    def xclaim(self, stream, group, consumer, min_idle_time, message_ids):
        self.claims.append((stream, group, consumer, min_idle_time, message_ids))

    def xack(self, stream, group, entry_id):
        self.acks.append((stream, group, entry_id))

    def xadd(self, stream, fields, **kwargs):
        self.dead_letters.append((stream, fields, kwargs))
        return "2-0"

    def incr(self, key):
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    def expire(self, key, seconds):
        return True

    def delete(self, key):
        self.counters.pop(key, None)


def make_subscriber(redis_client):
    subscriber = subscriber_module.RedisMessageSubscriber.__new__(
        subscriber_module.RedisMessageSubscriber
    )
    subscriber.redis_client = redis_client
    subscriber.consumer = "server-a"
    subscriber.group = "ocpp-route-workers"
    subscriber.stream = "ocpp:route:stream"
    subscriber.loop = None
    return subscriber


def test_non_local_message_is_handed_off_without_ack(monkeypatch):
    redis_client = FakeRedis()
    subscriber = make_subscriber(redis_client)

    monkeypatch.setattr(
        subscriber_module.distributed_connection_manager,
        "get_connection_server",
        lambda charger_id: "server-b",
    )
    monkeypatch.setattr(
        subscriber_module.distributed_connection_manager,
        "is_connected_locally",
        lambda charger_id: False,
    )

    subscriber._dispatch(
        "1-0",
        {"message": json.dumps({"charger_id": "CP-1", "target_server": "server-b"})},
    )

    assert redis_client.claims[0][2] == "server-b"
    assert redis_client.acks == []


def test_invalid_message_is_sent_to_dead_letter_after_max_attempts():
    redis_client = FakeRedis()
    subscriber = make_subscriber(redis_client)
    subscriber.MAX_ATTEMPTS = 1

    subscriber._dispatch("1-1", {"message": "not-json"})

    assert redis_client.dead_letters[0][0] == subscriber.DEAD_LETTER_STREAM
    assert redis_client.acks == [(subscriber.stream, subscriber.group, "1-1")]
