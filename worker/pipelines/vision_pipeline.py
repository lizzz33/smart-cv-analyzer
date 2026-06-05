"""Vision пайплайн: обработка изображений резюме через Qwen2-VL-2B-Instruct."""

import logging

import torch
from PIL import Image, ImageEnhance, ImageFilter
from qwen_vl_utils import process_vision_info

from worker.model_manager import model_manager
from worker.pipelines._json_utils import extract_json
from worker.pipelines.base import BasePipeline

logger = logging.getLogger(__name__)

MAX_NEW_TOKENS = 1024
MAX_IMAGE_SIZE = 768

IMAGE_FILE_TYPES = {"jpeg", "jpg", "png"}

EXTRACTION_PROMPT = """Извлеки данные из резюме в JSON.

ВАЖНЕЙШИЕ ПРАВИЛА:
1. НЕ ИСПОЛЬЗУЙ шаблоны - "Фамилия", "Имя", "Компания" и т.д.
2. Если данных нет - оставь поле пустым, а не пиши пример
3. Email и телефон копируй ДОСЛОВНО, цифра к цифре
4. Названия компаний и вузов копируй ТОЧНО из резюме
5. Навыки извлекай ИЗ ВСЕХ секций - "Навыки", "О себе", "Обо мне", "Ключевые навыки"

Верни ТОЛЬКО валидный JSON в таком формате:
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

Извлеки данные из резюме:"""

FALLBACK_PROMPT = """Извлеки данные из резюме в JSON.

Формат:
{{"personal_data": {{"last_name": "", "first_name": "", "middle_name": "", "email": "", "phone": "", "city": "", "birth_date": ""}}, "education": [], "experience": [], "skills": {{"hard_skills": {{"technical": [], "professional": [], "languages": []}}, "soft_skills": []}}, "additional": {{"certificates": [], "projects": [], "achievements": {{"awards": [], "publications": [], "conferences": []}}}}}}

Верни только JSON."""


class VisionPipeline(BasePipeline):
    """Пайплайн обработки изображений резюме (JPEG, PNG) через Qwen2-VL-2B."""

    def process(self, file_path: str) -> dict:
        """Предобработка изображения и генерация структурированного JSON."""
        self._detect_file_type(file_path)

        # Шаг 1: загрузка и предобработка изображения
        image = self._preprocess_image(file_path)
        logger.info("Изображение загружено и предобработано: %s", file_path)

        # Шаг 2: загрузка модели
        model_manager.load_vision_model()

        # Шаг 3: генерация с retry (основной -> fallback)
        result = self._generate_with_retry(image)

        logger.info("Результат vision пайплайна получен")
        return result

    def _detect_file_type(self, file_path: str) -> str:
        """Определение типа файла по расширению."""
        ext = file_path.rsplit(".", 1)[-1].lower()
        if ext not in IMAGE_FILE_TYPES:
            raise ValueError(f"Неподдерживаемое расширение для vision пайплайна: {ext}")
        return ext

    def _preprocess_image(self, file_path: str) -> Image.Image:
        """Предобработка: RGB-конвертация, ресайз, усиление резкости и контраста."""
        with Image.open(file_path) as img:
            img.load()  # Принудительное чтение в память до закрытия файла

            if img.mode != "RGB":
                img = img.convert("RGB")

            # Ресайз с сохранением пропорций
            if max(img.size) > MAX_IMAGE_SIZE:
                ratio = MAX_IMAGE_SIZE / max(img.size)
                new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                img = img.resize(new_size, Image.LANCZOS)

            # Усиление резкости для мелкого текста
            img = img.filter(ImageFilter.SHARPEN)

            # Небольшое увеличение контраста
            img = ImageEnhance.Contrast(img).enhance(1.15)

            # Увеличение яркости для тёмных участков
            img = ImageEnhance.Brightness(img).enhance(1.05)

            return img

    def _generate_with_retry(self, image: Image.Image) -> dict:
        """Генерация с fallback: основной промпт -> fallback промпт."""
        result = self._generate(image, EXTRACTION_PROMPT, temperature=0.2)
        if result is not None:
            logger.info("Успешно: основной промпт (попытка 1)")
            return result

        logger.warning("Основной промпт не дал результата, fallback (попытка 2)")
        result = self._generate(image, FALLBACK_PROMPT, temperature=0.3)
        if result is not None:
            logger.info("Успешно: fallback промпт (попытка 2)")
            return result

        raise ValueError("Не удалось извлечь JSON из ответа vision модели после 2 попыток")

    def _generate(self, image: Image.Image, prompt: str, temperature: float = 0.2) -> dict | None:
        """Генерация ответа vision модели и парсинг JSON (детерминированный режим)."""
        model = model_manager.model
        processor = model_manager.processor

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt},
                ],
            }
        ]

        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        image_inputs, _ = process_vision_info(messages)
        inputs = processor(
            text=[text],
            images=image_inputs,
            videos=None,
            padding=False,
            return_tensors="pt",
        )

        logger.info("Начало генерации vision: input_tokens=%d", inputs["input_ids"].shape[1])

        with torch.no_grad():
            output_ids = model.generate(
                **inputs,
                max_new_tokens=MAX_NEW_TOKENS,
                do_sample=True,
                temperature=temperature,
                top_p=0.9,
                top_k=40,
                repetition_penalty=1.1,
                num_beams=1,
                use_cache=True,
            )

        # Отсекаем входные токены
        generated_ids = [
            out_ids[len(in_ids):]
            for in_ids, out_ids in zip(inputs.input_ids, output_ids)
        ]
        response = processor.batch_decode(
            generated_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False,
        )[0].strip()

        logger.info("Генерация vision завершена: response_len=%d", len(response))

        return extract_json(response)
