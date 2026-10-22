import asyncio
import json
import logging
import os
import signal

import psycopg
from aiohttp import web
from psycopg_pool import AsyncConnectionPool

DATABASE_URL = os.environ["DATABASE_URL"]
POLL_INTERVAL = float(os.environ.get("POLL_INTERVAL", "1.0"))
MAX_ATTEMPTS = int(os.environ.get("MAX_ATTEMPTS", "5"))
HEALTH_PORT = int(os.environ.get("HEALTH_PORT", "8001"))

log = logging.getLogger("worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

_shutdown = asyncio.Event()


def _handle_signal(*_):
    log.info("shutdown requested")
    _shutdown.set()


def _health_failing() -> bool:
    # читаем при каждом запросе — чтобы можно было менять на лету (Часть 2)
    return os.getenv("HEALTH_FAIL", "false").lower() in ("1", "true", "yes")


async def _health(_request: web.Request) -> web.Response:
    if _health_failing():
        return web.Response(status=503, text="unhealthy")
    return web.Response(status=200, text="ok")


async def _livez(_request: web.Request) -> web.Response:
    return web.Response(status=200, text="alive")


async def start_http() -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/health", _health)
    app.router.add_get("/livez", _livez)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HEALTH_PORT)
    await site.start()
    log.info("health server listening on :%s", HEALTH_PORT)
    return runner


async def claim_one(pool: AsyncConnectionPool) -> dict | None:
    """Атомарно захватывает один заказ: new -> processing."""
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
    # Здесь была бы реальная бизнес-логика.
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
                # если попытки исчерпаны — failed, иначе возвращаем в new
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

    http_runner = await start_http()

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
            except (psycopg.OperationalError, psycopg.errors.UndefinedTable):
                log.exception("db error, retrying in 2s")
                await asyncio.sleep(2)
    finally:
        await http_runner.cleanup()
        await pool.close()
        log.info("worker stopped")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    asyncio.run(run())