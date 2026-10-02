import sqlite3
import json
from datetime import datetime
import pytz

DB_NAME = "sadaqah_bot.db"


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                frequency TEXT NOT NULL,
                day INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                is_active INTEGER DEFAULT 1,
                last_paid_month TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                payment_type TEXT,
                confirmed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
        """)

        defaults = {
            "card_number": "6037998800118522",
            "payment_link": "https://mehryazdan.ir/pay/",
            "reminder_time": "19:00",
            "global_message": "",
            "custom_amounts": json.dumps([10000, 50000, 100000, 200000])
        }

        for key, value in defaults.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value)
            )


# --- توابع کاربران ---
def add_user(user_id, username, first_name, frequency, day, amount):
    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO users
            (user_id, username, first_name, frequency, day, amount, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        """, (user_id, username, first_name, frequency, day, amount))


def get_user(user_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def update_user_amount(user_id, amount):
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET amount = ? WHERE user_id = ?",
            (amount, user_id)
        )


def update_user_frequency(user_id, frequency, day):
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET frequency = ?, day = ? WHERE user_id = ?",
            (frequency, day, user_id)
        )


def get_all_active_users():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM users WHERE is_active = 1"
        ).fetchall()
        return [dict(row) for row in rows]


def mark_paid(user_id):
    now = datetime.now(pytz.timezone("Asia/Tehran"))
    month = now.strftime("%Y-%m")
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET last_paid_month = ? WHERE user_id = ?",
            (month, user_id)
        )
        user = get_user(user_id)
        if user:
            conn.execute(
                "INSERT INTO payments (user_id, amount, payment_type) VALUES (?, ?, ?)",
                (user_id, user["amount"], "monthly")
            )


# --- توابع تنظیمات ---
def get_setting(key, default=""):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default


def set_setting(key, value):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, str(value))
        )


def get_card_number():
    return get_setting("card_number", "6037998800118522")


def get_payment_link():
    return get_setting("payment_link", "https://mehryazdan.ir/pay/")


def get_reminder_time():
    return get_setting("reminder_time", "19:00")


def get_global_message():
    return get_setting("global_message", "")


def clear_global_message():
    set_setting("global_message", "")


def get_custom_amounts():
    raw = get_setting("custom_amounts", "[10000, 50000, 100000, 200000]")
    try:
        return json.loads(raw)
    except:
        return [10000, 50000, 100000, 200000]
