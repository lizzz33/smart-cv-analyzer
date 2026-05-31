"""Интеграционные тесты API-эндпоинтов через AsyncClient."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.db import crud
from api.db.connection import get_db
from api.db.models import Resume
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
# Вспомогательные фикстуры
# ---------------------------------------------------------------------------


def _mock_magic(mime: str):
    """Возвращает контекстный менеджер, подменяющий magic.from_buffer."""
    return patch("api.services.file_validator.magic")


async def _make_task_with_status(async_session, status, file_name="resume.pdf"):
    """Создаёт задачу и переводит в указанный статус."""
    task = await crud.create_task(async_session, file_name, "pdf", 100)
    task.status = status
    if status == "failed":
        task.error_msg = "Тестовая ошибка"
    await async_session.commit()
    await async_session.refresh(task)
    return task


# ---------------------------------------------------------------------------
# POST /upload — базовые сценарии
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
# POST /upload — форматы DOCX, JPEG, PNG
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename, content, mime",
    [
        ("resume.docx", b"PK\x03\x04docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("photo.jpeg", b"\xff\xd8\xff\xe0jpeg", "image/jpeg"),
        ("photo.png", b"\x89PNG\r\n\x1a\npng", "image/png"),
    ],
    ids=["docx", "jpeg", "png"],
)
async def test_upload_supported_formats(client, filename, content, mime):
    """Поддерживаемые форматы проходят валидацию и возвращают 202."""
    with (
        patch("api.services.file_validator.magic") as m_magic,
        patch("api.routers.upload.publish_task", new_callable=AsyncMock),
    ):
        m_magic.from_buffer.return_value = mime

        resp = await client.post(
            "/api/v1/upload",
            files={"file": (filename, content, mime)},
        )

    assert resp.status_code == 202
    body = resp.json()
    assert "task_id" in body
    assert body["status"] == "pending"


async def test_upload_jpg_extension(client):
    """Расширение .jpg проходит валидацию и нормализуется."""
    with (
        patch("api.services.file_validator.magic") as m_magic,
        patch("api.routers.upload.publish_task", new_callable=AsyncMock),
    ):
        m_magic.from_buffer.return_value = "image/jpeg"

        resp = await client.post(
            "/api/v1/upload",
            files={"file": ("photo.jpg", b"\xff\xd8\xff\xe0jpg", "image/jpeg")},
        )

    assert resp.status_code == 202


# ---------------------------------------------------------------------------
# POST /upload — ошибки валидации
# ---------------------------------------------------------------------------


async def test_upload_empty_file(client):
    """Пустой файл отклоняется с 422."""
    with patch("api.services.file_validator.magic") as m_magic:
        m_magic.from_buffer.return_value = "application/pdf"

        resp = await client.post(
            "/api/v1/upload",
            files={"file": ("resume.pdf", b"", "application/pdf")},
        )

    assert resp.status_code == 422
    assert "empty" in resp.json()["detail"].lower()


async def test_upload_mime_mismatch(client):
    """Несовпадение расширения и MIME-типа отклоняется с 422."""
    with patch("api.services.file_validator.magic") as m_magic:
        # Файл с расширением .pdf, но внутри — JPEG
        m_magic.from_buffer.return_value = "image/jpeg"

        resp = await client.post(
            "/api/v1/upload",
            files={"file": ("resume.pdf", b"\xff\xd8\xff\xe0fake", "application/pdf")},
        )

    assert resp.status_code == 422
    assert "does not match" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /upload — полный цикл загрузки
# ---------------------------------------------------------------------------


async def test_upload_full_cycle(client, async_session, tmp_path):
    """Полный цикл: загрузка -> задача в БД -> файл на диске -> Kafka -> результат."""
    upload_dir = tmp_path / "uploads"

    with (
        patch("api.services.file_validator.magic") as m_magic,
        patch("api.routers.upload.publish_task", new_callable=AsyncMock) as mock_publish,
    ):
        m_magic.from_buffer.return_value = "application/pdf"

        # Шаг 1: загрузка файла
        resp = await client.post(
            "/api/v1/upload",
            files={"file": ("resume.pdf", b"%PDF-1.4 test", "application/pdf")},
        )

    assert resp.status_code == 202
    body = resp.json()
    task_id = body["task_id"]
    assert body["status"] == "pending"
    assert body["estimated_seconds"] == 150
    # task_id — валидный UUID
    uuid.UUID(task_id)

    # Шаг 2: задача создана в БД
    task = await crud.get_task(async_session, uuid.UUID(task_id))
    assert task is not None
    assert task.file_name == "resume.pdf"
    assert task.file_type == "pdf"
    assert task.status == "pending"

    # Шаг 3: файл сохранён на диск
    saved_path = upload_dir / f"{task_id}.pdf"
    assert saved_path.exists()
    assert saved_path.read_bytes() == b"%PDF-1.4 test"

    # Шаг 4: Kafka-сообщение отправлено с правильными параметрами
    mock_publish.assert_awaited_once()
    call_kwargs = mock_publish.call_args.kwargs
    assert call_kwargs["task_id"] == task_id
    assert call_kwargs["file_type"] == "pdf"
    assert call_kwargs["file_name"] == "resume.pdf"

    # Шаг 5: polling статуса — задача ещё pending
    resp = await client.get(f"/api/v1/tasks/{task_id}")
    assert resp.status_code == 202
    assert resp.json()["status"] == "pending"

    # Шаг 6: эмулируем завершение обработки (воркер)
    resume = Resume(
        task_id=uuid.UUID(task_id),
        raw_json={"personal_data": {"last_name": "Ivanov", "first_name": "Ivan"}},
    )
    async_session.add(resume)
    task.status = "completed"
    await async_session.commit()

    # Шаг 7: polling статуса — задача completed (200)
    resp = await client.get(f"/api/v1/tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"

    # Шаг 8: получение результата
    resp = await client.get(f"/api/v1/tasks/{task_id}/result")
    assert resp.status_code == 200
    result = resp.json()
    assert result["status"] == "completed"
    assert result["data"]["personal_data"]["last_name"] == "Ivanov"


async def test_upload_full_cycle_kafka_failure(client, async_session, tmp_path):
    """Полный цикл при падении Kafka: задача переходит в failed, файл сохранён."""
    upload_dir = tmp_path / "uploads"

    with (
        patch("api.services.file_validator.magic") as m_magic,
        patch(
            "api.routers.upload.publish_task",
            new_callable=AsyncMock,
            side_effect=Exception("Connection refused"),
        ),
    ):
        m_magic.from_buffer.return_value = "application/pdf"

        resp = await client.post(
            "/api/v1/upload",
            files={"file": ("resume.pdf", b"%PDF-1.4 test", "application/pdf")},
        )

    assert resp.status_code == 503
    task_id = resp.json()["task_id"]

    # Файл всё равно сохранён на диск
    saved_path = upload_dir / f"{task_id}.pdf"
    assert saved_path.exists()

    # Задача в БД переведена в failed
    task = await crud.get_task(async_session, uuid.UUID(task_id))
    assert task is not None
    assert task.status == "failed"
    assert "очередь" in task.error_msg.lower()

    # Результат недоступен — 422
    resp = await client.get(f"/api/v1/tasks/{task_id}/result")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /tasks/{id} — статус задачи
# ---------------------------------------------------------------------------


async def test_get_task_status_pending(client, async_session):
    """pending-задача возвращает 202 Accepted."""
    task = await crud.create_task(async_session, "resume.pdf", "pdf", 100)

    resp = await client.get(f"/api/v1/tasks/{task.id}")
    assert resp.status_code == 202
    assert resp.json()["status"] == "pending"


async def test_get_task_status_processing(client, async_session):
    """processing-задача возвращает 202 Accepted."""
    task = await _make_task_with_status(async_session, "processing")

    resp = await client.get(f"/api/v1/tasks/{task.id}")
    assert resp.status_code == 202
    assert resp.json()["status"] == "processing"


async def test_get_task_status_completed(client, async_session):
    """completed-задача возвращает 200 OK."""
    task = await _make_task_with_status(async_session, "completed")

    resp = await client.get(f"/api/v1/tasks/{task.id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


async def test_get_task_status_failed(client, async_session):
    """failed-задача возвращает 200 OK."""
    task = await _make_task_with_status(async_session, "failed")

    resp = await client.get(f"/api/v1/tasks/{task.id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "failed"


async def test_get_task_status_not_found(client):
    """Несуществующий task_id возвращает 404."""
    resp = await client.get(f"/api/v1/tasks/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_get_task_status_response_fields(client, async_session):
    """Ответ содержит все обязательные поля с корректными типами."""
    task = await crud.create_task(async_session, "cv.docx", "docx", 2048)

    resp = await client.get(f"/api/v1/tasks/{task.id}")
    body = resp.json()

    assert set(body.keys()) == {"task_id", "status", "file_name", "created_at", "updated_at"}
    assert body["task_id"] == str(task.id)
    assert body["status"] == "pending"
    assert body["file_name"] == "cv.docx"
    # created_at/updated_at — валидные ISO-8601 строки
    assert "T" in body["created_at"]
    assert "T" in body["updated_at"]


# ---------------------------------------------------------------------------
# GET /tasks/{id}/result — результат обработки
# ---------------------------------------------------------------------------


async def test_get_result_pending(client, async_session):
    """pending-задача без результата возвращает 202."""
    task = await crud.create_task(async_session, "resume.pdf", "pdf", 100)

    resp = await client.get(f"/api/v1/tasks/{task.id}/result")
    assert resp.status_code == 202


async def test_get_result_processing(client, async_session):
    """processing-задача возвращает 202 с сообщением о неготовности."""
    task = await _make_task_with_status(async_session, "processing")

    resp = await client.get(f"/api/v1/tasks/{task.id}/result")
    assert resp.status_code == 202
    assert "processing" in resp.json()["detail"]


async def test_get_result_failed(client, async_session):
    """failed-задача возвращает 422 с описанием ошибки."""
    task = await _make_task_with_status(async_session, "failed")

    resp = await client.get(f"/api/v1/tasks/{task.id}/result")
    assert resp.status_code == 422
    assert "failed" in resp.json()["detail"].lower()


async def test_get_result_completed_no_data(client, async_session):
    """completed-задача без строки в resumes возвращает 404."""
    task = await _make_task_with_status(async_session, "completed")

    resp = await client.get(f"/api/v1/tasks/{task.id}/result")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


async def test_get_result_not_found(client):
    """Несуществующий task_id возвращает 404."""
    resp = await client.get(f"/api/v1/tasks/{uuid.uuid4()}/result")
    assert resp.status_code == 404


async def test_get_result_completed(client, async_session):
    """Завершённая задача с результатом возвращает 200 и JSON."""
    task = await crud.create_task(async_session, "resume.pdf", "pdf", 100)

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
# Метрики интегрированы в эндпоинты
# ---------------------------------------------------------------------------


async def test_upload_increments_cv_uploads_total(client):
    """Успешная загрузка увеличивает счётчик cv_uploads_total."""
    from prometheus_client import REGISTRY

    before = REGISTRY.get_sample_value("cv_uploads_total") or 0

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

    after = REGISTRY.get_sample_value("cv_uploads_total")
    assert after == before + 1


async def test_upload_error_increments_cv_upload_errors_total(client):
    """Ошибочная загрузка увеличивает счётчик cv_upload_errors_total."""
    from prometheus_client import REGISTRY

    before = REGISTRY.get_sample_value("cv_upload_errors_total") or 0

    # Отправляем неподдерживаемый формат — валидация завершится ошибкой
    resp = await client.post(
        "/api/v1/upload",
        files={"file": ("resume.txt", b"plain text", "text/plain")},
    )

    assert resp.status_code == 422

    after = REGISTRY.get_sample_value("cv_upload_errors_total")
    assert after > before


async def test_tasks_endpoint_records_request_duration(client, async_session):
    """GET /tasks/{id} записывает observation в cv_api_request_duration_seconds."""
    from prometheus_client import REGISTRY

    task = await crud.create_task(async_session, "resume.pdf", "pdf", 100)

    resp = await client.get(f"/api/v1/tasks/{task.id}")
    assert resp.status_code == 202

    count = REGISTRY.get_sample_value(
        "cv_api_request_duration_seconds_count",
        {"method": "GET", "endpoint": "/api/v1/tasks/{task_id}", "status_code": "202"},
    )
    assert count is not None and count >= 1
