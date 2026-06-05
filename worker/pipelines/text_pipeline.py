"""Текстовый пайплайн: извлечение текста + Qwen2.5-3B-Instruct."""

import logging

import torch

from worker.extractors.router import get_extractor
from worker.model_manager import model_manager
from worker.pipelines._json_utils import extract_json
from worker.pipelines.base import BasePipeline

logger = logging.getLogger(__name__)

MAX_NEW_TOKENS = 2048

# Ограничения длины текста для разных попыток
TEXT_LIMIT_MAIN = 16000
TEXT_LIMIT_FALLBACK = 8000
TEXT_LIMIT_MINIMAL = 4000

EXTRACTION_PROMPT = """Ты - система извлечения данных из резюме. Проанализируй текст и извлеки структурированные данные в формате JSON.

Текст резюме:
{resume_text}

Верни ТОЛЬКО JSON в следующей структуре:
{{
  "personal_data": {{
    "last_name": "",
    "first_name": "",
    "middle_name": "",
    "email": "",
    "phone": "",
    "city": "",
    "birth_date": ""
  }},
  "education": [
    {{
      "institution": "",
      "specialty": "",
      "level": "",
      "start_year": null,
      "end_year": null
    }}
  ],
  "experience": [
    {{
      "company": "",
      "position": "",
      "start_date": "",
      "end_date": "",
      "responsibilities": ""
    }}
  ],
  "skills": {{
    "hard_skills": {{
      "technical": [],
      "professional": [],
      "languages": []
    }},
    "soft_skills": []
  }},
  "additional": {{
    "certificates": [{{"name": "", "issuer": "", "year": ""}}],
    "projects": [{{"name": "", "role": "", "description": ""}}],
    "achievements": {{
      "awards": [],
      "publications": [],
      "conferences": []
    }}
  }}
}}

Правила:
- Используй ТОЛЬКО информацию из текста
- Исправляй опечатки и нормализуй регистр
- Если данных нет - оставляй пустые строки/списки
- Верни ТОЛЬКО JSON"""

FALLBACK_PROMPT = """Извлеки данные из резюме в JSON.

{resume_text}

Формат:
{{"personal_data": {{"last_name": "", "first_name": "", "middle_name": "", "email": "", "phone": "", "city": "", "birth_date": ""}}, "education": [], "experience": [], "skills": {{"hard_skills": {{"technical": [], "professional": [], "languages": []}}, "soft_skills": []}}, "additional": {{"certificates": [], "projects": [], "achievements": {{"awards": [], "publications": [], "conferences": []}}}}}}

Верни только JSON."""


class TextPipeline(BasePipeline):
    """Пайплайн обработки текстовых резюме (PDF, DOCX, ODT) через Qwen2.5-3B."""

    def process(self, file_path: str) -> dict:
        """Извлечение текста из файла и генерация структурированного JSON."""
        file_type = self._detect_file_type(file_path)

        # Шаг 1: извлечение текста
        extractor = get_extractor(file_type)
        resume_text = extractor(file_path)

        if not resume_text.strip():
            raise ValueError("Не удалось извлечь текст из файла")

        logger.info("Извлечён текст: %d символов, файл: %s", len(resume_text), file_path)

        # Шаг 2: загрузка модели
        model_manager.load_text_model()

        # Шаг 3: генерация с retry (основной -> fallback короткий -> fallback минимальный)
        result = self._generate_with_retry(resume_text)

        logger.info("Результат успешно получен")
        return result

    def _detect_file_type(self, file_path: str) -> str:
        """Определение типа файла по расширению."""
        ext = file_path.rsplit(".", 1)[-1].lower()
        if ext not in ("pdf", "docx", "odt"):
            raise ValueError(f"Неподдерживаемое расширение для текстового пайплайна: {ext}")
        return ext

    def _generate_with_retry(self, resume_text: str) -> dict:
        """Генерация с постепенным fallback: полный текст -> укороченный -> минимальный."""
        # Попытка 1: основной промпт, полный текст
        result = self._generate(EXTRACTION_PROMPT, resume_text[:TEXT_LIMIT_MAIN])
        if result is not None:
            logger.info("Успешно: основной промпт (попытка 1)")
            return result

        # Попытка 2: fallback промпт, укороченный текст
        logger.warning("Основной промпт не дал результата, fallback (попытка 2)")
        result = self._generate(FALLBACK_PROMPT, resume_text[:TEXT_LIMIT_FALLBACK])
        if result is not None:
            logger.info("Успешно: fallback промпт (попытка 2)")
            return result

        # Попытка 3: fallback промпт, минимальный текст
        logger.warning("Fallback (попытка 2) не дал результата, минимальный текст (попытка 3)")
        result = self._generate(FALLBACK_PROMPT, resume_text[:TEXT_LIMIT_MINIMAL])
        if result is not None:
            logger.info("Успешно: минимальный текст (попытка 3)")
            return result

        raise ValueError("Не удалось извлечь JSON из ответа модели после 3 попыток")

    def _generate(self, prompt: str, text: str) -> dict | None:
        """Генерация ответа модели и парсинг JSON."""
        model = model_manager.model
        tokenizer = model_manager.tokenizer

        formatted_prompt = prompt.format(resume_text=text)
        messages = [{"role": "user", "content": formatted_prompt}]
        chat_text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True,
        )
        inputs = tokenizer([chat_text], return_tensors="pt", padding=True)

        logger.info(
            "Начало генерации: input_tokens=%d, text_len=%d",
            inputs["input_ids"].shape[1],
            len(text),
        )

        with torch.no_grad():
            output_ids = model.generate(
                **inputs,
                max_new_tokens=MAX_NEW_TOKENS,
                do_sample=False,
                temperature=None,
                top_p=None,
                top_k=None,
                use_cache=True,
            )

        # Отсекаем входные токены
        input_length = inputs["input_ids"].shape[1]
        new_tokens = output_ids[0][input_length:]
        response = tokenizer.decode(new_tokens, skip_special_tokens=True)

        logger.info("Генерация завершена: response_len=%d", len(response))

        return extract_json(response)
