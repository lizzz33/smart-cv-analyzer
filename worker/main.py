"""Точка входа воркера: запуск Kafka consumer loop + HTTP metrics-сервер."""

import asyncio
import logging
import threading

from prometheus_client import start_http_server

from worker.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


def _start_metrics_server() -> None:
    """Запуск HTTP-сервера для экспорта метрик Prometheus в фоновом потоке."""
    start_http_server(settings.METRICS_PORT)
    logger.info("Metrics-сервер запущен на порту %d", settings.METRICS_PORT)


def main():
    # Импорт здесь, чтобы lazy-load тяжёлые зависимости (torch, transformers)
    from worker.consumer import install_signal_handlers, run_consumer

    # Запуск metrics-сервера в отдельном потоке
    metrics_thread = threading.Thread(
        target=_start_metrics_server,
        daemon=True,
        name="metrics-server",
    )
    metrics_thread.start()

    install_signal_handlers()
    logger.info("Запуск worker...")
    asyncio.run(run_consumer())


if __name__ == "__main__":
    main()
