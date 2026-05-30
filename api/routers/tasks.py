"""Эндпоинты статуса и результата задачи: GET /api/v1/tasks/{task_id}[/result]."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.db import crud
from api.db.connection import get_db

router = APIRouter()


@router.get("/api/v1/tasks/{task_id}")
async def get_task_status(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Возвращает текущий статус задачи."""
    task = await crud.get_task(session=db, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    response = {
        "task_id": str(task.id),
        "status": task.status,
        "file_name": task.file_name,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }

    # Для незавершённых задач возвращаем 202 Accepted
    if task.status in ("pending", "processing"):
        return JSONResponse(status_code=202, content=response)

    return response


@router.get("/api/v1/tasks/{task_id}/result")
async def get_task_result(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Возвращает результат обработки, если задача завершена."""
    result = await crud.get_task_with_result(session=db, task_id=task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if result["status"] in ("pending", "processing"):
        raise HTTPException(
            status_code=202,
            detail=f"Task status is '{result['status']}', result not ready yet",
        )

    if result["status"] == "failed":
        raise HTTPException(
            status_code=422,
            detail=f"Task failed: {result.get('error_msg', 'unknown error')}",
        )

    if result["data"] is None:
        raise HTTPException(
            status_code=404,
            detail="Task completed but result data not found",
        )

    return result
