"""Тесты ModelManager: загрузка, выгрузка, переключение моделей."""

from unittest.mock import MagicMock, patch

import pytest

from worker.model_manager import ModelManager


@pytest.fixture
def manager():
    """Свежий экземпляр ModelManager для каждого теста."""
    return ModelManager()


# ---------------------------------------------------------------------------
# Свойства по умолчанию
# ---------------------------------------------------------------------------


def test_load_text_model(manager):
    """load_text_model загружает модель и токенизатор."""
    with (
        patch("worker.model_manager.AutoTokenizer") as mock_tok_cls,
        patch("worker.model_manager.AutoModelForCausalLM") as mock_model_cls,
    ):
        mock_tok_cls.from_pretrained.return_value = MagicMock(name="tokenizer")
        mock_model = MagicMock(name="model")
        mock_model_cls.from_pretrained.return_value = mock_model

        manager.load_text_model()

    assert manager._current_model_type == "text"
    assert manager.model is mock_model
    assert manager.tokenizer is not None
    # .eval() вызывается после загрузки
    mock_model.eval.assert_called_once()


def test_load_text_model_calls_correct_path(manager):
    """load_text_model использует settings.TEXT_MODEL_PATH."""
    with (
        patch("worker.model_manager.settings") as mock_settings,
        patch("worker.model_manager.AutoTokenizer") as mock_tok_cls,
        patch("worker.model_manager.AutoModelForCausalLM") as mock_model_cls,
    ):
        mock_settings.TEXT_MODEL_PATH = "/test/models/qwen"
        mock_tok_cls.from_pretrained.return_value = MagicMock()
        mock_model_cls.from_pretrained.return_value = MagicMock()

        manager.load_text_model()

    mock_tok_cls.from_pretrained.assert_called_once_with(
        "/test/models/qwen", trust_remote_code=True,
    )
    call_kwargs = mock_model_cls.from_pretrained.call_args[1]
    assert call_kwargs["device_map"] == "cpu"
    assert call_kwargs["trust_remote_code"] is True
    # torch_dtype — мок torch.float32, проверяем только наличие ключа
    assert "torch_dtype" in call_kwargs


# ---------------------------------------------------------------------------
# load_vision_model
# ---------------------------------------------------------------------------


def test_load_vision_model(manager):
    """load_vision_model загружает vision-модель и процессор."""
    with (
        patch("worker.model_manager.AutoProcessor") as mock_proc_cls,
        patch("worker.model_manager.Qwen2VLForConditionalGeneration") as mock_vision_cls,
    ):
        mock_proc_cls.from_pretrained.return_value = MagicMock(name="processor")
        mock_vision_model = MagicMock(name="vision_model")
        mock_vision_cls.from_pretrained.return_value = mock_vision_model

        manager.load_vision_model()

    assert manager._current_model_type == "vision"
    assert manager.processor is not None
    assert manager.model is mock_vision_model
    mock_vision_model.eval.assert_called_once()


def test_load_vision_model_unloads_text(manager):
    """Переключение с text на vision выгружает текстовую модель."""
    with (
        patch("worker.model_manager.AutoTokenizer") as mock_tok_cls,
        patch("worker.model_manager.AutoModelForCausalLM") as mock_model_cls,
        patch("worker.model_manager.AutoProcessor") as mock_proc_cls,
        patch("worker.model_manager.Qwen2VLForConditionalGeneration") as mock_vision_cls,
        patch("worker.model_manager.gc"),
    ):
        # Загружаем текстовую модель
        mock_tok_cls.from_pretrained.return_value = MagicMock(name="tokenizer")
        mock_model_cls.from_pretrained.return_value = MagicMock(name="text_model")
        manager.load_text_model()

        assert manager._current_model_type == "text"
        text_model_ref = manager.model

        # Переключаемся на vision
        mock_proc_cls.from_pretrained.return_value = MagicMock(name="processor")
        mock_vision_cls.from_pretrained.return_value = MagicMock(name="vision_model")
        manager.load_vision_model()

    assert manager._current_model_type == "vision"
    assert manager.model is not text_model_ref


# ---------------------------------------------------------------------------
# _unload
# ---------------------------------------------------------------------------


def test_unload_clears_everything(manager):
    """_unload очищает все ссылки и сбрасывает тип."""
    manager._model = MagicMock(name="model")
    manager._tokenizer = MagicMock(name="tokenizer")
    manager._processor = MagicMock(name="processor")
    manager._current_model_type = "text"

    with patch("worker.model_manager.gc"):
        manager._unload()

    assert manager.model is None
    assert manager.tokenizer is None
    assert manager.processor is None
    assert manager._current_model_type is None


def test_unload_calls_gc_collect(manager):
    """_unload вызывает gc.collect для освобождения памяти."""
    manager._model = MagicMock()

    with patch("worker.model_manager.gc") as mock_gc:
        manager._unload()

    mock_gc.collect.assert_called_once()
