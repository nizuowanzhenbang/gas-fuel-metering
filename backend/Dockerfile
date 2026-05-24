FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 项目以 `backend` 包形式运行，宿主层级是 /app/backend
COPY . /app/backend
WORKDIR /app

EXPOSE 8010

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8010"]
