"""Юнит-тесты consumer loop: _consume_loop, process_message, run_consumer (ошибки, shutdown, reconnect)."""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aiokafka.errors import CommitFailedError, KafkaError

from worker.consumer import _consume_loop, process_message, run_consumer


def _kafka_message(value: dict):
    """Мок Kafka-сообщения."""
    msg = MagicMock()
    msg.value = json.dumps(value).encode("utf-8")
    msg.partition = 0
    msg.offset = 1
    return msg


class _AsyncIter:
    """Хелпер: оборачивает список в async-итератор для `async for`."""

    def __init__(self, items):
        self._items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration:
            raise StopAsyncIteration


# ---------------------------------------------------------------------------
# _consume_loop — обработка битых сообщений
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_consume_loop_skips_invalid_json():
    """Битый JSON в сообщении — логируется, сообщение пропускается, offset коммитится."""
    bad_msg = MagicMock()
    bad_msg.value = b"not a valid json{{{"
    bad_msg.partition = 0
    bad_msg.offset = 42

    consumer = MagicMock()
    consumer.__aiter__ = MagicMock(return_value=_AsyncIter([bad_msg]))
    consumer.commit = AsyncMock()

    await _consume_loop(consumer)

    # Коммит вызван (сообщение пропущено, но offset закоммичен)
    consumer.commit.assert_awaited()


@pytest.mark.asyncio
async def test_consume_loop_skips_invalid_message():
    """Сообщение без обязательных полей — пропускается, offset коммитится."""
    msg_data = {"task_id": str(uuid.uuid4())}  # нет file_path, file_type, file_name
    bad_msg = _kafka_message(msg_data)

    consumer = MagicMock()
    consumer.__aiter__ = MagicMock(return_value=_AsyncIter([bad_msg]))
    consumer.commit = AsyncMock()

    await _consume_loop(consumer)

    consumer.commit.assert_awaited()


# ---------------------------------------------------------------------------
# _consume_loop — graceful shutdown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_consume_loop_stops_on_shutdown():
    """При получении сигнала _shutting_down цикл прерывается."""
    import worker.consumer as mod

    valid_msg = _kafka_message({
        "task_id": str(uuid.uuid4()),
        "file_path": "/tmp/test.pdf",
        "file_type": "pdf",
        "file_name": "test.pdf",
    })

    consumer = MagicMock()
    consumer.__aiter__ = MagicMock(return_value=_AsyncIter([valid_msg]))
    consumer.commit = AsyncMock()

    # Устанавливаем флаг завершения
    mod._shutting_down = True
    try:
        await _consume_loop(consumer)
    finally:
        mod._shutting_down = False

    # process_message не должен был вызваться — commit тоже
    consumer.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# process_message — ошибка пайплайна
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_message_pipeline_error_sets_failed():
    """При ошибке пайплайна задача переводится в статус failed."""
    task_id = str(uuid.uuid4())
    msg_data = {
        "task_id": task_id,
        "file_path": "/tmp/test.pdf",
        "file_type": "pdf",
        "file_name": "test.pdf",
    }

    mock_session = MagicMock()

    with (
        patch("worker.consumer.get_session", return_value=mock_session),
        patch("worker.consumer.update_task_status") as mock_update,
        patch("worker.consumer.save_full_result"),
        patch(
            "worker.pipelines.text_pipeline.TextPipeline",
            side_effect=RuntimeError("Модель не загружена"),
        ),
    ):
        await process_message(msg_data)

    # Первый вызов: processing, второй: failed с сообщением об ошибке
    assert mock_update.call_count == 2
    failed_call = mock_update.call_args_list[1]
    assert failed_call[0][2] == "failed"
    assert "Модель не загружена" in failed_call[1]["error_msg"]


@pytest.mark.asyncio
async def test_process_message_invalid_cv_data():
    """При невалидных данных от модели CVResult.model_validate выбрасывает ошибку."""
    task_id = str(uuid.uuid4())
    msg_data = {
        "task_id": task_id,
        "file_path": "/tmp/test.pdf",
        "file_type": "pdf",
        "file_name": "test.pdf",
    }

    mock_session = MagicMock()
    mock_pipeline = MagicMock()
    # Пайплайн возвращает данные, которые не проходят валидацию
    mock_pipeline.process.return_value = {"invalid_key": 123}

    with (
        patch("worker.consumer.get_session", return_value=mock_session),
        patch("worker.consumer.update_task_status") as mock_update,
        patch("worker.consumer.save_full_result"),
        patch("worker.consumer.CVResult") as mock_cv,
    ):
        # Имитация ошибки валидации
        mock_cv.model_validate.side_effect = ValueError("Невалидные данные")
        with patch(
            "worker.pipelines.text_pipeline.TextPipeline",
            return_value=mock_pipeline,
        ):
            await process_message(msg_data)

    # Задача переведена в failed
    failed_call = mock_update.call_args_list[-1]
    assert failed_call[0][2] == "failed"


# ---------------------------------------------------------------------------
# _consume_loop — CommitFailedError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_consume_loop_handles_commit_failed():
    """CommitFailedError не прерывает цикл — consumer продолжает работу."""
    valid_msg = _kafka_message({
        "task_id": str(uuid.uuid4()),
        "file_path": "/tmp/test.pdf",
        "file_type": "pdf",
        "file_name": "test.pdf",
    })

    consumer = MagicMock()
    consumer.__aiter__ = MagicMock(return_value=_AsyncIter([valid_msg]))
    consumer.commit = AsyncMock(side_effect=CommitFailedError())

    with (
        patch("worker.consumer.process_message", new_callable=AsyncMock),
    ):
        await _consume_loop(consumer)

    # commit вызван, CommitFailedError не прервал цикл
    consumer.commit.assert_awaited()


# ---------------------------------------------------------------------------
# run_consumer — reconnect-логика
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_consumer_reconnects_on_kafka_error():
    """При KafkaError в start() consumer переподключается."""
    import worker.consumer as mod

    with (
        patch("worker.consumer.AIOKafkaConsumer") as mock_cls,
        patch("worker.consumer.settings") as mock_settings,
        patch("worker.consumer._consume_loop", new_callable=AsyncMock) as mock_loop,
        patch("worker.consumer.RECONNECT_BACKOFF_INITIAL", 0.01),
        patch("worker.consumer.RECONNECT_BACKOFF_MAX", 0.02),
    ):
        mock_settings.KAFKA_TOPIC = "cv-tasks"
        mock_settings.KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"

        mock_consumer = AsyncMock()
        mock_cls.return_value = mock_consumer

        # Первый start() падает KafkaError, второй — успешен
        mock_consumer.start.side_effect = [KafkaError("Connection refused"), None]

        # После успешного подключения — завершаем через _consume_loop
        async def _set_shutdown(*args, **kwargs):
            mod._shutting_down = True
        mock_loop.side_effect = _set_shutdown

        mod._shutting_down = False
        try:
            await run_consumer()
        finally:
            mod._shutting_down = False

    # Consumer пересоздаётся дважды (reconnect после ошибки)
    assert mock_cls.call_count == 2


@pytest.mark.asyncio
async def test_run_consumer_exits_on_shutdown():
    """При _shutting_down=True run_consumer завершается без подключений."""
    import worker.consumer as mod

    mod._shutting_down = True
    try:
        await run_consumer()
    finally:
        mod._shutting_down = False

    # Если _shutting_down установлен, цикл while не выполняется — без ошибок
