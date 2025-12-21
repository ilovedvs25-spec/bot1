import asyncio
import sqlite3
import random
from datetime import datetime

from aiogram import Bot, Dispatcher, F, types
from aiogram.types import Message, FSInputFile, KeyboardButton, ReplyKeyboardMarkup

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
ADMIN_ID = int(config["ADMIN_ID"])
COMMISSION = 25
USER_SHARE = 75

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

# ---------- TEXTS ----------
def load_text(block):
    with open("texts.txt", "r", encoding="utf-8") as f:
        text = f.read()
    start = text.find(f"==={block}===")
    if start == -1:
        return "Текст не найден"
    start += len(block) + 6
    end = text.find("===", start)
    return text[start:end].strip()

# ---------- BOT ----------
bot = Bot(config["BOT_TOKEN"])
dp = Dispatcher()

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

# ---------- REPLY KEYBOARDS ----------
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
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📜 История заливов"), KeyboardButton(text="💬 Связь с админом")],
            [KeyboardButton(text="⬅️ В меню")]
        ],
        resize_keyboard=True
    )
    return kb

def admin_menu():
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить залив")],
            [KeyboardButton(text="⬅️ В меню")]
        ],
        resize_keyboard=True
    )
    return kb

def status_menu():
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Успешно"), KeyboardButton(text="⏳ В процессе"), KeyboardButton(text="❌ Отказ")]
        ],
        resize_keyboard=True
    )
    return kb

# ---------- START ----------
@dp.message(F.text == "/start")
async def start(msg: Message):
    get_or_create_user(msg.from_user)

    await msg.answer_photo(
        FSInputFile("start.jpg"),
        caption="👋 Добро пожаловать в сервис.\nВыберите действие:",
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
        f"🔢 ID (Telegram): {msg.from_user.id}\n"
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
    buttons = []
    for r in rows:
        buttons.append(f"Залив #{r[0]} ({r[1][:10]})")
    await msg.answer("📊 История заливов:\n" + "\n".join(buttons))

@dp.message(F.text == "💬 Связь с админом")
async def admin_contact(msg: Message):
    await msg.answer(f"👤 Администратор:\n{config['ADMIN_USERNAME']}")

@dp.message(F.text == "⬅️ В меню")
async def back_menu(msg: Message):
    await msg.answer("Главное меню:", reply_markup=main_menu(msg.from_user.id))

# ---------- CHECK ----------
@dp.message(F.text == "📤 Залив чека")
async def check(msg: Message):
    await msg.answer("📤 Отправьте чек (фото или PDF).")

@dp.message(F.photo | F.document)
async def get_check(msg: Message):
    await bot.forward_message(
        chat_id=ADMIN_ID,
        from_chat_id=msg.chat.id,
        message_id=msg.message_id
    )
    await msg.answer(
        f"✅ Чек получен.\nАдминистратор свяжется с вами.\n\n{config['ADMIN_USERNAME']}"
    )

# ---------- REKV / RULES / REVIEWS ----------
@dp.message(F.text == "💳 Реквизиты")
async def rekv(msg: Message):
    await msg.answer(load_text("REKVIZITY"))

@dp.message(F.text == "📜 Правила")
async def rules(msg: Message):
    await msg.answer(load_text("RULES"))

@dp.message(F.text == "⭐ Отзывы")
async def reviews(msg: Message):
    await msg.answer(config["REVIEWS_CHANNEL"])

# ---------- ADMIN PANEL ----------
@dp.message(F.text == "🛠 Админ-панель")
async def admin_panel(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        return
    await msg.answer("🛠 Админ-панель:", reply_markup=admin_menu())

@dp.message(F.text == "➕ Добавить залив")
async def add_dep_start(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        return
    await msg.answer("Введите ID пользователя:")

# ---------- FSM-like для пошагового добавления заливов ----------
user_steps = {}

@dp.message()
async def steps(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        return
    uid = msg.from_user.id
    step = user_steps.get(uid, {})
    text = msg.text.strip()

    # Шаг 1: ID пользователя
    if "step" not in step:
        try:
            step["user_id"] = int(text)
            step["step"] = 2
            user_steps[uid] = step
            await msg.answer("Введите сумму:")
        except:
            await msg.answer("❌ Неверный формат ID. Попробуйте ещё раз.")
        return

    # Шаг 2: сумма
    if step["step"] == 2:
        try:
            step["amount"] = float(text)
            step["step"] = 3
            user_steps[uid] = step
            await msg.answer("Введите карту:")
        except:
            await msg.answer("❌ Неверная сумма. Попробуйте ещё раз.")
        return

    # Шаг 3: карта
    if step["step"] == 3:
        step["card"] = text
        step["step"] = 4
        user_steps[uid] = step
        await msg.answer("Введите приёмщика:")
        return

    # Шаг 4: приёмщик
    if step["step"] == 4:
        step["receiver"] = text
        step["step"] = 5
        user_steps[uid] = step
        await msg.answer("Выберите статус:", reply_markup=status_menu())
        return

    # Шаг 5: статус
    if step["step"] == 5:
        if text not in ["✅ Успешно", "⏳ В процессе", "❌ Отказ"]:
            await msg.answer("❌ Выберите статус кнопкой.")
            return
        step["status"] = text
        # Сохраняем в БД
        cur.execute(
            "INSERT INTO deposits (user_id, amount, card, receiver, status, created) VALUES (?,?,?,?,?,?)",
            (step["user_id"], step["amount"], step["card"], step["receiver"], step["status"], datetime.now().strftime("%d.%m.%Y %H:%M"))
        )
        db.commit()
        user_steps.pop(uid)
        await msg.answer("✅ Залив добавлен!", reply_markup=admin_menu())
        return

# ---------- RUN ----------
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
