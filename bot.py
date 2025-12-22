import asyncio
import sqlite3
import random
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, F, types
from aiogram.types import (
    Message,
    FSInputFile,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove
)
from aiogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)

# ---------- CONFIG ----------
def load_config():
    data = {}
    try:
        with open("config.txt", "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    data[k] = v
    except FileNotFoundError:
        print("Файл config.txt не найден!")
    return data

config = load_config()
BOT_TOKEN = config.get("BOT_TOKEN")
ADMIN_ID = int(config.get("ADMIN_ID", 0))
ADMIN_USERNAME = config.get("ADMIN_USERNAME", "")

# ---------- BOT & DB ----------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

db = sqlite3.connect("database.db")
cur = db.cursor()

cur.execute("CREATE TABLE IF NOT EXISTS users (tg_id INTEGER PRIMARY KEY, username TEXT, bot_uid TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS deposits (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, card TEXT, status TEXT, created TEXT)")
db.commit()

# ---------- STATE & HELPERS ----------
# Состояния для админки и связи
user_states = {} # {user_id: 'step'}
admin_state = {"target_user": None, "step": None}
# Для того, чтобы админ мог отвечать на сообщения юзеров
reply_targets = {} 

def get_or_create_user(user):
    cur.execute("SELECT * FROM users WHERE tg_id=?", (user.id,))
    row = cur.fetchone()
    if not row:
        uid = f"#{random.randint(10000,99999)}"
        cur.execute("INSERT INTO users VALUES (?, ?, ?)", (user.id, user.username, uid))
        db.commit()
    return row

def load_text(block):
    try:
        with open("texts.txt", "r", encoding="utf-8") as f:
            text = f.read()
        start = text.find(f"==={block}===")
        if start == -1: return f"Ошибка: Блок {block} не найден"
        start_idx = start + len(block) + 6
        end_idx = text.find("===", start_idx)
        return text[start_idx:end_idx].strip()
    except:
        return "Текст не найден в файле."

# ---------- KEYBOARDS ----------
def main_menu(user_id):
    kb = [
        [KeyboardButton(text="📤 Залив чека"), KeyboardButton(text="👤 Профиль")],
        [KeyboardButton(text="💳 Реквизиты"), KeyboardButton(text="📜 Правила")],
        [KeyboardButton(text="⭐ Отзывы"), KeyboardButton(text="👨‍💻 Связь с админом")]
    ]
    if user_id == ADMIN_ID:
        kb.append([KeyboardButton(text="🛠 Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def admin_menu():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="➕ Добавить залив")], [KeyboardButton(text="⬅️ В меню")]],
        resize_keyboard=True
    )

def back_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ В меню")]], resize_keyboard=True)

# ---------- HANDLERS ----------

@dp.message(F.text == "/start")
async def start_cmd(msg: Message):
    get_or_create_user(msg.from_user)
    user_states[msg.from_user.id] = None
    try:
        await msg.answer_photo(
            FSInputFile("start.jpg"),
            caption="<b>👋 Добро пожаловать!</b>",
            reply_markup=main_menu(msg.from_user.id),
            parse_mode=ParseMode.HTML
        )
    except:
        await msg.answer("<b>👋 Добро пожаловать!</b>", reply_markup=main_menu(msg.from_user.id), parse_mode=ParseMode.HTML)

@dp.message(F.text == "📜 Правила")
async def rules_cmd(msg: Message):
    await msg.answer(load_text("RULES"), parse_mode=ParseMode.HTML)

@dp.message(F.text == "💳 Реквизиты")
async def rekv_cmd(msg: Message):
    await msg.answer(load_text("REKVIZITY"), parse_mode=ParseMode.HTML)

@dp.message(F.text == "⭐ Отзывы")
async def reviews_cmd(msg: Message):
    await msg.answer(f"Наши отзывы тут: {config.get('REVIEWS_CHANNEL', 'не указано')}")

@dp.message(F.text == "⬅️ В меню")
async def to_main(msg: Message):
    user_states[msg.from_user.id] = None
    if msg.from_user.id == ADMIN_ID: admin_state["step"] = None
    await msg.answer("Главное меню", reply_markup=main_menu(msg.from_user.id))

@dp.message(F.text == "👨‍💻 Связь с админом")
async def support_cmd(msg: Message):
    user_states[msg.from_user.id] = "wait_support"
    await msg.answer("📝 Напишите ваше сообщение админу. Он ответит вам в ближайшее время.", reply_markup=back_kb())

@dp.message(F.text == "👤 Профиль")
async def profile_cmd(msg: Message):
    cur.execute("SELECT COUNT(*) FROM deposits WHERE user_id=?", (msg.from_user.id,))
    count = cur.fetchone()[0]
    text = (f"<b>👤 Профиль:</b> @{msg.from_user.username}\n"
            f"<b>🆔 ID:</b> <code>{msg.from_user.id}</code>\n"
            f"<b>📊 Заливов:</b> {count}")
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📜 История заливов")], [KeyboardButton(text="⬅️ В меню")]], resize_keyboard=True)
    await msg.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)

@dp.message(F.text == "📜 История заливов")
async def history_cmd(msg: Message):
    cur.execute("SELECT amount, card, created FROM deposits WHERE user_id=? ORDER BY id DESC", (msg.from_user.id,))
    rows = cur.fetchall()
    if not rows:
        await msg.answer("❌ У вас еще нет заливов.")
        return
    res = "<b>📊 Ваша история:</b>\n\n"
    for r in rows: res += f"💰 {r[0]} | 💳 {r[1]} | 📅 {r[2]}\n"
    await msg.answer(res, parse_mode=ParseMode.HTML)

# ---------- ADMIN LOGIC ----------

@dp.message(F.text == "🛠 Админ-панель")
async def admin_panel(msg: Message):
    if msg.from_user.id == ADMIN_ID:
        await msg.answer("🛠 Режим админа", reply_markup=admin_menu())

@dp.message(F.text == "➕ Добавить залив")
async def add_dep_start(msg: Message):
    if msg.from_user.id == ADMIN_ID:
        admin_state["step"] = "wait_id"
        await msg.answer("1️⃣ Введите Telegram ID пользователя:", reply_markup=back_kb())

@dp.message(F.photo | F.document)
async def handle_docs(msg: Message):
    await bot.send_message(ADMIN_ID, f"🧾 <b>Новый чек!</b>\nОт: @{msg.from_user.username}\nID: <code>{msg.from_user.id}</code>", parse_mode=ParseMode.HTML)
    await bot.forward_message(ADMIN_ID, msg.chat.id, msg.message_id)
    reply_targets[ADMIN_ID] = msg.from_user.id
    await msg.answer("✅ Чек получен. Ожидайте проверки.")

# ---------- UNIVERSAL TEXT HANDLER ----------

@dp.message(F.text)
async def global_text_handler(msg: Message):
    uid = msg.from_user.id
    
    # Логика ответа админа (если админ отвечает на чье-то сообщение)
    if uid == ADMIN_ID and msg.reply_to_message:
        # Пробуем вытащить ID из текста или словаря
        target_id = reply_targets.get(ADMIN_ID)
        if target_id:
            try:
                await bot.send_message(target_id, f"<b>📩 Ответ от администратора:</b>\n\n{msg.text}", parse_mode=ParseMode.HTML)
                await msg.answer("✅ Ответ отправлен юзеру.")
                return
            except:
                await msg.answer("❌ Не удалось отправить сообщение.")

    # Логика связи с админом для юзера
    if user_states.get(uid) == "wait_support":
        await bot.send_message(ADMIN_ID, f"❓ <b>Новый вопрос!</b>\nОт: @{msg.from_user.username}\nID: <code>{uid}</code>\n\nТекст: {msg.text}", parse_mode=ParseMode.HTML)
        reply_targets[ADMIN_ID] = uid # Запоминаем кому отвечать
        await msg.answer("✅ Ваше сообщение отправлено админу.")
        user_states[uid] = None
        return

    # Логика добавления залива (админка)
    if uid == ADMIN_ID:
        step = admin_state.get("step")
        if step == "wait_id":
            admin_state["target_user"] = msg.text
            admin_state["step"] = "wait_amount"
            await msg.answer("2️⃣ Введите сумму:")
        elif step == "wait_amount":
            admin_state["amount"] = msg.text
            admin_state["step"] = "wait_system"
            await msg.answer("3️⃣ Введите систему:")
        elif step == "wait_system":
            cur.execute("INSERT INTO deposits (user_id, amount, card, status, created) VALUES (?, ?, ?, ?, ?)",
                (admin_state["target_user"], admin_state["amount"], msg.text, "Success", datetime.now().strftime("%d.%m.%Y %H:%M")))
            db.commit()
            admin_state["step"] = None
            await msg.answer("✅ Залив добавлен", reply_markup=admin_menu())
    
    elif msg.text == "📤 Залив чека":
        await msg.answer("📤 Отправьте скриншот чека боту.")

# ---------- RUN ----------
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())