"""Streamlit UI для сервиса извлечения данных из резюме."""

import html as html_module
import json
import logging
import os
import time
from datetime import timedelta

import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Настройка логирования
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------
API_URL = os.environ.get("API_URL", "http://localhost:8000")
POLL_INTERVAL_SEC = 5  # секунд между запросами статуса
MAX_POLL_ATTEMPTS = 60  # = 300 сек (5 минут) максимальное автоматическое ожидание
MAX_FILE_SIZE_MB = 1
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

ALLOWED_EXTENSIONS = ["pdf", "docx", "odt", "jpeg", "jpg", "png"]

# ---------------------------------------------------------------------------
# Параметры страницы
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="CV Analyzer",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Инициализация темы
# ---------------------------------------------------------------------------
st.session_state.setdefault("theme", "light")

# ---------------------------------------------------------------------------
# SVG-иконки
# ---------------------------------------------------------------------------
_ICONS = {
    "user": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20"'
        ' fill="none" stroke="currentColor" stroke-width="1.5">'
        '<circle cx="10" cy="7" r="3.5"/>'
        '<path d="M3 17.5c0-3.5 3.1-6 7-6s7 2.5 7 6"/></svg>'
    ),
    "email": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20"'
        ' fill="none" stroke="currentColor" stroke-width="1.5">'
        '<rect x="2" y="4" width="16" height="12" rx="2"/>'
        '<path d="M2 6l8 5 8-5"/></svg>'
    ),
    "phone": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20"'
        ' fill="none" stroke="currentColor" stroke-width="1.5">'
        '<path d="M5 3h3l1.5 4-2 1.5a11 11 0 004 4L13 10.5 17 12v3a2 2 0 01-2 2'
        'C8.5 16.5 3.5 11.5 3 5a2 2 0 012-2z"/></svg>'
    ),
    "location": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20"'
        ' fill="none" stroke="currentColor" stroke-width="1.5">'
        '<path d="M10 2a5.5 5.5 0 00-5.5 5.5C4.5 12 10 18 10 18s5.5-6 5.5-10.5'
        'A5.5 5.5 0 0010 2z"/><circle cx="10" cy="7.5" r="2"/></svg>'
    ),
    "calendar": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20"'
        ' fill="none" stroke="currentColor" stroke-width="1.5">'
        '<rect x="3" y="4" width="14" height="13" rx="2"/>'
        '<path d="M3 8h14M7 2v3M13 2v3"/></svg>'
    ),
    "edu": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20"'
        ' fill="none" stroke="currentColor" stroke-width="1.5">'
        '<path d="M10 2L2 7l8 5 8-5-8-5z"/>'
        '<path d="M5 9v5c0 1.5 2.2 3 5 3s5-1.5 5-3V9"/>'
        '<path d="M16 7v6"/></svg>'
    ),
    "briefcase": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20"'
        ' fill="none" stroke="currentColor" stroke-width="1.5">'
        '<rect x="2" y="6" width="16" height="11" rx="2"/>'
        '<path d="M7 6V4a2 2 0 012-2h2a2 2 0 012 2v2"/>'
        '<path d="M2 11h16"/></svg>'
    ),
    "code": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20"'
        ' fill="none" stroke="currentColor" stroke-width="1.5">'
        '<path d="M7 6L3 10l4 4M13 6l4 4-4 4"/></svg>'
    ),
    "star": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20"'
        ' fill="none" stroke="currentColor" stroke-width="1.5">'
        '<path d="M10 2l2.4 5.5H18l-4.2 3.3 1.6 5.7L10 13l-5.4 3.5'
        ' 1.6-5.7L2 7.5h5.6z"/></svg>'
    ),
    "cert": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20"'
        ' fill="none" stroke="currentColor" stroke-width="1.5">'
        '<rect x="3" y="2" width="14" height="14" rx="2"/>'
        '<path d="M7 17v1l3-1 3 1v-1"/>'
        '<path d="M7 8l2 2 4-4"/></svg>'
    ),
    "project": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20"'
        ' fill="none" stroke="currentColor" stroke-width="1.5">'
        '<rect x="3" y="3" width="14" height="14" rx="2"/>'
        '<path d="M3 7h14M7 3v4M13 3v4"/></svg>'
    ),
    "trophy": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20"'
        ' fill="none" stroke="currentColor" stroke-width="1.5">'
        '<path d="M6 3h8v6a4 4 0 01-8 0V3z"/>'
        '<path d="M6 5H3v2a3 3 0 003 3"/>'
        '<path d="M14 5h3v2a3 3 0 01-3 3"/>'
        '<path d="M8 13v2M12 13v2M7 17h6"/></svg>'
    ),
    "book": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20"'
        ' fill="none" stroke="currentColor" stroke-width="1.5">'
        '<path d="M3 3h6v14H3zM9 3h6a2 2 0 012 2v10a2 2 0 01-2 2H9"/>'
        '<path d="M3 7h6M9 7h8"/></svg>'
    ),
    "upload": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20"'
        ' fill="none" stroke="currentColor" stroke-width="1.5">'
        '<path d="M4 16v2h12v-2M10 12V2M6 6l4-4 4 4"/></svg>'
    ),
    "file": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20"'
        ' fill="none" stroke="currentColor" stroke-width="1.5">'
        '<path d="M6 2h5l5 5v9a2 2 0 01-2 2H6a2 2 0 01-2-2V4a2 2 0 012-2z"/>'
        '<path d="M11 2v5h5"/></svg>'
    ),
    "clock": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20"'
        ' fill="none" stroke="currentColor" stroke-width="1.5">'
        '<circle cx="10" cy="10" r="8"/>'
        '<path d="M10 5v5l3.5 3.5"/></svg>'
    ),
    "check": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20"'
        ' fill="none" stroke="currentColor" stroke-width="1.5">'
        '<path d="M5 10l3 3 7-7"/></svg>'
    ),
    "spinner": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20"'
        ' fill="none" stroke="currentColor" stroke-width="2">'
        '<circle cx="10" cy="10" r="7" stroke-opacity="0.25"/>'
        '<path d="M10 3a7 7 0 017 7"/></svg>'
    ),
    "globe": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20"'
        ' fill="none" stroke="currentColor" stroke-width="1.5">'
        '<circle cx="10" cy="10" r="8"/>'
        '<ellipse cx="10" cy="10" rx="3.5" ry="8"/>'
        '<path d="M2 10h16M3 6h14M3 14h14"/></svg>'
    ),
}


def _icon(name: str, size: int = 20) -> str:
    """Возвращает HTML-строку inline SVG-иконки."""
    svg = _ICONS.get(name, "")
    return (
        f'<span class="cv-icon" style="width:{size}px;height:{size}px;'
        f'display:inline-flex;align-items:center;justify-content:center">'
        f'{svg}</span>'
    )


# ---------------------------------------------------------------------------
# Переменные темы
# ---------------------------------------------------------------------------
_THEME_VARS = {
    "light": {
        "primary": "#6366F1",
        "primary-light": "#EEF2FF",
        "card-bg": "#FFFFFF",
        "card-border": "#F1F5F9",
        "card-shadow": "0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03)",
        "text-primary": "#0F172A",
        "text-secondary": "#64748B",
        "text-muted": "#94A3B8",
        "accent-green": "#10B981",
        "accent-green-bg": "#ECFDF5",
        "accent-amber": "#F59E0B",
        "accent-amber-bg": "#FFFBEB",
        "accent-red": "#EF4444",
        "accent-red-bg": "#FEF2F2",
        "accent-blue": "#3B82F6",
        "accent-blue-bg": "#EFF6FF",
        "badge-bg": "#F1F5F9",
        "badge-text": "#475569",
        "badge-tech-bg": "#DBEAFE",
        "badge-tech-text": "#1E40AF",
        "badge-prof-bg": "#D1FAE5",
        "badge-prof-text": "#059669",
        "badge-lang-bg": "#FEF3C7",
        "badge-lang-text": "#D97706",
        "badge-soft-bg": "#EDE9FE",
        "badge-soft-text": "#7C3AED",
        "badge-level-bg": "#F3E8FF",
        "badge-level-text": "#7C3AED",
        "timeline-line": "#E2E8F0",
        "timeline-dot": "#6366F1",
        "upload-border": "#CBD5E1",
        "upload-bg": "#F8FAFC",
        "hero-gradient": "linear-gradient(135deg, #667EEA 0%, #764BA2 100%)",
        "surface": "#F8FAFC",
        "sidebar-bg": "#FFFFFF",
    },
    "dark": {
        "primary": "#818CF8",
        "primary-light": "#1E1B4B",
        "card-bg": "#1E293B",
        "card-border": "#334155",
        "card-shadow": "0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 2px 4px -1px rgba(0, 0, 0, 0.2)",
        "text-primary": "#F1F5F9",
        "text-secondary": "#94A3B8",
        "text-muted": "#64748B",
        "accent-green": "#34D399",
        "accent-green-bg": "#064E3B",
        "accent-amber": "#FBBF24",
        "accent-amber-bg": "#78350F",
        "accent-red": "#F87171",
        "accent-red-bg": "#7F1D1D",
        "accent-blue": "#60A5FA",
        "accent-blue-bg": "#1E3A5F",
        "badge-bg": "#334155",
        "badge-text": "#CBD5E1",
        "badge-tech-bg": "#1E3A5F",
        "badge-tech-text": "#93C5FD",
        "badge-prof-bg": "#064E3B",
        "badge-prof-text": "#6EE7B7",
        "badge-lang-bg": "#78350F",
        "badge-lang-text": "#FCD34D",
        "badge-soft-bg": "#2E1065",
        "badge-soft-text": "#C4B5FD",
        "badge-level-bg": "#2E1065",
        "badge-level-text": "#C4B5FD",
        "timeline-line": "#334155",
        "timeline-dot": "#818CF8",
        "upload-border": "#475569",
        "upload-bg": "#1E293B",
        "hero-gradient": "linear-gradient(135deg, #667EEA 0%, #764BA2 100%)",
        "surface": "#0F172A",
        "sidebar-bg": "#1E293B",
    },
}


def _build_css(theme: str) -> str:
    """Генерирует полный CSS для текущей темы."""
    v = _THEME_VARS.get(theme, _THEME_VARS["light"])

    return f"""<style>
/* === Переменные ({theme}) === */
:root, [data-testid="stApp"] {{
    --cv-primary: {v['primary']};
    --cv-primary-light: {v['primary-light']};
    --cv-card-bg: {v['card-bg']};
    --cv-card-border: {v['card-border']};
    --cv-card-shadow: {v['card-shadow']};
    --cv-text-primary: {v['text-primary']};
    --cv-text-secondary: {v['text-secondary']};
    --cv-text-muted: {v['text-muted']};
    --cv-accent-green: {v['accent-green']};
    --cv-accent-green-bg: {v['accent-green-bg']};
    --cv-accent-amber: {v['accent-amber']};
    --cv-accent-amber-bg: {v['accent-amber-bg']};
    --cv-accent-red: {v['accent-red']};
    --cv-accent-red-bg: {v['accent-red-bg']};
    --cv-accent-blue: {v['accent-blue']};
    --cv-accent-blue-bg: {v['accent-blue-bg']};
    --cv-badge-bg: {v['badge-bg']};
    --cv-badge-text: {v['badge-text']};
    --cv-badge-tech-bg: {v['badge-tech-bg']};
    --cv-badge-tech-text: {v['badge-tech-text']};
    --cv-badge-prof-bg: {v['badge-prof-bg']};
    --cv-badge-prof-text: {v['badge-prof-text']};
    --cv-badge-lang-bg: {v['badge-lang-bg']};
    --cv-badge-lang-text: {v['badge-lang-text']};
    --cv-badge-soft-bg: {v['badge-soft-bg']};
    --cv-badge-soft-text: {v['badge-soft-text']};
    --cv-badge-level-bg: {v['badge-level-bg']};
    --cv-badge-level-text: {v['badge-level-text']};
    --cv-timeline-line: {v['timeline-line']};
    --cv-timeline-dot: {v['timeline-dot']};
    --cv-upload-border: {v['upload-border']};
    --cv-upload-bg: {v['upload-bg']};
    --cv-hero-gradient: {v['hero-gradient']};
    --cv-surface: {v['surface']};
    --cv-sidebar-bg: {v['sidebar-bg']};
}}

/* === Сброс и базовые стили === */
* {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}}
.block-container {{
    padding-top: 2.5rem;
    max-width: 1400px;
    padding-bottom: 3rem;
}}
.stApp {{
    background-color: var(--cv-surface);
}}
main {{
    background-color: transparent !important;
}}

/* === Заголовок / hero === */
.cv-hero {{
    background: var(--cv-hero-gradient);
    color: #FFFFFF;
    padding: 2.5rem 3rem;
    border-radius: 1rem;
    margin-bottom: 2rem;
    position: relative;
    overflow: hidden;
    box-shadow: 0 10px 40px -10px rgba(102, 126, 234, 0.4);
}}
.cv-hero::before {{
    content: '';
    position: absolute;
    top: -50%;
    right: -50%;
    width: 200%;
    height: 200%;
    background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 70%);
    pointer-events: none;
}}
.cv-hero-title {{
    font-size: 2.25rem;
    font-weight: 700;
    margin: 0 0 0.5rem 0;
    letter-spacing: -0.03em;
    position: relative;
    z-index: 1;
}}
.cv-hero-subtitle {{
    font-size: 1.1rem;
    margin: 0;
    opacity: 0.95;
    font-weight: 400;
    position: relative;
    z-index: 1;
}}

/* === Загрузка файлов === */
.cv-info-card {{
    background: var(--cv-card-bg);
    border: 1px solid var(--cv-card-border);
    border-radius: 1rem;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
    box-shadow: var(--cv-card-shadow);
    transition: box-shadow 0.2s ease, border-color 0.2s ease;
}}
.cv-info-card:hover {{
    box-shadow: 0 8px 25px -5px rgba(0, 0, 0, 0.1);
    border-color: var(--cv-primary-light);
}}
.cv-info-card-header {{
    font-weight: 600;
    font-size: 0.95rem;
    color: var(--cv-text-primary);
    margin-bottom: 0.75rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}}
.cv-chip {{
    display: inline-block;
    padding: 0.35rem 0.75rem;
    border-radius: 0.5rem;
    font-size: 0.75rem;
    font-weight: 600;
    background: var(--cv-primary-light);
    color: var(--cv-primary);
    margin-right: 0.4rem;
    margin-bottom: 0.4rem;
    letter-spacing: 0.02em;
}}
.cv-info-detail {{
    font-size: 0.85rem;
    color: var(--cv-text-secondary);
    margin: 0.5rem 0 0 0;
    line-height: 1.6;
}}

.cv-file-card {{
    display: flex;
    align-items: center;
    gap: 0.75rem;
    background: var(--cv-card-bg);
    border: 1px solid var(--cv-card-border);
    border-radius: 0.75rem;
    padding: 0.75rem 1rem;
    margin: 0.75rem 0;
    box-shadow: var(--cv-card-shadow);
}}
.cv-file-info {{
    flex: 1;
}}
.cv-file-name {{
    font-weight: 600;
    color: var(--cv-text-primary);
    display: block;
}}
.cv-file-size {{
    font-size: 0.8rem;
    color: var(--cv-text-secondary);
}}
.cv-file-status {{
    font-size: 0.8rem;
    font-weight: 500;
    display: flex;
    align-items: center;
    gap: 0.35rem;
    color: var(--cv-accent-green);
}}

/* === Прогресс / статусы === */
.cv-progress-panel {{
    background: var(--cv-card-bg);
    border: 1px solid var(--cv-card-border);
    border-radius: 0.75rem;
    padding: 1.5rem;
    margin: 1rem 0;
    box-shadow: var(--cv-card-shadow);
}}
.cv-progress-header {{
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 1rem;
    font-weight: 600;
    color: var(--cv-text-primary);
}}
@keyframes cv-spin {{
    from {{ transform: rotate(0deg); }}
    to {{ transform: rotate(360deg); }}
}}
.cv-spin svg {{
    animation: cv-spin 1s linear infinite;
}}
.cv-progress-bar-track {{
    background: var(--cv-card-border);
    height: 6px;
    border-radius: 3px;
    overflow: hidden;
    margin-bottom: 0.75rem;
}}
.cv-progress-bar-fill {{
    background: var(--cv-primary);
    height: 6px;
    border-radius: 3px;
    transition: width 0.5s ease;
}}
.cv-progress-meta {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 0.85rem;
    color: var(--cv-text-secondary);
}}

.cv-status-badge {{
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.2rem 0.65rem;
    border-radius: 9999px;
    font-size: 0.8rem;
    font-weight: 500;
}}
.cv-status-badge--pending {{
    background: var(--cv-accent-amber-bg);
    color: var(--cv-accent-amber);
}}
.cv-status-badge--processing {{
    background: var(--cv-accent-blue-bg);
    color: var(--cv-accent-blue);
}}
.cv-status-badge--completed {{
    background: var(--cv-accent-green-bg);
    color: var(--cv-accent-green);
}}
.cv-status-badge--failed {{
    background: var(--cv-accent-red-bg);
    color: var(--cv-accent-red);
}}

/* === Карточки результатов === */
.cv-card {{
    background: var(--cv-card-bg);
    border: 1px solid var(--cv-card-border);
    border-radius: 1rem;
    padding: 1.5rem;
    margin-bottom: 1rem;
    box-shadow: var(--cv-card-shadow);
    transition: box-shadow 0.2s ease, transform 0.2s ease;
}}
.cv-card:hover {{
    box-shadow: 0 8px 25px -5px rgba(0, 0, 0, 0.1);
    transform: translateY(-1px);
}}
.cv-card-header {{
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 1.25rem;
    padding-bottom: 0.75rem;
    border-bottom: 1px solid var(--cv-card-border);
}}
.cv-card-title {{
    font-weight: 600;
    font-size: 1.05rem;
    color: var(--cv-text-primary);
}}

/* Сетка полей (личные данные) */
.cv-field-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 1rem;
}}
.cv-field {{
    display: flex;
    flex-direction: column;
}}
.cv-field-label {{
    font-size: 0.7rem;
    color: var(--cv-text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.2rem;
    display: flex;
    align-items: center;
    gap: 0.3rem;
}}
.cv-field-value {{
    font-size: 0.95rem;
    color: var(--cv-text-primary);
    font-weight: 500;
}}

/* Компактные личные данные */
.cv-personal-name {{
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--cv-text-primary);
    margin-bottom: 0.5rem;
}}
.cv-personal-contacts {{
    font-size: 0.9rem;
    color: var(--cv-text-secondary);
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
    align-items: center;
}}

/* === Единый стиль для карточек (образование, опыт, проекты) === */
.cv-item-card {{
    background: var(--cv-card-bg);
    border: 1px solid var(--cv-card-border);
    border-radius: 0.75rem;
    padding: 1.25rem;
    margin-bottom: 1rem;
    transition: box-shadow 0.2s ease, border-color 0.2s ease;
}}
.cv-item-card:hover {{
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
    border-color: var(--cv-primary-light);
}}
.cv-item-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
}}
.cv-item-title {{
    font-weight: 600;
    color: var(--cv-text-primary);
    font-size: 1rem;
    display: flex;
    align-items: center;
    gap: 0.4rem;
}}
.cv-item-subtitle {{
    color: var(--cv-primary);
    font-size: 0.95rem;
    font-weight: 500;
}}
.cv-item-period {{
    font-size: 0.8rem;
    color: var(--cv-text-muted);
    display: flex;
    align-items: center;
    gap: 0.3rem;
}}
.cv-item-desc {{
    font-size: 0.9rem;
    color: var(--cv-text-secondary);
    line-height: 1.5;
    margin-top: 0.5rem;
}}

/* === Бейджи (навыки) === */
.cv-badge {{
    display: inline-block;
    padding: 0.35rem 0.85rem;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 600;
    margin: 0.25rem;
    line-height: 1.4;
    letter-spacing: 0.01em;
    transition: transform 0.1s ease;
}}
.cv-badge:hover {{
    transform: scale(1.05);
}}
.cv-badge--tech {{
    background: var(--cv-badge-tech-bg);
    color: var(--cv-badge-tech-text);
}}
.cv-badge--prof {{
    background: var(--cv-badge-prof-bg);
    color: var(--cv-badge-prof-text);
}}
.cv-badge--lang {{
    background: var(--cv-badge-lang-bg);
    color: var(--cv-badge-lang-text);
}}
.cv-badge--soft {{
    background: var(--cv-badge-soft-bg);
    color: var(--cv-badge-soft-text);
}}
.cv-badge--level {{
    background: var(--cv-badge-level-bg);
    color: var(--cv-badge-level-text);
}}
.cv-badge-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
    margin-bottom: 1rem;
}}
.cv-skills-group {{
    margin-bottom: 1rem;
}}
.cv-skills-group-title {{
    font-weight: 600;
    font-size: 0.9rem;
    color: var(--cv-text-primary);
    margin: 0 0 0.5rem 0;
    display: flex;
    align-items: center;
    gap: 0.4rem;
}}

/* === Стилизация Streamlit-виджетов === */
.stTabs [data-baseweb="tab-list"] {{
    gap: 0.25rem;
}}
[data-testid="stTab"] {{
    border-radius: 0.75rem 0.75rem 0 0;
    font-size: 0.9rem;
}}
.stAlert {{
    border-radius: 0.75rem;
}}
button[kind="primary"] {{
    border-radius: 0.75rem !important;
    font-weight: 600 !important;
    transition: all 0.2s ease !important;
}}
button[kind="primary"]:hover {{
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4) !important;
}}
div[data-testid="stFileUploader"] {{
    border: 2px dashed var(--cv-upload-border);
    border-radius: 1rem;
    background: var(--cv-upload-bg);
    padding: 1.5rem;
    transition: border-color 0.2s ease, background 0.2s ease;
}}
div[data-testid="stFileUploader"]:hover {{
    border-color: var(--cv-primary);
    background: var(--cv-primary-light);
}}
div[data-testid="stFileUploader"] label {{
    color: var(--cv-text-secondary);
    font-weight: 500;
}}

/* Сообщение "не найдено" */
.cv-empty {{
    color: var(--cv-text-muted);
    font-style: italic;
    padding: 1rem 0;
    font-size: 0.9rem;
}}

/* Секция task ID */
.cv-task-id {{
    font-size: 0.85rem;
    color: var(--cv-text-muted);
    margin-bottom: 0.5rem;
}}
</style>"""


# ---------------------------------------------------------------------------
# Инъекция CSS
# ---------------------------------------------------------------------------
st.markdown(_build_css(st.session_state.theme), unsafe_allow_html=True)




# ---------------------------------------------------------------------------
# Вспомогательные функции: API
# ---------------------------------------------------------------------------
def upload_file(file_bytes: bytes, file_name: str) -> dict | None:
    """Отправляет файл в API и возвращает ответ с task_id."""
    try:
        response = requests.post(
            f"{API_URL}/api/v1/upload",
            files={"file": (file_name, file_bytes)},
            timeout=60,
        )
        if response.status_code == 202:
            logger.info("Файл загружен: task_id=%s", response.json()["task_id"])
            return response.json()
        detail = response.json().get("detail", response.text)
        st.error(f"Ошибка загрузки: {detail}")
        logger.warning("Ошибка загрузки (%d): %s", response.status_code, detail)
        return None
    except requests.ConnectionError:
        st.error("Не удалось подключиться к серверу. Проверьте, что API запущен.")
        logger.exception("ConnectionError при загрузке файла")
        return None
    except requests.Timeout:
        st.error("Превышено время ожидания при загрузке файла.")
        logger.exception("Timeout при загрузке файла")
        return None
    except Exception:
        st.error("Произошла неожиданная ошибка при загрузке.")
        logger.exception("Неожиданная ошибка при загрузке файла")
        return None


def check_task_status(task_id: str) -> dict | None:
    """Выполняет один запрос статуса задачи.

    Возвращает словарь с данными задачи или None при ошибке / 404.
    """
    status_url = f"{API_URL}/api/v1/tasks/{task_id}"
    try:
        response = requests.get(status_url, timeout=30)
    except requests.RequestException:
        logger.exception("RequestException при polling task_id=%s", task_id)
        return None

    if response.status_code == 404:
        logger.warning("Задача %s не найдена (404)", task_id)
        return None

    if response.status_code in (200, 202):
        return response.json()

    logger.warning(
        "Неожиданный статус %d при polling task_id=%s",
        response.status_code,
        task_id,
    )
    return None


def fetch_result(task_id: str) -> dict | None:
    """Получает результат обработки задачи с валидацией структуры ответа."""
    try:
        response = requests.get(
            f"{API_URL}/api/v1/tasks/{task_id}/result",
            timeout=30,
        )
        if response.status_code == 200:
            result = response.json()
            if not isinstance(result, dict) or "data" not in result:
                st.error("Получен некорректный формат результата от сервера.")
                logger.warning(
                    "Некорректная структура результата для task_id=%s:"
                    " ожидается ключ 'data'",
                    task_id,
                )
                return None
            return result
        detail = response.json().get("detail", response.text)
        st.error(f"Не удалось получить результат: {detail}")
        logger.warning(
            "Ошибка получения результата (%d): %s", response.status_code, detail
        )
        return None
    except requests.RequestException:
        st.error("Ошибка при получении результата.")
        logger.exception(
            "RequestException при получении результата task_id=%s", task_id
        )
        return None
    except (ValueError, KeyError):
        st.error("Не удалось разобрать ответ сервера.")
        logger.exception("Ошибка парсинга ответа для task_id=%s", task_id)
        return None


# ---------------------------------------------------------------------------
# HTML-хелперы
# ---------------------------------------------------------------------------
def _esc(value: str | None) -> str:
    """Экранирует значение для вставки в HTML."""
    if not value:
        return ""
    return html_module.escape(str(value))


def _field_row(label: str, value: str | None, icon_name: str) -> str:
    """Возвращает HTML-строку поля с иконкой."""
    if not value:
        return ""
    return (
        f'<div class="cv-field">'
        f'<span class="cv-field-label">{_icon(icon_name, 14)} {label}</span>'
        f'<span class="cv-field-value">{_esc(value)}</span>'
        f'</div>'
    )


def _badge(text: str, variant: str = "default") -> str:
    """Возвращает HTML-строку бейджа."""
    return f'<span class="cv-badge cv-badge--{variant}">{_esc(text)}</span>'


def _status_badge(status: str, text: str) -> str:
    """Возвращает HTML-строку статусного бейджа."""
    icon_name = {
        "pending": "clock",
        "processing": "spinner",
        "completed": "check",
        "failed": "file",
    }.get(status, "clock")
    spin_class = " cv-spin" if status == "processing" else ""
    return (
        f'<span class="cv-status-badge cv-status-badge--{status}">'
        f'<span class="{spin_class.strip()}">{_icon(icon_name, 14)}</span>'
        f' {text}</span>'
    )


def _progress_panel(pct: int, label: str, status: str, eta_sec: int) -> str:
    """Возвращает HTML-строку панели прогресса."""
    return (
        f'<div class="cv-progress-panel">'
        f'<div class="cv-progress-header">'
        f'<span class="cv-spin">{_icon("spinner", 20)}</span>'
        f'<span>{label}</span>'
        f'</div>'
        f'<div class="cv-progress-bar-track">'
        f'<div class="cv-progress-bar-fill" style="width:{pct}%"></div>'
        f'</div>'
        f'<div class="cv-progress-meta">'
        f'<span>{_status_badge(status, status)}</span>'
        f'<span>Осталось ~{eta_sec} сек.</span>'
        f'</div>'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Отображение результата по секциям
# ---------------------------------------------------------------------------
def render_personal_data(data: dict):
    """Секция: Личные данные (компактная карточка)."""
    pd = data.get("personal_data", {})
    if not pd:
        st.markdown(
            '<div class="cv-empty">Личные данные не найдены.</div>',
            unsafe_allow_html=True,
        )
        return

    # ФИО в одну строку
    last_name = _esc(pd.get("last_name", ""))
    first_name = _esc(pd.get("first_name", ""))
    middle_name = _esc(pd.get("middle_name", ""))
    full_name = f"{last_name} {first_name} {middle_name}".strip()

    # Контакты через разделители
    contacts = []
    if pd.get("email"):
        contacts.append(f'{_icon("email", 14)} {_esc(pd.get("email"))}')
    if pd.get("phone"):
        contacts.append(f'{_icon("phone", 14)} {_esc(pd.get("phone"))}')
    if pd.get("city"):
        contacts.append(f'{_icon("location", 14)} {_esc(pd.get("city"))}')
    contacts_html = ' <span style="color:var(--cv-text-muted)">|</span> '.join(contacts)

    st.markdown(
        f'<div class="cv-card">'
        f'<div class="cv-card-header">{_icon("user", 18)} '
        f'<span class="cv-card-title">Контактная информация</span></div>'
        f'<div class="cv-personal-name">{full_name}</div>'
        f'<div class="cv-personal-contacts">{contacts_html}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_education(data: dict):
    """Секция: Образование."""
    education = data.get("education", [])
    if not education:
        st.markdown(
            '<div class="cv-empty">Информация об образовании не найдена.</div>',
            unsafe_allow_html=True,
        )
        return

    # Заголовок секции
    st.markdown(
        f'<h3 style="display: flex; align-items: center; gap: 0.5rem; '
        f'margin: 2rem 0 1rem 0; color: var(--cv-text-primary); '
        f'font-size: 1.25rem; font-weight: 600;">'
        f'{_icon("edu", 20)} Образование</h3>',
        unsafe_allow_html=True,
    )

    items = []
    for edu in education:
        institution = _esc(edu.get("institution", "Не указано"))
        specialty = _esc(edu.get("specialty", ""))
        level = _esc(edu.get("level", ""))
        start = edu.get("start_year", "")
        end = edu.get("end_year", "")
        period = f"{start} - {end}" if start or end else ""

        level_badge = (
            f'<span class="cv-badge cv-badge--level">{level}</span>'
            if level
            else ""
        )

        specialty_html = (
            f'<div class="cv-item-subtitle">{specialty}</div>'
            if specialty
            else ""
        )
        period_html = (
            f'<div class="cv-item-period">'
            f'{_icon("calendar", 14)} {period}</div>'
            if period
            else ""
        )
        items.append(
            f'<div class="cv-item-card">'
            f'<div class="cv-item-header">'
            f'<span class="cv-item-title">'
            f'{_icon("edu", 16)} {institution}</span>'
            f'{level_badge}'
            f'</div>'
            f'{specialty_html}'
            f'{period_html}'
            f'</div>'
        )

    st.markdown(f'<div style="display: grid; gap: 1rem;">{"".join(items)}</div>', unsafe_allow_html=True)


def render_experience(data: dict):
    """Секция: Опыт работы."""
    experience = data.get("experience", [])
    if not experience:
        st.markdown(
            '<div class="cv-empty">Информация об опыте работы не найдена.</div>',
            unsafe_allow_html=True,
        )
        return

    # Заголовок секции
    st.markdown(
        f'<h3 style="display: flex; align-items: center; gap: 0.5rem; '
        f'margin: 2rem 0 1rem 0; color: var(--cv-text-primary); '
        f'font-size: 1.25rem; font-weight: 600;">'
        f'{_icon("briefcase", 20)} Опыт работы</h3>',
        unsafe_allow_html=True,
    )

    items = []
    for exp in experience:
        company = _esc(exp.get("company", "Не указано"))
        position = _esc(exp.get("position", ""))
        start = _esc(exp.get("start_date", ""))
        end = _esc(exp.get("end_date", ""))
        responsibilities = _esc(exp.get("responsibilities"))
        period = f"{start} - {end}" if start or end else ""

        period_html = (
            f'<div class="cv-item-period">'
            f'{_icon("calendar", 14)} {period}</div>'
            if period
            else ""
        )
        position_html = (
            f'<div class="cv-item-subtitle">{position}</div>'
            if position
            else ""
        )
        desc_html = (
            f'<div class="cv-item-desc">{responsibilities}</div>'
            if responsibilities
            else ""
        )
        items.append(
            f'<div class="cv-item-card">'
            f'<div class="cv-item-header">'
            f'<span class="cv-item-title">'
            f'{_icon("briefcase", 16)} {company}</span>'
            f'{period_html if period else ""}'
            f'</div>'
            f'{position_html}'
            f'{desc_html}'
            f'</div>'
        )

    st.markdown(f'<div style="display: grid; gap: 1rem;">{"".join(items)}</div>', unsafe_allow_html=True)


def render_skills(data: dict):
    """Секция: Навыки (компактная карточка)."""
    skills = data.get("skills", {})
    if not skills:
        st.markdown(
            '<div class="cv-empty">Информация о навыках не найдена.</div>',
            unsafe_allow_html=True,
        )
        return

    hard_skills = skills.get("hard_skills", {})
    soft_skills = skills.get("soft_skills", [])

    tech = hard_skills.get("technical", [])
    prof = hard_skills.get("professional", [])
    langs = hard_skills.get("languages", [])

    parts = []

    if tech:
        badges = "".join(_badge(s, "tech") for s in tech)
        parts.append(f'<div class="cv-badge-row">{badges}</div>')
    if prof:
        badges = "".join(_badge(s, "prof") for s in prof)
        parts.append(f'<div class="cv-badge-row">{badges}</div>')
    if langs:
        badges = "".join(_badge(s, "lang") for s in langs)
        parts.append(f'<div class="cv-badge-row">{badges}</div>')
    if soft_skills:
        badges = "".join(_badge(s, "soft") for s in soft_skills)
        parts.append(
            f'<div style="margin-top:0.5rem; padding-top:0.5rem; border-top:1px solid var(--cv-card-border)">'
            f'{badges}</div>'
        )

    if parts:
        st.markdown(
            f'<div class="cv-card">'
            f'<div class="cv-card-header">{_icon("code", 18)} '
            f'<span class="cv-card-title">Навыки</span></div>'
            f'{"".join(parts)}'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="cv-empty">Информация о навыках не найдена.</div>',
            unsafe_allow_html=True,
        )


def render_additional(data: dict):
    """Секция: Дополнительная информация."""
    additional = data.get("additional", {})
    if not additional:
        st.markdown(
            '<div class="cv-empty">Дополнительная информация не найдена.</div>',
            unsafe_allow_html=True,
        )
        return

    # Заголовок секции
    st.markdown(
        f'<h3 style="display: flex; align-items: center; gap: 0.5rem; '
        f'margin: 2rem 0 1rem 0; color: var(--cv-text-primary); '
        f'font-size: 1.25rem; font-weight: 600;">'
        f'{_icon("star", 20)} Дополнительно</h3>',
        unsafe_allow_html=True,
    )

    items = []

    # Сертификаты
    certificates = additional.get("certificates", [])
    for cert in certificates:
        name = _esc(cert.get("name", ""))
        issuer = _esc(cert.get("issuer", ""))
        year = _esc(cert.get("year", ""))
        meta = f'{issuer} | {year}' if issuer and year else (issuer or year or "")
        items.append(
            f'<div class="cv-item-card">'
            f'<div class="cv-item-header">'
            f'<span class="cv-item-title">{_icon("cert", 16)} {name}</span>'
            f'</div>'
            f'<div class="cv-item-desc">{meta}</div>'
            f'</div>'
        )

    # Проекты
    projects = additional.get("projects", [])
    for proj in projects:
        name = _esc(proj.get("name", "Без названия"))
        role = _esc(proj.get("role", ""))
        desc = _esc(proj.get("description", ""))
        role_html = (
            f'<div class="cv-item-subtitle">Роль: {role}</div>'
            if role
            else ""
        )
        desc_html = (
            f'<div class="cv-item-desc">{desc}</div>'
            if desc
            else ""
        )
        items.append(
            f'<div class="cv-item-card">'
            f'<div class="cv-item-header">'
            f'<span class="cv-item-title">{_icon("project", 16)} {name}</span>'
            f'</div>'
            f'{role_html}'
            f'{desc_html}'
            f'</div>'
        )

    # Достижения
    achievements = additional.get("achievements") or {}
    awards = achievements.get("awards", [])
    publications = achievements.get("publications", [])
    conferences = achievements.get("conferences", [])

    for award in awards:
        items.append(
            f'<div class="cv-item-card">'
            f'<div class="cv-item-desc">{_icon("trophy", 14)} {_esc(award)}</div>'
            f'</div>'
        )
    for pub in publications:
        items.append(
            f'<div class="cv-item-card">'
            f'<div class="cv-item-desc">{_icon("book", 14)} {_esc(pub)}</div>'
            f'</div>'
        )
    for conf in conferences:
        items.append(
            f'<div class="cv-item-card">'
            f'<div class="cv-item-desc">{_icon("globe", 14)} {_esc(conf)}</div>'
            f'</div>'
        )

    if items:
        st.markdown(f'<div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 1rem;">{"".join(items)}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="cv-empty">Дополнительная информация не найдена.</div>', unsafe_allow_html=True)


def render_result(result_data: dict):
    """Отображает результат извлечения в виде карточной сетки (grid layout)."""
    data = result_data.get("data", {})

    # Grid layout: 2 колонки для компактных карточек (личные данные + навыки),
    # затем полноширинные карточки для остального
    col1, col2 = st.columns(2)

    with col1:
        render_personal_data(data)

    with col2:
        render_skills(data)

    # Полноширинные карточки
    render_education(data)
    render_experience(data)
    render_additional(data)

    # Кнопка скачивания JSON
    st.divider()
    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    st.download_button(
        label="Скачать результат (JSON)",
        data=json_str,
        file_name="cv_result.json",
        mime="application/json",
    )


# ---------------------------------------------------------------------------
# Очистка состояния polling
# ---------------------------------------------------------------------------
def clear_polling_state():
    """Удаляет из session_state все ключи, связанные с polling."""
    for key in ("task_id", "poll_start_time", "poll_attempts", "estimated_seconds"):
        st.session_state.pop(key, None)


# ---------------------------------------------------------------------------
# Fragment: неблокирующий polling статуса задачи
# ---------------------------------------------------------------------------
@st.fragment(run_every=timedelta(seconds=POLL_INTERVAL_SEC))
def polling_fragment():
    """Опрашивает статус задачи без блокировки основного приложения.

    Автоматически перезапускается каждые POLL_INTERVAL_SEC секунд.
    """
    task_id = st.session_state.get("task_id")
    if not task_id:
        return

    # Кнопка отмены
    if st.button("Отменить ожидание"):
        logger.info("Polling отменён пользователем для task_id=%s", task_id)
        clear_polling_state()
        st.rerun()
        return

    attempts = st.session_state.get("poll_attempts", 0)

    # Инкремент попыток ПЕРЕД проверкой лимита (правильный порядок)
    attempts += 1
    st.session_state["poll_attempts"] = attempts

    # Проверка лимита попыток
    if attempts > MAX_POLL_ATTEMPTS:
        st.error(
            f"Превышено время ожидания результата "
            f"({MAX_POLL_ATTEMPTS * POLL_INTERVAL_SEC} сек). "
        )
        st.warning("Задача может быть ещё в обработке. Нажмите кнопку ниже, чтобы продолжить ожидание.")
        logger.warning(
            "Timeout polling task_id=%s: %d попыток", task_id, attempts
        )
        # НЕ удаляем task_id — пользователь может продолжить ожидание
        if st.button("⏳ Продолжить ждать (ещё 5 мин)"):
            st.session_state["poll_attempts"] = 0  # сброс счётчика
            st.rerun()
        return

    # Один запрос статуса
    task_data = check_task_status(task_id)

    if task_data is None:
        st.error(
            "Не удалось получить статус задачи. Проверьте подключение к серверу."
        )
        # Ошибка сети — предлагаем подождать и повторить
        if st.button("🔄 Попробовать снова"):
            st.session_state["poll_attempts"] = max(0, attempts - 1)  # откат попытки
            st.rerun()
        return

    status = task_data.get("status", "unknown")

    if status == "completed":
        result = fetch_result(task_id)
        if result is None:
            # Задача завершена, но результат не получен — предлагаем повторить
            if st.button("🔄 Повторить загрузку результата"):
                # Не сбрасываем состояние, просто повторим запрос на следующем run
                st.rerun()
            return

        st.session_state["result"] = result
        logger.info("Задача %s завершена, результат сохранён", task_id)
        st.rerun()
        return

    if status == "failed":
        st.error(
            "Задача завершилась с ошибкой. Попробуйте загрузить файл заново."
        )
        logger.warning("Задача %s завершилась с ошибкой", task_id)
        clear_polling_state()
        return

    # Задача ещё обрабатывается — показываем прогресс
    estimated = st.session_state.get("estimated_seconds", 150)
    elapsed = time.time() - st.session_state.get("poll_start_time", time.time())
    progress_pct = min(int(elapsed / estimated * 100), 95)

    if status == "pending":
        label = "Ожидание в очереди..."
    else:
        label = "Обработка резюме..."

    remaining = max(0, int(estimated - elapsed))

    st.markdown(
        _progress_panel(progress_pct, label, status, remaining),
        unsafe_allow_html=True,
    )

    logger.info(
        "Polling task_id=%s: статус=%s, попытка %d", task_id, status, attempts
    )


# ---------------------------------------------------------------------------
# Главная страница
# ---------------------------------------------------------------------------
def main():
    """Главная точка входа Streamlit-приложения."""

    # --- Hero-секция ---
    st.markdown(
        '<div class="cv-hero">'
        '<h1 class="cv-hero-title">CV Analyzer</h1>'
        '<p class="cv-hero-subtitle">'
        'Извлечение и структурирование данных из резюме</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    # --- Инструкция ---
    format_chips = "".join(
        f'<span class="cv-chip">{ext.upper()}</span>'
        for ext in ALLOWED_EXTENSIONS
    )
    st.markdown(
        f'<div class="cv-info-card">'
        f'<div class="cv-info-card-header">'
        f'{_icon("file", 18)} Поддерживаемые форматы</div>'
        f'<div>{format_chips}</div>'
        f'<p class="cv-info-detail">'
        f'Максимальный размер: <strong>{MAX_FILE_SIZE_MB} МБ</strong> '
        f'| Время обработки: ~150 сек</p>'
        f'<p class="cv-info-detail">'
        f'<strong>Извлекаемые данные:</strong> '
        f'ФИО, email, телефон, город, образование, опыт работы, '
        f'навыки (technical/professional/languages/soft), '
        f'сертификаты, проекты, достижения</p>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # --- Форма загрузки ---
    uploaded_file = st.file_uploader(
        "Выберите файл резюме",
        type=ALLOWED_EXTENSIONS,
        accept_multiple_files=False,
    )

    if uploaded_file is not None:
        # Предварительная проверка размера
        file_size = len(uploaded_file.getvalue())
        file_name = uploaded_file.name

        if file_size > MAX_FILE_SIZE_BYTES:
            st.error(
                f"Размер файла ({file_size / 1024 / 1024:.1f} МБ) "
                f"превышает допустимый лимит ({MAX_FILE_SIZE_MB} МБ)."
            )
            return

        # Карточка информации о файле
        st.markdown(
            f'<div class="cv-file-card">'
            f'<span>{_icon("file", 24)}</span>'
            f'<div class="cv-file-info">'
            f'<span class="cv-file-name">{_esc(file_name)}</span>'
            f'<span class="cv-file-size">{file_size / 1024:.1f} КБ</span>'
            f'</div>'
            f'<div class="cv-file-status">'
            f'{_icon("check", 16)} Готов к загрузке</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        if st.button("Загрузить", type="primary", use_container_width=True):
            with st.spinner("Загрузка файла..."):
                upload_response = upload_file(
                    uploaded_file.getvalue(), file_name
                )

            if upload_response is None:
                return

            task_id = upload_response["task_id"]
            estimated = upload_response.get("estimated_seconds", 150)
            st.session_state["task_id"] = task_id
            st.session_state["estimated_seconds"] = estimated
            st.session_state["poll_start_time"] = time.time()
            st.session_state["poll_attempts"] = 0

            logger.info(
                "Задача создана: task_id=%s, estimated=%ds",
                task_id,
                estimated,
            )
            # Перенаправляем на polling в следующем run
            st.rerun()

    # --- Polling статуса и отображение результата ---
    task_id = st.session_state.get("task_id")

    if not task_id:
        return

    st.divider()
    st.markdown(
        f'<div class="cv-task-id">'
        f'ID задачи: <code>{_esc(task_id)}</code></div>',
        unsafe_allow_html=True,
    )

    # Если результат уже получен — отображаем
    if "result" in st.session_state:
        st.subheader("Результат извлечения")
        render_result(st.session_state["result"])

        if st.button("Обработать новое резюме"):
            for key in (
                "task_id",
                "result",
                "estimated_seconds",
                "poll_start_time",
                "poll_attempts",
            ):
                st.session_state.pop(key, None)
            st.rerun()
        return

    # Запускаем fragment для polling (неблокирующий)
    polling_fragment()


if __name__ == "__main__":
    main()
