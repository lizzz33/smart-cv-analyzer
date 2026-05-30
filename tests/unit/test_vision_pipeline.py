"""Юнит-тесты VisionPipeline: preprocessing, retry-логика, обработка ошибок."""

import json
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from worker.pipelines.vision_pipeline import (
    IMAGE_FILE_TYPES,
    VisionPipeline,
)


# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------

VALID_JSON_RESULT = {
    "personal_data": {
        "last_name": "Ivanov",
        "first_name": "Ivan",
        "middle_name": "",
        "email": "ivan@test.com",
        "phone": "+7-999-123-45-67",
        "city": "Moscow",
        "birth_date": "",
    },
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
}


def _make_pipeline() -> VisionPipeline:
    """Создаёт экземпляр VisionPipeline."""
    return VisionPipeline()


# ---------------------------------------------------------------------------
# _detect_file_type — определение поддерживаемых форматов
# ---------------------------------------------------------------------------


class TestDetectFileType:
    """Проверки определения типа файла по расширению."""

    @pytest.mark.parametrize("ext", sorted(IMAGE_FILE_TYPES))
    def test_supported_extensions(self, ext, tmp_path):
        """Поддерживаемые расширения не вызывают ошибку."""
        path = tmp_path / f"resume.{ext}"
        path.write_bytes(b"fake")
        pipeline = _make_pipeline()
        result = pipeline._detect_file_type(str(path))
        assert result == ext

    @pytest.mark.parametrize("ext", ["gif", "bmp", "tiff", "webp", "pdf", "txt"])
    def test_unsupported_extensions(self, ext, tmp_path):
        """Неподдерживаемые расширения вызывают ValueError."""
        path = tmp_path / f"resume.{ext}"
        path.write_bytes(b"fake")
        pipeline = _make_pipeline()
        with pytest.raises(ValueError, match="Неподдерживаемое расширение"):
            pipeline._detect_file_type(str(path))

    def test_uppercase_extension(self, tmp_path):
        """Расширение в верхнем регистре распознаётся (регистронезависимость)."""
        path = tmp_path / "resume.JPEG"
        path.write_bytes(b"fake")
        pipeline = _make_pipeline()
        result = pipeline._detect_file_type(str(path))
        assert result == "jpeg"


# ---------------------------------------------------------------------------
# _preprocess_image — RGB-конвертация, ресайз, sharpening, contrast/brightness
# ---------------------------------------------------------------------------


class TestPreprocessImage:
    """Проверки предобработки изображений."""

    def test_corrupted_image_raises(self, corrupted_image):
        """Битый файл вызывает исключение при загрузке."""
        pipeline = _make_pipeline()
        with pytest.raises(Exception):
            pipeline._preprocess_image(str(corrupted_image))

    def test_nonexistent_file_raises(self, tmp_path):
        """Несуществующий файл вызывает FileNotFoundError."""
        pipeline = _make_pipeline()
        with pytest.raises(FileNotFoundError):
            pipeline._preprocess_image(str(tmp_path / "missing.jpeg"))


# ---------------------------------------------------------------------------
# _generate_with_retry — двухстадийная логика retry
# ---------------------------------------------------------------------------


class TestGenerateWithRetry:
    """Проверки retry-механизма: основной промпт -> fallback."""

    @patch.object(VisionPipeline, "_generate")
    def test_primary_prompt_success(self, mock_generate):
        """Успешный результат с первого промпта."""
        mock_generate.return_value = VALID_JSON_RESULT
        pipeline = _make_pipeline()
        image = Image.new("RGB", (100, 100))
        result = pipeline._generate_with_retry(image)
        assert result == VALID_JSON_RESULT
        assert mock_generate.call_count == 1

    @patch.object(VisionPipeline, "_generate")
    def test_fallback_after_primary_failure(self, mock_generate):
        """Основной промпт возвращает None -> fallback успешен."""
        mock_generate.side_effect = [None, VALID_JSON_RESULT]
        pipeline = _make_pipeline()
        image = Image.new("RGB", (100, 100))
        result = pipeline._generate_with_retry(image)
        assert result == VALID_JSON_RESULT
        assert mock_generate.call_count == 2
        # Второй вызов с fallback-промптом и другим temperature
        second_call = mock_generate.call_args_list[1]
        assert second_call.kwargs.get("temperature", second_call.args[2] if len(second_call.args) > 2 else None) == 0.3

    @patch.object(VisionPipeline, "_generate")
    def test_both_prompts_fail_raises(self, mock_generate):
        """Оба промпта вернули None -> ValueError."""
        mock_generate.side_effect = [None, None]
        pipeline = _make_pipeline()
        image = Image.new("RGB", (100, 100))
        with pytest.raises(ValueError, match="Не удалось извлечь JSON"):
            pipeline._generate_with_retry(image)
        assert mock_generate.call_count == 2


# ---------------------------------------------------------------------------
# process — основной метод пайплайна (с mock model_manager)
# ---------------------------------------------------------------------------


class TestProcess:
    """Проверки основного метода process с замоканным model_manager."""

    @patch("worker.pipelines.vision_pipeline.model_manager")
    @patch.object(VisionPipeline, "_generate_with_retry")
    def test_full_process_flow(self, mock_retry, mock_mm, sample_jpeg):
        """Полный цикл process: детект типа -> предобработка -> генерация."""
        mock_retry.return_value = VALID_JSON_RESULT
        pipeline = _make_pipeline()
        result = pipeline.process(str(sample_jpeg))

        assert result == VALID_JSON_RESULT
        mock_mm.load_vision_model.assert_called_once()
        mock_retry.assert_called_once()

        # Аргумент _generate_with_retry — PIL-изображение
        image_arg = mock_retry.call_args[0][0]
        assert isinstance(image_arg, Image.Image)

    def test_process_unsupported_extension(self, tmp_path):
        """Неподдерживаемое расширение вызывает ValueError до загрузки модели."""
        path = tmp_path / "resume.pdf"
        path.write_bytes(b"fake")
        pipeline = _make_pipeline()
        with pytest.raises(ValueError, match="Неподдерживаемое расширение"):
            pipeline.process(str(path))

    @patch("worker.pipelines.vision_pipeline.model_manager")
    @patch.object(VisionPipeline, "_generate_with_retry")
    def test_process_corrupted_image_raises(self, mock_retry, mock_mm, corrupted_image):
        """Битое изображение вызывает ошибку до генерации."""
        pipeline = _make_pipeline()
        with pytest.raises(Exception):
            pipeline.process(str(corrupted_image))
        # Генерация не должна была вызваться
        mock_retry.assert_not_called()


# ---------------------------------------------------------------------------
# _generate — генерация и парсинг JSON (mock модели)
# ---------------------------------------------------------------------------


class TestGenerate:
    """Проверки метода _generate: взаимодействие с моделью и парсинг ответа."""

    @patch("worker.pipelines.vision_pipeline.extract_json")
    @patch("worker.pipelines.vision_pipeline.process_vision_info")
    @patch("worker.pipelines.vision_pipeline.model_manager")
    def test_valid_json_response(self, mock_mm, mock_vision_info, mock_extract):
        """Модель вернула валидный JSON — extract_json вызывается с response."""
        json_str = json.dumps(VALID_JSON_RESULT)
        mock_processor = MagicMock()
        mock_mm.processor = mock_processor
        mock_mm.model = MagicMock()
        mock_mm.model.generate.return_value = MagicMock()
        # Имитация: batch_decode возвращает JSON-строку
        mock_processor.batch_decode.return_value = [json_str]
        mock_processor.apply_chat_template.return_value = "template"
        mock_vision_info.return_value = ([MagicMock()], None)
        mock_extract.return_value = VALID_JSON_RESULT

        pipeline = _make_pipeline()
        image = Image.new("RGB", (100, 100))
        result = pipeline._generate(image, "prompt", temperature=0.2)

        assert result == VALID_JSON_RESULT
        mock_extract.assert_called_once_with(json_str)

    @patch("worker.pipelines.vision_pipeline.extract_json")
    @patch("worker.pipelines.vision_pipeline.process_vision_info")
    @patch("worker.pipelines.vision_pipeline.model_manager")
    def test_invalid_json_returns_none(self, mock_mm, mock_vision_info, mock_extract):
        """Модель вернула невалидный JSON — _generate возвращает None."""
        mock_processor = MagicMock()
        mock_mm.processor = mock_processor
        mock_mm.model = MagicMock()
        mock_mm.model.generate.return_value = MagicMock()
        mock_processor.batch_decode.return_value = ["not a json at all"]
        mock_processor.apply_chat_template.return_value = "template"
        mock_vision_info.return_value = ([MagicMock()], None)
        mock_extract.return_value = None

        pipeline = _make_pipeline()
        image = Image.new("RGB", (100, 100))
        result = pipeline._generate(image, "prompt")

        assert result is None
