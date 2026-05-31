"""Streamlit UI для сервиса извлечения данных из резюме."""

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
MAX_POLL_ATTEMPTS = 120  # ~10 минут при POLL_INTERVAL_SEC=5
MAX_FILE_SIZE_MB = 1
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

ALLOWED_EXTENSIONS = ["pdf", "docx", "odt", "jpeg", "jpg", "png"]

# MIME-типы для Streamlit file_uploader
ACCEPTED_MIME_TYPES = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.oasis.opendocument.text",
    "image/jpeg",
    "image/png",
]

# ---------------------------------------------------------------------------
# Параметры страницы
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="CV Analyzer",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Кастомные стили
# ---------------------------------------------------------------------------
st.markdown(
    """
<style>
    .block-container { padding-top: 2rem; }
    .stAlert { padding: 0.75rem 1rem; }
</style>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------
def upload_file(file_bytes: bytes, file_name: str) -> dict | None:
    """Отправляет файл в API и возвращает ответ с task_id."""
    try:
        response = requests.post(
            f"{API_URL}/api/v1/upload",
            files={"file": (file_name, file_bytes)},
            timeout=30,
        )
        if response.status_code == 202:
            logger.info("Файл загружен: task_id=%s", response.json()["task_id"])
            return response.json()
        # Ошибка валидации (422) или серверная ошибка
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
    Явно обрабатывает HTTP-коды: 200 (завершена), 202 (в работе), 404 (не найдена).
    """
    status_url = f"{API_URL}/api/v1/tasks/{task_id}"
    try:
        response = requests.get(status_url, timeout=10)
    except requests.RequestException:
        logger.exception("RequestException при polling task_id=%s", task_id)
        return None

    # Явная обработка HTTP-кодов
    if response.status_code == 404:
        logger.warning("Задача %s не найдена (404)", task_id)
        return None

    if response.status_code in (200, 202):
        return response.json()

    # Неожиданный код ответа
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
            timeout=10,
        )
        if response.status_code == 200:
            result = response.json()
            # Валидация структуры ответа API
            if not isinstance(result, dict) or "data" not in result:
                st.error("Получен некорректный формат результата от сервера.")
                logger.warning(
                    "Некорректная структура результата для task_id=%s: ожидается ключ 'data'",
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
# Отображение результата по секциям
# ---------------------------------------------------------------------------
def _render_value(label: str, value: str | None):
    """Отображает одно поле, если оно заполнено."""
    if value:
        st.markdown(f"**{label}:** {value}")


def render_personal_data(data: dict):
    """Секция: Личные данные."""
    pd = data.get("personal_data", {})
    if not pd:
        st.info("Личные данные не найдены.")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        _render_value("Фамилия", pd.get("last_name"))
        _render_value("Имя", pd.get("first_name"))
        _render_value("Отчество", pd.get("middle_name"))
    with col2:
        _render_value("Email", pd.get("email"))
        _render_value("Телефон", pd.get("phone"))
    with col3:
        _render_value("Город", pd.get("city"))
        _render_value("Дата рождения", pd.get("birth_date"))


def render_education(data: dict):
    """Секция: Образование."""
    education = data.get("education", [])
    if not education:
        st.info("Информация об образовании не найдена.")
        return

    for i, edu in enumerate(education, 1):
        with st.container(border=True):
            cols = st.columns([2, 2, 1, 1, 1])
            cols[0].markdown(f"**{edu.get('institution', 'Не указано')}**")
            cols[1].markdown(edu.get("specialty", ""))
            cols[2].markdown(f"Уровень: {edu.get('level', '')}")
            start = edu.get("start_year", "")
            end = edu.get("end_year", "")
            if start or end:
                cols[3].markdown(f"{start} - {end}")


def render_experience(data: dict):
    """Секция: Опыт работы."""
    experience = data.get("experience", [])
    if not experience:
        st.info("Информация об опыте работы не найдена.")
        return

    for i, exp in enumerate(experience, 1):
        with st.container(border=True):
            header_cols = st.columns([2, 2, 2])
            header_cols[0].markdown(f"**{exp.get('company', 'Не указано')}**")
            header_cols[1].markdown(f"Должность: {exp.get('position', '')}")
            start = exp.get("start_date", "")
            end = exp.get("end_date", "")
            if start or end:
                header_cols[2].markdown(f"Период: {start} - {end}")
            responsibilities = exp.get("responsibilities")
            if responsibilities:
                st.markdown(f"Обязанности: {responsibilities}")


def render_skills(data: dict):
    """Секция: Навыки."""
    skills = data.get("skills", {})
    if not skills:
        st.info("Информация о навыках не найдена.")
        return

    hard_skills = skills.get("hard_skills", {})
    soft_skills = skills.get("soft_skills", [])

    # Таблица hard skills
    tech = hard_skills.get("technical", [])
    prof = hard_skills.get("professional", [])
    langs = hard_skills.get("languages", [])

    col1, col2, col3 = st.columns(3)
    with col1:
        if tech:
            st.markdown("**Технические навыки**")
            for skill in tech:
                st.markdown(f"- {skill}")
    with col2:
        if prof:
            st.markdown("**Профессиональные навыки**")
            for skill in prof:
                st.markdown(f"- {skill}")
    with col3:
        if langs:
            st.markdown("**Языки**")
            for lang in langs:
                st.markdown(f"- {lang}")

    if soft_skills:
        st.markdown("**Soft skills**")
        st.markdown(", ".join(soft_skills))


def render_additional(data: dict):
    """Секция: Дополнительная информация."""
    additional = data.get("additional", {})
    if not additional:
        st.info("Дополнительная информация не найдена.")
        return

    col1, col2, col3 = st.columns(3)

    with col1:
        certificates = additional.get("certificates", [])
        if certificates:
            st.markdown("**Сертификаты**")
            for cert in certificates:
                name = cert.get("name", "")
                issuer = cert.get("issuer", "")
                year = cert.get("year", "")
                parts = [p for p in [name, issuer, year] if p]
                st.markdown(f"- {' | '.join(parts)}")

    with col2:
        projects = additional.get("projects", [])
        if projects:
            st.markdown("**Проекты**")
            for proj in projects:
                name = proj.get("name", "Без названия")
                st.markdown(f"- **{name}**")
                if proj.get("role"):
                    st.markdown(f"  Роль: {proj['role']}")
                if proj.get("description"):
                    st.markdown(f"  {proj['description']}")

    with col3:
        achievements = additional.get("achievements", {})
        awards = achievements.get("awards", [])
        publications = achievements.get("publications", [])
        conferences = achievements.get("conferences", [])

        if awards:
            st.markdown("**Награды**")
            for award in awards:
                st.markdown(f"- {award}")
        if publications:
            st.markdown("**Публикации**")
            for pub in publications:
                st.markdown(f"- {pub}")
        if conferences:
            st.markdown("**Конференции**")
            for conf in conferences:
                st.markdown(f"- {conf}")


def render_result(result_data: dict):
    """Отображает результат извлечения в виде вкладок по секциям."""
    data = result_data.get("data", {})

    tab_personal, tab_education, tab_experience, tab_skills, tab_additional = st.tabs(
        ["Личные данные", "Образование", "Опыт работы", "Навыки", "Дополнительно"]
    )

    with tab_personal:
        render_personal_data(data)

    with tab_education:
        render_education(data)

    with tab_experience:
        render_experience(data)

    with tab_skills:
        render_skills(data)

    with tab_additional:
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
    Останавливается, когда main() перестаёт вызывать этот fragment
    (задача завершена или отменена).
    """
    task_id = st.session_state.get("task_id")
    if not task_id:
        return

    # Кнопка отмены — кликабельна между запусками fragment
    if st.button("Отменить ожидание"):
        logger.info("Polling отменён пользователем для task_id=%s", task_id)
        clear_polling_state()
        st.rerun()
        return

    attempts = st.session_state.get("poll_attempts", 0)

    # Проверка лимита попыток
    if attempts >= MAX_POLL_ATTEMPTS:
        st.error(
            f"Превышено время ожидания результата "
            f"({MAX_POLL_ATTEMPTS * POLL_INTERVAL_SEC} сек). "
            "Попробуйте позже."
        )
        logger.warning(
            "Timeout polling task_id=%s: %d попыток", task_id, attempts
        )
        clear_polling_state()
        return

    # Один запрос статуса
    task_data = check_task_status(task_id)

    if task_data is None:
        st.error(
            "Не удалось получить статус задачи. Проверьте подключение к серверу."
        )
        if st.button("Повторить запрос статуса"):
            clear_polling_state()
            st.rerun()
        return

    status = task_data.get("status", "unknown")

    if status == "completed":
        # Получаем результат
        result = fetch_result(task_id)
        if result is None:
            if st.button("Повторить загрузку результата"):
                clear_polling_state()
                st.rerun()
            return

        st.session_state["result"] = result
        logger.info("Задача %s завершена, результат сохранён", task_id)
        # st.rerun() из fragment перезапускает всё приложение
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
    attempts += 1
    st.session_state["poll_attempts"] = attempts

    # Расчёт прогресса на основе estimated_seconds
    estimated = st.session_state.get("estimated_seconds", 150)
    elapsed = time.time() - st.session_state.get("poll_start_time", time.time())
    progress_pct = min(int(elapsed / estimated * 100), 95)

    if status == "pending":
        label = "Ожидание в очереди..."
    else:
        label = "Обработка резюме..."

    st.progress(progress_pct, text=label)

    remaining = max(0, estimated - elapsed)
    st.info(
        f"Статус: **{status}** | "
        f"Попытка {attempts}/{MAX_POLL_ATTEMPTS} | "
        f"Осталось ~{int(remaining)} сек."
    )

    logger.info(
        "Polling task_id=%s: статус=%s, попытка %d", task_id, status, attempts
    )


# ---------------------------------------------------------------------------
# Главная страница
# ---------------------------------------------------------------------------
def main():
    """Главная точка входа Streamlit-приложения."""
    st.title("CV Analyzer")
    st.subheader("Извлечение и структурирование данных из резюме")

    # --- Инструкция ---
    with st.expander("Инструкция по загрузке", expanded=True):
        st.markdown(
            f"""
**Поддерживаемые форматы:** {', '.join(ext.upper() for ext in ALLOWED_EXTENSIONS)}

**Ограничения:**
- Максимальный размер файла: **{MAX_FILE_SIZE_MB} МБ**
- Время обработки: ~150 секунд (зависит от содержимого)

**Как использовать:**
1. Выберите файл резюме в поддерживаемом формате
2. Нажмите «Загрузить»
3. Дождитесь завершения обработки
4. Результат будет отображён на этой странице
"""
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

        st.markdown(f"Файл: **{file_name}** ({file_size / 1024:.1f} КБ)")

        if st.button("Загрузить", type="primary", use_container_width=True):
            with st.spinner("Загрузка файла..."):
                upload_response = upload_file(uploaded_file.getvalue(), file_name)

            if upload_response is None:
                return

            task_id = upload_response["task_id"]
            estimated = upload_response.get("estimated_seconds", 150)
            st.session_state["task_id"] = task_id
            st.session_state["estimated_seconds"] = estimated
            st.session_state["poll_start_time"] = time.time()
            st.session_state["poll_attempts"] = 0

            logger.info(
                "Задача создана: task_id=%s, estimated=%ds", task_id, estimated
            )
            # Перенаправляем на polling в следующем run
            st.rerun()

    # --- Polling статуса и отображение результата ---
    task_id = st.session_state.get("task_id")

    if not task_id:
        return

    st.divider()
    st.markdown(f"**ID задачи:** `{task_id}`")

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
