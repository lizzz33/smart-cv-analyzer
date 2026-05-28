"""Извлечение текста из PDF-файлов через pdfplumber."""

import logging

import pdfplumber

logger = logging.getLogger(__name__)


def extract_text(file_path: str) -> str:
    """Извлекает текст из всех страниц PDF."""
    pages = []
    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text:
                pages.append(text)
            else:
                logger.debug("Пустая страница %d в %s", i + 1, file_path)

    logger.info("PDF: извлечено %d страниц из %s", len(pages), file_path)
    return "\n\n".join(pages)
