import os
import random
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response, status
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel
from psycopg.types.json import Jsonb

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

DATABASE_URL = os.environ["DATABASE_URL"]
HEALTH_FAIL_ENV = "HEALTH_FAIL"
VERSION = os.getenv("VERSION", "v1")
FAIL = os.getenv("FAIL", "false").lower() == "true"
FLAKY = os.getenv("FLAKY", "false").lower() == "true"


def _health_failing() -> bool:
    return os.getenv(HEALTH_FAIL_ENV, "false").lower() in ("1", "true", "yes")


# --- Метрики Prometheus ---
HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status", "version"],
)
HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration",
    ["method", "path", "version"],
)
ORDERS_CREATED = Counter(
    "orders_created_total",
    "Total orders created via POST /order",
)
ORDERS_QUEUE_SIZE = Gauge(
    "orders_queue_size",
    "Number of orders with status='new' (unprocessed)",
)


class OrderIn(BaseModel):
    payload: dict[str, Any]


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = AsyncConnectionPool(DATABASE_URL, min_size=1, max_size=10, open=False)
    await pool.open()
    app.state.pool = pool
    try:
        yield
    finally:
        await pool.close()


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Считает все HTTP-запросы для http_requests_total и http_request_duration_seconds."""
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    # /metrics и /health не считаем, чтобы не засорять метрики
    if request.url.path not in ("/metrics", "/health", "/livez"):
        HTTP_REQUESTS.labels(
            method=request.method,
            path=request.url.path,
            status=str(response.status_code),
            version=VERSION,
        ).inc()
        HTTP_REQUEST_DURATION.labels(
            method=request.method,
            path=request.url.path,
            version=VERSION,
        ).observe(elapsed)
    return response


@app.get("/version")
async def version():
    return {"version": VERSION}


@app.get("/health")
async def health():
    if _health_failing():
        raise HTTPException(status_code=503, detail="unhealthy")
    return {"status": "ok"}


@app.get("/livez")
async def livez():
    """Liveness: всегда 200, даже при HEALTH_FAIL=true. Нужен, чтобы под не рестартился."""
    return {"status": "alive"}


@app.get("/metrics")
async def metrics():
    """Prometheus scrape endpoint."""
    pool: AsyncConnectionPool = app.state.pool
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT count(*) FROM orders WHERE status='new'")
                (queue_size,) = await cur.fetchone()
        ORDERS_QUEUE_SIZE.set(queue_size)
    except Exception:
        # БД недоступна — не ломаем /metrics, просто не обновляем gauge
        pass
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/order", status_code=status.HTTP_201_CREATED)
async def create_order(order: OrderIn):
    if VERSION == "v2" and FAIL:
        raise HTTPException(status_code=500, detail="v2 failure injection")
    if VERSION == "v1" and FLAKY and random.random() < 0.3:
        raise HTTPException(status_code=500, detail="v1 transient failure injection")
    pool: AsyncConnectionPool = app.state.pool
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO orders (payload) VALUES (%s) "
                "RETURNING id, status, created_at",
                (Jsonb(order.payload),),
            )
            row = await cur.fetchone()
    ORDERS_CREATED.inc()
    return {"id": row[0], "status": row[1], "created_at": row[2]}


@app.get("/orders")
async def list_orders():
    pool: AsyncConnectionPool = app.state.pool
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, payload, status, attempts, created_at, updated_at "
                "FROM orders ORDER BY id DESC LIMIT 100"
            )
            rows = await cur.fetchall()
    return [
        {
            "id": r[0],
            "payload": r[1],
            "status": r[2],
            "attempts": r[3],
            "created_at": r[4],
            "updated_at": r[5],
        }
        for r in rows
    ]