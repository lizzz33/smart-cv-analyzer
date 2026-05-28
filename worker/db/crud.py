"""Операции воркера с БД: обновление статуса, сохранение результата."""

import json
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session


def update_task_status(
    session: Session,
    task_id: uuid.UUID,
    status: str,
    error_msg: str | None = None,
) -> None:
    """Обновляет статус задачи."""
    values: dict = {
        "task_id": task_id,
        "status": status,
    }
    set_clauses = "status = :status, updated_at = now()"

    if status == "completed":
        set_clauses += ", completed_at = now()"
    if error_msg is not None:
        values["error_msg"] = error_msg
        set_clauses += ", error_msg = :error_msg"

    stmt = text(f"UPDATE tasks SET {set_clauses} WHERE id = :task_id")
    session.execute(stmt, values)
    session.commit()


def save_result(
    session: Session,
    task_id: uuid.UUID,
    raw_json: dict,
) -> None:
    """Сохраняет результат извлечения резюме."""
    stmt = text(
        "INSERT INTO resumes (task_id, raw_json) VALUES (:task_id, :raw_json)"
    )
    session.execute(
        stmt,
        {"task_id": task_id, "raw_json": json.dumps(raw_json, ensure_ascii=False)},
    )
    session.commit()
