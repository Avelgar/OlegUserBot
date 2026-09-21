import asyncio
import itertools
import os
import random
import base64
import requests
import urllib.parse
from google import genai
from google.genai import types

# Предполагается, что эти списки импортируются из твоего config.py
from config import API_KEYS_POOL, TEXT_MODELS_POOL

# ================= СНИМАЕМ ВСЕ ОГРАНИЧЕНИЯ (NSFW, Жестокость и т.д.) =================
SAFETY_SETTINGS = [
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
]

# Создаем бесконечный итератор по индексам ключей
key_iterator = itertools.cycle(range(len(API_KEYS_POOL)))

# ================= РЕАЛЬНАЯ ГЕНЕРАЦИЯ (ВЫЗЫВАЕТСЯ ИЗ MAIN.PY) =================
def execute_image_generation(prompt: str) -> str:
    """Генерирует изображение через Pollinations AI и возвращает base64 строку"""
    try:
        safe_prompt = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{safe_prompt}"
        params = {
            "width": 512,
            "height": 512,
            "model": "flux",
            "nologo": "true",
            "enhance": "true",
            "seed": random.randint(1, 999999)
        }
        print(f"🖼️ Отправка GET-запроса к Pollinations AI для промпта: '{prompt}'")
        response = requests.get(url, params=params, timeout=60)
        if response.status_code == 200:
            return base64.b64encode(response.content).decode('utf-8')
        error_msg = response.text[:200] if response.text else "Нет описания ошибки"
        raise Exception(f"Pollinations API вернул код {response.status_code}. Ответ: {error_msg}")
    except requests.exceptions.Timeout:
        raise Exception("Ошибка: Время ожидания ответа от Pollinations AI истекло (более 60 секунд).")
    except Exception as e:
        raise Exception(f"Ошибка при работе с Pollinations AI: {str(e)}")

# ================= ИНСТРУМЕНТ (TOOL) ДЛЯ GEMINI =================
async def generate_image_pollinations(prompt: str) -> str:
    """
    Используй эту функцию, если тебя просят сгенерировать фотографию, нарисовать что-нибудь или сделать картинку.
    
    Args:
        prompt: детальное описание фото для нейросети строго на английском языке, не больше 10 слов.
    """
    print(f"🛠 [Tool] Gemini решил нарисовать картинку: {prompt}")
    # Подсказываем Gemini, что ей нужно вывести JSON-строку для срабатывания триггера в main.py
    return (
        f'SYSTEM: Изображение будет сгенерировано системой. '
        f'Чтобы отправить его пользователю, ТЫ ОБЯЗАН вставить в свой текстовый ответ следующий JSON блок (и добавь пару слов от себя):\n'
        f'{{"генерация фото": "{prompt}"}}'
    )

# ================= ИНСТРУМЕНТ ПОИСКА ДЛЯ 3.1 =================
async def google_search_tool(query: str) -> str:
    """
    Используй эту функцию, если пользователь просит найти актуальную информацию, 
    новости, погоду, факты или события в интернете, которых ты не знаешь.
    """
    api_key = random.choice(API_KEYS_POOL)
    search_client = genai.Client(api_key=api_key)
    
    try:
        print(f"🔍 [Gemini Search] Выполняю поиск в интернете по запросу: {query}")
        response = await search_client.aio.models.generate_content(
            model="gemini-2.5-flash", 
            contents=f"Найди в интернете актуальную информацию и сделай подробную выжимку фактов по запросу: {query}",
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.2 
            )
        )
        return response.text if response.text else "Ничего не найдено."
    except Exception as e:
        print(f"❌ Ошибка инструмента поиска: {e}")
        return f"Не удалось выполнить поиск из-за ошибки: {str(e)}"

# ================= РОТАЦИЯ КЛЮЧЕЙ С ТАЙМАУТОМ =================
async def generate_content_with_rotation(contents, system_instruction=None):
    """Генерация текста с ротацией ключей, таймаутами и передачей системного промпта"""
    last_error = None
    
    # Настраиваем конфигурацию
    config_kwargs = {
        "safety_settings": SAFETY_SETTINGS,
        "temperature": 0.7,
        # ДОБАВИЛИ ИНСТРУМЕНТ СЮДА 👇
        "tools": [google_search_tool, generate_image_pollinations],
    }
    
    if system_instruction:
        config_kwargs["system_instruction"] = types.Content(parts=[types.Part.from_text(text=system_instruction)])
        
    generate_config = types.GenerateContentConfig(**config_kwargs)
    
    keys_count = len(API_KEYS_POOL)
    
    for _ in range(keys_count):
        current_index = next(key_iterator)
        api_key = API_KEYS_POOL[current_index]
        temp_client = genai.Client(api_key=api_key)
        
        for model_name in TEXT_MODELS_POOL:
            try:
                response = await asyncio.wait_for(
                    temp_client.aio.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=generate_config,
                    ),
                    timeout=45.0
                )
                if not response.text:
                    continue
                print(f"✨ Успех (Ключ #{current_index + 1} | {model_name})")
                return response.text
                
            except asyncio.TimeoutError:
                print(f"⚠️ Таймаут API ({model_name}) на ключе #{current_index + 1}. Пробую дальше...")
                continue
                
            except Exception as e:
                error_str = str(e)
                print(f"❌ Ошибка API ({model_name}): {error_str}")
                
                if any(err in error_str for err in ["429", "RESOURCE_EXHAUSTED", "503", "500"]):
                    last_error = e
                    break 
                else:
                    raise e
                    
    return "Прости, все ключи сейчас заняты или выдают ошибки. Попробуй позже."