"""Юнит-тесты Kafka producer: start, stop, publish, RuntimeError при отсутствии."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from api.services.kafka_producer import _get_producer, publish_task


def test_get_producer_without_init_raises():
    """_get_producer выбрасывает RuntimeError, если producer не запущен."""
    with patch("api.services.kafka_producer._producer", None):
        with pytest.raises(RuntimeError, match="Kafka producer не инициализирован"):
            _get_producer()


@pytest.mark.asyncio
async def test_publish_task_sends_correct_message():
    """publish_task отправляет JSON с правильными полями в Kafka."""
    task_id = "11111111-2222-3333-4444-555555555555"
    file_path = "/tmp/test.pdf"
    file_type = "pdf"
    file_name = "test.pdf"

    mock_producer = AsyncMock()
    with (
        patch("api.services.kafka_producer._producer", mock_producer),
        patch("api.services.kafka_producer._get_producer", return_value=mock_producer),
        patch("api.services.kafka_producer.settings") as mock_settings,
    ):
        mock_settings.KAFKA_TOPIC = "cv-tasks"
        await publish_task(task_id, file_path, file_type, file_name)

    mock_producer.send_and_wait.assert_called_once()
    call_args = mock_producer.send_and_wait.call_args
    # Топик
    assert call_args[0][0] == "cv-tasks"
    # Тело сообщения
    sent_value = json.loads(call_args[1]["value"].decode("utf-8"))
    assert sent_value == {
        "task_id": task_id,
        "file_path": file_path,
        "file_type": file_type,
        "file_name": file_name,
    }


@pytest.mark.asyncio
async def test_start_producer_creates_and_starts():
    """start_producer создаёт AIOKafkaProducer и вызывает start()."""
    with (
        patch("api.services.kafka_producer.AIOKafkaProducer") as mock_cls,
        patch("api.services.kafka_producer.settings") as mock_settings,
    ):
        mock_settings.KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
        mock_instance = AsyncMock()
        mock_cls.return_value = mock_instance

        # Сбрасываем глобальное состояние
        import api.services.kafka_producer as mod

        mod._producer = None
        await mod.start_producer()

    mock_cls.assert_called_once_with(bootstrap_servers="localhost:9092")
    mock_instance.start.assert_called_once()


@pytest.mark.asyncio
async def test_stop_producer_closes_and_resets():
    """stop_producer вызывает stop() и обнуляет глобальную переменную."""
    import api.services.kafka_producer as mod

    mock_producer = AsyncMock()
    mod._producer = mock_producer

    await mod.stop_producer()

    mock_producer.stop.assert_called_once()
    assert mod._producer is None
