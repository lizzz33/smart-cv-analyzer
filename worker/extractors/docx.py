"""Извлечение текста из DOCX-файлов через python-docx."""

import logging

from docx import Document

logger = logging.getLogger(__name__)


def extract_text(file_path: str) -> str:
    """Извлекает текст всех параграфов DOCX."""
    doc = Document(file_path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]

    logger.info("DOCX: извлечено %d параграфов из %s", len(paragraphs), file_path)
    return "\n".join(paragraphs)
