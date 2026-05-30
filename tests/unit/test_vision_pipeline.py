"""Юнит-тесты VisionPipeline: preprocessing, retry-логика, обработка ошибок."""

import json
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from worker.pipelines.vision_pipeline import (
    IMAGE_FILE_TYPES,
    MAX_IMAGE_SIZE,
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

    def test_rgb_image_unchanged_mode(self, sample_jpeg):
        """RGB-изображение не требует конвертации режима."""
        pipeline = _make_pipeline()
        result = pipeline._preprocess_image(str(sample_jpeg))
        assert result.mode == "RGB"

    def test_rgba_image_converted_to_rgb(self, sample_png):
        """PNG с альфа-каналом конвертируется в RGB."""
        pipeline = _make_pipeline()
        result = pipeline._preprocess_image(str(sample_png))
        assert result.mode == "RGB"

    def test_grayscale_image_converted_to_rgb(self, grayscale_jpeg):
        """Grayscale-изображение конвертируется в RGB."""
        pipeline = _make_pipeline()
        result = pipeline._preprocess_image(str(grayscale_jpeg))
        assert result.mode == "RGB"

    def test_large_image_resized(self, large_jpeg):
        """Изображение больше MAX_IMAGE_SIZE уменьшается с сохранением пропорций."""
        pipeline = _make_pipeline()
        result = pipeline._preprocess_image(str(large_jpeg))
        assert max(result.size) <= MAX_IMAGE_SIZE
        # Пропорции сохранены: 1000x1200 -> 768x921
        orig_ratio = 1000 / 1200
        new_ratio = result.size[0] / result.size[1]
        assert abs(orig_ratio - new_ratio) < 0.01

    def test_small_image_not_resized(self, sample_jpeg):
        """Маленькое изображение не ресайзится."""
        pipeline = _make_pipeline()
        result = pipeline._preprocess_image(str(sample_jpeg))
        assert result.size == (200, 300)

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

    def test_sharpening_is_applied(self, varied_jpeg):
        """Полная цепочка preprocessing воспроизводима вручную."""
        from PIL import Image, ImageEnhance, ImageFilter

        pipeline = _make_pipeline()
        result = pipeline._preprocess_image(str(varied_jpeg))

        # Повторяем ту же цепочку вручную
        img = Image.open(varied_jpeg)
        img.load()
        if img.mode != "RGB":
            img = img.convert("RGB")
        expected = img.filter(ImageFilter.SHARPEN)
        expected = ImageEnhance.Contrast(expected).enhance(1.15)
        expected = ImageEnhance.Brightness(expected).enhance(1.05)

        assert result.size == expected.size
        assert list(result.getdata()) == list(expected.getdata())

    def test_contrast_enhancement_changes_pixels(self, varied_jpeg):
        """Contrast+brightness меняют пиксели относительно только sharpening."""
        from PIL import Image, ImageFilter

        pipeline = _make_pipeline()
        result = pipeline._preprocess_image(str(varied_jpeg))

        img = Image.open(varied_jpeg)
        img.load()
        if img.mode != "RGB":
            img = img.convert("RGB")
        sharpened_only = img.filter(ImageFilter.SHARPEN)

        # Считаем суммарную разницу пикселей (JPEG lossy, поэтому не строгое !=)
        result_pixels = list(result.getdata())
        sharpened_pixels = list(sharpened_only.getdata())
        diff = sum(
            abs(r - s)
            for rp, sp in zip(result_pixels, sharpened_pixels)
            for r, s in zip(rp, sp)
        )
        # На ненулевых пикселях contrast+brightness гарантированно дают разницу
        assert diff > 0


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

    @patch("worker.pipelines.vision_pipeline.model_manager")
    @patch.object(VisionPipeline, "_generate_with_retry")
    def test_process_jpg_extension(self, mock_retry, mock_mm, sample_jpg):
        """Файл с расширением .jpg проходит корректно."""
        mock_retry.return_value = VALID_JSON_RESULT
        pipeline = _make_pipeline()
        result = pipeline.process(str(sample_jpg))
        assert result == VALID_JSON_RESULT

    @patch("worker.pipelines.vision_pipeline.model_manager")
    @patch.object(VisionPipeline, "_generate_with_retry")
    def test_process_png_extension(self, mock_retry, mock_mm, sample_png):
        """PNG-файл проходит корректно."""
        mock_retry.return_value = VALID_JSON_RESULT
        pipeline = _make_pipeline()
        result = pipeline.process(str(sample_png))
        assert result == VALID_JSON_RESULT

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
