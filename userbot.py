import os
import asyncio
import mysql.connector
from datetime import datetime
from telethon import TelegramClient, events
from google import genai
from google.genai import types

# ================= КОНФИГУРАЦИЯ =================

# Telegram API
API_ID = 123 #ID
API_HASH = 'qwerty' #HASH

# Gemini API
GEMINI_API_KEY = 'test123' #API KEY
GEMINI_MODEL = 'gemini-2.0-flash'

# Настройки бота
TRIGGER_WORD = "олег"

# База данных MySQL
DB_CONFIG = {
    'user': 'user', 
    'password': 'password',
    'host': 'host',
    'database': 'database',
    'port': 1234,
    'charset': 'utf8mb4',
    'collation': 'utf8mb4_unicode_ci'
}

# Инициализация клиентов
ai_client = genai.Client(api_key=GEMINI_API_KEY)
client = TelegramClient('userbot_session', API_ID, API_HASH)

# Глобальные буферы для обработки альбомов (групп фото)
album_buffer = {}  # {grouped_id: [event_list]}
album_tasks = {}   # {grouped_id: asyncio_task}

# ================= РАБОТА С БАЗОЙ ДАННЫХ =================

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

def init_db():
    """Создает таблицу, если её нет."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INT AUTO_INCREMENT PRIMARY KEY,
                chat_id BIGINT,
                text TEXT,
                from_bot BOOLEAN
            )
        """)
        conn.commit()
        print("База данных успешно подключена и проверена.")
    except Exception as e:
        print(f"Критическая ошибка БД: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

def add_message_to_history(chat_id, text, from_bot):
    """Сохраняет сообщение в историю."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (chat_id, text, from_bot) VALUES (%s, %s, %s)", 
            (chat_id, text, from_bot)
        )
        conn.commit()
    except Exception as e:
        print(f"Ошибка записи в БД: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

def get_chat_history(chat_id, limit=15):
    """Загружает последние сообщения для контекста."""
    history_str = ""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Важно: выбираем ID во вложенном запросе, чтобы внешний ORDER BY работал
        query = """
            SELECT * FROM (
                SELECT id, text, from_bot FROM messages 
                WHERE chat_id = %s 
                ORDER BY id DESC LIMIT %s
            ) sub ORDER BY id ASC
        """
        cursor.execute(query, (chat_id, limit))
        rows = cursor.fetchall()
        
        for row in rows:
            role = "Бот" if row['from_bot'] else "Сообщение из чата"
            content = row['text']
            history_str += f'{role}: "{content}"\n'
            
    except Exception as e:
        print(f"Ошибка чтения истории: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()
    return history_str

def clear_chat_history(chat_id):
    """Очищает память бота о чате."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages WHERE chat_id = %s", (chat_id,))
        conn.commit()
        print(f"История чата {chat_id} очищена.")
    except Exception as e:
        print(f"Ошибка очистки: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

# ================= ЛОГИКА ОБРАБОТКИ (GEMINI) =================

async def process_batch(events_list):
    """
    Главная функция обработки. Принимает список событий (одно сообщение или альбом).
    Скачивает файлы, формирует промпт и отправляет в Gemini.
    """
    if not events_list:
        return

    # Берем последнее сообщение из пачки для ответа
    main_event = events_list[-1]
    chat_id = main_event.chat_id
    
    # Собираем весь текст из подписей к фото/видео
    full_text = " ".join([e.raw_text for e in events_list if e.raw_text])
    text_lower = full_text.lower()
    
    should_answer = False
    
    # --- ПРОВЕРКА УСЛОВИЙ ---
    if main_event.is_private:
        should_answer = True
    elif main_event.is_group:
        if TRIGGER_WORD in text_lower:
            should_answer = True
        # В группах игнорируем просто картинки без ключевого слова
    
    if not should_answer:
        return

    # --- КОМАНДА ОЧИСТКИ ---
    if "очистить историю" in text_lower:
        clear_chat_history(chat_id)
        await main_event.reply("История сообщений этого чата очищена! 🧹")
        return

    print(f"\n>>> Обработка запроса (Вложений: {len(events_list)}) Чат: {chat_id}")

    # Списки для контента и временных файлов
    gemini_contents = []
    temp_files = []

    try:
        async with client.action(chat_id, 'typing'):
            # 1. Скачивание файлов (Фото/Видео)
            for ev in events_list:
                if ev.message.media:
                    try:
                        path = await ev.message.download_media()
                        if path:
                            temp_files.append(path)
                            
                            # Определяем MIME (по умолчанию jpeg)
                            mime = "image/jpeg"
                            if hasattr(ev.message, 'file') and ev.message.file:
                                mime = ev.message.file.mime_type
                            
                            # Читаем файл в байты для отправки
                            with open(path, "rb") as f:
                                file_data = f.read()
                                gemini_contents.append(types.Part.from_bytes(
                                    data=file_data,
                                    mime_type=mime
                                ))
                            print(f" + Файл добавлен: {mime}")
                    except Exception as e:
                        print(f"Ошибка загрузки медиа: {e}")

            # 2. Подготовка текстового промпта
            current_time = datetime.now().strftime("%H:%M %d.%m.%Y")
            history_text = get_chat_history(chat_id, limit=15)
            
            prompt_text = f"""Сейчас {current_time}. Ты юзербот телеграмм по имени Олег. В чате {chat_id} тебе прислали сообщение.
Текст сообщения: "{full_text}"
Если есть прикрепленные фото или видео, проанализируй их.
Ответь кратко и по делу.
Вот история сообщений из этого чата:
{history_text}"""

            gemini_contents.append(prompt_text)

            # 3. Логирование запроса пользователя в БД
            log_msg = full_text
            if temp_files:
                log_msg = f"[Вложений: {len(temp_files)}] {full_text}"
            add_message_to_history(chat_id, log_msg, from_bot=False)

            # 4. Запрос к Gemini
            response = await ai_client.aio.models.generate_content(
                model=GEMINI_MODEL,
                contents=gemini_contents
            )
            
            reply_text = response.text

            # 5. Сохранение ответа и отправка
            add_message_to_history(chat_id, reply_text, from_bot=True)
            await main_event.reply(reply_text)
            print("<<< Ответ отправлен.")

    except Exception as e:
        print(f"!!! Ошибка AI или сети: {e}")
    finally:
        # 6. Удаление временных файлов (обязательно!)
        for path in temp_files:
            if os.path.exists(path):
                os.remove(path)

# ================= МЕНЕДЖЕР АЛЬБОМОВ =================

async def wait_and_process_album(grouped_id):
    """Ждет 2 секунды, чтобы собрались все фото альбома, и запускает обработку."""
    await asyncio.sleep(2)
    
    # Забираем все события из буфера
    events_list = album_buffer.pop(grouped_id, [])
    album_tasks.pop(grouped_id, None)
    
    if events_list:
        await process_batch(events_list)

@client.on(events.NewMessage)
async def message_handler(event):
    if event.message.out:
        return

    grouped_id = event.grouped_id

    if grouped_id:
        # === ЭТО ЧАСТЬ АЛЬБОМА ===
        if grouped_id not in album_buffer:
            album_buffer[grouped_id] = []
        
        album_buffer[grouped_id].append(event)

        # Если таймер еще не запущен для этой группы, запускаем
        if grouped_id not in album_tasks:
            task = asyncio.create_task(wait_and_process_album(grouped_id))
            album_tasks[grouped_id] = task
    else:
        # === ОБЫЧНОЕ СООБЩЕНИЕ ===
        # Обрабатываем сразу как список из 1 элемента
        await process_batch([event])

# ================= ЗАПУСК =================

async def main():
    print("--- Инициализация ---")
    init_db()
    
    print("--- Запуск Telegram ---")
    await client.start()
    
    print(f"Userbot ОЛЕГ запущен!")
    print(f"Модель: {GEMINI_MODEL}")
    print("Ожидание сообщений...")
    
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())