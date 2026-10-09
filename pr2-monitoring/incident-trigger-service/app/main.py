import asyncio
import random
import time
import os
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.metrics import (
    REQUEST_COUNT, REQUEST_DURATION, REQUESTS_IN_PROGRESS,
    FAIL_COUNTER, metrics_endpoint
)
from app.tracing import setup_tracing
from app.logging_config import setup_logging
from app.load_generator import generate_load
import structlog

# Инициализация
setup_logging()
logger = structlog.get_logger()

app = FastAPI(title="Incident Trigger Service")

# Трейсинг
setup_tracing(app)

# Порт для внутренней нагрузки (в Kubernetes — имя сервиса)
SELF_URL = os.getenv("SELF_URL", "http://localhost:8000")

# ---------- Middleware ----------
class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)

        method = request.method
        endpoint = request.url.path

        REQUESTS_IN_PROGRESS.labels(method=method, endpoint=endpoint).inc()
        start = time.monotonic()
        status = "500"

        try:
            response = await call_next(request)
            status = str(response.status_code)
            return response
        except Exception:
            status = "500"
            raise
        finally:
            duration = time.monotonic() - start
            REQUESTS_IN_PROGRESS.labels(method=method, endpoint=endpoint).dec()
            REQUEST_COUNT.labels(method=method, endpoint=endpoint, status_code=status).inc()
            REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)

app.add_middleware(PrometheusMiddleware)

# ---------- Эндпоинты ----------
@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/fail")
async def fail():
    FAIL_COUNTER.inc()
    logger.error("provoked_failure", reason="manual trigger")
    return Response(status_code=500, content="Internal Server Error")

@app.get("/slow")
async def slow():
    delay = random.uniform(1.0, 3.0)
    logger.info("slow_request", delay_seconds=delay)
    await asyncio.sleep(delay)
    return {"slept": delay}

@app.get("/load")
async def load(
    concurrent: int = 10,
    total: int = 50,
    target: str = "/health"
):
    logger.info("load_generation_started", concurrent=concurrent, total=total, target=target)
    result = await generate_load(
        base_url=SELF_URL,
        concurrent=concurrent,
        total=total,
        target=target
    )
    logger.info("load_generation_finished", **result)
    return result

# ---------- Метрики ----------
app.add_route("/metrics", metrics_endpoint, methods=["GET"])