"""Фикстуры для модульных тестов UI."""

import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Подмена streamlit для импорта ui.app без запуска Streamlit-сервера.
#
# Модуль ui/app.py вызывает st.set_page_config() и st.markdown() на уровне
# модуля, что требует активного контекста Streamlit. Мок позволяет импортировать
# отдельные функции без поднятия сервера.
# ---------------------------------------------------------------------------

# Принудительно импортируем оригинальный streamlit до подмены
import streamlit as _real_streamlit  # noqa: E402

_mock_st = MagicMock()
# Декоратор @st.fragment — возвращает исходную функцию без обёртки
_mock_st.fragment = lambda **_kwargs: lambda fn: fn

sys.modules["streamlit"] = _mock_st

# Импортируем модуль с подменённым streamlit
import ui.app  # noqa: E402, F401

# Восстанавливаем оригинальный streamlit (нужен для AppTest в test_ui_main.py)
sys.modules["streamlit"] = _real_streamlit
