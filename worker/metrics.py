"""Prometheus-метрики Worker-сервиса."""

import os
import logging

from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

# --- Обработка резюме ---

cv_processing_duration_seconds = Histogram(
    "cv_processing_duration_seconds",
    "Время обработки одного резюме (секунды)",
    labelnames=["file_type"],
    buckets=(10, 30, 60, 120, 180, 300, 600),
)

cv_processed_total = Counter(
    "cv_processed_total",
    "Успешно обработанных резюме",
    labelnames=["file_type"],
)

cv_failed_total = Counter(
    "cv_failed_total",
    "Ошибок обработки резюме",
    labelnames=["file_type"],
)

cv_by_format_total = Counter(
    "cv_by_format_total",
    "Резюме по форматам файлов",
    labelnames=["format"],
)

# --- Модели ---

cv_model_load_duration_seconds = Histogram(
    "cv_model_load_duration_seconds",
    "Время загрузки модели (секунды)",
    labelnames=["model_type"],
    buckets=(5, 10, 30, 60, 120, 300),
)

# --- Ресурсы ---

cv_ram_usage_bytes = Gauge(
    "cv_ram_usage_bytes",
    "Потребление RAM воркером (байты)",
)


_psutil_process = None


def _get_psutil_process():
    """Получение кэшированного экземпляра psutil.Process."""
    global _psutil_process
    if _psutil_process is None:
        import psutil

        _psutil_process = psutil.Process(os.getpid())
    return _psutil_process


def update_ram_usage():
    """Обновление метрики потребления RAM."""
    try:
        process = _get_psutil_process()
    except (ImportError, OSError):
        logger.debug("psutil недоступен — метрика RAM не обновляется")
        return
    try:
        mem_info = process.memory_info()
        cv_ram_usage_bytes.set(mem_info.rss)
    except Exception:
        logger.debug("Не удалось получить информацию о памяти", exc_info=True)
