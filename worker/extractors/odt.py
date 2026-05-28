"""Извлечение текста из ODT-файлов через odfpy."""

import logging

from odf.opendocument import load
from odf.text import P
from odf import teletype

logger = logging.getLogger(__name__)


def extract_text(file_path: str) -> str:
    """Извлекает текст всех параграфов ODT."""
    doc = load(file_path)
    paragraphs = []

    for p in doc.getElementsByType(P):
        text = teletype.extractText(p).strip()
        if text:
            paragraphs.append(text)

    logger.info("ODT: извлечено %d параграфов из %s", len(paragraphs), file_path)
    return "\n".join(paragraphs)
