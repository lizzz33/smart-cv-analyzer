"""Интеграционные тесты ограничений БД: FK, NOT NULL, триггер updated_at, дефолты."""

import uuid

import pytest
from sqlalchemy import text

from api.db.models import Task


# ---------------------------------------------------------------------------
# NOT NULL — обязательные поля
# ---------------------------------------------------------------------------


async def test_task_file_name_not_null(async_session):
    """Попытка создать задачу без file_name вызывает ошибку."""
    task = Task(file_type="pdf", file_size=100, status="pending")
    async_session.add(task)
    with pytest.raises(Exception):
        await async_session.commit()
    await async_session.rollback()


async def test_task_file_type_not_null(async_session):
    """Попытка создать задачу без file_type вызывает ошибку."""
    task = Task(file_name="resume.pdf", file_size=100, status="pending")
    async_session.add(task)
    with pytest.raises(Exception):
        await async_session.commit()
    await async_session.rollback()


async def test_task_file_size_not_null(async_session):
    """Попытка создать задачу без file_size вызывает ошибку."""
    task = Task(file_name="resume.pdf", file_type="pdf", status="pending")
    async_session.add(task)
    with pytest.raises(Exception):
        await async_session.commit()
    await async_session.rollback()


# ---------------------------------------------------------------------------
# FOREIGN KEY — resume → task
# ---------------------------------------------------------------------------


async def test_resume_fk_task_must_exist(async_session):
    """INSERT resume с несуществующим task_id вызывает ошибку FK."""
    fake_task_id = uuid.uuid4()
    with pytest.raises(Exception):
        await async_session.execute(
            text(
                "INSERT INTO resumes (task_id, raw_json) "
                "VALUES (:task_id, :raw_json)"
            ),
            {"task_id": fake_task_id, "raw_json": "{}"},
        )
        await async_session.commit()
    await async_session.rollback()


# ---------------------------------------------------------------------------
# Триггер updated_at — автообновление при UPDATE
# ---------------------------------------------------------------------------


async def test_updated_at_changes_on_status_update(async_session):
    """При обновлении статуса задачи updated_at меняется автоматически."""
    # Создаём задачу
    result = await async_session.execute(
        text(
            "INSERT INTO tasks (file_name, file_type, file_size, status) "
            "VALUES ('resume.pdf', 'pdf', 100, 'pending') "
            "RETURNING id, updated_at"
        )
    )
    row = result.one()
    task_id, original_updated_at = row.id, row.updated_at
    await async_session.commit()

    # Небольшая пауза для гарантии разницы во времени
    import asyncio

    await asyncio.sleep(0.05)

    # Обновляем статус
    await async_session.execute(
        text("UPDATE tasks SET status = 'processing' WHERE id = :id"),
        {"id": task_id},
    )
    await async_session.commit()

    # Проверяем, что updated_at изменился
    result = await async_session.execute(
        text("SELECT updated_at FROM tasks WHERE id = :id"),
        {"id": task_id},
    )
    new_updated_at = result.scalar_one()
    assert new_updated_at > original_updated_at


# ---------------------------------------------------------------------------
# DEFAULT — статус по умолчанию
# ---------------------------------------------------------------------------


async def test_status_default_is_pending(async_session):
    """При INSERT без указания status — дефолт 'pending'."""
    result = await async_session.execute(
        text(
            "INSERT INTO tasks (file_name, file_type, file_size) "
            "VALUES ('resume.pdf', 'pdf', 1024) "
            "RETURNING status"
        )
    )
    status = result.scalar_one()
    assert status == "pending"
