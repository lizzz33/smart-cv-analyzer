"""Точка входа FastAPI-приложения."""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import generate_latest

from api.config import settings
from api.db.connection import engine
from api.metrics import cv_api_request_duration_seconds
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

# CORS: разрешаем запросы от Streamlit UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# --- Middleware для метрик latency ---

# Автогенерируемые пути FastAPI, исключаемые из метрик
_METRICS_SKIP_PATHS = frozenset({"/docs", "/openapi.json", "/redoc"})
# Тег маршрута для инфраструктурных эндпоинтов
_METRICS_SKIP_TAGS = frozenset({"infra"})


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Замер длительности HTTP-запросов и запись в Prometheus Histogram."""
    start = time.monotonic()
    response: Response = await call_next(request)

    route = request.scope.get("route")

    # Пропускаем незарегистрированные маршруты (route=None),
    # чтобы избежать cardinality explosion от уникальных URL
    if route is None:
        return response

    # Пропускаем инфраструктурные эндпоинты по пути или тегу
    if route.path in _METRICS_SKIP_PATHS:
        return response
    route_tags = getattr(route, "tags", [])
    if _METRICS_SKIP_TAGS.intersection(route_tags):
        return response

    # route.path содержит шаблон вида /api/v1/tasks/{task_id},
    # а не конкретный UUID — это предотвращает cardinality explosion
    cv_api_request_duration_seconds.labels(
        method=request.method,
        endpoint=route.path,
        status_code=response.status_code,
    ).observe(time.monotonic() - start)

    return response


# --- Служебные эндпоинты ---


@app.get("/health", tags=["infra"])
async def health():
    """Проверка работоспособности сервиса."""
    return {"status": "ok"}


@app.get("/metrics", tags=["infra"])
async def metrics():
    """Экспорт метрик Prometheus."""
    return Response(content=generate_latest(), media_type="text/plain")
