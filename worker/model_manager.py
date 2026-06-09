"""Управление загрузкой/выгрузкой ML-моделей (lazy load, одна модель в памяти)."""

import gc
import logging
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, AutoProcessor, Qwen2VLForConditionalGeneration

from worker.config import settings
from worker.metrics import cv_model_load_duration_seconds, update_ram_usage

logger = logging.getLogger(__name__)


class ModelManager:
    """Синглтон для управления моделями: загружает по требованию, выгружает перед сменой."""

    def __init__(self):
        self._current_model_type: str | None = None
        self._model = None
        self._tokenizer = None
        self._processor = None

    def load_text_model(self):
        """Загрузка Qwen2.5-3B-Instruct для текстового пайплайна."""
        if self._current_model_type == "text":
            logger.debug("Текстовая модель уже загружена")
            return

        self._unload()
        model_path = settings.TEXT_MODEL_PATH
        logger.info("Загрузка текстовой модели: %s", model_path)

        start_time = time.monotonic()
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
        self._model.generation_config.do_sample = True
        self._current_model_type = "text"

        duration = time.monotonic() - start_time
        cv_model_load_duration_seconds.labels(model_type="text").observe(duration)
        update_ram_usage()
        logger.info("Текстовая модель загружена за %.1f сек", duration)

    def load_vision_model(self):
        """Загрузка Qwen2-VL-2B-Instruct для vision пайплайна."""
        if self._current_model_type == "vision":
            logger.debug("Vision модель уже загружена")
            return

        self._unload()
        model_path = settings.VISION_MODEL_PATH
        logger.info("Загрузка vision модели: %s", model_path)

        start_time = time.monotonic()
        self._processor = AutoProcessor.from_pretrained(
            model_path, trust_remote_code=True,
        )
        self._model = Qwen2VLForConditionalGeneration.from_pretrained(
            model_path,
            torch_dtype="auto",
            device_map="cpu",
            trust_remote_code=True,
            attn_implementation="eager",
        )
        self._model.eval()
        self._model.generation_config.do_sample = True
        self._current_model_type = "vision"

        duration = time.monotonic() - start_time
        cv_model_load_duration_seconds.labels(model_type="vision").observe(duration)
        update_ram_usage()
        logger.info("Vision модель загружена за %.1f сек", duration)

    def _unload(self):
        """Выгрузка текущей модели для освобождения памяти."""
        if self._model is None:
            return

        logger.info("Выгрузка модели: %s", self._current_model_type)
        self._model = None
        self._tokenizer = None
        self._processor = None
        self._current_model_type = None
        gc.collect()
        logger.info("Память освобождена")

    @property
    def model(self):
        return self._model

    @property
    def tokenizer(self):
        return self._tokenizer

    @property
    def processor(self):
        return self._processor


# Глобальный синглтон
model_manager = ModelManager()
