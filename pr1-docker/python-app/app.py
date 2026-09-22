"""
HTTP-сервис для нагрузочного тестирования.

Эндпоинты:
    GET /health      — health-check, возвращает {"status": "ok"}
    GET /eat?mb=N    — выделяет N мегабайт памяти и удерживает их
    GET /burn        — нагружает одно ядро CPU в бесконечном цикле

Запуск:
    uvicorn app:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import os
import threading
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

app = FastAPI(
    title="Chaos Loader",
    description="Сервис для проверки алертов по CPU и памяти",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Хранилище "съеденной" памяти и воркеров CPU.
#
# Держим ссылки на объекты, чтобы GC их не собрал.
# ---------------------------------------------------------------------------
_memory_chunks: list[bytearray] = []
_memory_lock = threading.Lock()
_memory_bytes_total = 0

_burn_threads: list[threading.Thread] = []
_burn_stop_events: list[threading.Event] = []
_burn_lock = threading.Lock()


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------
@app.get("/health")
async def health() -> dict[str, str]:
    """Простой health-check."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# GET /eat?mb=N
# ---------------------------------------------------------------------------
@app.get("/eat")
async def eat(mb: int = Query(..., ge=1, le=4096, description="Сколько МБ выделить")) -> JSONResponse:
    """
    Выделяет `mb` мегабайт памяти и держит их до перезапуска процесса.

    Память не освобождается — за это отвечает сборщик мусора, но мы храним
    ссылки в глобальном списке, поэтому GC её не тронет.
    """
    global _memory_bytes_total

    chunk_size = mb * 1024 * 1024

    try:
        # bytearray сразу занимает реальную память и заполняется нулями,
        # в отличие от bytes-литерала, который может быть оптимизирован.
        chunk = bytearray(chunk_size)
    except MemoryError as exc:
        raise HTTPException(
            status_code=507,  # Insufficient Storage
            detail=f"Не удалось выделить {mb} МБ: {exc}",
        ) from exc

    with _memory_lock:
        _memory_chunks.append(chunk)
        _memory_bytes_total += chunk_size
        total_mb = _memory_bytes_total // (1024 * 1024)
        chunks_count = len(_memory_chunks)

    return JSONResponse(
        {
            "status": "ok",
            "allocated_mb": mb,
            "total_allocated_mb": total_mb,
            "chunks": chunks_count,
        }
    )


# ---------------------------------------------------------------------------
# GET /burn
# ---------------------------------------------------------------------------
def _cpu_burner(stop_event: threading.Event) -> None:
    """Бесконечный цикл, нагружающий одно ядро CPU."""
    x = 0
    while not stop_event.is_set():
        # Немного арифметики, чтобы Python не оптимизировал цикл.
        x = (x * 31 + 17) % 1_000_003


@app.get("/burn")
async def burn() -> JSONResponse:
    """
    Запускает новый поток, который грузит одно ядро CPU в бесконечном цикле.

    Каждый вызов добавляет +1 поток = +1 загруженное ядро.
    Чтобы остановить, надо перезапустить процесс (или реализовать /cool).
    """
    stop_event = threading.Event()
    thread = threading.Thread(
        target=_cpu_burner,
        args=(stop_event,),
        name=f"cpu-burner-{len(_burn_threads)}",
        daemon=True,  # не мешает корректному завершению процесса
    )

    with _burn_lock:
        _burn_threads.append(thread)
        _burn_stop_events.append(stop_event)
        active = len(_burn_threads)

    thread.start()

    return JSONResponse(
        {
            "status": "ok",
            "active_burners": active,
            "cpu_count": os.cpu_count(),
        }
    )


# ---------------------------------------------------------------------------
# (бонус) GET /stats — посмотреть текущее состояние
# ---------------------------------------------------------------------------
@app.get("/stats")
async def stats() -> dict[str, Any]:
    with _memory_lock:
        mem_mb = _memory_bytes_total // (1024 * 1024)
        chunks = len(_memory_chunks)
    with _burn_lock:
        burners = len(_burn_threads)

    return {
        "memory_allocated_mb": mem_mb,
        "memory_chunks": chunks,
        "active_burners": burners,
        "cpu_count": os.cpu_count(),
    }


# ---------------------------------------------------------------------------
# (бонус) GET /cool — остановить все CPU-нагрузчики
# ---------------------------------------------------------------------------
@app.get("/cool")
async def cool() -> dict[str, int]:
    with _burn_lock:
        stopped = len(_burn_stop_events)
        for ev in _burn_stop_events:
            ev.set()
        _burn_stop_events.clear()
        _burn_threads.clear()

    # Дадим потокам шанс завершиться.
    await asyncio.sleep(0.1)

    return {"stopped_burners": stopped}