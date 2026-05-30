"""Валидация загруженного файла: формат, MIME-тип, размер."""

import magic

from fastapi import HTTPException, UploadFile

from api.config import ALLOWED_TYPES, settings
from api.metrics import cv_upload_errors_total


async def validate_file(file: UploadFile) -> tuple[str, int, bytes]:
    """Проверяет файл и возвращает (расширение, размер, содержимое).

    Выбрасывает HTTPException(422) при ошибке валидации.
    """
    if not file.filename:
        cv_upload_errors_total.inc()
        raise HTTPException(status_code=422, detail="File name is missing")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_TYPES:
        cv_upload_errors_total.inc()
        allowed = ", ".join(sorted(ALLOWED_TYPES.keys()))
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file format. Allowed: {allowed}",
        )

    content = await file.read()
    file_size = len(content)

    if file_size == 0:
        cv_upload_errors_total.inc()
        raise HTTPException(status_code=422, detail="File is empty")

    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if file_size > max_bytes:
        cv_upload_errors_total.inc()
        raise HTTPException(
            status_code=422,
            detail=f"File size exceeds {settings.MAX_FILE_SIZE_MB} MB limit",
        )

    mime = magic.from_buffer(content, mime=True)
    if ext == "jpg":
        ext = "jpeg"
    expected_mimes = ALLOWED_TYPES.get(ext, [])
    if mime not in expected_mimes:
        cv_upload_errors_total.inc()
        raise HTTPException(
            status_code=422,
            detail=f"File content does not match extension .{ext} (detected: {mime})",
        )

    return ext, file_size, content
