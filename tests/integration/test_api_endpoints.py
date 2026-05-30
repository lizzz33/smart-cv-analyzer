"""Интеграционные тесты API-эндпоинтов через AsyncClient."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.db import crud
from api.db.connection import get_db
from api.main import app


@pytest_asyncio.fixture
async def client(async_engine, tmp_path):
    """Async-клиент с переопределённой БД и замоканным Kafka."""
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
# POST /upload
# ---------------------------------------------------------------------------


async def test_upload_valid_pdf(client):
    with (
        patch("api.services.file_validator.magic") as m_magic,
        patch("api.routers.upload.publish_task", new_callable=AsyncMock),
    ):
        m_magic.from_buffer.return_value = "application/pdf"

        resp = await client.post(
            "/api/v1/upload",
            files={"file": ("resume.pdf", b"%PDF-1.4 test", "application/pdf")},
        )

    assert resp.status_code == 202
    body = resp.json()
    assert "task_id" in body
    assert body["status"] == "pending"


async def test_upload_unsupported_format(client):
    resp = await client.post(
        "/api/v1/upload",
        files={"file": ("resume.txt", b"plain text", "text/plain")},
    )
    assert resp.status_code == 422


async def test_upload_file_too_large(client):
    big = b"x" * (2 * 1024 * 1024)
    resp = await client.post(
        "/api/v1/upload",
        files={"file": ("resume.pdf", big, "application/pdf")},
    )
    assert resp.status_code == 422


async def test_upload_valid_docx(client):
    """Upload DOCX — 202 Accepted."""
    with (
        patch("api.services.file_validator.magic") as m_magic,
        patch("api.routers.upload.publish_task", new_callable=AsyncMock),
    ):
        m_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        m_magic.from_buffer.return_value = m_mime

        resp = await client.post(
            "/api/v1/upload",
            files={"file": ("resume.docx", b"PK\x03\x04 docx content", m_mime)},
        )

    assert resp.status_code == 202
    assert resp.json()["status"] == "pending"


async def test_upload_valid_odt(client):
    """Upload ODT — 202 Accepted."""
    with (
        patch("api.services.file_validator.magic") as m_magic,
        patch("api.routers.upload.publish_task", new_callable=AsyncMock),
    ):
        m_magic.from_buffer.return_value = "application/vnd.oasis.opendocument.text"

        resp = await client.post(
            "/api/v1/upload",
            files={"file": ("resume.odt", b"ODT content here", "application/vnd.oasis.opendocument.text")},
        )

    assert resp.status_code == 202
    assert resp.json()["status"] == "pending"


async def test_upload_valid_jpeg(client):
    """Upload JPEG — 202 Accepted."""
    with (
        patch("api.services.file_validator.magic") as m_magic,
        patch("api.routers.upload.publish_task", new_callable=AsyncMock),
    ):
        m_magic.from_buffer.return_value = "image/jpeg"

        resp = await client.post(
            "/api/v1/upload",
            files={"file": ("photo.jpg", b"\xff\xd8\xff\xe0 jpeg data", "image/jpeg")},
        )

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "pending"


async def test_upload_valid_png(client):
    """Upload PNG — 202 Accepted."""
    with (
        patch("api.services.file_validator.magic") as m_magic,
        patch("api.routers.upload.publish_task", new_callable=AsyncMock),
    ):
        m_magic.from_buffer.return_value = "image/png"

        resp = await client.post(
            "/api/v1/upload",
            files={"file": ("scan.png", b"\x89PNG\r\n\x1a\n png data", "image/png")},
        )

    assert resp.status_code == 202
    assert resp.json()["status"] == "pending"


async def test_upload_kafka_unavailable(client):
    with (
        patch("api.services.file_validator.magic") as m_magic,
        patch(
            "api.routers.upload.publish_task",
            new_callable=AsyncMock,
            side_effect=Exception("Kafka down"),
        ),
    ):
        m_magic.from_buffer.return_value = "application/pdf"

        resp = await client.post(
            "/api/v1/upload",
            files={"file": ("resume.pdf", b"%PDF-1.4 test", "application/pdf")},
        )

    assert resp.status_code == 503
    assert resp.json()["status"] == "failed"


# ---------------------------------------------------------------------------
# GET /tasks/{id}
# ---------------------------------------------------------------------------


async def test_get_task_status_exists(client, async_session):
    task = await crud.create_task(async_session, "resume.pdf", "pdf", 100)

    resp = await client.get(f"/api/v1/tasks/{task.id}")
    assert resp.status_code == 202
    assert resp.json()["status"] == "pending"


async def test_get_task_status_not_found(client):
    resp = await client.get(f"/api/v1/tasks/{uuid.uuid4()}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /tasks/{id}/result
# ---------------------------------------------------------------------------


async def test_get_result_pending(client, async_session):
    task = await crud.create_task(async_session, "resume.pdf", "pdf", 100)

    resp = await client.get(f"/api/v1/tasks/{task.id}/result")
    assert resp.status_code == 202


async def test_get_result_not_found(client):
    resp = await client.get(f"/api/v1/tasks/{uuid.uuid4()}/result")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


async def test_health(client):
    """Эндпоинт /health возвращает статус ok."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# GET /metrics
# ---------------------------------------------------------------------------


async def test_metrics(client):
    """Эндпоинт /metrics возвращает текстовый формат Prometheus."""
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]


# ---------------------------------------------------------------------------
# GET /tasks/{id}/result — completed (happy path)
# ---------------------------------------------------------------------------


async def test_get_result_completed(client, async_session):
    """Завершённая задача с результатом возвращает 200 и JSON."""
    task = await crud.create_task(async_session, "resume.pdf", "pdf", 100)

    # Сохраняем результат через sync-style INSERT (эмуляция воркера)
    from api.db.models import Resume

    resume = Resume(
        task_id=task.id,
        raw_json={"personal_data": {"last_name": "Ivanov", "first_name": "Ivan"}},
    )
    async_session.add(resume)
    task.status = "completed"
    await async_session.commit()

    resp = await client.get(f"/api/v1/tasks/{task.id}/result")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["data"]["personal_data"]["last_name"] == "Ivanov"
