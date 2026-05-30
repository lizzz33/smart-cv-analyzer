"""Тесты upload_file и fetch_result (ui/app.py).

Кейсы 1-12 из docs/test_plan_ui.md.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from ui.app import API_URL, fetch_result, upload_file


# ---------------------------------------------------------------------------
# upload_file()
# ---------------------------------------------------------------------------


class TestUploadFile:
    """upload_file() — отправка файла в API."""

    # Кейс 1: успешная загрузка — 202
    def test_success_returns_response(self):
        resp = MagicMock()
        resp.status_code = 202
        resp.json.return_value = {
            "task_id": "abc-123",
            "status": "pending",
            "estimated_seconds": 150,
        }

        with patch("ui.app.requests.post", return_value=resp) as mock_post, \
             patch("ui.app.st"):
            result = upload_file(b"content", "resume.pdf")

        assert result == {
            "task_id": "abc-123",
            "status": "pending",
            "estimated_seconds": 150,
        }
        mock_post.assert_called_once_with(
            f"{API_URL}/api/v1/upload",
            files={"file": ("resume.pdf", b"content")},
            timeout=30,
        )

    # Кейс 2: ошибка валидации — 422
    def test_validation_error(self):
        resp = MagicMock()
        resp.status_code = 422
        resp.json.return_value = {"detail": "File size exceeds 1 MB limit"}

        with patch("ui.app.requests.post", return_value=resp), \
             patch("ui.app.st") as mock_st:
            result = upload_file(b"big", "file.pdf")

        assert result is None
        mock_st.error.assert_called_once()
        assert "File size exceeds 1 MB limit" in mock_st.error.call_args[0][0]

    # Кейс 3: серверная ошибка — 500
    def test_server_error(self):
        resp = MagicMock()
        resp.status_code = 500
        resp.json.return_value = {"detail": "Internal error"}

        with patch("ui.app.requests.post", return_value=resp), \
             patch("ui.app.st") as mock_st:
            result = upload_file(b"data", "file.pdf")

        assert result is None
        mock_st.error.assert_called_once()

    # Кейс 4-5: ошибки сети (ConnectionError, Timeout)
    @pytest.mark.parametrize(
        "exc, expected_text",
        [
            (requests.ConnectionError, "Не удалось подключиться"),
            (requests.Timeout, "Превышено время ожидания"),
        ],
        ids=["connection-error", "timeout"],
    )
    def test_network_errors(self, exc, expected_text):
        with patch("ui.app.requests.post", side_effect=exc), \
             patch("ui.app.st") as mock_st:
            result = upload_file(b"data", "file.pdf")

        assert result is None
        assert expected_text in mock_st.error.call_args[0][0]

    # Кейс 6: неожиданное исключение
    def test_unexpected_exception(self):
        with patch("ui.app.requests.post", side_effect=RuntimeError("boom")), \
             patch("ui.app.st") as mock_st:
            result = upload_file(b"data", "file.pdf")

        assert result is None
        assert "неожиданная ошибка" in mock_st.error.call_args[0][0]


# ---------------------------------------------------------------------------
# fetch_result()
# ---------------------------------------------------------------------------


class TestFetchResult:
    """fetch_result() — получение результата обработки."""

    # Кейс 8: успешное получение — 200
    def test_success(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"task_id": "abc", "data": {"personal_data": {}}}

        with patch("ui.app.requests.get", return_value=resp), \
             patch("ui.app.st"):
            result = fetch_result("abc")

        assert result == {"task_id": "abc", "data": {"personal_data": {}}}

    # Кейс 9: результат не найден — 404
    def test_not_found(self):
        resp = MagicMock()
        resp.status_code = 404
        resp.json.return_value = {"detail": "Task not found"}

        with patch("ui.app.requests.get", return_value=resp), \
             patch("ui.app.st") as mock_st:
            result = fetch_result("abc")

        assert result is None
        mock_st.error.assert_called_once()

    # Кейс 11: ошибка сети — RequestException
    def test_network_error(self):
        with patch("ui.app.requests.get", side_effect=requests.RequestException), \
             patch("ui.app.st") as mock_st:
            result = fetch_result("abc")

        assert result is None
        mock_st.error.assert_called_once()


