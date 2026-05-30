"""Настройки воркера, загружаемые из переменных окружения."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://cv_user:changeme@localhost/cv_analyzer"
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_TOPIC: str = "cv-tasks"
    TEXT_MODEL_PATH: str = "/models/Qwen2.5-3B"
    VISION_MODEL_PATH: str = "/models/Qwen2-VL-2B-Instruct"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
