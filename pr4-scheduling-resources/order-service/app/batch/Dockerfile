FROM python:3.12-slim

# непривилегированный пользователь
RUN useradd -r -u 10001 -m batch
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt || true

COPY main.py .

USER batch
ENV CPU_THREADS=2 \
    MEM_STEP_MB=50 \
    MEM_SLEEP=1.0 \
    MEM_LIMIT_MB=1024 \
    PYTHONUNBUFFERED=1

CMD ["python", "-u", "main.py"]