"""Настройки сервиса, загружаемые из переменных окружения."""

from pydantic_settings import BaseSettings

# Поддерживаемые форматы: расширение -> список MIME-типов
ALLOWED_TYPES: dict[str, list[str]] = {
    "pdf": ["application/pdf"],
    "docx": [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ],
    "odt": ["application/vnd.oasis.opendocument.text"],
    "jpeg": ["image/jpeg"],
    "jpg": ["image/jpeg"],
    "png": ["image/png"],
}

MAX_FILE_SIZE_BYTES = 1_048_576  # 1 МБ


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://cv_user:changeme@localhost/cv_analyzer"
    MAX_FILE_SIZE_MB: int = 1
    UPLOAD_DIR: str = "/tmp/cv_uploads"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
