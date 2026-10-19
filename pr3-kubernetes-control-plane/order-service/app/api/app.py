import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, status
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel
from psycopg.types.json import Jsonb

DATABASE_URL = os.environ["DATABASE_URL"]
# HEALTH_FAIL можно менять на лету (без рестарта) — удобно для демо в Части 2
HEALTH_FAIL_ENV = "HEALTH_FAIL"


def _health_failing() -> bool:
    return os.getenv(HEALTH_FAIL_ENV, "false").lower() in ("1", "true", "yes")


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


@app.get("/health")
async def health():
    if _health_failing():
        # 503 Service Unavailable — readiness/liveness в Части 2 увидят проблему
        raise HTTPException(status_code=503, detail="unhealthy")
    return {"status": "ok"}


@app.post("/order", status_code=status.HTTP_201_CREATED)
async def create_order(order: OrderIn):
    pool: AsyncConnectionPool = app.state.pool
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO orders (payload) VALUES (%s) "
                "RETURNING id, status, created_at",
                (Jsonb(order.payload),),
            )
            row = await cur.fetchone()
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