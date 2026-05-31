"""Prometheus-метрики API-сервиса."""

from prometheus_client import Counter, Gauge, Histogram

# --- Счётчики загрузок ---

cv_uploads_total = Counter(
    "cv_uploads_total",
    "Общее количество успешно загруженных файлов",
)

cv_upload_errors_total = Counter(
    "cv_upload_errors_total",
    "Ошибки при загрузке файлов (валидация, сохранение)",
)

# --- Очередь задач ---

cv_tasks_in_progress = Gauge(
    "cv_tasks_in_progress",
    "Задачи со статусом pending или processing",
)

# --- Latency HTTP-запросов ---

cv_api_request_duration_seconds = Histogram(
    "cv_api_request_duration_seconds",
    "Длительность обработки HTTP-запросов",
    labelnames=["method", "endpoint", "status_code"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
