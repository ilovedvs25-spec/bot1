import asyncio
import sqlite3
import random
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, FSInputFile,
    KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
)

logging.basicConfig(level=logging.INFO)

# ---------- CONFIG ----------
def load_config():
    data = {}
    with open("config.txt", "r", encoding="utf-8") as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                data[k] = v
    return data

config = load_config()
BOT_TOKEN = config["BOT_TOKEN"]
ADMIN_ID = int(config["ADMIN_ID"])
ADMIN_USERNAME = config["ADMIN_USERNAME"]

# ---------- BOT ----------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ---------- DATABASE ----------
db = sqlite3.connect("database.db")
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    tg_id INTEGER PRIMARY KEY,
    username TEXT,
    bot_uid TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS deposits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount REAL,
    card TEXT,
    status TEXT,
    created TEXT
)
""")

db.commit()

# ---------- HELPERS ----------
def get_or_create_user(user):
    cur.execute("SELECT * FROM users WHERE tg_id=?", (user.id,))
    row = cur.fetchone()
    if not row:
        uid = f"#{random.randint(10000,99999)}"
        cur.execute(
            "INSERT INTO users VALUES (?, ?, ?)",
            (user.id, user.username, uid)
        )
        db.commit()
    cur.execute("SELECT * FROM users WHERE tg_id=?", (user.id,))
    return cur.fetchone()

def load_text(block):
    try:
        with open("texts.txt", "r", encoding="utf-8") as f:
            text = f.read()
        start = text.find(f"==={block}===")
        if start == -1:
            return "Текст не найден"
        start += len(block) + 6
        end = text.find("===", start)
        return text[start:end].strip()
    except:
        return "Ошибка чтения файла"

# ---------- STATES ----------
admin_state = {"step": None}
reply_targets = {}

# ---------- KEYBOARDS ----------
def main_menu(user_id):
    kb = [
        [KeyboardButton(text="📤 Залив чека"), KeyboardButton(text="👤 Профиль")],
        [KeyboardButton(text="💳 Реквизиты"), KeyboardButton(text="📜 Правила")],
        [KeyboardButton(text="⭐ Отзывы")]
    ]
    if user_id == ADMIN_ID:
        kb.append([KeyboardButton(text="🛠 Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def admin_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить залив")],
            [KeyboardButton(text="⬅️ В меню")]
        ],
        resize_keyboard=True
    )

# ---------- START ----------
@dp.message(F.text == "/start")
async def start_cmd(msg: Message):
    get_or_create_user(msg.from_user)
    await msg.answer_photo(
        FSInputFile("start.jpg"),
        caption="👋 Добро пожаловать!",
        reply_markup=main_menu(msg.from_user.id)
    )

# ---------- PROFILE ----------
@dp.message(F.text == "👤 Профиль")
async def profile_cmd(msg: Message):
    user = get_or_create_user(msg.from_user)
    cur.execute("SELECT COUNT(*) FROM deposits WHERE user_id=?", (msg.from_user.id,))
    count = cur.fetchone()[0]

    text = (
        f"👤 @{msg.from_user.username}\n"
        f"🆔 {msg.from_user.id}\n"
        f"🔹 BOT ID: {user[2]}\n\n"
        f"📊 Заливов: {count}"
    )

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📜 История заливов")],
            [KeyboardButton(text="⬅️ В меню")]
        ],
        resize_keyboard=True
    )

    await msg.answer(text, reply_markup=kb)

# ---------- HISTORY ----------
@dp.message(F.text == "📜 История заливов")
async def history_cmd(msg: Message):
    cur.execute(
        "SELECT amount, card, created FROM deposits WHERE user_id=? ORDER BY id DESC",
        (msg.from_user.id,)
    )
    rows = cur.fetchall()

    if not rows:
        await msg.answer("❌ История пустая")
        return

    text = "📊 Ваша история:\n\n"
    for r in rows:
        text += f"💰 {r[0]} | 💳 {r[1]} | 📅 {r[2]}\n"

    await msg.answer(text)

# ---------- ADMIN PANEL ----------
@dp.message(F.text == "🛠 Админ-панель")
async def admin_panel(msg: Message):
    if msg.from_user.id == ADMIN_ID:
        await msg.answer("🛠 Админ-панель", reply_markup=admin_menu())

@dp.message(F.text == "➕ Добавить залив")
async def add_dep_start(msg: Message):
    if msg.from_user.id == ADMIN_ID:
        admin_state["step"] = "wait_id"
        await msg.answer(
            "Введите Telegram ID пользователя:",
            reply_markup=ReplyKeyboardRemove()
        )

# ---------- CHECK ----------
@dp.message(F.text == "📤 Залив чека")
async def check_start(msg: Message):
    await msg.answer("📤 Отправьте фото или PDF чека.")

@dp.message(F.photo | F.document)
async def handle_check(msg: Message):
    reply_targets[ADMIN_ID] = msg.from_user.id

    await bot.send_message(
        ADMIN_ID,
        f"🧾 Новый чек\n@{msg.from_user.username}\nID: {msg.from_user.id}"
    )
    await bot.forward_message(ADMIN_ID, msg.chat.id, msg.message_id)
    await msg.answer("✅ Чек получен.")

# ---------- ADMIN STEPS (ТОЛЬКО ЕСЛИ STEP АКТИВЕН) ----------
@dp.message(F.text)
async def admin_steps(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        return

    if admin_state["step"] is None:
        return  # ⬅️ ВАЖНО! больше не ломает кнопки

    if admin_state["step"] == "wait_id":
        admin_state["user_id"] = msg.text
        admin_state["step"] = "wait_amount"
        await msg.answer("Введите сумму:")
        return

    if admin_state["step"] == "wait_amount":
        admin_state["amount"] = msg.text
        admin_state["step"] = "wait_system"
        await msg.answer("Введите систему:")
        return

    if admin_state["step"] == "wait_system":
        cur.execute(
            "INSERT INTO deposits (user_id, amount, card, status, created) VALUES (?, ?, ?, ?, ?)",
            (
                admin_state["user_id"],
                admin_state["amount"],
                msg.text,
                "Success",
                datetime.now().strftime("%d.%m.%Y %H:%M")
            )
        )
        db.commit()
        admin_state["step"] = None
        await msg.answer("✅ Залив добавлен", reply_markup=admin_menu())

# ---------- OTHER ----------
@dp.message(F.text == "💳 Реквизиты")
async def rekv(msg: Message):
    await msg.answer(load_text("REKVIZITY"))

@dp.message(F.text == "📜 Правила")
async def rules(msg: Message):
    await msg.answer(load_text("RULES"))

@dp.message(F.text == "⭐ Отзывы")
async def reviews(msg: Message):
    await msg.answer(config.get("REVIEWS_CHANNEL", "Канал не указан"))

@dp.message(F.text == "⬅️ В меню")
async def back_menu(msg: Message):
    await msg.answer("Главное меню", reply_markup=main_menu(msg.from_user.id))

# ---------- RUN ----------
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
