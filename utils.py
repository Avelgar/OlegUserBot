# utils.py
import os
import asyncio
import speech_recognition as sr
from pydub import AudioSegment

def transcribe_audio_file(file_path):
    wav_path = file_path + ".wav"
    try:
        audio = AudioSegment.from_file(file_path)
        audio.export(wav_path, format="wav")
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language="ru-RU")
            return text
    except: return "" 
    finally:
        if os.path.exists(wav_path): os.remove(wav_path)

async def recognize_speech_async(file_path):
    """Используется только для проверки триггер-слова в группах"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, transcribe_audio_file, file_path)