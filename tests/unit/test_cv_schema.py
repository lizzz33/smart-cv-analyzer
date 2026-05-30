"""Тесты Pydantic-схем результата извлечения из резюме."""

from worker.schemas.cv import (
    CVResult,
    Education,
    Experience,
    Skills,
    Additional,
    HardSkills,
    PersonalData,
)


# ---------------------------------------------------------------------------
# PersonalData
# ---------------------------------------------------------------------------


class TestPersonalData:
    """Проверки модели персональных данных."""

    def test_full_data(self):
        """Корректные данные сохраняются."""
        pd = PersonalData(
            last_name="Ivanov",
            first_name="Ivan",
            middle_name="Petrovich",
            email="ivan@example.com",
            phone="+7-999-123-45-67",
            city="Moscow",
            birth_date="1990-01-15",
        )
        assert pd.last_name == "Ivanov"
        assert pd.email == "ivan@example.com"

    def test_partial_data(self):
        """Частичные данные — остальные поля дефолтные."""
        pd = PersonalData(last_name="Petrov")
        assert pd.last_name == "Petrov"
        assert pd.first_name == ""


# ---------------------------------------------------------------------------
# Education — год с coerce-валидатором
# ---------------------------------------------------------------------------


class TestEducation:
    """Проверки coerce-валидатора года — единственная кастомная логика."""

    def test_invalid_start_year(self):
        """Невалидный start_year (строка) -> None."""
        edu = Education(institution="MSU", start_year="две тысячи десятый", end_year=2015)
        assert edu.start_year is None
        assert edu.end_year == 2015

    def test_string_number_year(self):
        """Строка с числом конвертируется в int."""
        edu = Education(institution="MSU", start_year="2010", end_year="2015")
        assert edu.start_year == 2010
        assert edu.end_year == 2015


# ---------------------------------------------------------------------------
# Experience
# ---------------------------------------------------------------------------


class TestExperience:
    """Проверки модели опыта работы."""

    def test_full_data(self):
        """Полные данные сохраняются."""
        exp = Experience(
            company="Yandex",
            position="Backend Developer",
            start_date="2020-01",
            end_date="2023-06",
            responsibilities="Backend development",
        )
        assert exp.company == "Yandex"
        assert exp.position == "Backend Developer"


# ---------------------------------------------------------------------------
# Skills, Additional — вложенные структуры
# ---------------------------------------------------------------------------


class TestSkills:
    """Проверки вложенной структуры навыков."""

    def test_nested_data(self):
        """Вложенные данные корректно разбираются."""
        sk = Skills(
            hard_skills=HardSkills(technical=["Go"]),
            soft_skills=["Teamwork", "Leadership"],
        )
        assert sk.hard_skills.technical == ["Go"]
        assert sk.soft_skills == ["Teamwork", "Leadership"]


class TestAdditional:
    """Проверки вложенной структуры дополнительных данных."""

    def test_nested_data(self):
        from worker.schemas.cv import Certificate, Project, Achievements

        add = Additional(
            certificates=[Certificate(name="AWS")],
            projects=[Project(name="CV Analyzer")],
            achievements=Achievements(awards=["Best Paper"]),
        )
        assert add.certificates[0].name == "AWS"
        assert add.achievements.awards == ["Best Paper"]


# ---------------------------------------------------------------------------
# CVResult — корневая модель
# ---------------------------------------------------------------------------


class TestCVResult:
    """Проверки корневой модели результата."""

    def test_full_data(self):
        """Полный результат с данными во всех секциях."""
        cv = CVResult.model_validate({
            "personal_data": {
                "last_name": "Ivanov",
                "first_name": "Ivan",
                "email": "ivan@example.com",
            },
            "education": [
                {"institution": "MSU", "start_year": 2010, "end_year": 2015},
            ],
            "experience": [
                {"company": "Yandex", "position": "Dev"},
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
        })
        assert cv.personal_data.last_name == "Ivanov"
        assert cv.education[0].institution == "MSU"
        assert cv.experience[0].company == "Yandex"
        assert cv.skills.hard_skills.technical == ["Python"]
        assert cv.additional.certificates[0].name == "AWS"

    def test_partial_data(self):
        """Частичные данные — недостающие секции дефолтные."""
        cv = CVResult.model_validate({
            "personal_data": {"last_name": "Petrov"},
        })
        assert cv.personal_data.last_name == "Petrov"
        assert cv.education == []
        assert cv.experience == []

    def test_model_dump_roundtrip(self):
        """Сериализация и десериализация не теряют данные."""
        original = CVResult.model_validate({
            "personal_data": {"last_name": "Sidorov"},
            "education": [{"institution": "MIT", "start_year": 2018}],
        })
        dumped = original.model_dump()
        restored = CVResult.model_validate(dumped)
        assert restored.personal_data.last_name == "Sidorov"
        assert restored.education[0].start_year == 2018
