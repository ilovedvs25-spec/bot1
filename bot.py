import asyncio
import sqlite3
import random
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, KeyboardButton, ReplyKeyboardMarkup
from aiogram.enums import ParseMode

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

# ---------- BOT & DB ----------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

db = sqlite3.connect("database.db")
cur = db.cursor()
# (Таблицы создаются автоматически при запуске)
cur.execute("CREATE TABLE IF NOT EXISTS users (tg_id INTEGER PRIMARY KEY, username TEXT, bot_uid TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS deposits (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, card TEXT, status TEXT, created TEXT)")
db.commit()

# ---------- HELPERS ----------
def get_or_create_user(user):
    cur.execute("SELECT * FROM users WHERE tg_id=?", (user.id,))
    row = cur.fetchone()
    if not row:
        uid = f"#{random.randint(10000,99999)}"
        cur.execute("INSERT INTO users VALUES (?, ?, ?)", (user.id, user.username, uid))
        db.commit()
    cur.execute("SELECT * FROM users WHERE tg_id=?", (user.id,))
    return cur.fetchone()

def load_text(block):
    try:
        with open("texts.txt", "r", encoding="utf-8") as f:
            text = f.read()
        start = text.find(f"==={block}===")
        if start == -1: return f"Блок {block} не найден в texts.txt"
        start_idx = start + len(block) + 6
        end_idx = text.find("===", start_idx)
        return text[start_idx:end_idx].strip() if end_idx != -1 else text[start_idx:].strip()
    except Exception as e:
        return f"Ошибка чтения файла: {e}"

# ---------- СОСТОЯНИЯ ----------
reply_targets = {ADMIN_ID: None, "wait_reply": False, "wait_deposit": False}

# ---------- КЛАВИАТУРЫ ----------
def main_menu(user_id):
    kb = [
        [KeyboardButton(text="📤 Залив чека"), KeyboardButton(text="👤 Профиль")],
        [KeyboardButton(text="💳 Реквизиты"), KeyboardButton(text="📜 Правила")],
        [KeyboardButton(text="⭐ Отзывы")]
    ]
    if user_id == ADMIN_ID: kb.append([KeyboardButton(text="🛠 Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def admin_menu():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="➕ Добавить залив")], [KeyboardButton(text="⬅️ В меню")]], resize_keyboard=True)

# ---------- ОБРАБОТЧИКИ (ВАЖЕН ПОРЯДОК!) ----------

@dp.message(F.text == "/start")
async def start(msg: Message):
    get_or_create_user(msg.from_user)
    await msg.answer_photo(FSInputFile("start.jpg"), caption="<b>👋 Добро пожаловать!</b>", reply_markup=main_menu(msg.from_user.id), parse_mode="HTML")

@dp.message(F.text == "💳 Реквизиты")
async def rekv(msg: Message):
    text = load_text("REKVIZITY")
    await msg.answer(text, parse_mode="HTML")

@dp.message(F.text == "📜 Правила")
async def rules(msg: Message):
    text = load_text("RULES")
    await msg.answer(text, parse_mode="HTML", disable_web_page_preview=False)

@dp.message(F.text == "👤 Профиль")
async def profile(msg: Message):
    user = get_or_create_user(msg.from_user)
    text = f"<b>👤 Профиль:</b> @{msg.from_user.username}\n<b>🆔 ID:</b> <code>{msg.from_user.id}</code>\n<b>🔸 BOT ID:</b> {user[2]}"
    await msg.answer(text, parse_mode="HTML")

@dp.message(F.text == "🛠 Админ-панель")
async def admin_p(msg: Message):
    if msg.from_user.id == ADMIN_ID:
        await msg.answer("🛠 Панель управления", reply_markup=admin_menu())

@dp.message(F.text == "➕ Добавить залив")
async def add_dep(msg: Message):
    if msg.from_user.id == ADMIN_ID:
        reply_targets["wait_deposit"] = True
        await msg.answer("📝 Введите данные залива (например: 5000р Сбербанк):")

@dp.message(F.text == "✉️ Ответить заливщику")
async def ask_rep(msg: Message):
    if msg.from_user.id == ADMIN_ID:
        reply_targets["wait_reply"] = True
        await msg.answer("✍️ Напишите ответ пользователю:")

@dp.message(F.text == "⬅️ В меню")
async def to_menu(msg: Message):
    await msg.answer("Главное меню", reply_markup=main_menu(msg.from_user.id))

# ОБРАБОТКА ФОТО (ЧЕКОВ)
@dp.message(F.photo | F.document)
async def handle_docs(msg: Message):
    user = msg.from_user
    reply_targets[ADMIN_ID] = user.id # Запоминаем кому отвечать
    await bot.send_message(ADMIN_ID, f"🧾 <b>Новый чек от</b> @{user.username}\nID: <code>{user.id}</code>", parse_mode="HTML", 
                           reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="✉️ Ответить заливщику")]], resize_keyboard=True))
    await bot.forward_message(ADMIN_ID, msg.chat.id, msg.message_id)
    await msg.answer("✅ Чек отправлен админу!")

# ГЛОБАЛЬНЫЙ ОБРАБОТЧИК ТЕКСТА (В САМОМ КОНЦЕ)
@dp.message(F.text)
async def global_text(msg: Message):
    # 1. Если админ отвечает на чек
    if msg.from_user.id == ADMIN_ID and reply_targets.get("wait_reply"):
        uid = reply_targets.get(ADMIN_ID)
        if uid:
            try:
                await bot.send_message(uid, f"<b>📩 Ответ от админа:</b>\n\n{msg.text}", parse_mode="HTML")
                await msg.answer("✅ Отправлено!")
            except: await msg.answer("❌ Не удалось отправить.")
        reply_targets["wait_reply"] = False
        return

    # 2. Если админ добавляет залив
    if msg.from_user.id == ADMIN_ID and reply_targets.get("wait_deposit"):
        # Тут логика сохранения в БД
        await msg.answer(f"✅ Залив «{msg.text}» успешно добавлен в базу (тестово).")
        reply_targets["wait_deposit"] = False
        return
    
    # 3. Команда отзывы
    if msg.text == "⭐ Отзывы":
        await msg.answer(config.get("REVIEWS_CHANNEL", "Канал не указан"))

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())