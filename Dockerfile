FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --gid 10001 axiomrisk \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin axiomrisk

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/data \
    && chown -R axiomrisk:axiomrisk /app/data \
    && chmod 750 /app/data

USER 10001:10001

EXPOSE 8765
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765", "--proxy-headers"]
