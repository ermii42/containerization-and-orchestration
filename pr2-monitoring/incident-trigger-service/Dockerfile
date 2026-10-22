FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.12-slim

WORKDIR /app

# Копируем зависимости из builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONPATH=/root/.local/lib/python3.12/site-packages:$PYTHONPATH

# Копируем приложение
COPY app/ ./app/

# Непривилегированный пользователь
# RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app /root/.local && \
    chmod 755 /root
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]