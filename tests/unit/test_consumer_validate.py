"""Тесты валидации Kafka-сообщений."""

import uuid

import pytest

from worker.consumer import _validate_message


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
