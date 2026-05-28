"""Prometheus-метрики сервиса."""

from prometheus_client import Counter, Gauge

cv_uploads_total = Counter(
    "cv_uploads_total",
    "Общее количество успешно загруженных файлов",
)

cv_upload_errors_total = Counter(
    "cv_upload_errors_total",
    "Ошибки при загрузке файлов (валидация)",
)

cv_tasks_in_progress = Gauge(
    "cv_tasks_in_progress",
    "Задачи со статусом pending или processing",
)
