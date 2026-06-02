#!/bin/bash
set -e

TEXT_MODEL_REPO="${TEXT_MODEL_REPO:-Qwen/Qwen2.5-3B-Instruct}"
VISION_MODEL_REPO="${VISION_MODEL_REPO:-Qwen/Qwen2-VL-2B-Instruct}"

# Скачивание текстовой модели при первом запуске
if [ ! -f "${TEXT_MODEL_PATH}/config.json" ]; then
    echo "[entrypoint] Скачивание текстовой модели: ${TEXT_MODEL_REPO} -> ${TEXT_MODEL_PATH}"
    huggingface-cli download "${TEXT_MODEL_REPO}" --local-dir "${TEXT_MODEL_PATH}"
    echo "[entrypoint] Текстовая модель скачана"
else
    echo "[entrypoint] Текстовая модель уже присутствует: ${TEXT_MODEL_PATH}"
fi

# Скачивание vision модели при первом запуске
if [ ! -f "${VISION_MODEL_PATH}/config.json" ]; then
    echo "[entrypoint] Скачивание vision модели: ${VISION_MODEL_REPO} -> ${VISION_MODEL_PATH}"
    huggingface-cli download "${VISION_MODEL_REPO}" --local-dir "${VISION_MODEL_PATH}"
    echo "[entrypoint] Vision модель скачана"
else
    echo "[entrypoint] Vision модель уже присутствует: ${VISION_MODEL_PATH}"
fi

echo "[entrypoint] Модели готовы. Запуск воркера..."
exec python -m worker.main
