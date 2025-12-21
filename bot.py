import asyncio
import sqlite3
import random
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    FSInputFile,
    KeyboardButton,
    ReplyKeyboardMarkup
)

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

COMMISSION = 25
USER_SHARE = 75

# ---------- BOT ----------
bot = Bot(BOT_TOKEN)
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
    receiver TEXT,
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
    with open("texts.txt", "r", encoding="utf-8") as f:
        text = f.read()
    start = text.find(f"==={block}===")
    if start == -1:
        return "Текст не найден"
    start += len(block) + 6
    end = text.find("===", start)
    return text[start:end].strip()

# ---------- STATE ----------
reply_targets = {}
admin_steps = {}

# ---------- KEYBOARDS ----------
def main_menu(user_id):
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📤 Залив чека"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="💳 Реквизиты"), KeyboardButton(text="📜 Правила")],
            [KeyboardButton(text="⭐ Отзывы")],
        ],
        resize_keyboard=True
    )
    if user_id == ADMIN_ID:
        kb.keyboard.append([KeyboardButton(text="🛠 Админ-панель")])
    return kb

def profile_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📜 История заливов")],
            [KeyboardButton(text="💬 Связь с админом")],
            [KeyboardButton(text="⬅️ В меню")]
        ],
        resize_keyboard=True
    )

def admin_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить залив")],
            [KeyboardButton(text="⬅️ В меню")]
        ],
        resize_keyboard=True
    )

def reply_button():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✉️ Ответить заливщику")]],
        resize_keyboard=True
    )

def status_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Успешно"), KeyboardButton(text="⏳ В процессе"), KeyboardButton(text="❌ Отказ")]
        ],
        resize_keyboard=True
    )

# ---------- START ----------
@dp.message(F.text == "/start")
async def start(msg: Message):
    get_or_create_user(msg.from_user)
    await msg.answer_photo(
        FSInputFile("start.jpg"),
        caption="👋 Добро пожаловать.\nВыберите действие:",
        reply_markup=main_menu(msg.from_user.id)
    )

# ---------- PROFILE ----------
@dp.message(F.text == "👤 Профиль")
async def profile(msg: Message):
    user = get_or_create_user(msg.from_user)
    cur.execute("SELECT COUNT(*) FROM deposits WHERE user_id=?", (msg.from_user.id,))
    count = cur.fetchone()[0]

    text = (
        f"👤 Пользователь: @{msg.from_user.username}\n"
        f"🆔 Telegram ID: {msg.from_user.id}\n"
        f"🔸 BOT ID: {user[2]}\n\n"
        f"💼 Комиссия: {COMMISSION}%\n"
        f"💰 Ваша доля: {USER_SHARE}%\n\n"
        f"📊 Всего заливов: {count}"
    )
    await msg.answer(text, reply_markup=profile_menu())

@dp.message(F.text == "📜 История заливов")
async def history(msg: Message):
    cur.execute(
        "SELECT id, created FROM deposits WHERE user_id=? ORDER BY id DESC",
        (msg.from_user.id,)
    )
    rows = cur.fetchall()
    if not rows:
        await msg.answer("❌ История пустая")
        return
    await msg.answer(
        "📊 История заливов:\n" +
        "\n".join([f"Залив #{r[0]} ({r[1]})" for r in rows])
    )

@dp.message(F.text == "💬 Связь с админом")
async def contact(msg: Message):
    await msg.answer(f"👤 Администратор:\n{ADMIN_USERNAME}")

@dp.message(F.text == "⬅️ В меню")
async def back(msg: Message):
    await msg.answer("Главное меню:", reply_markup=main_menu(msg.from_user.id))

# ---------- CHECK ----------
@dp.message(F.text == "📤 Залив чека")
async def check(msg: Message):
    await msg.answer("📤 Отправьте чек (фото или PDF).")

@dp.message(F.photo | F.document)
async def get_check(msg: Message):
    user = msg.from_user
    row = get_or_create_user(user)

    text = (
        "🧾 <b>Новый чек</b>\n\n"
        f"👤 @{user.username if user.username else 'без username'}\n"
        f"🆔 Telegram ID: <code>{user.id}</code>\n"
        f"🔸 BOT ID: {row[2]}"
    )

    reply_targets[ADMIN_ID] = user.id

    await bot.send_message(
        ADMIN_ID,
        text,
        parse_mode="HTML",
        reply_markup=reply_button()
    )

    await bot.forward_message(
        ADMIN_ID,
        msg.chat.id,
        msg.message_id
    )

    await msg.answer(
        f"✅ Чек принят.\nАдминистратор свяжется с вами.\n\n{ADMIN_USERNAME}"
    )

# ---------- STATIC ----------
@dp.message(F.text == "💳 Реквизиты")
async def rekv(msg: Message):
    await msg.answer(load_text("REKVIZITY"))

@dp.message(F.text == "📜 Правила")
async def rules(msg: Message):
    await msg.answer(load_text("RULES"))

@dp.message(F.text == "⭐ Отзывы")
async def reviews(msg: Message):
    await msg.answer(config["REVIEWS_CHANNEL"])

# ---------- ADMIN ----------
@dp.message(F.text == "🛠 Админ-панель")
async def admin_panel(msg: Message):
    if msg.from_user.id == ADMIN_ID:
        await msg.answer("🛠 Админ-панель", reply_markup=admin_menu())

@dp.message(F.text == "✉️ Ответить заливщику")
async def reply_user(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        return
    reply_targets["wait"] = True
    await msg.answer("✍️ Напишите сообщение пользователю:")

@dp.message()
async def admin_steps_handler(msg: Message):
    # ответ пользователю
    if msg.from_user.id == ADMIN_ID and reply_targets.get("wait"):
        uid = reply_targets.get(ADMIN_ID)
        if uid:
            await bot.send_message(uid, f"📩 Сообщение от администратора:\n\n{msg.text}")
        reply_targets.clear()
        await msg.answer("✅ Сообщение отправлено.")
        return

# ---------- RUN ----------
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
