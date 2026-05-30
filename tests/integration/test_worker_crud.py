"""Интеграционные тесты CRUD Worker (PostgreSQL)."""

import json
import uuid

from sqlalchemy import text

from worker.db.crud import save_full_result, update_task_status
from worker.schemas.cv import CVResult


def _insert_task(session) -> uuid.UUID:
    """Создаёт задачу напрямую через SQL и возвращает её id."""
    task_id = uuid.uuid4()
    session.execute(
        text(
            "INSERT INTO tasks (id, file_name, file_type, file_size, status) "
            "VALUES (:id, 'resume.pdf', 'pdf', 1024, 'pending')"
        ),
        {"id": task_id},
    )
    session.commit()
    return task_id


def test_update_status_processing(sync_session):
    task_id = _insert_task(sync_session)

    update_task_status(sync_session, task_id, "processing")

    row = sync_session.execute(
        text("SELECT status FROM tasks WHERE id = :id"), {"id": task_id}
    ).fetchone()
    assert row[0] == "processing"


def test_update_status_failed_with_error(sync_session):
    task_id = _insert_task(sync_session)

    update_task_status(sync_session, task_id, "failed", error_msg="Model crashed")

    row = sync_session.execute(
        text("SELECT status, error_msg FROM tasks WHERE id = :id"), {"id": task_id}
    ).fetchone()
    assert row[0] == "failed"
    assert row[1] == "Model crashed"


def test_save_full_result_complete(sync_session):
    """Полный CVResult — все 6 таблиц заполняются."""
    task_id = _insert_task(sync_session)
    update_task_status(sync_session, task_id, "processing")

    raw = {
        "personal_data": {
            "last_name": "Ivanov",
            "first_name": "Ivan",
            "email": "ivan@example.com",
        },
        "education": [
            {"institution": "MSU", "specialty": "CS", "start_year": 2010, "end_year": 2015}
        ],
        "experience": [
            {"company": "Yandex", "position": "Dev", "responsibilities": "Backend"}
        ],
        "skills": {
            "hard_skills": {
                "technical": ["Python"],
                "professional": [],
                "languages": ["English"],
            },
            "soft_skills": ["Teamwork"],
        },
        "additional": {
            "certificates": [{"name": "AWS", "issuer": "Amazon", "year": "2020"}],
            "projects": [],
            "achievements": {"awards": [], "publications": [], "conferences": []},
        },
    }
    cv = CVResult.model_validate(raw)

    save_full_result(sync_session, task_id, raw, cv)

    # resumes
    resume_row = sync_session.execute(
        text("SELECT count(*) FROM resumes WHERE task_id = :id"), {"id": task_id}
    ).scalar_one()
    assert resume_row == 1

    # personal_data
    pd = sync_session.execute(
        text("SELECT last_name, email FROM personal_data")
    ).fetchone()
    assert pd[0] == "Ivanov"
    assert pd[1] == "ivan@example.com"

    # education
    edu = sync_session.execute(text("SELECT institution FROM education")).fetchone()
    assert edu[0] == "MSU"

    # experience
    exp = sync_session.execute(text("SELECT company FROM experience")).fetchone()
    assert exp[0] == "Yandex"

    # skills (JSONB возвращается как Python-объект)
    sk = sync_session.execute(text("SELECT technical FROM skills")).fetchone()
    technical = sk[0] if isinstance(sk[0], list) else json.loads(sk[0])
    assert technical == ["Python"]

    # additional
    ad = sync_session.execute(text("SELECT certificates FROM additional")).fetchone()
    certs = ad[0] if isinstance(ad[0], list) else json.loads(ad[0])
    assert certs[0]["name"] == "AWS"


def test_save_full_result_empty(sync_session):
    """Пустой CVResult — нет ошибок, дефолтные значения."""
    task_id = _insert_task(sync_session)
    update_task_status(sync_session, task_id, "processing")

    raw = {}
    cv = CVResult.model_validate(raw)

    save_full_result(sync_session, task_id, raw, cv)

    # resumes создана
    count = sync_session.execute(text("SELECT count(*) FROM resumes")).scalar_one()
    assert count == 1

    # personal_data — пустые значения
    pd = sync_session.execute(text("SELECT last_name FROM personal_data")).fetchone()
    assert pd[0] is None  # пустая строка конвертируется в NULL

    # education и experience — 0 строк
    assert sync_session.execute(text("SELECT count(*) FROM education")).scalar_one() == 0
    assert sync_session.execute(text("SELECT count(*) FROM experience")).scalar_one() == 0
