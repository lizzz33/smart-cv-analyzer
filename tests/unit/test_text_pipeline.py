"""Тесты текстового пайплайна (TextPipeline)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from worker.pipelines.text_pipeline import (
    EXTRACTION_PROMPT,
    FALLBACK_PROMPT,
    TEXT_LIMIT_FALLBACK,
    TEXT_LIMIT_MAIN,
    TEXT_LIMIT_MINIMAL,
    TextPipeline,
)

# Минимальный валидный JSON, соответствующий CVResult
VALID_CV_JSON = json.dumps({
    "personal_data": {"last_name": "Ivanov", "first_name": "Ivan"},
    "education": [],
    "experience": [],
    "skills": {
        "hard_skills": {"technical": [], "professional": [], "languages": []},
        "soft_skills": [],
    },
    "additional": {
        "certificates": [],
        "projects": [],
        "achievements": {"awards": [], "publications": [], "conferences": []},
    },
})


# ---------------------------------------------------------------------------
# _detect_file_type
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("filename,expected", [
    ("resume.pdf", "pdf"),
    ("resume.PDF", "pdf"),
    ("my.cv.pdf", "pdf"),
    ("cv.docx", "docx"),
    ("cv.odt", "odt"),
])
def test_detect_file_type_supported(filename, expected):
    """Поддерживаемые расширения распознаются корректно."""
    pipeline = TextPipeline()
    assert pipeline._detect_file_type(filename) == expected


@pytest.mark.parametrize("filename", [
    "resume.txt",
    "photo.jpeg",
    "archive.zip",
    "noext",
    "",
])
def test_detect_file_type_unsupported(filename):
    """Неподдерживаемые расширения вызывают ValueError."""
    pipeline = TextPipeline()
    with pytest.raises(ValueError, match="Неподдерживаемое расширение"):
        pipeline._detect_file_type(filename)


# ---------------------------------------------------------------------------
# _generate
# ---------------------------------------------------------------------------


def test_generate_returns_parsed_json():
    """При валидном JSON в ответе модели _generate возвращает dict."""
    pipeline = TextPipeline()

    mock_model = MagicMock()
    mock_model.generate.return_value = MagicMock()

    mock_tokenizer = MagicMock()
    mock_tokenizer.apply_chat_template.return_value = "chat"
    mock_input_ids = MagicMock()
    mock_input_ids.shape = [1, 10]
    mock_tokenizer.return_value = {"input_ids": mock_input_ids}
    mock_tokenizer.decode.return_value = VALID_CV_JSON

    with patch("worker.pipelines.text_pipeline.model_manager") as mock_mm:
        mock_mm.model = mock_model
        mock_mm.tokenizer = mock_tokenizer
        result = pipeline._generate("Промпт: {resume_text}", "Текст резюме")

    assert result is not None
    assert result["personal_data"]["last_name"] == "Ivanov"
    assert result["personal_data"]["first_name"] == "Ivan"


def test_generate_returns_none_when_no_json():
    """Если модель вернула текст без JSON — _generate возвращает None."""
    pipeline = TextPipeline()

    mock_model = MagicMock()
    mock_model.generate.return_value = MagicMock()

    mock_tokenizer = MagicMock()
    mock_tokenizer.apply_chat_template.return_value = "chat"
    mock_input_ids = MagicMock()
    mock_input_ids.shape = [1, 5]
    mock_tokenizer.return_value = {"input_ids": mock_input_ids}
    mock_tokenizer.decode.return_value = "Извините, не удалось обработать."

    with patch("worker.pipelines.text_pipeline.model_manager") as mock_mm:
        mock_mm.model = mock_model
        mock_mm.tokenizer = mock_tokenizer
        result = pipeline._generate("Промпт: {resume_text}", "Текст")

    assert result is None


def test_generate_calls_model_with_correct_params():
    """_generate передаёт параметры генерации в model.generate."""
    pipeline = TextPipeline()

    mock_model = MagicMock()
    mock_model.generate.return_value = MagicMock()

    mock_tokenizer = MagicMock()
    mock_tokenizer.apply_chat_template.return_value = "chat"
    mock_input_ids = MagicMock()
    mock_input_ids.shape = [1, 10]
    mock_tokenizer.return_value = {"input_ids": mock_input_ids}
    mock_tokenizer.decode.return_value = VALID_CV_JSON

    with patch("worker.pipelines.text_pipeline.model_manager") as mock_mm:
        mock_mm.model = mock_model
        mock_mm.tokenizer = mock_tokenizer
        pipeline._generate("Промпт: {resume_text}", "Текст")

    mock_model.generate.assert_called_once()
    call_kwargs = mock_model.generate.call_args[1]
    assert call_kwargs["max_new_tokens"] == 2048
    assert call_kwargs["do_sample"] is False
    assert call_kwargs["use_cache"] is True


# ---------------------------------------------------------------------------
# _generate_with_retry
# ---------------------------------------------------------------------------


def test_retry_success_first_attempt():
    """Успешная генерация с первой попытки (основной промпт)."""
    pipeline = TextPipeline()

    with patch.object(pipeline, "_generate", return_value={"personal_data": {}}) as mock_gen:
        result = pipeline._generate_with_retry("Текст резюме")

    assert result == {"personal_data": {}}
    assert mock_gen.call_count == 1
    # Передан основной промпт
    assert mock_gen.call_args[0][0] == EXTRACTION_PROMPT


def test_retry_success_second_attempt():
    """Основной промпт не дал результата — успех на fallback (попытка 2)."""
    pipeline = TextPipeline()

    with patch.object(pipeline, "_generate", side_effect=[None, {"personal_data": {}}]) as mock_gen:
        result = pipeline._generate_with_retry("Текст резюме")

    assert result == {"personal_data": {}}
    assert mock_gen.call_count == 2
    # Второй вызов — fallback промпт
    assert mock_gen.call_args_list[1][0][0] == FALLBACK_PROMPT


def test_retry_success_third_attempt():
    """Первые две попытки провалились — успех на минимальном тексте (попытка 3)."""
    pipeline = TextPipeline()

    with patch.object(pipeline, "_generate", side_effect=[None, None, {"personal_data": {}}]) as mock_gen:
        result = pipeline._generate_with_retry("Текст резюме")

    assert result == {"personal_data": {}}
    assert mock_gen.call_count == 3


def test_retry_all_attempts_fail():
    """Все 3 попытки провалились — генерируется ValueError."""
    pipeline = TextPipeline()

    with patch.object(pipeline, "_generate", side_effect=[None, None, None]):
        with pytest.raises(ValueError, match="Не удалось извлечь JSON"):
            pipeline._generate_with_retry("Текст резюме")


def test_retry_truncates_long_text():
    """Длинный текст обрезается до лимитов на каждой попытке."""
    long_text = "А" * 20000
    pipeline = TextPipeline()

    with patch.object(pipeline, "_generate", side_effect=[None, None, {"data": 1}]) as mock_gen:
        pipeline._generate_with_retry(long_text)

    calls = mock_gen.call_args_list
    assert len(calls[0][0][1]) == TEXT_LIMIT_MAIN
    assert len(calls[1][0][1]) == TEXT_LIMIT_FALLBACK
    assert len(calls[2][0][1]) == TEXT_LIMIT_MINIMAL


# ---------------------------------------------------------------------------
# process
# ---------------------------------------------------------------------------


def test_process_full_success(tmp_path):
    """Полный цикл process: экстракция -> загрузка модели -> генерация -> результат."""
    test_file = tmp_path / "test.pdf"
    test_file.write_text("dummy")

    expected_result = {
        "personal_data": {"last_name": "Ivanov", "first_name": "Ivan"},
        "education": [],
        "experience": [],
        "skills": {"hard_skills": {"technical": [], "professional": [], "languages": []}, "soft_skills": []},
        "additional": {"certificates": [], "projects": [], "achievements": {"awards": [], "publications": [], "conferences": []}},
    }

    pipeline = TextPipeline()

    with (
        patch("worker.pipelines.text_pipeline.get_extractor") as mock_get,
        patch("worker.pipelines.text_pipeline.model_manager") as mock_mm,
        patch.object(pipeline, "_generate_with_retry", return_value=expected_result) as mock_retry,
    ):
        mock_extractor = MagicMock(return_value="Иван Иванов — Python Developer, 5 лет опыта")
        mock_get.return_value = mock_extractor

        result = pipeline.process(str(test_file))

    assert result == expected_result
    mock_get.assert_called_once_with("pdf")
    mock_extractor.assert_called_once_with(str(test_file))
    mock_mm.load_text_model.assert_called_once()
    mock_retry.assert_called_once_with("Иван Иванов — Python Developer, 5 лет опыта")


def test_process_empty_text_raises(tmp_path):
    """Пустой текст из экстрактора — ValueError."""
    test_file = tmp_path / "test.pdf"
    test_file.write_text("dummy")

    pipeline = TextPipeline()

    with (
        patch("worker.pipelines.text_pipeline.get_extractor") as mock_get,
        patch("worker.pipelines.text_pipeline.model_manager"),
    ):
        mock_get.return_value = MagicMock(return_value="   \n  \t  ")

        with pytest.raises(ValueError, match="Не удалось извлечь текст"):
            pipeline.process(str(test_file))


def test_process_unsupported_format_raises(tmp_path):
    """Неподдерживаемый формат файла — ValueError до вызова модели."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("dummy")

    pipeline = TextPipeline()

    with patch("worker.pipelines.text_pipeline.model_manager") as mock_mm:
        with pytest.raises(ValueError, match="Неподдерживаемое расширение"):
            pipeline.process(str(test_file))

    # Модель не должна загружаться при невалидном формате
    mock_mm.load_text_model.assert_not_called()


@pytest.mark.parametrize("filename", ["resume.docx", "resume.odt"])
def test_process_supported_text_formats(tmp_path, filename):
    """DOCX и ODT направляются в текстовый пайплайн."""
    test_file = tmp_path / filename
    test_file.write_text("dummy")

    pipeline = TextPipeline()

    with (
        patch("worker.pipelines.text_pipeline.get_extractor") as mock_get,
        patch("worker.pipelines.text_pipeline.model_manager"),
        patch.object(pipeline, "_generate_with_retry", return_value={"personal_data": {}}),
    ):
        mock_get.return_value = MagicMock(return_value="Текст резюме")
        pipeline.process(str(test_file))

    # Определён тип файла и выбран экстрактор
    file_type = filename.rsplit(".", 1)[-1].lower()
    mock_get.assert_called_once_with(file_type)
