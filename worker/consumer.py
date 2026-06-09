"""Kafka consumer loop: получение задач из топика cv-tasks."""

import asyncio
import json
import logging
import signal
import time
import uuid

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import CommitFailedError, KafkaError

from worker.config import settings
from worker.db.connection import get_session
from worker.db.crud import save_full_result, update_task_status
from worker.metrics import (
    cv_by_format_total,
    cv_failed_total,
    cv_processed_total,
    cv_processing_duration_seconds,
    update_ram_usage,
)
from worker.schemas.cv import CVResult

logger = logging.getLogger(__name__)

CONSUMER_GROUP = "cv-worker-group"

# Типы файлов для текстового пайплайна
TEXT_FILE_TYPES = {"pdf", "docx", "odt"}
# Все поддерживаемые типы файлов
SUPPORTED_FILE_TYPES = TEXT_FILE_TYPES | {"jpeg", "jpg", "png"}

# Обязательные поля в сообщении Kafka
REQUIRED_FIELDS = {"task_id", "file_path", "file_type", "file_name"}

# Параметры переподключения
RECONNECT_BACKOFF_INITIAL = 5.0
RECONNECT_BACKOFF_MAX = 120.0

_shutting_down = False


def _request_shutdown():
    global _shutting_down
    _shutting_down = True
    logger.info("Получен сигнал завершения, graceful shutdown...")


def install_signal_handlers():
    """Установка обработчиков SIGTERM/SIGINT для graceful shutdown."""
    signal.signal(signal.SIGTERM, lambda *_: _request_shutdown())
    signal.signal(signal.SIGINT, lambda *_: _request_shutdown())


def _validate_message(msg_data: dict) -> str | None:
    """Валидация сообщения. Возвращает описание ошибки или None."""
    missing = REQUIRED_FIELDS - msg_data.keys()
    if missing:
        return f"нет обязательных полей: {missing}"
    try:
        uuid.UUID(msg_data["task_id"])
    except (ValueError, AttributeError, TypeError):
        return f"некорректный task_id={msg_data.get('task_id')!r}"
    if msg_data["file_type"] not in SUPPORTED_FILE_TYPES:
        return f"неподдерживаемый file_type={msg_data['file_type']}"
    return None


def _process_message_sync(msg_data: dict) -> None:
    """Синхронная логика обработки задачи (выполняется в отдельном потоке).

    Вся работа с БД (SQLAlchemy sync) и моделями вынесена сюда,
    чтобы не блокировать event loop aiokafka.
    """
    task_id = uuid.UUID(msg_data["task_id"])
    file_type = msg_data["file_type"]
    file_path = msg_data["file_path"]

    start_time = time.monotonic()
    session = None
    try:
        session = get_session()

        # Проверяем, существует ли задача (обработка старых сообщений из Kafka)
        from sqlalchemy import text
        task_exists = session.execute(
            text("SELECT 1 FROM tasks WHERE id = :task_id"),
            {"task_id": task_id}
        ).scalar_one_or_none()

        if task_exists is None:
            logger.warning(
                "Задача %s не найдена в БД (вероятно, старое сообщение из Kafka), пропуск",
                task_id
            )
            return  # Пропкаем обработку, но коммитим offset в Kafka

        update_task_status(session, task_id, "processing")

        if file_type in TEXT_FILE_TYPES:
            from worker.pipelines.text_pipeline import TextPipeline

            pipeline = TextPipeline()
            result = pipeline.process(file_path)
        else:
            from worker.pipelines.vision_pipeline import VisionPipeline

            pipeline = VisionPipeline()
            result = pipeline.process(file_path)

        cv = CVResult.model_validate(result)
        save_full_result(session, task_id, result, cv)
        update_task_status(session, task_id, "completed")
        session.commit()

        # Метрики: успех
        duration = time.monotonic() - start_time
        cv_processing_duration_seconds.labels(file_type=file_type).observe(duration)
        cv_processed_total.labels(file_type=file_type).inc()
        cv_by_format_total.labels(format=file_type).inc()
        logger.info("Задача завершена успешно: task_id=%s, duration=%.1f сек", task_id, duration)
    except Exception as e:
        error_msg = str(e)
        cv_failed_total.labels(file_type=file_type).inc()
        cv_by_format_total.labels(format=file_type).inc()
        if session is not None:
            try:
                session.rollback()
                update_task_status(session, task_id, "failed", error_msg=error_msg)
                session.commit()
            except Exception:
                logger.exception(
                    "КРИТИЧНО: не удалось обновить статус задачи %s на 'failed' — "
                    "задача может зависнуть в 'processing'. Требуется ручное вмешательство.",
                    task_id,
                )
        logger.exception("Ошибка обработки задачи: task_id=%s", task_id)
    finally:
        if session is not None:
            session.close()
        # Обновление метрики RAM после каждой задачи
        update_ram_usage()


async def process_message(msg_data: dict) -> None:
    """Обработка одной задачи: маршрутизация по типу файла к нужному пайплайну."""
    logger.info(
        "Обработка задачи: task_id=%s, file_type=%s, file_path=%s",
        msg_data["task_id"],
        msg_data["file_type"],
        msg_data["file_path"],
    )
    await asyncio.to_thread(_process_message_sync, msg_data)


async def _consume_loop(consumer: AIOKafkaConsumer) -> None:
    """Внутренний цикл потребления сообщений.

    Использует getmany с таймаутом 2 сек вместо async for,
    чтобы периодически проверять флаг _shutting_down и корректно
    завершать работу даже при отсутствии новых сообщений.
    """
    while not _shutting_down:
        try:
            batches = await consumer.getmany(timeout_ms=2000, max_records=1)
        except Exception:
            logger.exception("Ошибка при получении сообщений из Kafka")
            continue

        if _shutting_down:
            logger.info("Shutdown — завершаю обработку")
            break

        for _tp, messages in batches.items():
            for message in messages:
                # Парсинг JSON
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

                # Валидация схемы сообщения
                validation_error = _validate_message(msg_data)
                if validation_error:
                    logger.warning("Пропуск: %s: offset=%d", validation_error, message.offset)
                    await consumer.commit()
                    continue

                # Обработка с защитой от краша
                try:
                    await process_message(msg_data)
                except Exception:
                    logger.exception("Необработанная ошибка: offset=%d", message.offset)

                # Коммит offset в любом случае
                try:
                    await consumer.commit()
                except CommitFailedError:
                    logger.exception("Ошибка коммита offset")


async def run_consumer() -> None:
    """Основной цикл потребления сообщений из Kafka с переподключением."""
    backoff = RECONNECT_BACKOFF_INITIAL
    while not _shutting_down:
        consumer = AIOKafkaConsumer(
            settings.KAFKA_TOPIC,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id=CONSUMER_GROUP,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        try:
            await consumer.start()
            logger.info("Worker запущен, слушаю топик %s", settings.KAFKA_TOPIC)
            backoff = RECONNECT_BACKOFF_INITIAL
            await _consume_loop(consumer)
        except KafkaError:
            logger.exception("Ошибка Kafka, переподключение через %.1f сек", backoff)
        except Exception:
            logger.exception("Неожиданная ошибка consumer, переподключение через %.1f сек", backoff)
        finally:
            await consumer.stop()
            logger.info("Consumer остановлен")

        if not _shutting_down:
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, RECONNECT_BACKOFF_MAX)
