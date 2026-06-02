"""Тесты check_task_status и polling_fragment (ui/app.py).

Кейсы 13-22 из docs/test_plan_ui.md, адаптированные к текущей реализации
(check_task_status + polling_fragment вместо poll_task_status).
"""

import time
from unittest.mock import MagicMock, patch

import requests

from ui.app import (
    API_URL,
    MAX_POLL_ATTEMPTS,
    check_task_status,
    polling_fragment,
)


# ---------------------------------------------------------------------------
# check_task_status() — одиночный запрос статуса
# ---------------------------------------------------------------------------


class TestCheckTaskStatus:
    """check_task_status() — одиночный HTTP-запрос статуса задачи."""

    def test_completed_200(self):
        """200 — задача завершена, возвращает данные."""
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"task_id": "abc", "status": "completed"}

        with patch("ui.app.requests.get", return_value=resp):
            result = check_task_status("abc")

        assert result == {"task_id": "abc", "status": "completed"}

    def test_pending_202(self):
        """202 — задача в очереди, возвращает данные."""
        resp = MagicMock()
        resp.status_code = 202
        resp.json.return_value = {"task_id": "abc", "status": "pending"}

        with patch("ui.app.requests.get", return_value=resp):
            result = check_task_status("abc")

        assert result["status"] == "pending"

    def test_not_found_404(self):
        """Кейс 17: 404 — задача не найдена, возвращает None."""
        resp = MagicMock()
        resp.status_code = 404

        with patch("ui.app.requests.get", return_value=resp) as mock_get:
            result = check_task_status("abc")

        assert result is None
        mock_get.assert_called_once_with(
            f"{API_URL}/api/v1/tasks/abc", timeout=10,
        )

    def test_unexpected_status_500(self):
        """Неожиданный HTTP-код (500) — возвращает None."""
        resp = MagicMock()
        resp.status_code = 500

        with patch("ui.app.requests.get", return_value=resp):
            result = check_task_status("abc")

        assert result is None

    def test_request_exception(self):
        """Кейс 18: RequestException — возвращает None."""
        with patch("ui.app.requests.get", side_effect=requests.RequestException):
            result = check_task_status("abc")

        assert result is None


# ---------------------------------------------------------------------------
# polling_fragment() — логика polling
# ---------------------------------------------------------------------------


class TestPollingFragment:
    """polling_fragment() — логика опроса статуса задачи."""

    def _make_state(self, **overrides):
        """Создаёт словарь session_state для polling."""
        state = {
            "task_id": "abc-123",
            "poll_attempts": 0,
            "poll_start_time": time.time(),
            "estimated_seconds": 150,
        }
        state.update(overrides)
        return state

    # Кейс 13: сразу completed
    def test_completed_fetches_result(self):
        state = self._make_state()

        with patch("ui.app.st") as mock_st, \
             patch("ui.app.check_task_status") as mock_check, \
             patch("ui.app.fetch_result") as mock_fetch:
            mock_st.session_state = state
            mock_st.button.return_value = False
            mock_check.return_value = {"status": "completed", "task_id": "abc-123"}
            mock_fetch.return_value = {"task_id": "abc-123", "data": {"personal_data": {}}}

            polling_fragment()

        assert state.get("result") == {"task_id": "abc-123", "data": {"personal_data": {}}}
        mock_st.rerun.assert_called_once()

    # completed, но fetch_result вернул None
    def test_completed_fetch_fails_shows_retry(self):
        state = self._make_state()

        with patch("ui.app.st") as mock_st, \
             patch("ui.app.check_task_status") as mock_check, \
             patch("ui.app.fetch_result") as mock_fetch:
            mock_st.session_state = state
            mock_st.button.return_value = False
            mock_check.return_value = {"status": "completed"}
            mock_fetch.return_value = None

            polling_fragment()

        assert "result" not in state
        # Должна быть кнопка повтора загрузки результата
        button_labels = [call[0][0] for call in mock_st.button.call_args_list]
        assert any("Повторить" in label for label in button_labels)

    # Кейс 16: задача failed
    def test_failed_shows_error(self):
        state = self._make_state()

        with patch("ui.app.st") as mock_st, \
             patch("ui.app.check_task_status") as mock_check:
            mock_st.session_state = state
            mock_st.button.return_value = False
            mock_check.return_value = {"status": "failed"}

            polling_fragment()

        mock_st.error.assert_called()
        # clear_polling_state должен удалить ключи
        assert "task_id" not in state

    # Кейс 18: ошибка сети при polling
    def test_network_error_shows_retry(self):
        state = self._make_state()

        with patch("ui.app.st") as mock_st, \
             patch("ui.app.check_task_status") as mock_check:
            mock_st.session_state = state
            mock_st.button.return_value = False
            mock_check.return_value = None

            polling_fragment()

        mock_st.error.assert_called()
        error_text = mock_st.error.call_args[0][0]
        assert "Не удалось получить статус" in error_text

    # Кейс 19: превышение max_attempts
    def test_max_attempts_exceeded(self):
        state = self._make_state(poll_attempts=MAX_POLL_ATTEMPTS)

        with patch("ui.app.st") as mock_st:
            mock_st.session_state = state
            mock_st.button.return_value = False

            polling_fragment()

        mock_st.error.assert_called()
        error_text = mock_st.error.call_args[0][0]
        assert "Превышено время ожидания" in error_text
        # Состояние должно быть очищено
        assert "task_id" not in state

    # Кейс 20: pending показывает прогресс и увеличивает попытки
    def test_pending_shows_progress(self):
        state = self._make_state()

        with patch("ui.app.st") as mock_st, \
             patch("ui.app.check_task_status") as mock_check:
            mock_st.session_state = state
            mock_st.button.return_value = False
            mock_check.return_value = {"status": "pending"}

            polling_fragment()

        # Прогресс теперь рендерится через st.markdown (кастомный HTML)
        md_calls = mock_st.markdown.call_args_list
        md_texts = " ".join(str(c) for c in md_calls)
        assert "cv-progress-bar-fill" in md_texts
        assert state["poll_attempts"] == 1

    # Кейс 21: прогресс для pending не превышает 95%
    def test_pending_progress_capped(self):
        # Устанавливаем poll_start_time далеко в прошлом
        state = self._make_state(
            poll_start_time=time.time() - 300,  # 5 минут назад
            estimated_seconds=10,  # мало времени -> большой прогресс
        )

        with patch("ui.app.st") as mock_st, \
             patch("ui.app.check_task_status") as mock_check:
            mock_st.session_state = state
            mock_st.button.return_value = False
            mock_check.return_value = {"status": "pending"}

            polling_fragment()

        # Проверяем, что в HTML нет значения > 95%
        md_calls = mock_st.markdown.call_args_list
        md_texts = " ".join(str(c) for c in md_calls)
        assert "width:95%" in md_texts

    # Кнопка отмены очищает состояние
    def test_cancel_button_clears_state(self):
        state = self._make_state()

        with patch("ui.app.st") as mock_st:
            mock_st.session_state = state
            # Первая кнопка — "Отменить ожидание", нажата
            mock_st.button.return_value = True

            polling_fragment()

        mock_st.rerun.assert_called_once()
        assert "task_id" not in state

    # Нет task_id — ранний выход
    def test_no_task_id_returns_early(self):
        with patch("ui.app.st") as mock_st:
            mock_st.session_state = {}

            polling_fragment()

        mock_st.error.assert_not_called()
        mock_st.rerun.assert_not_called()
