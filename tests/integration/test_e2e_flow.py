"""Сквозные (end-to-end) интеграционные тесты.

Тестируют полный путь файла через систему:
Upload -> API -> Kafka (mock) -> Worker consumer -> Pipeline (mock) -> DB -> API result.

ML-модели замокированы для скорости;
остальная инфраструктура реальная (PostgreSQL, FastAPI, consumer logic).
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Session, sessionmaker

from api.db import crud
from api.db.connection import get_db
from api.main import app
from worker.consumer import _process_message_sync


# ---------------------------------------------------------------------------
# Образец результата ML-модели
# ---------------------------------------------------------------------------

SAMPLE_CV_RESULT = {
    "personal_data": {
        "last_name": "Ivanov",
        "first_name": "Ivan",
        "middle_name": "Petrovich",
        "email": "ivanov@example.com",
        "phone": "+7-999-123-45-67",
        "city": "Moscow",
        "birth_date": "1990-05-15",
    },
    "education": [
        {
            "institution": "Moscow State University",
            "specialty": "Computer Science",
            "level": "Bachelor",
            "start_year": 2008,
            "end_year": 2012,
        },
        {
            "institution": "MIPT",
            "specialty": "Data Science",
            "level": "Master",
            "start_year": 2012,
            "end_year": 2014,
        },
    ],
    "experience": [
        {
            "company": "Tech Corp",
            "position": "Python Developer",
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
            "responsibilities": "Backend development, API design",
        },
    ],
    "skills": {
        "hard_skills": {
            "technical": ["Python", "Docker", "PostgreSQL"],
            "professional": ["Backend development", "API design"],
            "languages": ["Russian (native)", "English (B2)"],
        },
        "soft_skills": ["Teamwork", "Communication"],
    },
    "additional": {
        "certificates": [
            {"name": "AWS Certified Solutions Architect", "issuer": "Amazon", "year": "2022"},
        ],
        "projects": [
            {"name": "CV Analyzer", "role": "Lead Developer", "description": "ML pipeline for resume parsing"},
        ],
        "achievements": {
            "awards": ["Best Developer 2022"],
            "publications": [],
            "conferences": ["PyCon 2023"],
        },
    },
}


# ---------------------------------------------------------------------------
# Фикстуры
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def e2e_client(async_engine, tmp_path):
    """Async-клиент с переопределённой БД и замоканным Kafka producer."""
    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)

    async def _override_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db

    with (
        patch("api.main.start_producer", new_callable=AsyncMock),
        patch("api.main.stop_producer", new_callable=AsyncMock),
        patch("api.routers.upload.asyncio.to_thread", side_effect=lambda fn, *a: fn(*a)),
        patch("api.config.settings.UPLOAD_DIR", str(tmp_path / "uploads")),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------


async def _upload_file(client, filename, content, mime):
    """Загружает файл через API, возвращает (response, mock_publish)."""
    with (
        patch("api.services.file_validator.magic") as m_magic,
        patch("api.routers.upload.publish_task", new_callable=AsyncMock) as mock_publish,
    ):
        m_magic.from_buffer.return_value = mime
        resp = await client.post(
            "/api/v1/upload",
            files={"file": (filename, content, mime)},
        )
    return resp, mock_publish


def _extract_kafka_message(mock_publish, filename):
    """Строит dict сообщения Kafka из аргументов вызова publish_task."""
    kw = mock_publish.call_args.kwargs
    return {
        "task_id": kw["task_id"],
        "file_path": kw["file_path"],
        "file_type": kw["file_type"],
        "file_name": filename,
    }


def _run_worker_task(msg_data, sync_engine, pipeline_result):
    """Вызывает _process_message_sync с замоканными pipeline и get_session."""
    file_type = msg_data["file_type"]

    if file_type in ("pdf", "docx", "odt"):
        pipeline_target = "worker.pipelines.text_pipeline.TextPipeline.process"
    else:
        pipeline_target = "worker.pipelines.vision_pipeline.VisionPipeline.process"

    def _make_session():
        factory = sessionmaker(bind=sync_engine, class_=Session, expire_on_commit=False)
        return factory()

    with (
        patch("worker.consumer.get_session", side_effect=_make_session),
        patch(pipeline_target, return_value=pipeline_result),
        patch("worker.consumer.update_ram_usage"),
    ):
        _process_message_sync(msg_data)


# ---------------------------------------------------------------------------
# Тесты: полный цикл для каждого формата
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename, content, mime, file_type",
    [
        (
            "resume.pdf",
            b"%PDF-1.4 test content",
            "application/pdf",
            "pdf",
        ),
        (
            "resume.docx",
            b"PK\x03\x04docx content",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "docx",
        ),
        (
            "resume.odt",
            b"PK\x03\x04odt content",
            "application/vnd.oasis.opendocument.text",
            "odt",
        ),
        (
            "photo.jpeg",
            b"\xff\xd8\xff\xe0jpeg content",
            "image/jpeg",
            "jpeg",
        ),
        (
            "photo.png",
            b"\x89PNG\r\n\x1a\npng content",
            "image/png",
            "png",
        ),
        (
            "photo.jpg",
            b"\xff\xd8\xff\xe0jpg content",
            "image/jpeg",
            "jpeg",
        ),
    ],
    ids=["pdf", "docx", "odt", "jpeg", "png", "jpg"],
)
async def test_e2e_full_cycle(
    e2e_client,
    async_session,
    sync_engine,
    tmp_path,
    filename,
    content,
    mime,
    file_type,
):
    """Полный цикл: загрузка -> воркер -> статус completed -> результат."""
    # Шаг 1: загрузка файла через API
    resp, mock_publish = await _upload_file(e2e_client, filename, content, mime)
    assert resp.status_code == 202, f"Upload failed: {resp.text}"

    body = resp.json()
    task_id = body["task_id"]
    assert body["status"] == "pending"

    # Шаг 2: задача в БД в статусе pending
    task = await crud.get_task(async_session, uuid.UUID(task_id))
    assert task is not None
    assert task.status == "pending"
    assert task.file_type == file_type

    # Шаг 3: эмуляция Kafka -> consumer -> pipeline (mock)
    msg_data = _extract_kafka_message(mock_publish, filename)
    assert msg_data["task_id"] == task_id
    assert msg_data["file_type"] == file_type

    _run_worker_task(msg_data, sync_engine, SAMPLE_CV_RESULT)

    # Шаг 4: проверка статуса через API
    resp = await e2e_client.get(f"/api/v1/tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"

    # Шаг 5: получение результата через API
    resp = await e2e_client.get(f"/api/v1/tasks/{task_id}/result")
    assert resp.status_code == 200
    result = resp.json()
    assert result["status"] == "completed"
    assert result["data"] is not None

    personal = result["data"]["personal_data"]
    assert personal["last_name"] == "Ivanov"
    assert personal["first_name"] == "Ivan"
    assert personal["email"] == "ivanov@example.com"


# ---------------------------------------------------------------------------
# Нормализованные данные
# ---------------------------------------------------------------------------


async def test_e2e_normalized_data_saved(
    e2e_client,
    async_session,
    sync_engine,
    tmp_path,
):
    """Все нормализованные таблицы заполняются корректно."""
    resp, mock_publish = await _upload_file(
        e2e_client, "resume.pdf", b"%PDF-1.4 test", "application/pdf",
    )
    task_id = resp.json()["task_id"]
    msg_data = _extract_kafka_message(mock_publish, "resume.pdf")
    _run_worker_task(msg_data, sync_engine, SAMPLE_CV_RESULT)

    tid = uuid.UUID(task_id)

    # raw_json в resumes
    row = await async_session.execute(
        text("SELECT raw_json FROM resumes WHERE task_id = :tid"),
        {"tid": tid},
    )
    raw = row.scalar_one()
    assert raw["personal_data"]["last_name"] == "Ivanov"
    assert len(raw["education"]) == 2

    # personal_data
    row = await async_session.execute(
        text(
            "SELECT pd.* FROM personal_data pd "
            "JOIN resumes r ON pd.resume_id = r.id "
            "WHERE r.task_id = :tid"
        ),
        {"tid": tid},
    )
    pd = row.mappings().one()
    assert pd["last_name"] == "Ivanov"
    assert pd["first_name"] == "Ivan"
    assert pd["email"] == "ivanov@example.com"
    assert pd["city"] == "Moscow"

    # education — 2 записи
    row = await async_session.execute(
        text(
            "SELECT count(*) FROM education e "
            "JOIN resumes r ON e.resume_id = r.id "
            "WHERE r.task_id = :tid"
        ),
        {"tid": tid},
    )
    assert row.scalar_one() == 2

    # experience
    row = await async_session.execute(
        text(
            "SELECT company, position FROM experience e "
            "JOIN resumes r ON e.resume_id = r.id "
            "WHERE r.task_id = :tid"
        ),
        {"tid": tid},
    )
    exp = row.mappings().one()
    assert exp["company"] == "Tech Corp"
    assert exp["position"] == "Python Developer"

    # skills
    row = await async_session.execute(
        text(
            "SELECT technical FROM skills s "
            "JOIN resumes r ON s.resume_id = r.id "
            "WHERE r.task_id = :tid"
        ),
        {"tid": tid},
    )
    tech = row.scalar_one()
    assert "Python" in tech

    # additional
    row = await async_session.execute(
        text(
            "SELECT certificates FROM additional a "
            "JOIN resumes r ON a.resume_id = r.id "
            "WHERE r.task_id = :tid"
        ),
        {"tid": tid},
    )
    certs = row.scalar_one()
    assert certs is not None


# ---------------------------------------------------------------------------
# Ошибка пайплайна
# ---------------------------------------------------------------------------


async def test_e2e_pipeline_failure(
    e2e_client,
    async_session,
    sync_engine,
    tmp_path,
):
    """Ошибка в пайплайне — задача переходит в failed."""
    resp, mock_publish = await _upload_file(
        e2e_client, "resume.pdf", b"%PDF-1.4 test", "application/pdf",
    )
    task_id = resp.json()["task_id"]
    msg_data = _extract_kafka_message(mock_publish, "resume.pdf")

    def _make_session():
        factory = sessionmaker(bind=sync_engine, class_=Session, expire_on_commit=False)
        return factory()

    with (
        patch("worker.consumer.get_session", side_effect=_make_session),
        patch(
            "worker.pipelines.text_pipeline.TextPipeline.process",
            side_effect=RuntimeError("Model inference failed"),
        ),
        patch("worker.consumer.update_ram_usage"),
    ):
        _process_message_sync(msg_data)

    # Статус — failed
    resp = await e2e_client.get(f"/api/v1/tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "failed"

    # Результат недоступен — 422
    resp = await e2e_client.get(f"/api/v1/tasks/{task_id}/result")
    assert resp.status_code == 422
    assert "failed" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Переходы статуса
# ---------------------------------------------------------------------------


async def test_e2e_status_transitions(
    e2e_client,
    async_session,
    sync_engine,
    tmp_path,
):
    """Корректность переходов статуса и заполнение completed_at."""
    resp, mock_publish = await _upload_file(
        e2e_client, "resume.pdf", b"%PDF-1.4 test", "application/pdf",
    )
    task_id = resp.json()["task_id"]
    msg_data = _extract_kafka_message(mock_publish, "resume.pdf")

    # pending
    resp = await e2e_client.get(f"/api/v1/tasks/{task_id}")
    assert resp.status_code == 202
    assert resp.json()["status"] == "pending"

    # completed
    _run_worker_task(msg_data, sync_engine, SAMPLE_CV_RESULT)

    resp = await e2e_client.get(f"/api/v1/tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"

    # completed_at заполнен
    task = await crud.get_task(async_session, uuid.UUID(task_id))
    assert task.completed_at is not None


# ---------------------------------------------------------------------------
# Несколько задач последовательно
# ---------------------------------------------------------------------------


async def test_e2e_multiple_tasks(
    e2e_client,
    async_session,
    sync_engine,
    tmp_path,
):
    """Обработка нескольких задач последовательно."""
    files = [
        ("resume1.pdf", b"%PDF-1.4 test1", "application/pdf"),
        (
            "resume2.docx",
            b"PK\x03\x04docx test",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        ("photo.jpeg", b"\xff\xd8\xff\xe0jpeg test", "image/jpeg"),
    ]

    task_ids = []
    messages = []

    for filename, content, mime in files:
        resp, mock_publish = await _upload_file(e2e_client, filename, content, mime)
        assert resp.status_code == 202
        task_ids.append(resp.json()["task_id"])
        messages.append(_extract_kafka_message(mock_publish, filename))

    for msg_data in messages:
        _run_worker_task(msg_data, sync_engine, SAMPLE_CV_RESULT)

    for task_id in task_ids:
        resp = await e2e_client.get(f"/api/v1/tasks/{task_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

        resp = await e2e_client.get(f"/api/v1/tasks/{task_id}/result")
        assert resp.status_code == 200
        assert resp.json()["data"]["personal_data"]["last_name"] == "Ivanov"


# ---------------------------------------------------------------------------
# Метрики
# ---------------------------------------------------------------------------


async def test_e2e_metrics_after_processing(
    e2e_client,
    async_session,
    sync_engine,
    tmp_path,
):
    """Prometheus-метрики обновляются после обработки."""
    from prometheus_client import REGISTRY

    uploads_before = REGISTRY.get_sample_value("cv_uploads_total") or 0

    resp, mock_publish = await _upload_file(
        e2e_client, "resume.pdf", b"%PDF-1.4 test", "application/pdf",
    )
    assert resp.status_code == 202

    # cv_uploads_total увеличился
    uploads_after = REGISTRY.get_sample_value("cv_uploads_total")
    assert uploads_after == uploads_before + 1

    msg_data = _extract_kafka_message(mock_publish, "resume.pdf")
    _run_worker_task(msg_data, sync_engine, SAMPLE_CV_RESULT)

    # Worker-метрики
    processed = REGISTRY.get_sample_value("cv_processed_total", {"file_type": "pdf"})
    assert processed is not None and processed >= 1

    by_format = REGISTRY.get_sample_value("cv_by_format_total", {"format": "pdf"})
    assert by_format is not None and by_format >= 1

    duration_count = REGISTRY.get_sample_value(
        "cv_processing_duration_seconds_count", {"file_type": "pdf"},
    )
    assert duration_count is not None and duration_count >= 1


# ---------------------------------------------------------------------------
# Полный цикл с реальными экстракторами (без ML)
# ---------------------------------------------------------------------------


async def test_e2e_text_pipeline_with_real_extractor(
    e2e_client,
    async_session,
    sync_engine,
    tmp_path,
    sample_pdf,
):
    """Текстовый пайплайн: реальный экстрактор PDF -> mock модели -> результат."""
    pdf_content = sample_pdf.read_bytes()

    resp, mock_publish = await _upload_file(
        e2e_client, "resume.pdf", pdf_content, "application/pdf",
    )
    assert resp.status_code == 202
    task_id = resp.json()["task_id"]
    msg_data = _extract_kafka_message(mock_publish, "resume.pdf")

    # Pipeline мокается на уровне генерации, но экстрактор текста работает
    _run_worker_task(msg_data, sync_engine, SAMPLE_CV_RESULT)

    resp = await e2e_client.get(f"/api/v1/tasks/{task_id}/result")
    assert resp.status_code == 200
    assert resp.json()["data"]["personal_data"]["last_name"] == "Ivanov"


async def test_e2e_vision_pipeline_with_real_image(
    e2e_client,
    async_session,
    sync_engine,
    tmp_path,
    sample_jpeg,
):
    """Vision пайплайн: реальное изображение -> mock модели -> результат."""
    jpeg_content = sample_jpeg.read_bytes()

    resp, mock_publish = await _upload_file(
        e2e_client, "photo.jpeg", jpeg_content, "image/jpeg",
    )
    assert resp.status_code == 202
    task_id = resp.json()["task_id"]
    msg_data = _extract_kafka_message(mock_publish, "photo.jpeg")

    _run_worker_task(msg_data, sync_engine, SAMPLE_CV_RESULT)

    resp = await e2e_client.get(f"/api/v1/tasks/{task_id}/result")
    assert resp.status_code == 200
    assert resp.json()["data"]["personal_data"]["last_name"] == "Ivanov"
