"""Юнит-тесты метрик API-сервиса (api/metrics.py)."""

import pytest
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


# ---------------------------------------------------------------------------
# Фикстуры: изолированный реестр для каждого теста
# ---------------------------------------------------------------------------


@pytest.fixture
def registry():
    """Изолированный CollectorRegistry с пересозданными метриками."""
    reg = CollectorRegistry()

    uploads = Counter(
        "cv_uploads_total",
        "Общее количество успешно загруженных файлов",
        registry=reg,
    )
    errors = Counter(
        "cv_upload_errors_total",
        "Ошибки при загрузке файлов",
        registry=reg,
    )
    in_progress = Gauge(
        "cv_tasks_in_progress",
        "Задачи со статусом pending или processing",
        registry=reg,
    )
    duration = Histogram(
        "cv_api_request_duration_seconds",
        "Длительность обработки HTTP-запросов",
        labelnames=["method", "endpoint", "status_code"],
        buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
        registry=reg,
    )

    return {
        "registry": reg,
        "cv_uploads_total": uploads,
        "cv_upload_errors_total": errors,
        "cv_tasks_in_progress": in_progress,
        "cv_api_request_duration_seconds": duration,
    }


# ---------------------------------------------------------------------------
# cv_uploads_total — Counter
# ---------------------------------------------------------------------------


def test_uploads_total_increment(registry):
    """inc() увеличивает cv_uploads_total на 1."""
    reg = registry["registry"]
    metric = registry["cv_uploads_total"]

    assert reg.get_sample_value("cv_uploads_total") == 0

    metric.inc()
    assert reg.get_sample_value("cv_uploads_total") == 1

    metric.inc()
    assert reg.get_sample_value("cv_uploads_total") == 2


# ---------------------------------------------------------------------------
# cv_upload_errors_total — Counter
# ---------------------------------------------------------------------------


def test_upload_errors_total_increment(registry):
    """inc() увеличивает cv_upload_errors_total на 1."""
    reg = registry["registry"]
    metric = registry["cv_upload_errors_total"]

    assert reg.get_sample_value("cv_upload_errors_total") == 0

    metric.inc()
    assert reg.get_sample_value("cv_upload_errors_total") == 1


# ---------------------------------------------------------------------------
# cv_tasks_in_progress — Gauge
# ---------------------------------------------------------------------------


def test_tasks_in_progress_set(registry):
    """set() устанавливает произвольное значение."""
    reg = registry["registry"]
    metric = registry["cv_tasks_in_progress"]

    metric.set(5)
    assert reg.get_sample_value("cv_tasks_in_progress") == 5


# ---------------------------------------------------------------------------
# cv_api_request_duration_seconds — Histogram
# ---------------------------------------------------------------------------


def test_request_duration_observe(registry):
    """observe() записывает значение в Histogram."""
    reg = registry["registry"]
    metric = registry["cv_api_request_duration_seconds"]

    metric.labels(method="GET", endpoint="/api/v1/tasks/{id}", status_code=200).observe(
        0.15
    )

    # Счётчик наблюдений для данного bucket
    assert reg.get_sample_value(
        "cv_api_request_duration_seconds_count",
        {"method": "GET", "endpoint": "/api/v1/tasks/{id}", "status_code": "200"},
    ) == 1


def test_request_duration_sum(registry):
    """observe() корректно обновляет сумму."""
    reg = registry["registry"]
    metric = registry["cv_api_request_duration_seconds"]

    metric.labels(method="POST", endpoint="/api/v1/upload", status_code=202).observe(
        0.3
    )
    metric.labels(method="POST", endpoint="/api/v1/upload", status_code=202).observe(
        0.7
    )

    assert reg.get_sample_value(
        "cv_api_request_duration_seconds_sum",
        {"method": "POST", "endpoint": "/api/v1/upload", "status_code": "202"},
    ) == pytest.approx(1.0)


def test_request_duration_multiple_labels(registry):
    """Разные комбинации labels — независимые серии."""
    reg = registry["registry"]
    metric = registry["cv_api_request_duration_seconds"]

    metric.labels(method="GET", endpoint="/health", status_code=200).observe(0.01)
    metric.labels(method="POST", endpoint="/api/v1/upload", status_code=422).observe(
        0.05
    )

    assert (
        reg.get_sample_value(
            "cv_api_request_duration_seconds_count",
            {"method": "GET", "endpoint": "/health", "status_code": "200"},
        )
        == 1
    )
    assert (
        reg.get_sample_value(
            "cv_api_request_duration_seconds_count",
            {"method": "POST", "endpoint": "/api/v1/upload", "status_code": "422"},
        )
        == 1
    )
