"""Pydantic-схема результата извлечения данных из резюме."""

from pydantic import BaseModel, field_validator


class PersonalData(BaseModel):
    last_name: str = ""
    first_name: str = ""
    middle_name: str = ""
    email: str = ""
    phone: str = ""
    city: str = ""
    birth_date: str = ""


class Education(BaseModel):
    institution: str = ""
    specialty: str = ""
    level: str = ""
    start_year: int | None = None
    end_year: int | None = None

    @field_validator("start_year", "end_year", mode="before")
    @classmethod
    def coerce_year(cls, v: object) -> int | None:
        """Пустые строки и невалидные значения -> None."""
        if v in ("", None):
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            return None


class Experience(BaseModel):
    company: str = ""
    position: str = ""
    start_date: str = ""
    end_date: str = ""
    responsibilities: str = ""


class HardSkills(BaseModel):
    technical: list[str] = []
    professional: list[str] = []
    languages: list[str] = []


class Skills(BaseModel):
    hard_skills: HardSkills = HardSkills()
    soft_skills: list[str] = []


class Certificate(BaseModel):
    name: str = ""
    issuer: str = ""
    year: str = ""


class Project(BaseModel):
    name: str = ""
    role: str = ""
    description: str = ""


class Achievements(BaseModel):
    awards: list[str] = []
    publications: list[str] = []
    conferences: list[str] = []


class Additional(BaseModel):
    certificates: list[Certificate] = []
    projects: list[Project] = []
    achievements: Achievements = Achievements()


class CVResult(BaseModel):
    personal_data: PersonalData = PersonalData()
    education: list[Education] = []
    experience: list[Experience] = []
    skills: Skills = Skills()
    additional: Additional = Additional()
