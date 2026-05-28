"""Абстрактный базовый класс пайплайна обработки резюме."""

from abc import ABC, abstractmethod


class BasePipeline(ABC):
    """Базовый класс пайплайна."""

    @abstractmethod
    def process(self, file_path: str) -> dict:
        """Обработка файла и возврат структурированного результата."""
        ...
