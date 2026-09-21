# database.py
import mysql.connector
from config import DB_CONFIG

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

def init_db():
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
        print("✅ База данных подключена.")
    except Exception as e:
        print(f"❌ Ошибка БД: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

def add_message_to_history(chat_id, text, from_bot):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO messages (chat_id, text, from_bot) VALUES (%s, %s, %s)", (chat_id, text, from_bot))
        conn.commit()
    except: pass
    finally:
        if 'conn' in locals() and conn.is_connected(): cursor.close(); conn.close()

def get_chat_history(chat_id, limit=15):
    history_str = ""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM (SELECT id, text, from_bot FROM messages WHERE chat_id = %s ORDER BY id DESC LIMIT %s) sub ORDER BY id ASC", (chat_id, limit))
        for row in cursor.fetchall():
            role = "Бот" if row['from_bot'] else "Юзер"
            history_str += f'{role}: "{row["text"]}"\n'
    except: pass
    finally:
        if 'conn' in locals() and conn.is_connected(): cursor.close(); conn.close()
    return history_str

def clear_chat_history(chat_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages WHERE chat_id = %s", (chat_id,))
        conn.commit()
    except: pass
    finally:
        if 'conn' in locals() and conn.is_connected(): cursor.close(); conn.close()