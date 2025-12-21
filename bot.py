import asyncio
import sqlite3
import random
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    FSInputFile,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove
)
from aiogram.enums import ParseMode

# Настройка логирования, чтобы видеть ошибки в консоли хоста
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
        return data
    except FileNotFoundError:
        print("Ошибка: Файл config.txt не найден!")
        return None

config = load_config()
BOT_TOKEN = config["BOT_TOKEN"]
ADMIN_ID = int(config["ADMIN_ID"])
ADMIN_USERNAME = config["ADMIN_USERNAME"]

COMMISSION = 25
USER_SHARE = 75

# ---------- BOT & DB ----------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

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
            "INSERT INTO users (tg_id, username, bot_uid) VALUES (?, ?, ?)",
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
        if start == -1: return "Текст не найден"
        start += len(block) + 6
        end = text.find("===", start)
        res = text[start:end].strip() if end != -1 else text[start:].strip()
        return res
    except:
        return "Ошибка загрузки текста"

# ---------- STATE (Временная память) ----------
# reply_targets[ADMIN_ID] хранит ID пользователя, которому отвечаем
# wait_reply — флаг, что админ сейчас пишет текст ответа
reply_targets = {ADMIN_ID: None, "wait_reply": False}

# ---------- KEYBOARDS ----------
def main_menu(user_id):
    buttons = [
        [KeyboardButton(text="📤 Залив чека"), KeyboardButton(text="👤 Профиль")],
        [KeyboardButton(text="💳 Реквизиты"), KeyboardButton(text="📜 Правила")],
        [KeyboardButton(text="⭐ Отзывы")]
    ]
    if user_id == ADMIN_ID:
        buttons.append([KeyboardButton(text="🛠 Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def profile_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📜 История заливов")],
        [KeyboardButton(text="💬 Связь с админом")],
        [KeyboardButton(text="⬅️ В меню")]
    ], resize_keyboard=True)

def admin_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Добавить залив")],
        [KeyboardButton(text="⬅️ В меню")]
    ], resize_keyboard=True)

def reply_button():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="✉️ Ответить заливщику")]], resize_keyboard=True)

# ---------- HANDLERS ----------

@dp.message(F.text == "/start")
async def start(msg: Message):
    get_or_create_user(msg.from_user)
    try:
        await msg.answer_photo(
            FSInputFile("start.jpg"),
            caption="<b>👋 Добро пожаловать.</b>\nВыберите действие в меню:",
            reply_markup=main_menu(msg.from_user.id),
            parse_mode=ParseMode.HTML
        )
    except:
        await msg.answer("👋 Добро пожаловать.\nВыберите действие:", reply_markup=main_menu(msg.from_user.id))

@dp.message(F.text == "👤 Профиль")
async def profile(msg: Message):
    user = get_or_create_user(msg.from_user)
    cur.execute("SELECT COUNT(*) FROM deposits WHERE user_id=?", (msg.from_user.id,))
    count = cur.fetchone()[0]

    text = (
        f"<b>👤 Пользователь:</b> @{msg.from_user.username if msg.from_user.username else 'NoName'}\n"
        f"<b>🆔 Telegram ID:</b> <code>{msg.from_user.id}</code>\n"
        f"<b>🔸 BOT ID:</b> <code>{user[2]}</code>\n\n"
        f"<b>💼 Комиссия:</b> {COMMISSION}%\n"
        f"<b>💰 Ваша доля:</b> {USER_SHARE}%\n\n"
        f"<b>📊 Всего заливов:</b> {count}"
    )
    await msg.answer(text, reply_markup=profile_menu(), parse_mode=ParseMode.HTML)

@dp.message(F.text == "⬅️ В меню")
async def back(msg: Message):
    await msg.answer("Главное меню:", reply_markup=main_menu(msg.from_user.id))

@dp.message(F.text == "💬 Связь с админом")
async def contact(msg: Message):
    await msg.answer(f"<b>👤 Администратор:</b>\n{ADMIN_USERNAME}", parse_mode=ParseMode.HTML)

@dp.message(F.text == "💳 Реквизиты")
async def rekv(msg: Message):
    await msg.answer(load_text("REKVIZITY"), parse_mode=ParseMode.HTML)

@dp.message(F.text == "📜 Правила")
async def rules(msg: Message):
    await msg.answer(load_text("RULES"), parse_mode=ParseMode.HTML, disable_web_page_preview=False)

# ---------- ОБРАБОТКА ЧЕКА ----------
@dp.message(F.text == "📤 Залив чека")
async def check_step(msg: Message):
    await msg.answer("<b>📤 Отправьте чек</b> (фото или файл).", parse_mode=ParseMode.HTML)

@dp.message(F.photo | F.document)
async def get_check(msg: Message):
    user = msg.from_user
    row = get_or_create_user(user)

    # Запоминаем ID того, кто прислал чек, чтобы админ мог ответить
    reply_targets[ADMIN_ID] = user.id

    admin_text = (
        "<b>🧾 НОВЫЙ ЧЕК</b>\n\n"
        f"👤 @{user.username if user.username else 'Нет username'}\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"🔸 BOT ID: <code>{row[2]}</code>"
    )

    # Шлем уведомление админу
    await bot.send_message(ADMIN_ID, admin_text, parse_mode=ParseMode.HTML, reply_markup=reply_button())
    # Пересылаем сам файл
    await bot.forward_message(ADMIN_ID, msg.chat.id, msg.message_id)

    await msg.answer(f"✅ <b>Чек принят на проверку.</b>\nОжидайте ответа от {ADMIN_USERNAME}", parse_mode=ParseMode.HTML)

# ---------- ADMIN LOGIC ----------
@dp.message(F.text == "🛠 Админ-панель")
async def admin_panel(msg: Message):
    if msg.from_user.id == ADMIN_ID:
        await msg.answer("🛠 <b>Режим администратора</b>", reply_markup=admin_menu(), parse_mode=ParseMode.HTML)

@dp.message(F.text == "✉️ Ответить заливщику")
async def reply_handler(msg: Message):
    if msg.from_user.id == ADMIN_ID:
        if reply_targets[ADMIN_ID]:
            reply_targets["wait_reply"] = True
            await msg.answer("<b>✍️ Введите текст ответа:</b>", parse_mode=ParseMode.HTML)
        else:
            await msg.answer("❌ Нет активного диалога (никто не присылал чек).")

# Ловим любой текст (для ответа админа или просто ошибок)
@dp.message(F.text)
async def global_handler(msg: Message):
    # Если админ в режиме ответа
    if msg.from_user.id == ADMIN_ID and reply_targets["wait_reply"]:
        target_id = reply_targets[ADMIN_ID]
        try:
            await bot.send_message(
                target_id, 
                f"<b>📩 Сообщение от администратора:</b>\n\n{msg.text}", 
                parse_mode=ParseMode.HTML
            )
            await msg.answer("✅ Отправлено пользователю.")
        except Exception as e:
            await msg.answer(f"❌ Ошибка отправки: {e}")
        
        reply_targets["wait_reply"] = False
        return

    # Остальные текстовые команды
    if msg.text == "⭐ Отзывы":
        await msg.answer(config.get("REVIEWS_CHANNEL", "Канал не указан"))
    elif msg.text == "📜 История заливов":
        cur.execute("SELECT id, created FROM deposits WHERE user_id=? ORDER BY id DESC", (msg.from_user.id,))
        rows = cur.fetchall()
        if not rows:
            await msg.answer("❌ История пустая")
        else:
            res = "<b>📊 История заливов:</b>\n\n" + "\n".join([f"Залив #{r[0]} ({r[1]})" for r in rows])
            await msg.answer(res, parse_mode=ParseMode.HTML)

# ---------- RUN ----------
async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен")