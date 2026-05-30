"""Операции воркера с БД: обновление статуса, сохранение результата."""

import json
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from worker.schemas.cv import CVResult


def update_task_status(
    session: Session,
    task_id: uuid.UUID,
    status: str,
    error_msg: str | None = None,
) -> None:
    """Обновляет статус задачи.

    Внимание: метод НЕ вызывает session.commit(). Коммит должен выполняться
    вызывающим кодом (consumer.py) для обеспечения атомарности транзакции.
    """
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


def save_full_result(
    session: Session,
    task_id: uuid.UUID,
    raw_json: dict,
    cv: CVResult,
) -> None:
    """Сохраняет raw_json и нормализованные данные атомарно в одной транзакции."""
    # INSERT в resumes с возвратом id
    row = session.execute(
        text(
            "INSERT INTO resumes (task_id, raw_json) "
            "VALUES (:task_id, :raw_json) RETURNING id"
        ),
        {
            "task_id": task_id,
            "raw_json": json.dumps(raw_json, ensure_ascii=False),
        },
    )
    resume_id = row.scalar_one()

    # Персональные данные
    pd = cv.personal_data
    if pd is not None:
        session.execute(
            text(
                "INSERT INTO personal_data (resume_id, last_name, first_name, middle_name, "
                "email, phone, city, birth_date) "
                "VALUES (:resume_id, :last_name, :first_name, :middle_name, "
                ":email, :phone, :city, :birth_date)"
            ),
            {
                "resume_id": resume_id,
                "last_name": pd.last_name or None,
                "first_name": pd.first_name or None,
                "middle_name": pd.middle_name or None,
                "email": pd.email or None,
                "phone": pd.phone or None,
                "city": pd.city or None,
                "birth_date": pd.birth_date or None,
            },
        )

    # Образование
    for edu in cv.education:
        session.execute(
            text(
                "INSERT INTO education (resume_id, institution, specialty, level, "
                "start_year, end_year) "
                "VALUES (:resume_id, :institution, :specialty, :level, "
                ":start_year, :end_year)"
            ),
            {
                "resume_id": resume_id,
                "institution": edu.institution or None,
                "specialty": edu.specialty or None,
                "level": edu.level or None,
                "start_year": edu.start_year,
                "end_year": edu.end_year,
            },
        )

    # Опыт работы
    for exp in cv.experience:
        session.execute(
            text(
                "INSERT INTO experience (resume_id, company, position, "
                "start_date, end_date, responsibilities) "
                "VALUES (:resume_id, :company, :position, "
                ":start_date, :end_date, :responsibilities)"
            ),
            {
                "resume_id": resume_id,
                "company": exp.company or None,
                "position": exp.position or None,
                "start_date": exp.start_date or None,
                "end_date": exp.end_date or None,
                "responsibilities": exp.responsibilities or None,
            },
        )

    # Навыки
    sk = cv.skills
    if sk is not None:
        session.execute(
            text(
                "INSERT INTO skills (resume_id, technical, professional, languages, soft_skills) "
                "VALUES (:resume_id, :technical, :professional, :languages, :soft_skills)"
            ),
            {
                "resume_id": resume_id,
                "technical": json.dumps(sk.hard_skills.technical, ensure_ascii=False) if sk.hard_skills.technical is not None else None,
                "professional": json.dumps(sk.hard_skills.professional, ensure_ascii=False) if sk.hard_skills.professional is not None else None,
                "languages": json.dumps(sk.hard_skills.languages, ensure_ascii=False) if sk.hard_skills.languages is not None else None,
                "soft_skills": json.dumps(sk.soft_skills, ensure_ascii=False) if sk.soft_skills is not None else None,
            },
        )

    # Дополнительно
    add = cv.additional
    if add is not None:
        session.execute(
            text(
                "INSERT INTO additional (resume_id, certificates, projects, achievements) "
                "VALUES (:resume_id, :certificates, :projects, :achievements)"
            ),
            {
                "resume_id": resume_id,
                "certificates": json.dumps([c.model_dump() for c in add.certificates], ensure_ascii=False) if add.certificates is not None else None,
                "projects": json.dumps([p.model_dump() for p in add.projects], ensure_ascii=False) if add.projects is not None else None,
                "achievements": json.dumps(add.achievements.model_dump(), ensure_ascii=False) if any(add.achievements.model_dump().values()) else None,
            },
        )
