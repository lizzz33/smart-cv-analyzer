"""Тесты валидации Kafka-сообщений и роутинга по типу файла."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from worker.consumer import TEXT_FILE_TYPES, _validate_message, process_message


def _valid_msg(**overrides):
    """Полное корректное сообщение."""
    msg = {
        "task_id": str(uuid.uuid4()),
        "file_path": "/tmp/test.pdf",
        "file_type": "pdf",
        "file_name": "test.pdf",
    }
    msg.update(overrides)
    return msg


# ---------------------------------------------------------------------------
# Валидация сообщений
# ---------------------------------------------------------------------------


def test_valid_message():
    assert _validate_message(_valid_msg()) is None


def test_missing_file_path():
    msg = _valid_msg()
    del msg["file_path"]
    result = _validate_message(msg)
    assert result is not None
    assert "file_path" in result


def test_invalid_task_id():
    msg = _valid_msg(task_id="not-a-uuid")
    result = _validate_message(msg)
    assert result is not None
    assert "task_id" in result


@pytest.mark.parametrize("file_type", ["exe", "txt", "gif", "bmp"])
def test_unsupported_file_type(file_type):
    msg = _valid_msg(file_type=file_type)
    result = _validate_message(msg)
    assert result is not None
    assert "file_type" in result


# ---------------------------------------------------------------------------
# Валидация image-типов
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("file_type", ["jpeg", "jpg", "png"])
def test_image_file_types_are_supported(file_type):
    """Изображения (jpeg, jpg, png) проходят валидацию."""
    msg = _valid_msg(file_type=file_type)
    assert _validate_message(msg) is None


# ---------------------------------------------------------------------------
# Роутинг: text vs vision pipeline
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("file_type", sorted(TEXT_FILE_TYPES))
@pytest.mark.asyncio
async def test_text_file_routes_to_text_pipeline(file_type):
    """Текстовые типы файлов направляются в TextPipeline."""
    task_id = str(uuid.uuid4())
    msg = _valid_msg(task_id=task_id, file_type=file_type)

    with (
        patch("worker.consumer.get_session") as mock_session,
        patch("worker.consumer.update_task_status"),
        patch("worker.consumer.save_full_result"),
        patch("worker.consumer.CVResult") as mock_cv,
    ):
        mock_sess = MagicMock()
        mock_session.return_value = mock_sess
        mock_cv.model_validate.return_value = MagicMock()

        with patch("worker.pipelines.text_pipeline.TextPipeline") as mock_cls:
            mock_pipeline = MagicMock()
            mock_pipeline.process.return_value = {"personal_data": {}}
            mock_cls.return_value = mock_pipeline

            await process_message(msg)

            mock_cls.assert_called_once()
            mock_pipeline.process.assert_called_once_with(msg["file_path"])


@pytest.mark.parametrize("file_type", ["jpeg", "jpg", "png"])
@pytest.mark.asyncio
async def test_image_file_routes_to_vision_pipeline(file_type):
    """Image-типы файлов направляются в VisionPipeline."""
    task_id = str(uuid.uuid4())
    msg = _valid_msg(task_id=task_id, file_type=file_type)

    with (
        patch("worker.consumer.get_session") as mock_session,
        patch("worker.consumer.update_task_status"),
        patch("worker.consumer.save_full_result"),
        patch("worker.consumer.CVResult") as mock_cv,
    ):
        mock_sess = MagicMock()
        mock_session.return_value = mock_sess
        mock_cv.model_validate.return_value = MagicMock()

        with patch("worker.pipelines.vision_pipeline.VisionPipeline") as mock_cls:
            mock_pipeline = MagicMock()
            mock_pipeline.process.return_value = {"personal_data": {}}
            mock_cls.return_value = mock_pipeline

            await process_message(msg)

            mock_cls.assert_called_once()
            mock_pipeline.process.assert_called_once_with(msg["file_path"])
