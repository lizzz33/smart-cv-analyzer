"""Эндпоинт загрузки файла резюме: POST /api/v1/upload."""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.db import crud
from api.db.connection import get_db
from api.metrics import cv_uploads_total
from api.services.file_validator import validate_file

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/v1/upload", status_code=202)
async def upload_file(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
):
    """Принимает файл резюме, валидирует и создаёт задачу в БД."""
    ext, file_size = await validate_file(file)

    task = await crud.create_task(
        session=db,
        file_name=file.filename,
        file_type=ext,
        file_size=file_size,
    )

    # Сохраняем файл на диск для последующей обработки воркером
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f"{task.id}.{ext}"

    content = await file.read()
    dest.write_bytes(content)
    logger.info("Файл сохранён: %s (%d байт)", dest, file_size)

    cv_uploads_total.inc()

    return {
        "task_id": str(task.id),
        "status": "pending",
        "estimated_seconds": 150,
    }
