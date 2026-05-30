"""Тесты валидации загруженного файла."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile

from api.services.file_validator import validate_file


def _make_upload(filename: str, content: bytes) -> UploadFile:
    """Создаёт мок UploadFile с заданным именем и содержимым."""
    file = MagicMock(spec=UploadFile)
    file.filename = filename
    file.read = AsyncMock(return_value=content)
    return file


@pytest.fixture
def _mock_metrics():
    with patch("api.services.file_validator.cv_upload_errors_total"):
        yield


async def test_valid_pdf(_mock_metrics):
    file = _make_upload("resume.pdf", b"%PDF-1.4 some content")

    with patch("api.services.file_validator.magic") as m_magic:
        m_magic.from_buffer.return_value = "application/pdf"
        ext, size, content = await validate_file(file)

    assert ext == "pdf"
    assert size == len(b"%PDF-1.4 some content")
    assert content == b"%PDF-1.4 some content"


async def test_valid_docx(_mock_metrics):
    file = _make_upload("resume.docx", b"PK\x03\x04 docx content")

    with patch("api.services.file_validator.magic") as m_magic:
        m_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        m_magic.from_buffer.return_value = m_mime
        ext, size, content = await validate_file(file)

    assert ext == "docx"
    assert content == b"PK\x03\x04 docx content"


async def test_missing_filename(_mock_metrics):
    file = _make_upload(None, b"data")
    # file.filename is None — file.read() не вызывается

    with pytest.raises(HTTPException) as exc_info:
        await validate_file(file)

    assert exc_info.value.status_code == 422
    assert "File name is missing" in exc_info.value.detail


async def test_unsupported_extension(_mock_metrics):
    file = _make_upload("resume.txt", b"plain text")

    with pytest.raises(HTTPException) as exc_info:
        await validate_file(file)

    assert exc_info.value.status_code == 422
    assert "Unsupported" in exc_info.value.detail


async def test_empty_file(_mock_metrics):
    file = _make_upload("resume.pdf", b"")

    with pytest.raises(HTTPException) as exc_info:
        with patch("api.services.file_validator.magic"):
            await validate_file(file)

    assert exc_info.value.status_code == 422
    assert "empty" in exc_info.value.detail.lower()


async def test_file_too_large(_mock_metrics):
    big_content = b"x" * (2 * 1024 * 1024)  # 2 MB
    file = _make_upload("resume.pdf", big_content)

    with pytest.raises(HTTPException) as exc_info:
        with patch("api.services.file_validator.magic"):
            await validate_file(file)

    assert exc_info.value.status_code == 422
    assert "exceeds" in exc_info.value.detail.lower()


async def test_mime_mismatch(_mock_metrics):
    file = _make_upload("resume.pdf", b"<html>not a pdf</html>")

    with patch("api.services.file_validator.magic") as m_magic:
        m_magic.from_buffer.return_value = "text/html"
        with pytest.raises(HTTPException) as exc_info:
            await validate_file(file)

    assert exc_info.value.status_code == 422
    assert "does not match" in exc_info.value.detail


async def test_jpg_normalized_to_jpeg(_mock_metrics):
    file = _make_upload("photo.jpg", b"\xff\xd8\xff\xe0 jpeg data")

    with patch("api.services.file_validator.magic") as m_magic:
        m_magic.from_buffer.return_value = "image/jpeg"
        ext, _, _ = await validate_file(file)

    assert ext == "jpeg"


async def test_valid_odt(_mock_metrics):
    """ODT-файл проходит валидацию."""
    file = _make_upload("resume.odt", b"ODT content data")

    with patch("api.services.file_validator.magic") as m_magic:
        m_magic.from_buffer.return_value = "application/vnd.oasis.opendocument.text"
        ext, size, content = await validate_file(file)

    assert ext == "odt"
    assert size == len(b"ODT content data")


async def test_valid_jpeg(_mock_metrics):
    """JPEG-файл проходит валидацию."""
    file = _make_upload("photo.jpeg", b"\xff\xd8\xff\xe0 jpeg data")

    with patch("api.services.file_validator.magic") as m_magic:
        m_magic.from_buffer.return_value = "image/jpeg"
        ext, size, content = await validate_file(file)

    assert ext == "jpeg"
    assert content == b"\xff\xd8\xff\xe0 jpeg data"


async def test_valid_png(_mock_metrics):
    """PNG-файл проходит валидацию."""
    file = _make_upload("scan.png", b"\x89PNG\r\n\x1a\n png data")

    with patch("api.services.file_validator.magic") as m_magic:
        m_magic.from_buffer.return_value = "image/png"
        ext, size, content = await validate_file(file)

    assert ext == "png"
    assert content == b"\x89PNG\r\n\x1a\n png data"
