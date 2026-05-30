"""Тесты функций отображения результата (ui/app.py).

Кейсы 23-44 из docs/test_plan_ui.md.
"""

from unittest.mock import MagicMock, patch

import pytest

from ui.app import (
    render_additional,
    render_education,
    render_experience,
    render_personal_data,
    render_result,
    render_skills,
)


# ---------------------------------------------------------------------------
# Вспомогательные фикстуры
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_st():
    """Мок streamlit с настроенными columns/container/tabs.

    Колонки используют тот же mock-объект markdown, что и st,
    чтобы вызовы cols[0].markdown(...) попадали в st.markdown.call_args_list.
    """
    with patch("ui.app.st") as st_mock:
        # columns(N) или columns([spec...]) — возвращает список колонок
        def _columns(*args, **kwargs):
            spec = args[0] if args else kwargs.get("spec", 3)
            n = spec if isinstance(spec, int) else len(spec)
            cols = []
            for _ in range(n):
                col = MagicMock()
                # Общий mock-объект — все вызовы markdown собираются в одном месте
                col.markdown = st_mock.markdown
                cols.append(col)
            return cols

        st_mock.columns.side_effect = _columns
        # container — контекстный менеджер
        st_mock.container.return_value = MagicMock()
        # tabs — возвращает список контекстных менеджеров
        st_mock.tabs.side_effect = lambda labels: [MagicMock() for _ in labels]
        yield st_mock


@pytest.fixture
def full_cv_data():
    """Полные данные резюме для тестирования."""
    return {
        "personal_data": {
            "last_name": "Иванов",
            "first_name": "Иван",
            "middle_name": "Иваныч",
            "email": "a@b.c",
            "phone": "+7900",
            "city": "Москва",
            "birth_date": "1990-01-01",
        },
        "education": [
            {
                "institution": "МГУ",
                "specialty": "CS",
                "level": "Магистр",
                "start_year": 2018,
                "end_year": 2020,
            },
            {
                "institution": "МФТИ",
                "specialty": "Math",
                "level": "Бакалавр",
            },
        ],
        "experience": [
            {
                "company": "Яндекс",
                "position": "Dev",
                "start_date": "2020",
                "end_date": "2023",
                "responsibilities": "Разработка",
            }
        ],
        "skills": {
            "hard_skills": {
                "technical": ["Python"],
                "professional": ["Аналитика"],
                "languages": ["Английский"],
            },
            "soft_skills": ["Коммуникация"],
        },
        "additional": {
            "certificates": [{"name": "AWS", "issuer": "Amazon", "year": "2023"}],
            "projects": [{"name": "Site", "role": "Lead", "description": "Web app"}],
            "achievements": {
                "awards": ["Победитель хакатона"],
                "publications": ["Статья в журнале"],
                "conferences": ["PyCon 2023"],
            },
        },
    }


# ---------------------------------------------------------------------------
# render_personal_data()
# ---------------------------------------------------------------------------


class TestRenderPersonalData:
    """render_personal_data() — секция «Личные данные»."""

    # Кейс 23: все 7 полей заполнены
    def test_all_fields(self, mock_st):
        data = {
            "personal_data": {
                "last_name": "Иванов",
                "first_name": "Иван",
                "middle_name": "Иваныч",
                "email": "a@b.c",
                "phone": "+7900",
                "city": "Москва",
                "birth_date": "1990-01-01",
            }
        }
        render_personal_data(data)

        # Должно быть 7 вызовов markdown (по одному на поле)
        md_calls = mock_st.markdown.call_args_list
        md_texts = " ".join(str(c) for c in md_calls)
        for field in ("Иванов", "Иван", "Иваныч", "a@b.c", "+7900", "Москва", "1990-01-01"):
            assert field in md_texts, f"Поле '{field}' не найдено в выводе"
        mock_st.info.assert_not_called()

    # Кейс 26: отсутствует ключ personal_data
    def test_missing_personal_data(self, mock_st):
        render_personal_data({})

        mock_st.info.assert_called_once()
        assert "не найдены" in mock_st.info.call_args[0][0]


# ---------------------------------------------------------------------------
# render_education()
# ---------------------------------------------------------------------------


class TestRenderEducation:
    """render_education() — секция «Образование»."""

    # Кейс 27: две записи
    def test_two_entries(self, mock_st):
        data = {
            "education": [
                {
                    "institution": "МГУ",
                    "specialty": "CS",
                    "level": "Магистр",
                    "start_year": 2018,
                    "end_year": 2020,
                },
                {
                    "institution": "МФТИ",
                    "specialty": "Math",
                    "level": "Бакалавр",
                },
            ]
        }
        render_education(data)

        md_calls = mock_st.markdown.call_args_list
        md_texts = " ".join(str(c) for c in md_calls)
        assert "МГУ" in md_texts
        assert "МФТИ" in md_texts
        assert "2018 - 2020" in md_texts
        # Два контейнера (два вызова container)
        assert mock_st.container.call_count == 2

    # Кейс 28: пустой массив
    def test_empty_array(self, mock_st):
        render_education({"education": []})

        mock_st.info.assert_called_once()
        assert "не найдена" in mock_st.info.call_args[0][0]


# ---------------------------------------------------------------------------
# render_experience()
# ---------------------------------------------------------------------------


class TestRenderExperience:
    """render_experience() — секция «Опыт работы»."""

    # Кейс 30: с обязанностями
    def test_with_responsibilities(self, mock_st):
        data = {
            "experience": [
                {
                    "company": "Яндекс",
                    "position": "Dev",
                    "start_date": "2020",
                    "end_date": "2023",
                    "responsibilities": "Разработка",
                }
            ]
        }
        render_experience(data)

        md_calls = mock_st.markdown.call_args_list
        md_texts = " ".join(str(c) for c in md_calls)
        assert "Яндекс" in md_texts
        assert "Обязанности" in md_texts
        assert "Разработка" in md_texts

    # Кейс 31: без обязанностей
    def test_without_responsibilities(self, mock_st):
        data = {
            "experience": [{"company": "Яндекс", "position": "Dev"}]
        }
        render_experience(data)

        md_calls = mock_st.markdown.call_args_list
        md_texts = " ".join(str(c) for c in md_calls)
        assert "Яндекс" in md_texts
        assert "Обязанности" not in md_texts

    # Кейс 32: пустой массив
    def test_empty_array(self, mock_st):
        render_experience({"experience": []})

        mock_st.info.assert_called_once()
        assert "не найдена" in mock_st.info.call_args[0][0]


# ---------------------------------------------------------------------------
# render_skills()
# ---------------------------------------------------------------------------


class TestRenderSkills:
    """render_skills() — секция «Навыки»."""

    # Кейс 33: все категории
    def test_all_categories(self, mock_st):
        data = {
            "skills": {
                "hard_skills": {
                    "technical": ["Python"],
                    "professional": ["Аналитика"],
                    "languages": ["Английский"],
                },
                "soft_skills": ["Коммуникация"],
            }
        }
        render_skills(data)

        md_calls = mock_st.markdown.call_args_list
        md_texts = " ".join(str(c) for c in md_calls)
        assert "Python" in md_texts
        assert "Аналитика" in md_texts
        assert "Английский" in md_texts
        assert "Коммуникация" in md_texts
        assert "Технические" in md_texts
        assert "Soft skills" in md_texts

    # Кейс 34: только soft_skills
    def test_only_soft_skills(self, mock_st):
        data = {"skills": {"soft_skills": ["Коммуникация"]}}
        render_skills(data)

        md_calls = mock_st.markdown.call_args_list
        md_texts = " ".join(str(c) for c in md_calls)
        assert "Коммуникация" in md_texts
        assert "Soft skills" in md_texts

    # Кейс 35: пустой skills
    def test_empty_skills(self, mock_st):
        render_skills({"skills": {}})

        mock_st.info.assert_called_once()
        assert "не найдена" in mock_st.info.call_args[0][0]


# ---------------------------------------------------------------------------
# render_additional()
# ---------------------------------------------------------------------------


class TestRenderAdditional:
    """render_additional() — секция «Дополнительная информация»."""

    # Кейс 37: полные данные
    def test_full_data(self, mock_st):
        data = {
            "additional": {
                "certificates": [{"name": "AWS", "issuer": "Amazon", "year": "2023"}],
                "projects": [{"name": "Site", "role": "Lead", "description": "Web app"}],
                "achievements": {
                    "awards": ["Победитель хакатона"],
                    "publications": ["Статья"],
                    "conferences": ["PyCon 2023"],
                },
            }
        }
        render_additional(data)

        md_calls = mock_st.markdown.call_args_list
        md_texts = " ".join(str(c) for c in md_calls)
        assert "AWS" in md_texts
        assert "Amazon" in md_texts
        assert "Site" in md_texts
        assert "Победитель" in md_texts
        assert "Статья" in md_texts
        assert "PyCon" in md_texts

    # Кейс 41: отсутствует additional
    def test_missing_additional(self, mock_st):
        render_additional({})

        mock_st.info.assert_called_once()
        assert "не найдена" in mock_st.info.call_args[0][0]


# ---------------------------------------------------------------------------
# render_result()
# ---------------------------------------------------------------------------


class TestRenderResult:
    """render_result() — отображение результата в виде вкладок."""

    # Кейс 42: полные данные — 5 вкладок + кнопка скачивания
    def test_full_data(self, mock_st, full_cv_data):
        render_result({"data": full_cv_data})

        # 5 вкладок
        mock_st.tabs.assert_called_once()
        tab_labels = mock_st.tabs.call_args[0][0]
        assert len(tab_labels) == 5
        # Кнопка скачивания
        mock_st.download_button.assert_called_once()

    # Кейс 44: JSON скачивания — mime и file_name
    def test_download_button_params(self, mock_st):
        render_result({"data": {"personal_data": {}}})

        mock_st.download_button.assert_called_once()
        _, kwargs = mock_st.download_button.call_args
        assert kwargs["file_name"] == "cv_result.json"
        assert kwargs["mime"] == "application/json"
