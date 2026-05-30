"""Интеграционные тесты CRUD API (PostgreSQL)."""

import uuid


from api.db import crud


async def test_create_task(async_session):
    task = await crud.create_task(
        async_session, file_name="resume.pdf", file_type="pdf", file_size=1024
    )

    assert task.id is not None
    assert task.status == "pending"
    assert task.file_name == "resume.pdf"
    assert task.file_type == "pdf"
    assert task.file_size == 1024


async def test_get_task_exists(async_session):
    created = await crud.create_task(
        async_session, file_name="resume.docx", file_type="docx", file_size=512
    )

    found = await crud.get_task(async_session, created.id)
    assert found is not None
    assert found.id == created.id
    assert found.file_name == "resume.docx"


async def test_get_task_not_exists(async_session):
    random_id = uuid.uuid4()
    found = await crud.get_task(async_session, random_id)
    assert found is None


async def test_fail_task(async_session):
    created = await crud.create_task(
        async_session, file_name="resume.pdf", file_type="pdf", file_size=100
    )

    await crud.fail_task(async_session, created.id, error_msg="Kafka unavailable")

    updated = await crud.get_task(async_session, created.id)
    assert updated.status == "failed"
    assert updated.error_msg == "Kafka unavailable"


async def test_count_in_progress(async_session):
    await crud.create_task(async_session, "a.pdf", "pdf", 100)
    await crud.create_task(async_session, "b.docx", "docx", 200)

    count = await crud.count_in_progress(async_session)
    assert count == 2


async def test_get_task_with_result_no_resume(async_session):
    created = await crud.create_task(async_session, "resume.pdf", "pdf", 100)

    result = await crud.get_task_with_result(async_session, created.id)
    assert result is not None
    assert result["status"] == "pending"
    assert result["data"] is None


async def test_get_task_with_normalized_no_resume(async_session):
    created = await crud.create_task(async_session, "resume.pdf", "pdf", 100)

    result = await crud.get_task_with_normalized(async_session, created.id)
    assert result is not None
    assert result["status"] == "pending"
    assert result["data"] is None
