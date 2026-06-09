"""Общие утилиты для парсинга JSON из ответов ML-моделей."""

import json
import logging
import re

from worker.schemas.cv import CVResult

logger = logging.getLogger(__name__)


def _extract_skill_name(skill: str | dict) -> str:
    """Извлекает название навыка из строки или словаря."""
    if isinstance(skill, str):
        return skill
    if isinstance(skill, dict):
        # Приоритет полей для извлечения названия
        for key in ["name", "title", "skill", "technology", "description"]:
            if key in skill and skill[key]:
                return str(skill[key])
        # Fallback на любое строковое значение
        for value in skill.values():
            if value:
                return str(value)
    return str(skill)


def _normalize_additional(data: dict) -> dict:
    """Нормализация поля additional: если LLM вернул список вместо объекта."""
    if "additional" in data and isinstance(data["additional"], list):
        # LLM вернул additional как список, берём первый элемент
        if data["additional"]:
            first_item = data["additional"][0]
            if isinstance(first_item, dict):
                data["additional"] = first_item
                logger.info("Нормализован additional: преобразован из списка в объект")
            else:
                # Если первый элемент не dict, создаём пустую структуру
                data["additional"] = {
                    "certificates": [],
                    "projects": [],
                    "achievements": {"awards": [], "publications": [], "conferences": []}
                }
                logger.info("Нормализован additional: создана пустая структура")
        else:
            # Пустой список -> пустая структура
            data["additional"] = {
                "certificates": [],
                "projects": [],
                "achievements": {"awards": [], "publications": [], "conferences": []}
            }
            logger.info("Нормализован additional: пустой список -> пустая структура")
    return data


def _normalize_experience(data: dict) -> dict:
    """Нормализация поля experience: строковые поля могут прийти как списки."""
    if "experience" in data and isinstance(data["experience"], list):
        for exp in data["experience"]:
            if isinstance(exp, dict):
                # Все строковые поля в experience, которые LLM может вернуть как список
                string_fields = ["company", "position", "start_date", "end_date", "responsibilities"]
                for field in string_fields:
                    if field in exp and isinstance(exp[field], list):
                        # Превращаем список в строку, объединяя элементы
                        exp[field] = "\n".join(
                            str(item) for item in exp[field] if item is not None
                        )
                        logger.info(f"Нормализован experience[].{field}: список -> строка")
    return data


def _normalize_skills(data: dict) -> dict:
    """Нормализация поля skills: если hard_skills — список, превращаем в структуру."""
    if "skills" in data and isinstance(data["skills"], dict):
        skills = data["skills"]

        # Нормализация hard_skills структуры
        if "hard_skills" in skills:
            if isinstance(skills["hard_skills"], list):
                # LLM вернул плоский список вместо структуры
                raw_skills = skills["hard_skills"]
                technical = []
                professional = []
                languages = []

                # Простая эвристика для распределения навыков
                for skill in raw_skills:
                    skill_name = _extract_skill_name(skill)
                    skill_lower = skill_name.lower()
                    # Определяем категорию по ключевым словам
                    if any(w in skill_lower for w in ["python", "java", "javascript", "sql", "docker", "kubernetes",
                                                        "git", "linux", "react", "angular", "django", "flask",
                                                        "tensorflow", "pytorch", "pandas", "numpy", "machine learning",
                                                        "ml", "ai", "nlp", "api", "rest", "graphql", "mongodb",
                                                        "postgresql", "redis", "aws", "azure", "gcp"]):
                        technical.append(skill_name)
                    elif any(w in skill_lower for w in ["english", "русский", "language", "a1", "a2", "b1", "b2",
                                                          "c1", "c2", "intermediate", "advanced", "fluent",
                                                          "native", "deutsch", "francais"]):
                        languages.append(skill_name)
                    else:
                        # По умолчанию — professional
                        professional.append(skill_name)

                skills["hard_skills"] = {
                    "technical": technical,
                    "professional": professional,
                    "languages": languages
                }
                logger.info("Нормализован hard_skills: %d технических, %d профессиональных, %d языков",
                           len(technical), len(professional), len(languages))
            elif isinstance(skills["hard_skills"], dict):
                # LLM вернул структуру, но значения могут быть dicts instead of strings
                for key in ["technical", "professional", "languages"]:
                    if key in skills["hard_skills"] and isinstance(skills["hard_skills"][key], list):
                        skills["hard_skills"][key] = [
                            _extract_skill_name(skill) for skill in skills["hard_skills"][key]
                        ]
                        logger.info("Нормализован %s: %d навыков", key, len(skills["hard_skills"][key]))

        # Нормализация soft_skills
        if "soft_skills" in skills and isinstance(skills["soft_skills"], list):
            skills["soft_skills"] = [
                _extract_skill_name(skill) for skill in skills["soft_skills"]
            ]

    return data


def extract_json(text: str) -> dict | None:
    """Извлечение и восстановление JSON из ответа модели."""
    # Удаление markdown-обёрток
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)

    start = text.find("{")
    if start == -1:
        return None

    # Подсчёт скобок для определения конца JSON
    brace_count = 0
    end = start
    for i in range(start, len(text)):
        if text[i] == "{":
            brace_count += 1
        elif text[i] == "}":
            brace_count -= 1
            if brace_count == 0:
                end = i + 1
                break

    # Если JSON не закрыт — берём весь остаток текста
    if end == start:
        json_str = text[start:]
        open_braces = json_str.count("{") - json_str.count("}")
        open_brackets = json_str.count("[") - json_str.count("]")
        json_str += "]" * open_brackets + "}" * open_braces
        json_str = re.sub(r",\s*$", "", json_str)
    else:
        json_str = text[start:end]

    # Очистка trailing commas
    json_str = re.sub(r",\s*([}\]])", r"\1", json_str)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        try:
            data = json.loads(json_str.replace("'", '"'))
        except json.JSONDecodeError:
            logger.warning("Не удалось распарсить JSON из ответа модели")
            return None

    # Нормализация данных перед валидацией
    data = _normalize_additional(data)
    data = _normalize_skills(data)
    data = _normalize_experience(data)

    # Валидация через Pydantic
    try:
        validated = CVResult.model_validate(data)
        return validated.model_dump()
    except Exception:
        logger.warning("JSON не прошёл валидацию схемы, возврат как есть", exc_info=True)
        return data
