"""Тесты парсинга JSON из ответа модели (_extract_json)."""


from worker.pipelines._json_utils import extract_json as _extract_json

# Минимальный валидный JSON, соответствующий CVResult
VALID_CV_JSON = """{
    "personal_data": {"last_name": "Ivanov", "first_name": "Ivan"},
    "education": [],
    "experience": [],
    "skills": {"hard_skills": {"technical": [], "professional": [], "languages": []}, "soft_skills": []},
    "additional": {"certificates": [], "projects": [], "achievements": {"awards": [], "publications": [], "conferences": []}}
}"""


def test_plain_json():
    """Валидный JSON без обёрток."""
    result = _extract_json(VALID_CV_JSON)
    assert result is not None
    assert result["personal_data"]["last_name"] == "Ivanov"


def test_json_in_markdown_wrapper():
    """JSON внутри ```json ... ```."""
    text = f"```json\n{VALID_CV_JSON}\n```"
    result = _extract_json(text)
    assert result is not None
    assert result["personal_data"]["first_name"] == "Ivan"


def test_unclosed_braces():
    """Незакрытая внешняя скобка — автодополнение."""
    # Только внешняя `}` не закрыта, внутренние объекты корректны
    text = '{"personal_data": {"last_name": "Test"}, "education": [{"institution": "MSU"}]'
    result = _extract_json(text)
    assert result is not None
    assert result["personal_data"]["last_name"] == "Test"


def test_trailing_commas():
    """Trailing commas очищаются."""
    text = '{"personal_data": {"last_name": "Test",}, "education": [],}'
    result = _extract_json(text)
    assert result is not None
    assert result["personal_data"]["last_name"] == "Test"


def test_single_quotes():
    """Одинарные кавычки заменяются на двойные."""
    text = "{'personal_data': {'last_name': 'Test'}, 'education': []}"
    result = _extract_json(text)
    assert result is not None
    assert result["personal_data"]["last_name"] == "Test"


def test_no_json():
    """Нет JSON — просто текст. Возврат None."""
    result = _extract_json("Это просто текст без JSON структуры.")
    assert result is None


def test_empty_string():
    """Пустая строка — возврат None."""
    result = _extract_json("")
    assert result is None
