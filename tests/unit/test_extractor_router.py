"""Тесты маршрутизации экстракторов."""

import pytest

from worker.extractors import docx, odt, pdf
from worker.extractors.router import get_extractor


def test_pdf():
    assert get_extractor("pdf") is pdf.extract_text


def test_docx():
    assert get_extractor("docx") is docx.extract_text


def test_odt():
    assert get_extractor("odt") is odt.extract_text


@pytest.mark.parametrize("file_type", ["jpeg", "txt", "png", "gif", ""])
def test_unsupported_raises(file_type):
    with pytest.raises(ValueError, match="Неподдерживаемый"):
        get_extractor(file_type)
