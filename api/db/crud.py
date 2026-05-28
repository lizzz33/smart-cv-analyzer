"""Операции с БД: создание и чтение задач."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import Resume, Task


async def create_task(
    session: AsyncSession, file_name: str, file_type: str, file_size: int
) -> Task:
    """Создаёт новую задачу со статусом pending."""
    task = Task(
        file_name=file_name,
        file_type=file_type,
        file_size=file_size,
        status="pending",
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def get_task(session: AsyncSession, task_id: uuid.UUID) -> Task | None:
    """Возвращает задачу по id или None."""
    result = await session.execute(select(Task).where(Task.id == task_id))
    return result.scalar_one_or_none()


async def get_task_with_result(
    session: AsyncSession, task_id: uuid.UUID
) -> dict | None:
    """Возвращает задачу с raw_json резюме или None."""
    task = await get_task(session, task_id)
    if task is None:
        return None
    result = await session.execute(
        select(Resume.raw_json).where(Resume.task_id == task_id)
    )
    row = result.scalar_one_or_none()
    return {
        "task_id": str(task.id),
        "status": task.status,
        "data": row,
    }
