"""Юнит-тесты метрик Worker-сервиса (worker/metrics.py)."""

import sys
from unittest.mock import MagicMock, patch

import pytest
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

# Импортируем worker.metrics один раз при загрузке файла,
# чтобы метрики зарегистрировались в REGISTRY до начала тестов.
import worker.metrics as _wm


# ---------------------------------------------------------------------------
# Фикстуры: изолированный реестр для каждого теста
# ---------------------------------------------------------------------------


@pytest.fixture
def registry():
    """Изолированный CollectorRegistry с пересозданными метриками Worker."""
    reg = CollectorRegistry()

    processing_duration = Histogram(
        "cv_processing_duration_seconds",
        "Время обработки одного резюме (секунды)",
        labelnames=["file_type"],
        buckets=(10, 30, 60, 120, 180, 300, 600),
        registry=reg,
    )
    processed = Counter(
        "cv_processed_total",
        "Успешно обработанных резюме",
        labelnames=["file_type"],
        registry=reg,
    )
    failed = Counter(
        "cv_failed_total",
        "Ошибок обработки резюме",
        labelnames=["file_type"],
        registry=reg,
    )
    by_format = Counter(
        "cv_by_format_total",
        "Резюме по форматам файлов",
        labelnames=["format"],
        registry=reg,
    )
    model_load = Histogram(
        "cv_model_load_duration_seconds",
        "Время загрузки модели (секунды)",
        labelnames=["model_type"],
        buckets=(5, 10, 30, 60, 120, 300),
        registry=reg,
    )
    ram_usage = Gauge(
        "cv_ram_usage_bytes",
        "Потребление RAM воркером (байты)",
        registry=reg,
    )

    return {
        "registry": reg,
        "cv_processing_duration_seconds": processing_duration,
        "cv_processed_total": processed,
        "cv_failed_total": failed,
        "cv_by_format_total": by_format,
        "cv_model_load_duration_seconds": model_load,
        "cv_ram_usage_bytes": ram_usage,
    }


# ---------------------------------------------------------------------------
# cv_processing_duration_seconds — Histogram
# ---------------------------------------------------------------------------


def test_processing_duration_observe(registry):
    """observe() с label file_type записывает значение."""
    reg = registry["registry"]
    metric = registry["cv_processing_duration_seconds"]

    metric.labels(file_type="pdf").observe(120.5)

    assert (
        reg.get_sample_value(
            "cv_processing_duration_seconds_count",
            {"file_type": "pdf"},
        )
        == 1
    )
    assert reg.get_sample_value(
        "cv_processing_duration_seconds_sum",
        {"file_type": "pdf"},
    ) == pytest.approx(120.5)


def test_processing_duration_different_file_types(registry):
    """Разные file_type — независимые серии."""
    reg = registry["registry"]
    metric = registry["cv_processing_duration_seconds"]

    metric.labels(file_type="pdf").observe(100)
    metric.labels(file_type="docx").observe(50)

    assert (
        reg.get_sample_value(
            "cv_processing_duration_seconds_count",
            {"file_type": "pdf"},
        )
        == 1
    )
    assert (
        reg.get_sample_value(
            "cv_processing_duration_seconds_count",
            {"file_type": "docx"},
        )
        == 1
    )


# ---------------------------------------------------------------------------
# cv_processed_total — Counter
# ---------------------------------------------------------------------------


def test_processed_total_increment(registry):
    """inc() увеличивает cv_processed_total для file_type."""
    reg = registry["registry"]
    metric = registry["cv_processed_total"]

    metric.labels(file_type="pdf").inc()
    assert (
        reg.get_sample_value("cv_processed_total", {"file_type": "pdf"}) == 1
    )

    metric.labels(file_type="pdf").inc()
    assert (
        reg.get_sample_value("cv_processed_total", {"file_type": "pdf"}) == 2
    )


def test_processed_total_separate_labels(registry):
    """Разные file_type инкрементируются независимо."""
    reg = registry["registry"]
    metric = registry["cv_processed_total"]

    metric.labels(file_type="pdf").inc()
    metric.labels(file_type="docx").inc()
    metric.labels(file_type="docx").inc()

    assert (
        reg.get_sample_value("cv_processed_total", {"file_type": "pdf"}) == 1
    )
    assert (
        reg.get_sample_value("cv_processed_total", {"file_type": "docx"}) == 2
    )


# ---------------------------------------------------------------------------
# cv_failed_total — Counter
# ---------------------------------------------------------------------------


def test_failed_total_increment(registry):
    """inc() увеличивает cv_failed_total для file_type."""
    reg = registry["registry"]
    metric = registry["cv_failed_total"]

    metric.labels(file_type="jpeg").inc()
    assert (
        reg.get_sample_value("cv_failed_total", {"file_type": "jpeg"}) == 1
    )


# ---------------------------------------------------------------------------
# cv_by_format_total — Counter
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fmt",
    ["pdf", "docx", "odt", "jpeg", "png"],
    ids=["pdf", "docx", "odt", "jpeg", "png"],
)
def test_by_format_total_increment(registry, fmt):
    """inc() считает резюме по каждому формату."""
    reg = registry["registry"]
    metric = registry["cv_by_format_total"]

    metric.labels(format=fmt).inc()
    assert (
        reg.get_sample_value("cv_by_format_total", {"format": fmt}) == 1
    )


# ---------------------------------------------------------------------------
# cv_model_load_duration_seconds — Histogram
# ---------------------------------------------------------------------------


def test_model_load_duration_observe(registry):
    """observe() с label model_type записывает время загрузки модели."""
    reg = registry["registry"]
    metric = registry["cv_model_load_duration_seconds"]

    metric.labels(model_type="qwen25").observe(60.0)

    assert (
        reg.get_sample_value(
            "cv_model_load_duration_seconds_count",
            {"model_type": "qwen25"},
        )
        == 1
    )
    assert reg.get_sample_value(
        "cv_model_load_duration_seconds_sum",
        {"model_type": "qwen25"},
    ) == pytest.approx(60.0)


# ---------------------------------------------------------------------------
# cv_ram_usage_bytes — Gauge
# ---------------------------------------------------------------------------


def test_ram_usage_set(registry):
    """set() устанавливает значение потребления RAM."""
    reg = registry["registry"]
    metric = registry["cv_ram_usage_bytes"]

    metric.set(2_000_000_000)
    assert reg.get_sample_value("cv_ram_usage_bytes") == 2_000_000_000


# ---------------------------------------------------------------------------
# update_ram_usage() — функция обновления RAM
# ---------------------------------------------------------------------------


def test_update_ram_usage_without_psutil():
    """update_ram_usage() не падает, если psutil не установлен."""
    with patch.dict(sys.modules, {"psutil": None}):
        # psutil отсутствует в модулях — функция должна gracefully отработать
        from worker.metrics import update_ram_usage

        # Не выбрасывает исключение
        update_ram_usage()


def test_update_ram_usage_with_psutil():
    """update_ram_usage() вызывает psutil.Process и устанавливает Gauge."""
    mock_process = MagicMock()
    mock_process.memory_info.return_value = MagicMock(rss=4_000_000_000)
    mock_psutil = MagicMock()
    mock_psutil.Process.return_value = mock_process

    # update_ram_usage() делает `import psutil` внутри try/except,
    # поэтому подменяем через sys.modules + мокируем getpid и Gauge
    original_psutil = sys.modules.get("psutil")
    sys.modules["psutil"] = mock_psutil

    try:
        with (
            patch("worker.metrics.os.getpid", return_value=12345),
            patch.object(_wm, "cv_ram_usage_bytes") as mock_gauge,
        ):
            _wm.update_ram_usage()

            mock_psutil.Process.assert_called_once_with(12345)
            mock_process.memory_info.assert_called_once()
            mock_gauge.set.assert_called_once_with(4_000_000_000)
    finally:
        if original_psutil is not None:
            sys.modules["psutil"] = original_psutil
        else:
            sys.modules.pop("psutil", None)
