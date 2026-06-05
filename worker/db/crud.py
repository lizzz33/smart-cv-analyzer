"""Операции воркера с БД: обновление статуса, сохранение результата."""

import json
import logging
import re
import uuid
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from worker.schemas.cv import CVResult

logger = logging.getLogger(__name__)


def _parse_birth_date(value: str | None) -> date | None:
    """Попытка распарсить строку с датой рождения.

    Поддерживаемые форматы: YYYY-MM-DD, DD.MM.YYYY, DD/MM/YYYY.
    Если строку не удалось распарсить, возвращаем None и логируем предупреждение.
    """
    if not value or not value.strip():
        return None

    value = value.strip()

    # YYYY-MM-DD
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", value)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            logger.warning("Некорректная дата рождения (YYYY-MM-DD): %s", value)
            return None

    # DD.MM.YYYY или DD/MM/YYYY
    m = re.match(r"^(\d{1,2})[./](\d{1,2})[./](\d{4})$", value)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            logger.warning("Некорректная дата рождения (DD.MM.YYYY): %s", value)
            return None

    logger.warning("Не удалось распарсить дату рождения: %s", value)
    return None


# Карта русских названий месяцев (в родительном падеже, как в резюме)
_RUSSIAN_MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}

# Альтернативные формы месяцев (именительный падеж и сокращения)
_RUSSIAN_MONTHS_ALT = {
    "январь": 1,
    "февраль": 2,
    "март": 3,
    "апрель": 4,
    "май": 5,
    "июнь": 6,
    "июль": 7,
    "август": 8,
    "сентябрь": 9,
    "октябрь": 10,
    "ноябрь": 11,
    "декабрь": 12,
}


def _parse_experience_date(value: str | None) -> date | None:
    """Парсит дату из опыта работы в различных форматах.

    Поддерживаемые форматы:
    - "Месяц Год" (рус): "Август 2023", "августа 2023"
    - "Месяц Год" (eng): "August 2023"
    - "ГГГГ-ММ": "2023-08"
    - "н.в.", "present", "по настоящее время": текущая дата (или None)
    - Пустые строки: None

    Для "н.в." и похожих значений возвращаем None, так как дата окончания
    текущей работы не определена.
    """
    if not value or not value.strip():
        return None

    value = value.strip().lower()

    # Специальные маркеры для "текущее время"
    present_markers = {"н.в.", "по настоящее время", "present", "текущее", "сейчас"}
    if value in present_markers or any(marker in value for marker in present_markers):
        return None

    # ГГГГ-ММ (ISO-like)
    m = re.match(r"^(\d{4})-(\d{1,2})$", value)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), 1)
        except ValueError:
            logger.warning("Некорректная дата опыта (YYYY-MM): %s", value)
            return None

    # ММ.ГГГГ или ГГГГ.ММ
    m = re.match(r"^(\d{1,2})\.(\d{4})$", value)
    if m:
        try:
            return date(int(m.group(2)), int(m.group(1)), 1)
        except ValueError:
            logger.warning("Некорректная дата опыта (MM.YYYY): %s", value)
            return None

    # Русские названия месяцев
    for month_name, month_num in {**_RUSSIAN_MONTHS, **_RUSSIAN_MONTHS_ALT}.items():
        if month_name in value:
            # Извлекаем год
            year_match = re.search(r"\b(20\d{2})\b", value)
            if year_match:
                try:
                    return date(int(year_match.group(1)), month_num, 1)
                except ValueError:
                    logger.warning("Некорректная дата опыта (рус месяц): %s", value)
                    return None
            break

    # English months
    english_months = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }
    for month_name, month_num in english_months.items():
        if month_name in value:
            year_match = re.search(r"\b(20\d{2})\b", value)
            if year_match:
                try:
                    return date(int(year_match.group(1)), month_num, 1)
                except ValueError:
                    logger.warning("Некорректная дата опыта (eng месяц): %s", value)
                    return None
            break

    logger.warning("Не удалось распарсить дату опыта: %s", value)
    return None


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
                "birth_date": _parse_birth_date(pd.birth_date),
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
                "start_date": _parse_experience_date(exp.start_date) if exp.start_date else None,
                "end_date": _parse_experience_date(exp.end_date) if exp.end_date else None,
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
                "achievements": json.dumps(add.achievements.model_dump(), ensure_ascii=False),
            },
        )
