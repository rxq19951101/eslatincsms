#!/usr/bin/env python3
"""Bounded, local-only BE-211 capacity measurements.

The harness deliberately uses a temporary SQLite database and deterministic
fakes.  It measures the shape of the write/lease/fallback paths and reports
local observations; it does not establish PostgreSQL or production capacity.
No network, Provider credential, production database, or production setting is
read or changed.
"""

from __future__ import annotations

import argparse
import json
import queue
import os
import sqlite3
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class FailingRedis:
    """Minimal Redis double that exercises MeterValues DB fallback."""

    def eval(self, *args: Any, **kwargs: Any) -> Any:
        raise OSError("BE-211 deterministic Redis outage")


def _now() -> float:
    return time.perf_counter()


def _rate(count: int, elapsed: float) -> float:
    return round(count / elapsed, 2) if elapsed else float(count)


def _setup_database(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA busy_timeout=1000;
        CREATE TABLE be211_writes (
            id INTEGER PRIMARY KEY,
            tenant_ref TEXT NOT NULL,
            status TEXT NOT NULL,
            source_ref TEXT NOT NULL,
            payload TEXT NOT NULL
        );
        CREATE INDEX idx_be211_writes_tenant_status ON be211_writes (tenant_ref, status, id);
        CREATE TABLE be211_queue (
            id INTEGER PRIMARY KEY,
            status TEXT NOT NULL,
            lease_owner TEXT,
            lease_until REAL,
            attempts INTEGER NOT NULL DEFAULT 0,
            source_ref TEXT NOT NULL UNIQUE
        );
        CREATE INDEX idx_be211_queue_claim ON be211_queue (status, lease_until, id);
        CREATE TABLE be211_reconciliation (
            id INTEGER PRIMARY KEY,
            business_date TEXT NOT NULL,
            source_cursor INTEGER NOT NULL,
            status TEXT NOT NULL,
            amount_cents INTEGER NOT NULL
        );
        CREATE INDEX idx_be211_reconciliation_cursor
            ON be211_reconciliation (business_date, source_cursor, id);
        """
    )


def measure_database_writes(connection: sqlite3.Connection, rows: int) -> dict[str, Any]:
    started = _now()
    connection.executemany(
        "INSERT INTO be211_writes (tenant_ref, status, source_ref, payload) VALUES (?, ?, ?, ?)",
        (("tenant:be211", "pending", f"write:{index}", "{}") for index in range(rows)),
    )
    connection.commit()
    elapsed = _now() - started
    plan = connection.execute(
        "EXPLAIN QUERY PLAN SELECT id FROM be211_writes "
        "WHERE tenant_ref = 'tenant:be211' AND status = 'pending' ORDER BY id LIMIT 10"
    ).fetchall()
    return {
        "rows": rows,
        "elapsed_seconds": round(elapsed, 6),
        "rows_per_second": _rate(rows, elapsed),
        "index_plan": " ".join(str(part) for row in plan for part in row),
        "index_observed": any("INDEX" in str(part).upper() for row in plan for part in row),
    }


def measure_lock_wait(database_path: Path) -> dict[str, Any]:
    first = sqlite3.connect(database_path, timeout=1.0, check_same_thread=False)
    second = sqlite3.connect(database_path, timeout=1.0, check_same_thread=False)
    first.execute("PRAGMA busy_timeout=1000")
    second.execute("PRAGMA busy_timeout=1000")
    first.execute("BEGIN IMMEDIATE")
    first.execute(
        "INSERT INTO be211_writes (tenant_ref, status, source_ref, payload) "
        "VALUES ('tenant:lock', 'pending', 'lock:owner', '{}')"
    )
    started = _now()
    outcome = "blocked_then_committed"
    try:
        second.execute("BEGIN IMMEDIATE")
        second.execute(
            "INSERT INTO be211_writes (tenant_ref, status, source_ref, payload) "
            "VALUES ('tenant:lock', 'pending', 'lock:waiter', '{}')"
        )
        second.commit()
        outcome = "unexpected_no_wait"
    except sqlite3.OperationalError as exc:
        outcome = "busy_timeout_observed" if "locked" in str(exc).lower() else type(exc).__name__
        second.rollback()
    finally:
        first.rollback()
        first.close()
        second.close()
    return {"elapsed_seconds": round(_now() - started, 6), "outcome": outcome}


def measure_connection_pool(database_path: Path, workers: int) -> dict[str, Any]:
    """Measure bounded checkout contention in a temporary local connection pool."""

    pool_size = max(1, min(4, workers))
    pool: queue.Queue[sqlite3.Connection] = queue.Queue(maxsize=pool_size)
    for _ in range(pool_size):
        connection = sqlite3.connect(database_path, timeout=1.0, check_same_thread=False)
        connection.execute("PRAGMA busy_timeout=1000")
        pool.put(connection)

    wait_samples: list[float] = []
    wait_lock = threading.Lock()

    def pooled_query(_: int) -> int:
        checkout_started = _now()
        connection = pool.get()
        try:
            with wait_lock:
                wait_samples.append(_now() - checkout_started)
            return int(connection.execute("SELECT COUNT(*) FROM be211_writes").fetchone()[0])
        finally:
            pool.put(connection)

    started = _now()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        counts = list(executor.map(pooled_query, range(workers * 2)))
    elapsed = _now() - started
    while not pool.empty():
        pool.get_nowait().close()
    return {
        "pool_size": pool_size,
        "workers": workers,
        "checkouts": len(counts),
        "elapsed_seconds": round(elapsed, 6),
        "max_checkout_wait_seconds": round(max(wait_samples, default=0.0), 6),
        "bounded": len(counts) == workers * 2,
    }


def measure_pool_and_provider_burst(rows: int, workers: int) -> dict[str, Any]:
    lock = threading.Lock()
    active = 0
    peak_active = 0

    def provider_call(index: int) -> str:
        nonlocal active, peak_active
        with lock:
            active += 1
            peak_active = max(peak_active, active)
        time.sleep(0.0005)
        with lock:
            active -= 1
        return f"provider-fake:{index}"

    started = _now()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        completed = list(executor.map(provider_call, range(rows)))
    elapsed = _now() - started
    return {
        "requests": rows,
        "workers": workers,
        "completed": len(completed),
        "elapsed_seconds": round(elapsed, 6),
        "requests_per_second": _rate(rows, elapsed),
        "peak_inflight_fake_provider": peak_active,
        "real_provider_used": False,
    }


def measure_queue_lease_dlq(connection: sqlite3.Connection, rows: int) -> dict[str, Any]:
    connection.executemany(
        "INSERT INTO be211_queue (status, lease_owner, lease_until, attempts, source_ref) "
        "VALUES ('queued', NULL, NULL, 0, ?)",
        ((f"queue:{index}",) for index in range(rows)),
    )
    connection.commit()
    started = _now()
    leased = connection.execute(
        "SELECT id FROM be211_queue WHERE status = 'queued' ORDER BY id LIMIT ?", (rows,)
    ).fetchall()
    for (item_id,) in leased:
        connection.execute(
            "UPDATE be211_queue SET status='leased', lease_owner='be211-worker', "
            "lease_until=?, attempts=attempts+1 WHERE id=?",
            (time.time() + 60, item_id),
        )
    connection.execute(
        "UPDATE be211_queue SET status='dead_letter', lease_owner=NULL, lease_until=NULL "
        "WHERE id IN (SELECT id FROM be211_queue ORDER BY id LIMIT 1)"
    )
    connection.commit()
    elapsed = _now() - started
    dead_letters = connection.execute(
        "SELECT COUNT(*) FROM be211_queue WHERE status='dead_letter'"
    ).fetchone()[0]
    return {
        "queued": rows,
        "leased": len(leased),
        "dead_lettered": dead_letters,
        "elapsed_seconds": round(elapsed, 6),
        "items_per_second": _rate(rows, elapsed),
        "bounded": len(leased) == rows and dead_letters == 1,
    }


def measure_meter_fallback() -> dict[str, Any]:
    from app.services.meter_telemetry_service import MeterTelemetryService

    decision = MeterTelemetryService(redis_client=FailingRedis()).record_latest(
        tenant_id="tenant-be211",
        session_id="session-be211",
        message_key="meter-1",
        snapshot={"energy_wh": 100},
    )
    return {
        "redis_available": decision.redis_available,
        "should_persist": decision.should_persist,
        "duplicate": decision.duplicate,
        "fallback_fail_closed": decision.redis_available is False and decision.should_persist is True,
    }


def measure_reconciliation_batches(connection: sqlite3.Connection, rows: int, batch_size: int) -> dict[str, Any]:
    connection.executemany(
        "INSERT INTO be211_reconciliation (business_date, source_cursor, status, amount_cents) "
        "VALUES ('2026-08-14', ?, 'pending', 100)",
        ((index,) for index in range(rows)),
    )
    connection.commit()
    cursor = -1
    processed = 0
    batches = 0
    started = _now()
    while True:
        batch = connection.execute(
            "SELECT id, source_cursor FROM be211_reconciliation "
            "WHERE business_date=? AND source_cursor>? ORDER BY source_cursor, id LIMIT ?",
            ("2026-08-14", cursor, batch_size),
        ).fetchall()
        if not batch:
            break
        connection.executemany(
            "UPDATE be211_reconciliation SET status='matched' WHERE id=?",
            ((row[0],) for row in batch),
        )
        connection.commit()
        cursor = batch[-1][1]
        processed += len(batch)
        batches += 1
    elapsed = _now() - started
    return {
        "rows": rows,
        "batch_size": batch_size,
        "batches": batches,
        "processed": processed,
        "elapsed_seconds": round(elapsed, 6),
        "rows_per_second": _rate(processed, elapsed),
        "bounded_cursor": processed == rows and batches == (rows + batch_size - 1) // batch_size,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    if os.getenv("ENVIRONMENT", "test").lower() == "production":
        raise SystemExit("BE-211 measurement is disabled in production")
    with tempfile.TemporaryDirectory(prefix="eslatin-be211-") as temp_dir:
        database_path = Path(temp_dir) / "measurements.sqlite3"
        connection = sqlite3.connect(database_path)
        try:
            _setup_database(connection)
            result = {
                "environment": "local-test-only",
                "production_capacity_claim": False,
                "parameters": vars(args),
                "database_writes": measure_database_writes(connection, args.rows),
                "lock_probe": measure_lock_wait(database_path),
                "connection_pool": measure_connection_pool(database_path, args.workers),
                "queue_lease_dlq": measure_queue_lease_dlq(connection, args.rows),
                "provider_burst": measure_pool_and_provider_burst(args.rows, args.workers),
                "meter_values_fallback": measure_meter_fallback(),
                "reconciliation_batches": measure_reconciliation_batches(
                    connection, args.rows, args.batch_size
                ),
            }
        finally:
            connection.close()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=200, help="bounded synthetic rows per measurement")
    parser.add_argument("--workers", type=int, default=8, help="bounded fake Provider workers")
    parser.add_argument("--batch-size", type=int, default=50, help="bounded reconciliation batch size")
    args = parser.parse_args()
    if args.rows < 1 or args.rows > 10_000 or args.workers < 1 or args.workers > 32:
        parser.error("rows must be 1..10000 and workers must be 1..32")
    if args.batch_size < 1 or args.batch_size > args.rows:
        parser.error("batch-size must be between 1 and rows")
    print(json.dumps(run(args), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
