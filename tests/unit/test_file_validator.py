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


# ---------------------------------------------------------------------------
# Валидные форматы — один parametrize
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "filename, content, mime, expected_ext",
    [
        ("resume.pdf", b"%PDF-1.4 some content", "application/pdf", "pdf"),
        (
            "resume.docx",
            b"PK\x03\x04 docx content",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "docx",
        ),
        (
            "resume.odt",
            b"ODT content data",
            "application/vnd.oasis.opendocument.text",
            "odt",
        ),
        ("photo.jpeg", b"\xff\xd8\xff\xe0 jpeg data", "image/jpeg", "jpeg"),
        ("scan.png", b"\x89PNG\r\n\x1a\n png data", "image/png", "png"),
    ],
    ids=["pdf", "docx", "odt", "jpeg", "png"],
)
async def test_valid_formats(_mock_metrics, filename, content, mime, expected_ext):
    """Поддерживаемые форматы проходят валидацию."""
    file = _make_upload(filename, content)

    with patch("api.services.file_validator.magic") as m_magic:
        m_magic.from_buffer.return_value = mime
        ext, size, result_content = await validate_file(file)

    assert ext == expected_ext
    assert size == len(content)
    assert result_content == content


# ---------------------------------------------------------------------------
# Нормализация .jpg -> .jpeg
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jpg_normalized_to_jpeg(_mock_metrics):
    file = _make_upload("photo.jpg", b"\xff\xd8\xff\xe0 jpeg data")

    with patch("api.services.file_validator.magic") as m_magic:
        m_magic.from_buffer.return_value = "image/jpeg"
        ext, _, _ = await validate_file(file)

    assert ext == "jpeg"


# ---------------------------------------------------------------------------
# Ошибки валидации
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_filename(_mock_metrics):
    file = _make_upload(None, b"data")

    with pytest.raises(HTTPException) as exc_info:
        await validate_file(file)

    assert exc_info.value.status_code == 422
    assert "File name is missing" in exc_info.value.detail


@pytest.mark.asyncio
async def test_unsupported_extension(_mock_metrics):
    file = _make_upload("resume.txt", b"plain text")

    with pytest.raises(HTTPException) as exc_info:
        await validate_file(file)

    assert exc_info.value.status_code == 422
    assert "Unsupported" in exc_info.value.detail


@pytest.mark.asyncio
async def test_empty_file(_mock_metrics):
    file = _make_upload("resume.pdf", b"")

    with pytest.raises(HTTPException) as exc_info:
        with patch("api.services.file_validator.magic"):
            await validate_file(file)

    assert exc_info.value.status_code == 422
    assert "empty" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_file_too_large(_mock_metrics):
    big_content = b"x" * (2 * 1024 * 1024)  # 2 MB
    file = _make_upload("resume.pdf", big_content)

    with pytest.raises(HTTPException) as exc_info:
        with patch("api.services.file_validator.magic"):
            await validate_file(file)

    assert exc_info.value.status_code == 422
    assert "exceeds" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_mime_mismatch(_mock_metrics):
    file = _make_upload("resume.pdf", b"<html>not a pdf</html>")

    with patch("api.services.file_validator.magic") as m_magic:
        m_magic.from_buffer.return_value = "text/html"
        with pytest.raises(HTTPException) as exc_info:
            await validate_file(file)

    assert exc_info.value.status_code == 422
    assert "does not match" in exc_info.value.detail
