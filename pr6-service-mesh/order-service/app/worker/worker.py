import asyncio
import json
import logging
import os
import signal

import psycopg
from aiohttp import web
from psycopg_pool import AsyncConnectionPool

from prometheus_client import (
    Counter,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

DATABASE_URL = os.environ["DATABASE_URL"]
POLL_INTERVAL = float(os.environ.get("POLL_INTERVAL", "1.0"))
MAX_ATTEMPTS = int(os.environ.get("MAX_ATTEMPTS", "5"))
HEALTH_PORT = int(os.environ.get("HEALTH_PORT", "8001"))

log = logging.getLogger("worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

_shutdown = asyncio.Event()

# --- Метрики Prometheus ---
ORDERS_PROCESSED = Counter(
    "orders_processed_total",
    "Total orders processed (status -> done)",
)
ORDERS_FAILED = Counter(
    "orders_failed_total",
    "Total orders that exhausted attempts (status -> failed)",
)
ORDERS_QUEUE_SIZE = Gauge(
    "worker_orders_queue_size",
    "Number of orders with status='new' (unprocessed)",
)
WORKER_UP = Gauge(
    "worker_up",
    "1 if worker is running and can reach DB, 0 otherwise",
)


def _handle_signal(*_):
    log.info("shutdown requested")
    _shutdown.set()


def _health_failing() -> bool:
    return os.getenv("HEALTH_FAIL", "false").lower() in ("1", "true", "yes")


async def _health(_request: web.Request) -> web.Response:
    if _health_failing():
        return web.Response(status=503, text="unhealthy")
    return web.Response(status=200, text="ok")


async def _livez(_request: web.Request) -> web.Response:
    return web.Response(status=200, text="alive")


async def _metrics(request: web.Request) -> web.Response:
    pool: AsyncConnectionPool = request.app["pool"]
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT count(*) FROM orders WHERE status='new'")
                (qsize,) = await cur.fetchone()
        ORDERS_QUEUE_SIZE.set(qsize)
        WORKER_UP.set(1)
    except Exception:
        WORKER_UP.set(0)
    return web.Response(body=generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST})


async def start_http(pool: AsyncConnectionPool) -> web.AppRunner:
    app = web.Application()
    app["pool"] = pool
    app.router.add_get("/health", _health)
    app.router.add_get("/livez", _livez)
    app.router.add_get("/metrics", _metrics)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HEALTH_PORT)
    await site.start()
    log.info("health/metrics server listening on :%s", HEALTH_PORT)
    return runner


async def claim_one(pool: AsyncConnectionPool) -> dict | None:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                WITH claimed AS (
                    SELECT id FROM orders
                     WHERE status = 'new'
                     ORDER BY id
                     FOR UPDATE SKIP LOCKED
                     LIMIT 1
                )
                UPDATE orders o
                   SET status = 'processing',
                       attempts = o.attempts + 1,
                       updated_at = now()
                  FROM claimed
                 WHERE o.id = claimed.id
                RETURNING o.id, o.payload, o.attempts
                """
            )
            row = await cur.fetchone()
        await conn.commit()
    if not row:
        return None
    return {"id": row[0], "payload": row[1], "attempts": row[2]}


async def process(order: dict) -> None:
    log.info("processing order id=%s attempts=%s payload=%s",
             order["id"], order["attempts"], json.dumps(order["payload"]))


async def mark(pool: AsyncConnectionPool, order_id: int, ok: bool) -> None:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            if ok:
                await cur.execute(
                    "UPDATE orders SET status='done', updated_at=now() WHERE id=%s",
                    (order_id,),
                )
            else:
                await cur.execute(
                    """
                    UPDATE orders
                       SET status = CASE WHEN attempts >= %s THEN 'failed' ELSE 'new' END,
                           updated_at = now()
                     WHERE id = %s
                    """,
                    (MAX_ATTEMPTS, order_id),
                )
        await conn.commit()


async def run() -> None:
    pool = AsyncConnectionPool(DATABASE_URL, min_size=1, max_size=5, open=False)
    await pool.open()

    http_runner = await start_http(pool)

    try:
        while not _shutdown.is_set():
            try:
                order = await claim_one(pool)
                if not order:
                    try:
                        await asyncio.wait_for(_shutdown.wait(), timeout=POLL_INTERVAL)
                    except asyncio.TimeoutError:
                        pass
                    continue

                try:
                    await process(order)
                    ok = True
                except Exception:
                    log.exception("order %s failed", order["id"])
                    ok = False

                await mark(pool, order["id"], ok)

                if ok:
                    ORDERS_PROCESSED.inc()
                else:
                    # failed или будет retry — решаем по attempts
                    if order["attempts"] + 1 >= MAX_ATTEMPTS:
                        ORDERS_FAILED.inc()

                WORKER_UP.set(1)
            except (psycopg.OperationalError, psycopg.errors.UndefinedTable):
                log.exception("db error, retrying in 2s")
                WORKER_UP.set(0)
                await asyncio.sleep(2)
    finally:
        WORKER_UP.set(0)
        await http_runner.cleanup()
        await pool.close()
        log.info("worker stopped")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    asyncio.run(run())
