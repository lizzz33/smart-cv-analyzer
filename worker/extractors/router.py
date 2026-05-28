"""Маршрутизация к нужному экстрактору по типу файла."""

import logging

from worker.extractors import docx, odt, pdf

logger = logging.getLogger(__name__)

_TEXT_EXTRACTORS = {
    "pdf": pdf.extract_text,
    "docx": docx.extract_text,
    "odt": odt.extract_text,
}


def get_extractor(file_type: str):
    """Возвращает функцию-экстрактор для заданного типа файла."""
    extractor = _TEXT_EXTRACTORS.get(file_type)
    if extractor is None:
        raise ValueError(f"Неподдерживаемый тип файла для текстового пайплайна: {file_type}")
    return extractor
