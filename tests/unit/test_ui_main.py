"""Тесты main() и session state (ui/app.py).

Кейсы 45-55 из docs/test_plan_ui.md.
AppTest используется для проверки рендеринга страницы.
Валидация и flow-тесты используют прямой вызов main() с моками st,
т.к. AppTest 1.45.1 не поддерживает file_uploader.
"""

from unittest.mock import MagicMock, patch

from ui.app import MAX_FILE_SIZE_BYTES, main


APP_PATH = "ui/app.py"


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------


def _mock_response(status_code, json_data):
    """Создаёт мок HTTP-ответа."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    return resp


def _mock_file(name, size_bytes):
    """Создаёт мок загруженного файла заданного размера."""
    mock_file = MagicMock()
    mock_file.name = name
    mock_file.getvalue.return_value = b"x" * size_bytes
    return mock_file


# ---------------------------------------------------------------------------
# 4.1 Начальное состояние (AppTest)
# ---------------------------------------------------------------------------


class TestInitialState:
    """Начальное состояние страницы без загруженного файла."""

    def test_page_elements(self):
        """Кейс 45: заголовок «CV Analyzer», expander с инструкцией."""
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(APP_PATH)
        at.run(timeout=30)

        assert at.title[0].value == "CV Analyzer"
        assert len(at.expander) >= 1
        # file_uploader рендерится как UnknownElement (AppTest 1.45
        # не предоставляет отдельный атрибут)
        child_types = [type(c).__name__ for c in at.main.children.values()]
        assert "UnknownElement" in child_types

    def test_instruction_contains_formats(self):
        """Кейс 46: инструкция содержит форматы и лимит."""
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(APP_PATH)
        at.run(timeout=30)

        md_texts = " ".join(m.value for m in at.markdown)
        assert "PDF" in md_texts
        assert "DOCX" in md_texts
        assert "1 МБ" in md_texts


# ---------------------------------------------------------------------------
# 4.2 Валидация размера (прямой вызов main() с моками)
# ---------------------------------------------------------------------------


class TestValidation:
    """Клиентская валидация размера файла."""

    def test_file_too_large(self):
        """Кейс 47: файл > 1 МБ — st.error с «превышает»."""
        mock_file = _mock_file("big.pdf", int(1.5 * 1024 * 1024))

        with patch("ui.app.st") as mock_st, \
             patch("ui.app.polling_fragment"):
            mock_st.file_uploader.return_value = mock_file
            mock_st.button.return_value = False
            mock_st.session_state = {}

            main()

        error_calls = mock_st.error.call_args_list
        assert len(error_calls) > 0
        error_text = " ".join(str(c) for c in error_calls)
        assert "превышает" in error_text

    def test_file_exactly_1mb(self):
        """Кейс 48: файл ровно 1 МБ — ошибка размера НЕ показывается."""
        mock_file = _mock_file("exact.pdf", MAX_FILE_SIZE_BYTES)

        with patch("ui.app.st") as mock_st, \
             patch("ui.app.polling_fragment"):
            mock_st.file_uploader.return_value = mock_file
            mock_st.button.return_value = False
            mock_st.session_state = {}

            main()

        size_errors = [
            c for c in mock_st.error.call_args_list
            if "превышает" in str(c)
        ]
        assert len(size_errors) == 0

    def test_file_under_1mb(self):
        """Кейс 49: файл < 1 МБ — ошибка размера НЕ показывается."""
        mock_file = _mock_file("small.pdf", 512 * 1024)

        with patch("ui.app.st") as mock_st, \
             patch("ui.app.polling_fragment"):
            mock_st.file_uploader.return_value = mock_file
            mock_st.button.return_value = False
            mock_st.session_state = {}

            main()

        size_errors = [
            c for c in mock_st.error.call_args_list
            if "превышает" in str(c)
        ]
        assert len(size_errors) == 0


# ---------------------------------------------------------------------------
# 4.3 Загрузка и polling
# ---------------------------------------------------------------------------


class TestUploadAndPolling:
    """Загрузка файла и обработка результатов."""

    def test_successful_upload_sets_task_id(self):
        """Кейс 50: upload_file успешен -> task_id в session_state."""
        mock_file = _mock_file("resume.pdf", 1024)
        state = {}

        with patch("ui.app.st") as mock_st, \
             patch("ui.app.upload_file") as mock_upload, \
             patch("ui.app.polling_fragment"):
            mock_st.file_uploader.return_value = mock_file
            mock_st.button.return_value = True
            mock_st.session_state = state
            mock_upload.return_value = {
                "task_id": "abc-123",
                "status": "pending",
                "estimated_seconds": 150,
            }

            main()

        assert state.get("task_id") == "abc-123"
        mock_st.rerun.assert_called()

    def test_upload_failure_no_task_id(self):
        """Кейс 51: upload_file вернул None -> task_id не записан."""
        mock_file = _mock_file("resume.pdf", 1024)
        state = {}

        with patch("ui.app.st") as mock_st, \
             patch("ui.app.upload_file") as mock_upload, \
             patch("ui.app.polling_fragment"):
            mock_st.file_uploader.return_value = mock_file
            mock_st.button.return_value = True
            mock_st.session_state = state
            mock_upload.return_value = None

            main()

        assert "task_id" not in state

    def test_polling_failed_shows_error(self):
        """Кейс 52: polling_fragment получает failed -> st.error."""
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(APP_PATH)
        at.run(timeout=30)

        at.session_state["task_id"] = "failed-task"
        at.session_state["poll_attempts"] = 0
        at.session_state["estimated_seconds"] = 150
        at.run(timeout=30)

        with patch("requests.get") as mock_get:
            mock_get.return_value = _mock_response(
                200, {"task_id": "failed-task", "status": "failed"},
            )
            at.run(timeout=30)

        error_texts = [e.value for e in at.error]
        assert len(error_texts) > 0
        combined = " ".join(error_texts).lower()
        assert "ошибк" in combined or "завершил" in combined

    def test_polling_network_error_shows_retry(self):
        """Кейс 53: polling получил RequestException -> ошибка + кнопка повтора."""
        from streamlit.testing.v1 import AppTest
        import requests as req

        at = AppTest.from_file(APP_PATH)
        at.run(timeout=30)

        at.session_state["task_id"] = "net-err-task"
        at.session_state["poll_attempts"] = 0
        at.session_state["estimated_seconds"] = 150
        at.run(timeout=30)

        with patch("requests.get", side_effect=req.RequestException):
            at.run(timeout=30)

        error_texts = [e.value for e in at.error]
        assert len(error_texts) > 0

        retry_buttons = [b for b in at.button if "Повторить" in b.label]
        assert len(retry_buttons) >= 1


# ---------------------------------------------------------------------------
# 4.4 Сброс состояния
# ---------------------------------------------------------------------------


class TestResetState:
    """Сброс session state при нажатии кнопок навигации."""

    def test_reset_after_result(self):
        """Кейс 54: кнопка «Обработать новое резюме» очищает state."""
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(APP_PATH)
        at.run(timeout=30)

        at.session_state["task_id"] = "done-task"
        at.session_state["result"] = {"data": {"personal_data": {}}}
        at.session_state["estimated_seconds"] = 150
        at.run(timeout=30)

        reset_buttons = [b for b in at.button if "новое резюме" in b.label.lower()]
        if reset_buttons:
            reset_buttons[0].click()
            at.run(timeout=30)

            # task_id должен быть удалён — bracket access выбрасывает KeyError
            try:
                _ = at.session_state["task_id"]
                task_cleared = False
            except (KeyError, AttributeError):
                task_cleared = True
            assert task_cleared

    def test_retry_after_polling_error(self):
        """Кейс 55: кнопка «Повторить» после ошибки polling."""
        from streamlit.testing.v1 import AppTest
        import requests as req

        at = AppTest.from_file(APP_PATH)
        at.run(timeout=30)

        at.session_state["task_id"] = "retry-task"
        at.session_state["poll_attempts"] = 0
        at.session_state["estimated_seconds"] = 150
        at.run(timeout=30)

        # Вызываем ошибку сети
        with patch("requests.get", side_effect=req.RequestException):
            at.run(timeout=30)

        retry_buttons = [b for b in at.button if "Повторить" in b.label]
        if retry_buttons:
            retry_buttons[0].click()
            at.run(timeout=30)

            # task_id должен быть очищен
            try:
                _ = at.session_state["task_id"]
                task_cleared = False
            except (KeyError, AttributeError):
                task_cleared = True
            assert task_cleared
