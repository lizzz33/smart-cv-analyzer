"""Тесты Pydantic-схем результата извлечения из резюме."""


from worker.schemas.cv import (
    Achievements,
    Additional,
    CVResult,
    Certificate,
    Education,
    Experience,
    HardSkills,
    PersonalData,
    Project,
    Skills,
)


# ---------------------------------------------------------------------------
# PersonalData
# ---------------------------------------------------------------------------


class TestPersonalData:
    """Проверки модели персональных данных."""

    def test_defaults(self):
        """Все поля по умолчанию — пустые строки."""
        pd = PersonalData()
        assert pd.last_name == ""
        assert pd.first_name == ""
        assert pd.middle_name == ""
        assert pd.email == ""
        assert pd.phone == ""
        assert pd.city == ""
        assert pd.birth_date == ""

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
    """Проверки модели образования и coerce-валидатора года."""

    def test_valid_years(self):
        """Числовые годы сохраняются корректно."""
        edu = Education(institution="MSU", start_year=2010, end_year=2015)
        assert edu.start_year == 2010
        assert edu.end_year == 2015

    def test_invalid_start_year(self):
        """Невалидный start_year (строка) -> None."""
        edu = Education(institution="MSU", start_year="две тысячи десятый", end_year=2015)
        assert edu.start_year is None
        assert edu.end_year == 2015

    def test_empty_string_year(self):
        """Пустая строка для года -> None."""
        edu = Education(institution="MSU", start_year="", end_year="")
        assert edu.start_year is None
        assert edu.end_year is None

    def test_none_year(self):
        """None для года -> None."""
        edu = Education(institution="MSU", start_year=None, end_year=None)
        assert edu.start_year is None
        assert edu.end_year is None

    def test_string_number_year(self):
        """Строка с числом конвертируется в int."""
        edu = Education(institution="MSU", start_year="2010", end_year="2015")
        assert edu.start_year == 2010
        assert edu.end_year == 2015

    def test_defaults(self):
        """Дефолтные значения."""
        edu = Education()
        assert edu.institution == ""
        assert edu.start_year is None


# ---------------------------------------------------------------------------
# Experience
# ---------------------------------------------------------------------------


class TestExperience:
    """Проверки модели опыта работы."""

    def test_defaults(self):
        """Все поля по умолчанию — пустые строки."""
        exp = Experience()
        assert exp.company == ""
        assert exp.position == ""
        assert exp.start_date == ""
        assert exp.end_date == ""
        assert exp.responsibilities == ""

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
# HardSkills
# ---------------------------------------------------------------------------


class TestHardSkills:
    """Проверки модели технических навыков."""

    def test_defaults(self):
        """Списки по умолчанию пустые."""
        hs = HardSkills()
        assert hs.technical == []
        assert hs.professional == []
        assert hs.languages == []

    def test_with_data(self):
        """Списки навыков заполняются."""
        hs = HardSkills(
            technical=["Python", "Docker"],
            professional=["Backend"],
            languages=["English", "Russian"],
        )
        assert "Python" in hs.technical
        assert len(hs.languages) == 2


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


class TestSkills:
    """Проверки модели навыков."""

    def test_defaults(self):
        """Дефолтные значения — пустые HardSkills и пустой список."""
        sk = Skills()
        assert sk.hard_skills.technical == []
        assert sk.soft_skills == []

    def test_nested_data(self):
        """Вложенные данные корректно разбираются."""
        sk = Skills(
            hard_skills=HardSkills(technical=["Go"]),
            soft_skills=["Teamwork", "Leadership"],
        )
        assert sk.hard_skills.technical == ["Go"]
        assert sk.soft_skills == ["Teamwork", "Leadership"]

    def test_from_dict(self):
        """Создание из dict (как при model_validate)."""
        sk = Skills.model_validate({
            "hard_skills": {"technical": ["Rust"], "professional": [], "languages": []},
            "soft_skills": [],
        })
        assert sk.hard_skills.technical == ["Rust"]


# ---------------------------------------------------------------------------
# Certificate, Project, Achievements
# ---------------------------------------------------------------------------


class TestCertificate:
    """Проверки модели сертификата."""

    def test_defaults(self):
        cert = Certificate()
        assert cert.name == ""
        assert cert.issuer == ""
        assert cert.year == ""

    def test_with_data(self):
        cert = Certificate(name="AWS Solutions Architect", issuer="Amazon", year="2023")
        assert cert.name == "AWS Solutions Architect"
        assert cert.year == "2023"


class TestProject:
    """Проверки модели проекта."""

    def test_defaults(self):
        proj = Project()
        assert proj.name == ""
        assert proj.role == ""
        assert proj.description == ""

    def test_with_data(self):
        proj = Project(name="CV Analyzer", role="Lead", description="ML project")
        assert proj.name == "CV Analyzer"


class TestAchievements:
    """Проверки модели достижений."""

    def test_defaults(self):
        ach = Achievements()
        assert ach.awards == []
        assert ach.publications == []
        assert ach.conferences == []

    def test_with_data(self):
        ach = Achievements(
            awards=["Best Paper 2023"],
            publications=["DOI:10.1234"],
            conferences=["PyCon 2022"],
        )
        assert len(ach.awards) == 1


# ---------------------------------------------------------------------------
# Additional
# ---------------------------------------------------------------------------


class TestAdditional:
    """Проверки модели дополнительных данных."""

    def test_defaults(self):
        add = Additional()
        assert add.certificates == []
        assert add.projects == []
        assert add.achievements.awards == []

    def test_nested_data(self):
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

    def test_defaults(self):
        """Пустой CVResult содержит дефолтные вложенные модели."""
        cv = CVResult()
        assert cv.personal_data.last_name == ""
        assert cv.education == []
        assert cv.experience == []
        assert cv.skills.hard_skills.technical == []
        assert cv.additional.certificates == []

    def test_from_empty_dict(self):
        """Создание из пустого dict — все поля дефолтные."""
        cv = CVResult.model_validate({})
        assert cv.personal_data.first_name == ""
        assert cv.education == []

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
