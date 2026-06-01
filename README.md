# Smart CV Analyzer

Сервис для извлечения и структурирования данных из резюме. Загружает файл (PDF, DOCX, ODT, JPEG, PNG), обрабатывает с помощью локальных ML-моделей и возвращает структурированный JSON с персональными данными, образованием, опытом работы, навыками и дополнительной информацией.

## Архитектура

```
                    ┌─────────────┐
                    │  Streamlit  │  http://localhost:8501
                    │  UI (8501)  │
                    └──────┬──────┘
                           │ HTTP (upload / polling)
                           ▼
                    ┌─────────────┐
                    │   FastAPI   │  http://localhost:8000
                    │   API       │  /api/v1/upload, /api/v1/tasks/{id}
                    └──┬────┬─────┘
                 ┌─────┘    └──────────┐
                 ▼                     ▼
           ┌──────────┐         ┌────────────┐
           │ PostgreSQL│         │  Redpanda  │
           │  (5432)  │         │   (9092)   │
           └────┬─────┘         └─────┬──────┘
                │                     │
                │              ┌──────▼──────┐
                └──────────────│   Worker    │
                               │ Qwen2.5-3B │
                               │ Qwen2-VL   │
                               └─────────────┘

           ┌──────────────┐    ┌──────────────┐
           │  Prometheus   │    │   Grafana    │
           │   (9090)      │    │   (3000)     │
           └──────────────┘    └──────────────┘
```

## Быстрый старт

### Предварительные требования

- Docker и Docker Compose
- ~15 ГБ свободного места на диске (модели + образы)
- Минимум 12 ГБ RAM

### 1. Клонировать репозиторий

```bash
git clone <repo-url>
cd smart-cv-analyzer
```

### 2. Настроить переменные окружения

```bash
cp .env.example .env
```

Отредактируйте `.env`: укажите пароль для PostgreSQL.

### 3. Скачать модели

Модели не включены в репозиторий из-за размера. Их нужно скачать вручную.

#### Qwen2.5-3B (текстовый пайплайн)

```bash
# Через huggingface-cli (рекомендуется)
pip install huggingface_hub
huggingface-cli download Qwen/Qwen2.5-3B-Instruct --local-dir ./models/Qwen2.5-3B

# Или через git lfs
git lfs install
git clone https://huggingface.co/Qwen/Qwen2.5-3B-Instruct ./models/Qwen2.5-3B
```

Размер: ~6.5 ГБ на диске.

#### Qwen2-VL-2B-Instruct (vision пайплайн)

```bash
# Через huggingface-cli
huggingface-cli download Qwen/Qwen2-VL-2B-Instruct --local-dir ./models/Qwen2-VL-2B-Instruct

# Или через git lfs
git clone https://huggingface.co/Qwen/Qwen2-VL-2B-Instruct ./models/Qwen2-VL-2B-Instruct
```

Размер: ~4.2 ГБ на диске.

Структура директории `models/`:

```
models/
├── Qwen2.5-3B/
│   ├── config.json
│   ├── tokenizer.json
│   ├── model.safetensors (или pytorch_model.bin)
│   └── ...
└── Qwen2-VL-2B-Instruct/
    ├── config.json
    ├── preprocessor_config.json
    ├── model.safetensors (или pytorch_model.bin)
    └── ...
```

### 4. Запустить сервисы

```bash
docker compose up -d
```

При первом запуске Docker соберёт образы (5-10 минут). После запуска:

| Сервис       | URL                          | Назначение                 |
|--------------|------------------------------|----------------------------|
| UI           | http://localhost:8501        | Загрузка и просмотр резюме |
| API          | http://localhost:8000/docs   | Swagger UI                 |
| Prometheus   | http://localhost:9090        | Метрики                    |
| Grafana      | http://localhost:3000        | Дашборды (admin/admin)     |

### 5. Использовать

1. Открыть http://localhost:8501
2. Загрузить файл резюме (PDF, DOCX, ODT, JPEG, PNG, до 1 МБ)
3. Дождаться обработки (~150 сек на страницу, CPU-only)
4. Результат отобразится на странице по секциям

## Поддерживаемые форматы

| Формат | Расширение       | Пайплайн            | Экстрактор   |
|--------|------------------|---------------------|--------------|
| PDF    | `.pdf`           | Qwen2.5-3B (текст) | pdfplumber   |
| DOCX   | `.docx`          | Qwen2.5-3B (текст) | python-docx  |
| ODT    | `.odt`           | Qwen2.5-3B (текст) | odfpy        |
| JPEG   | `.jpeg`, `.jpg`  | Qwen2-VL-2B (vision)| -           |
| PNG    | `.png`           | Qwen2-VL-2B (vision)| -           |

Ограничения:
- Максимальный размер файла: **1 МБ**
- Параллельных воркеров: **1** (ограничение RAM)
- Обработка на **CPU** (без GPU)

## API

### POST /api/v1/upload

Загрузка файла резюме. Возвращает `task_id` для отслеживания.

```bash
curl -X POST http://localhost:8000/api/v1/upload \
  -F "file=@resume.pdf"
```

Ответ (202 Accepted):

```json
{
  "task_id": "uuid",
  "status": "pending",
  "estimated_seconds": 150
}
```

### GET /api/v1/tasks/{task_id}

Статус задачи. Возвращает 202 для задач в обработке, 200 для завершённых.

### GET /api/v1/tasks/{task_id}/result

Результат обработки (доступен после завершения).

### GET /health

Проверка работоспособности API.

Полная документация: http://localhost:8000/docs

## Мониторинг

| Компонент   | URL                    | Учётные данные |
|-------------|------------------------|----------------|
| Prometheus  | http://localhost:9090  | -              |
| Grafana     | http://localhost:3000  | admin / admin  |

Метрики:
- `cv_uploads_total` — количество загруженных файлов
- `cv_tasks_in_progress` — задачи в обработке
- `cv_processed_total` — успешно обработанные (по формату)
- `cv_failed_total` — ошибки обработки (по формату)
- `cv_processing_duration_seconds` — длительность обработки
- `cv_ram_usage_bytes` — потребление RAM воркером
- `cv_api_request_duration_seconds` — latency HTTP-запросов

## Переменные окружения

### API

| Переменная              | По умолчанию                        | Описание                |
|-------------------------|--------------------------------------|-------------------------|
| `DATABASE_URL`          | `postgresql+asyncpg://...`          | Строка подключения к БД |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092`                   | Адрес Redpanda          |
| `KAFKA_TOPIC`           | `cv-tasks`                          | Топик для задач         |
| `MAX_FILE_SIZE_MB`      | `1`                                 | Макс. размер файла (МБ) |
| `UPLOAD_DIR`            | `/tmp/cv_uploads`                   | Директория для файлов   |

### Worker

| Переманная              | По умолчанию                        | Описание                |
|-------------------------|--------------------------------------|-------------------------|
| `DATABASE_URL`          | `postgresql://...`                  | Строка подключения к БД |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092`                   | Адрес Redpanda          |
| `KAFKA_TOPIC`           | `cv-tasks`                          | Топик для задач         |
| `TEXT_MODEL_PATH`       | `/models/Qwen2.5-3B`               | Путь к текстовой модели |
| `VISION_MODEL_PATH`     | `/models/Qwen2-VL-2B-Instruct`     | Путь к vision модели    |
| `METRICS_PORT`          | `8001`                              | Порт метрик Prometheus  |

### UI

| Переменная  | По умолчанию           | Описание        |
|-------------|------------------------|-----------------|
| `API_URL`   | `http://localhost:8000` | Адрес API       |

## Разработка

Для локальной разработки используется Python 3.12 и `uv`:

```bash
# Создать виртуальное окружение
python -m venv .venv
source .venv/bin/activate

# Установить зависимости (нужные для конкретного сервиса)
uv pip install -r api/requirements.txt
uv pip install -r requirements-test.txt

# Запустить тесты
pytest

# Линтинг
ruff check --fix .
```

### Структура проекта

```
smart-cv-analyzer/
├── api/                        # FastAPI: загрузка файлов, статус задач
│   ├── main.py                 # Точка входа, middleware, /health
│   ├── config.py               # Настройки из env
│   ├── routers/
│   │   ├── upload.py           # POST /api/v1/upload
│   │   └── tasks.py            # GET /api/v1/tasks/{id}[/result]
│   ├── services/
│   │   ├── file_validator.py   # Валидация формата, MIME, размера
│   │   └── kafka_producer.py   # Отправка задач в Redpanda
│   ├── db/
│   │   ├── connection.py       # AsyncSession
│   │   ├── models.py           # SQLAlchemy модели
│   │   └── crud.py             # Операции с БД
│   └── metrics.py              # Prometheus метрики API
│
├── worker/                     # Обработка резюме
│   ├── main.py                 # Точка входа, metrics-сервер
│   ├── consumer.py             # Redpanda consumer loop
│   ├── model_manager.py        # Lazy-load/Unload моделей
│   ├── pipelines/
│   │   ├── text_pipeline.py    # Qwen2.5-3B (PDF, DOCX, ODT)
│   │   └── vision_pipeline.py  # Qwen2-VL-2B (JPEG, PNG)
│   ├── extractors/
│   │   ├── pdf.py              # pdfplumber
│   │   ├── docx.py             # python-docx
│   │   ├── odt.py              # odfpy
│   │   └── router.py           # Маршрутизация по расширению
│   ├── db/
│   │   ├── connection.py       # Sync Session
│   │   └── crud.py             # Сохранение результатов
│   ├── schemas/
│   │   └── cv.py               # Pydantic-схема результата
│   └── metrics.py              # Prometheus метрики worker
│
├── ui/                         # Streamlit
│   └── app.py                  # Загрузка, polling, отображение
│
├── monitoring/
│   ├── prometheus.yml          # Конфигурация сбора метрик
│   ├── alerts.yml              # Правила алертов
│   └── grafana/                # Дашборды
│
├── migrations/
│   └── 001_init.sql            # Схема БД PostgreSQL
│
└── docker-compose.yml          # Оркестрация сервисов
```

## Остановка

```bash
docker compose down
```

Для удаления данных (БД, загрузки, метрики):

```bash
docker compose down -v
```

## Ограничения MVP

- Обработка на **CPU** (нет GPU) — одна страница ~150 секунд
- **1 воркер** параллельно (ограничение 12 ГБ RAM)
- Модели загружаются/выгружаются по одной (ModelManager синглтон)
- Нет авторизации пользователей
- Нет очереди повторных попыток (dead letter queue)
- Нет истории обработанных резюме

## Стек технологий

- **Python 3.12**, FastAPI, Streamlit
- **PostgreSQL 16** + SQLAlchemy 2.0
- **Redpanda** (Kafka-совместимый брокер, via aiokafka)
- **PyTorch** + Hugging Face Transformers (Qwen2.5-3B, Qwen2-VL-2B)
- **Docker Compose** для оркестрации
- **Prometheus** + **Grafana** для мониторинга
