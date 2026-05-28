"""Kafka consumer loop: получение задач из топика cv-tasks."""

import asyncio
import json
import logging
import signal
import uuid

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import CommitFailedError

from worker.config import settings
from worker.db.connection import get_session
from worker.db.crud import save_result, update_task_status

logger = logging.getLogger(__name__)

KAFKA_TOPIC = "cv-tasks"
CONSUMER_GROUP = "cv-worker-group"

# Типы файлов для текстового пайплайна
TEXT_FILE_TYPES = {"pdf", "docx", "odt"}

_shutting_down = False


def _request_shutdown():
    global _shutting_down
    _shutting_down = True
    logger.info("Получен сигнал завершения, graceful shutdown...")


def install_signal_handlers():
    """Установка обработчиков SIGTERM/SIGINT для graceful shutdown."""
    signal.signal(signal.SIGTERM, lambda *_: _request_shutdown())
    signal.signal(signal.SIGINT, lambda *_: _request_shutdown())


async def process_message(msg_data: dict) -> None:
    """Обработка одной задачи: маршрутизация по типу файла к нужному пайплайну."""
    task_id = uuid.UUID(msg_data["task_id"])
    file_type = msg_data["file_type"]
    file_path = msg_data["file_path"]
    logger.info("Обработка задачи: task_id=%s, file_type=%s, file_path=%s", task_id, file_type, file_path)

    session = get_session()
    try:
        update_task_status(session, task_id, "processing")
        logger.info("Статус обновлён на processing: task_id=%s", task_id)

        if file_type in TEXT_FILE_TYPES:
            from worker.pipelines.text_pipeline import TextPipeline
            pipeline = TextPipeline()
            result = await asyncio.to_thread(pipeline.process, file_path)
        else:
            raise NotImplementedError(f"Пайплайн для типа {file_type} не реализован")

        save_result(session, task_id, result)
        update_task_status(session, task_id, "completed")
        logger.info("Задача завершена успешно: task_id=%s", task_id)
    except Exception as e:
        error_msg = str(e)
        update_task_status(session, task_id, "failed", error_msg=error_msg)
        logger.exception("Ошибка обработки задачи: task_id=%s", task_id)
    finally:
        session.close()


async def run_consumer() -> None:
    """Основной цикл потребления сообщений из Kafka."""
    consumer = AIOKafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=CONSUMER_GROUP,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )

    await consumer.start()
    logger.info("Worker запущен, слушаю топик %s", KAFKA_TOPIC)

    try:
        async for message in consumer:
            if _shutting_down:
                logger.info("Shutdown — завершаю обработку")
                break

            try:
                msg_data = json.loads(message.value.decode("utf-8"))
                logger.info(
                    "Получено сообщение: partition=%d, offset=%d",
                    message.partition,
                    message.offset,
                )
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.exception("Некорректное сообщение, пропуск: offset=%d", message.offset)
                await consumer.commit()
                continue

            await process_message(msg_data)

            try:
                await consumer.commit()
            except CommitFailedError:
                logger.exception("Ошибка коммита offset: task_id=%s", msg_data.get("task_id"))

    finally:
        await consumer.stop()
        logger.info("Consumer остановлен")
