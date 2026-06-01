"""Операции с БД: создание и чтение задач."""

import logging
import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.db.models import (
    Resume,
    Task,
)


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


async def fail_task(
    session: AsyncSession, task_id: uuid.UUID, error_msg: str
) -> None:
    """Переводит задачу в статус failed с сообщением об ошибке."""
    logger = logging.getLogger(__name__)
    task = await get_task(session, task_id)
    if task is None:
        logger.error("fail_task: задача %s не найдена", task_id)
        return
    task.status = "failed"
    task.error_msg = error_msg
    await session.commit()


async def count_in_progress(session: AsyncSession) -> int:
    """Возвращает количество задач в статусе pending или processing."""
    result = await session.execute(
        select(func.count()).where(Task.status.in_(["pending", "processing"]))
    )
    return result.scalar_one()


async def get_task(session: AsyncSession, task_id: uuid.UUID) -> Task | None:
    """Возвращает задачу по id или None."""
    result = await session.execute(select(Task).where(Task.id == task_id))
    return result.scalar_one_or_none()


async def get_task_with_normalized(
    session: AsyncSession, task_id: uuid.UUID
) -> dict | None:
    """Возвращает задачу с нормализованными данными из всех таблиц."""
    task = await get_task(session, task_id)
    if task is None:
        return None

    result = await session.execute(
        select(Resume)
        .where(Resume.task_id == task_id)
        .options(
            selectinload(Resume.personal_data),
            selectinload(Resume.education),
            selectinload(Resume.experience),
            selectinload(Resume.skills),
            selectinload(Resume.additional),
        )
    )
    resume = result.scalar_one_or_none()
    if resume is None:
        return {
            "task_id": str(task.id),
            "status": task.status,
            "data": None,
        }

    pd = resume.personal_data
    personal = {
        "last_name": pd.last_name,
        "first_name": pd.first_name,
        "middle_name": pd.middle_name,
        "email": pd.email,
        "phone": pd.phone,
        "city": pd.city,
        "birth_date": str(pd.birth_date) if pd.birth_date else None,
    } if pd else None

    education = [
        {
            "institution": e.institution,
            "specialty": e.specialty,
            "level": e.level,
            "start_year": e.start_year,
            "end_year": e.end_year,
        }
        for e in resume.education
    ]

    experience = [
        {
            "company": e.company,
            "position": e.position,
            "start_date": str(e.start_date) if e.start_date else None,
            "end_date": str(e.end_date) if e.end_date else None,
            "responsibilities": e.responsibilities,
        }
        for e in resume.experience
    ]

    sk = resume.skills
    skills = {
        "hard_skills": {
            "technical": sk.technical,
            "professional": sk.professional,
            "languages": sk.languages,
        },
        "soft_skills": sk.soft_skills,
    } if sk else None

    ad = resume.additional
    additional = {
        "certificates": ad.certificates,
        "projects": ad.projects,
        "achievements": ad.achievements,
    } if ad else None

    return {
        "task_id": str(task.id),
        "status": task.status,
        "raw_json": resume.raw_json,
        "data": {
            "personal_data": personal,
            "education": education,
            "experience": experience,
            "skills": skills,
            "additional": additional,
        },
    }
