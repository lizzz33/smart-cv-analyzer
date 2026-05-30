"""Общие утилиты для парсинга JSON из ответов ML-моделей."""

import json
import logging
import re

from worker.schemas.cv import CVResult

logger = logging.getLogger(__name__)


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

    # Валидация через Pydantic
    try:
        validated = CVResult.model_validate(data)
        return validated.model_dump()
    except Exception:
        logger.warning("JSON не прошёл валидацию схемы, возврат как есть", exc_info=True)
        return data
