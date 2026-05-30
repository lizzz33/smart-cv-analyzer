"""Точка входа FastAPI-приложения."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_client import generate_latest

from api.config import settings
from api.db.connection import engine
from api.routers import tasks, upload
from api.services.kafka_producer import start_producer, stop_producer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Инициализация и очистка ресурсов приложения."""
    logger.info("API запускается, DATABASE_URL=%s", settings.DATABASE_URL.split("@")[-1])
    try:
        await start_producer()
    except Exception:
        logger.warning("Kafka недоступна — запуск без продюсера", exc_info=True)
    yield
    await stop_producer()
    await engine.dispose()
    logger.info("API остановлен")


app = FastAPI(
    title="smart-cv-analyzer API",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(upload.router)
app.include_router(tasks.router)


@app.get("/health")
async def health():
    """Проверка работоспособности сервиса."""
    return {"status": "ok"}


@app.get("/metrics")
async def metrics():
    """Экспорт метрик Prometheus."""
    from starlette.responses import Response

    return Response(content=generate_latest(), media_type="text/plain")
