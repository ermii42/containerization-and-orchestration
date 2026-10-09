import asyncio
import httpx
from typing import Optional

async def generate_load(
    base_url: str,
    concurrent: int = 10,
    total: int = 50,
    target: str = "/health"
) -> dict:
    """Параллельно дёргает указанный эндпоинт."""
    results = {"total": total, "success": 0, "failed": 0}

    async with httpx.AsyncClient(timeout=10.0) as client:
        sem = asyncio.Semaphore(concurrent)

        async def one_request(idx: int):
            async with sem:
                try:
                    r = await client.get(f"{base_url}{target}")
                    if r.status_code < 500:
                        results["success"] += 1
                    else:
                        results["failed"] += 1
                except Exception:
                    results["failed"] += 1

        tasks = [one_request(i) for i in range(total)]
        await asyncio.gather(*tasks)

    return results