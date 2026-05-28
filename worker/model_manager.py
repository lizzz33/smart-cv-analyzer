"""Управление загрузкой/выгрузкой ML-моделей (lazy load, одна модель в памяти)."""

import gc
import logging

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from worker.config import settings

logger = logging.getLogger(__name__)


class ModelManager:
    """Синглтон для управления моделями: загружает по требованию, выгружает перед сменой."""

    def __init__(self):
        self._current_model_type: str | None = None
        self._model = None
        self._tokenizer = None

    def load_text_model(self):
        """Загрузка Qwen2.5-3B-Instruct для текстового пайплайна."""
        if self._current_model_type == "text":
            logger.debug("Текстовая модель уже загружена")
            return

        self._unload()
        model_path = settings.TEXT_MODEL_PATH
        logger.info("Загрузка текстовой модели: %s", model_path)

        self._tokenizer = AutoTokenizer.from_pretrained(
            model_path, trust_remote_code=True,
        )
        self._model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=torch.float32,
            device_map="cpu",
            trust_remote_code=True,
        )
        self._model.eval()
        self._current_model_type = "text"
        logger.info("Текстовая модель загружена")

    def _unload(self):
        """Выгрузка текущей модели для освобождения памяти."""
        if self._model is None:
            return

        logger.info("Выгрузка модели: %s", self._current_model_type)
        del self._model
        del self._tokenizer
        self._model = None
        self._tokenizer = None
        self._current_model_type = None
        gc.collect()
        logger.info("Память освобождена")

    @property
    def model(self):
        return self._model

    @property
    def tokenizer(self):
        return self._tokenizer


# Глобальный синглтон
model_manager = ModelManager()
