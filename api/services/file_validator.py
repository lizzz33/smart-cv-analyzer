"""Валидация загруженного файла: формат, MIME-тип, размер."""

import magic

from fastapi import HTTPException, UploadFile

from api.config import ALLOWED_TYPES, MAX_FILE_SIZE_BYTES

# Обратный маппинг: MIME -> расширение
_MIME_TO_EXT: dict[str, str] = {}
for _ext, _mimes in ALLOWED_TYPES.items():
    for _m in _mimes:
        _MIME_TO_EXT[_m] = _ext


async def validate_file(file: UploadFile) -> tuple[str, int]:
    """Проверяет файл и возвращает (нормализованное расширение, размер в байтах).

    Выбрасывает HTTPException(422) при ошибке валидации.
    """
    if not file.filename:
        raise HTTPException(status_code=422, detail="File name is missing")

    # Проверка расширения
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_TYPES:
        allowed = ", ".join(sorted(ALLOWED_TYPES.keys()))
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file format. Allowed: {allowed}",
        )

    # Чтение содержимого для проверки MIME и размера
    content = await file.read()
    file_size = len(content)

    if file_size == 0:
        raise HTTPException(status_code=422, detail="File is empty")

    if file_size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=422,
            detail="File size exceeds 1 MB limit",
        )

    # Определение MIME-типа по содержимому
    mime = magic.from_buffer(content, mime=True)
    if ext == "jpg":
        ext = "jpeg"
    expected_mimes = ALLOWED_TYPES.get(ext, [])
    if mime not in expected_mimes:
        raise HTTPException(
            status_code=422,
            detail=f"File content does not match extension .{ext} (detected: {mime})",
        )

    # Возвращаем файловый указатель в начало
    await file.seek(0)

    return ext, file_size
