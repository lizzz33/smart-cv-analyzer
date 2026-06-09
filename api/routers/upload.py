"""Эндпоинт загрузки файла резюме: POST /api/v1/upload."""

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.db import crud
from api.db.connection import get_db
from api.metrics import cv_uploads_total, cv_tasks_in_progress
from api.services.file_validator import validate_file
from api.services.kafka_producer import publish_task

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/v1/upload", status_code=202)
async def upload_file(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
):
    """Принимает файл резюме, валидирует и создаёт задачу в БД."""
    ext, file_size, content = await validate_file(file)

    task = await crud.create_task(
        session=db,
        file_name=file.filename,
        file_type=ext,
        file_size=file_size,
    )
    cv_tasks_in_progress.set(await crud.count_in_progress(db))

    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f"{task.id}.{ext}"

    await asyncio.to_thread(dest.write_bytes, content)
    logger.info("Файл сохранён: %s (%d байт)", dest, file_size)

    try:
        await publish_task(
            task_id=str(task.id),
            file_path=str(dest),
            file_type=ext,
            file_name=file.filename,
        )
    except Exception:
        logger.exception("Ошибка отправки в Kafka: task_id=%s", task.id)
        await crud.fail_task(db, task.id, "Ошибка отправки задачи в очередь")
        cv_tasks_in_progress.set(await crud.count_in_progress(db))
        return JSONResponse(
            status_code=503,
            content={
                "task_id": str(task.id),
                "status": "failed",
                "error": "Не удалось отправить задачу в очередь обработки",
            },
        )

    cv_uploads_total.inc()

    return {
        "task_id": str(task.id),
        "status": task.status,
        "estimated_seconds": 600,
    }
