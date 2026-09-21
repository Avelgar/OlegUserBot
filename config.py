# config.py
from google.genai import types

API_ID = 
API_HASH = ''

# Твой список ключей
API_KEYS_POOL = [
]


TEXT_MODELS_POOL = [
    "gemini-3.5-flash-lite" # Если она работает, можно оставить, но лучше 2.0
]

CALL_MODEL = "models/gemini-2.5-flash-native-audio-preview-12-2025"
CALL_API_KEY = API_KEYS_POOL[0]

TRIGGER_WORD = "олег,"
PIPE_PATH = "gemini_audio.raw"

DB_CONFIG = {

}

LIVE_CONFIG = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Zephyr")
        )
    )
)

# === НАСТРОЙКИ БЕЗОПАСНОСТИ (ОТКЛЮЧАЕМ ЦЕНЗУРУ) ===
# Это заставляет модель отвечать всегда, даже если вопрос спорный
SAFETY_SETTINGS = [
    types.SafetySetting(
        category="HARM_CATEGORY_HATE_SPEECH",
        threshold="BLOCK_NONE",
    ),
    types.SafetySetting(
        category="HARM_CATEGORY_DANGEROUS_CONTENT",
        threshold="BLOCK_NONE",
    ),
    types.SafetySetting(
        category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
        threshold="BLOCK_NONE",
    ),
    types.SafetySetting(
        category="HARM_CATEGORY_HARASSMENT",
        threshold="BLOCK_NONE",
    ),
]