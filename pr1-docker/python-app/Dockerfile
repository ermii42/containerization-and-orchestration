FROM python:3.12-slim

# Не создавать .pyc и не буферизовать stdout (важно для логов)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Сначала зависимости — так кэш слоёв работает эффективнее
COPY python-app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Затем код приложения
COPY python-app/ .

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]