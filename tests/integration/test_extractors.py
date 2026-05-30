"""Интеграционные тесты текстовых экстракторов на реальных файлах."""

from worker.extractors.docx import extract_text as extract_docx
from worker.extractors.odt import extract_text as extract_odt
from worker.extractors.pdf import extract_text as extract_pdf


# ---------------------------------------------------------------------------
# Текстовые экстракторы
# ---------------------------------------------------------------------------


def test_pdf_with_text(sample_pdf):
    """PDF с текстом — извлекается непустой текст."""
    text = extract_pdf(str(sample_pdf))
    assert len(text) > 0
    assert "Ivan" in text or "Python" in text or "Developer" in text


def test_pdf_empty(empty_pdf):
    """PDF без текста — возвращается пустая строка."""
    text = extract_pdf(str(empty_pdf))
    assert text == ""


def test_docx_with_text(sample_docx):
    """DOCX с текстом — извлекается непустой текст."""
    text = extract_docx(str(sample_docx))
    assert len(text) > 0
    assert "Ivan" in text
    assert "Developer" in text


def test_odt_with_text(sample_odt):
    """ODT с текстом — извлекается непустой текст."""
    text = extract_odt(str(sample_odt))
    assert len(text) > 0
    assert "Ivan" in text
    assert "Developer" in text
