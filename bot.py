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
support_wait = set()

# ---------- KEYBOARDS ----------
def main_menu(user_id):
    kb = [
        [KeyboardButton(text="📤 Залив чека"), KeyboardButton(text="👤 Профиль")],
        [KeyboardButton(text="💬 Связь с админом")],
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

def reply_menu():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✉️ Ответить заливщику")]],
        resize_keyboard=True
    )

# ---------- START ----------
@dp.message(F.text == "/start")
async def start_cmd(msg: Message):
    get_or_create_user(msg.from_user)
    await msg.answer_photo(
        FSInputFile("start.jpg"),
        caption="👋 Добро пожаловать!\nВыберите действие:",
        reply_markup=main_menu(msg.from_user.id)
    )

# ---------- PROFILE ----------
@dp.message(F.text == "👤 Профиль")
async def profile_cmd(msg: Message):
    user = get_or_create_user(msg.from_user)
    cur.execute("SELECT COUNT(*) FROM deposits WHERE user_id=?", (msg.from_user.id,))
    count = cur.fetchone()[0]

    text = (
        f"👤 Пользователь: @{msg.from_user.username}\n"
        f"🆔 ID: {msg.from_user.id}\n"
        f"🔹 BOT ID: {user[2]}\n\n"
        f"📊 Всего заливов: {count}"
    )
    await msg.answer(text, reply_markup=main_menu(msg.from_user.id))

# ---------- SUPPORT (USER → ADMIN) ----------
@dp.message(F.text == "💬 Связь с админом")
async def support_start(msg: Message):
    support_wait.add(msg.from_user.id)
    await msg.answer(
        "✍️ Напишите сообщение администратору:",
        reply_markup=ReplyKeyboardRemove()
    )

@dp.message()
async def support_send(msg: Message):
    # пользователь пишет админу
    if msg.from_user.id in support_wait:
        support_wait.remove(msg.from_user.id)

        text = (
            "📩 <b>Сообщение от пользователя</b>\n\n"
            f"👤 @{msg.from_user.username}\n"
            f"🆔 ID: <code>{msg.from_user.id}</code>\n\n"
            f"{msg.text}"
        )

        reply_targets[ADMIN_ID] = msg.from_user.id

        await bot.send_message(
            ADMIN_ID,
            text,
            parse_mode="HTML",
            reply_markup=reply_menu()
        )

        await msg.answer(
            "✅ Сообщение отправлено админу.",
            reply_markup=main_menu(msg.from_user.id)
        )
        return

# ---------- CHECK ----------
@dp.message(F.text == "📤 Залив чека")
async def check_start(msg: Message):
    await msg.answer("📤 Отправьте фото или PDF чека.")

@dp.message(F.photo | F.document)
async def handle_check(msg: Message):
    reply_targets[ADMIN_ID] = msg.from_user.id

    text = (
        "🧾 <b>Новый чек</b>\n"
        f"👤 @{msg.from_user.username}\n"
        f"🆔 <code>{msg.from_user.id}</code>"
    )

    await bot.send_message(
        ADMIN_ID,
        text,
        parse_mode="HTML",
        reply_markup=reply_menu()
    )
    await bot.forward_message(ADMIN_ID, msg.chat.id, msg.message_id)
    await msg.answer("✅ Чек получен. Ожидайте проверки.")

# ---------- ADMIN REPLY ----------
@dp.message(F.text == "✉️ Ответить заливщику")
async def admin_reply_start(msg: Message):
    if msg.from_user.id == ADMIN_ID:
        admin_state["step"] = "reply"
        await msg.answer("✍️ Введите сообщение пользователю:")

@dp.message(F.text)
async def admin_reply(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        return

    if admin_state.get("step") == "reply":
        target = reply_targets.get(ADMIN_ID)
        if target:
            await bot.send_message(
                target,
                f"📩 Сообщение от админа:\n\n{msg.text}"
            )
            await msg.answer("✅ Отправлено", reply_markup=admin_menu())
        admin_state["step"] = None

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

@dp.message(F.text == "🛠 Админ-панель")
async def admin_panel(msg: Message):
    if msg.from_user.id == ADMIN_ID:
        await msg.answer("🛠 Админ-панель", reply_markup=admin_menu())

@dp.message(F.text == "⬅️ В меню")
async def back_menu(msg: Message):
    await msg.answer("Главное меню", reply_markup=main_menu(msg.from_user.id))

# ---------- RUN ----------
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
