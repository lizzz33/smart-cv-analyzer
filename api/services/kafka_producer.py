"""Kafka producer: отправка задач в топик cv-tasks."""

import json
import logging

from aiokafka import AIOKafkaProducer

from api.config import settings

logger = logging.getLogger(__name__)

KAFKA_TOPIC = "cv-tasks"

_producer: AIOKafkaProducer | None = None


def _get_producer() -> AIOKafkaProducer:
    if _producer is None:
        raise RuntimeError("Kafka producer не инициализирован")
    return _producer


async def start_producer() -> None:
    """Инициализация и запуск Kafka producer."""
    global _producer
    _producer = AIOKafkaProducer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
    )
    await _producer.start()
    logger.info("Kafka producer запущен, servers=%s", settings.KAFKA_BOOTSTRAP_SERVERS)


async def stop_producer() -> None:
    """Остановка Kafka producer."""
    if _producer is not None:
        await _producer.stop()
        _producer = None
        logger.info("Kafka producer остановлен")


async def publish_task(
    task_id: str,
    file_path: str,
    file_type: str,
    file_name: str,
) -> None:
    """Отправить сообщение о задаче в топик cv-tasks."""
    message = {
        "task_id": task_id,
        "file_path": file_path,
        "file_type": file_type,
        "file_name": file_name,
    }
    producer = _get_producer()
    await producer.send_and_wait(
        KAFKA_TOPIC,
        value=json.dumps(message).encode("utf-8"),
    )
    logger.info("Сообщение отправлено в Kafka: task_id=%s", task_id)
