"""Точка входа воркера: запуск Kafka consumer loop."""

import asyncio
import logging

from worker.consumer import install_signal_handlers, run_consumer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


def main():
    install_signal_handlers()
    logger.info("Запуск worker...")
    asyncio.run(run_consumer())


if __name__ == "__main__":
    main()
