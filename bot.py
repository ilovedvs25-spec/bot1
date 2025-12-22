import asyncio
import sqlite3
import random
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
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
        if start == -1: return f"Ошибка: Блок {block} не найден в texts.txt"
        start_idx = start + len(block) + 6
        end_idx = text.find("===", start_idx)
        return text[start_idx:end_idx].strip() if end_idx != -1 else text[start_idx:].strip()
    except Exception as e:
        return f"Ошибка файла: {e}"

# ---------- STATE (Временные данные админа) ----------
admin_state = {
    "target_user": None,
    "step": None, # "wait_id", "wait_amount", "wait_system", "wait_reply"
}
reply_targets = {ADMIN_ID: None}

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
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Добавить залив")],
        [KeyboardButton(text="⬅️ В меню")]
    ], resize_keyboard=True)

# ---------- HANDLERS ----------

@dp.message(F.text == "/start")
async def start_cmd(msg: Message):
    get_or_create_user(msg.from_user)
    await msg.answer_photo(FSInputFile("start.jpg"), caption="<b>👋 Добро пожаловать!</b>", reply_markup=main_menu(msg.from_user.id), parse_mode="HTML")

@dp.message(F.text == "💳 Реквизиты")
async def rekv_cmd(msg: Message):
    await msg.answer(load_text("REKVIZITY"), parse_mode="HTML")

@dp.message(F.text == "📜 Правила")
async def rules_cmd(msg: Message):
    await msg.answer(load_text("RULES"), parse_mode="HTML", disable_web_page_preview=False)

@dp.message(F.text == "👤 Профиль")
async def profile_cmd(msg: Message):
    user = get_or_create_user(msg.from_user)
    cur.execute("SELECT COUNT(*) FROM deposits WHERE user_id=?", (msg.from_user.id,))
    count = cur.fetchone()[0]
    text = (f"<b>👤 Профиль:</b> @{msg.from_user.username}\n"
            f"<b>🆔 ID:</b> <code>{msg.from_user.id}</code>\n"
            f"<b>📊 Заливов:</b> {count}")
    await msg.answer(text, reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📜 История заливов")],[KeyboardButton(text="⬅️ В меню")]], resize_keyboard=True), parse_mode="HTML")

@dp.message(F.text == "📜 История заливов")
async def history_cmd(msg: Message):
    cur.execute("SELECT amount, card, created FROM deposits WHERE user_id=? ORDER BY id DESC", (msg.from_user.id,))
    rows = cur.fetchall()
    if not rows:
        await msg.answer("❌ У вас еще нет заливов.")
    else:
        res = "<b>📊 Ваша история:</b>\n\n"
        for r in rows:
            res += f"💰 {r[0]} руб | 💳 {r[1]} | 📅 {r[2]}\n"
        await msg.answer(res, parse_mode="HTML")

@dp.message(F.text == "🛠 Админ-панель")
async def admin_panel(msg: Message):
    if msg.from_user.id == ADMIN_ID:
        await msg.answer("🛠 Режим админа", reply_markup=admin_menu())

# --- ЛОГИКА ДОБАВЛЕНИЯ ЗАЛИВА ---
@dp.message(F.text == "➕ Добавить залив")
async def add_dep_start(msg: Message):
    if msg.from_user.id == ADMIN_ID:
        admin_state["step"] = "wait_id"
        await msg.answer("1️⃣ Введите <b>Telegram ID</b> пользователя, которому добавляем залив:", parse_mode="HTML", reply_markup=ReplyKeyboardRemove())

@dp.message(F.text == "✉️ Ответить заливщику")
async def reply_start(msg: Message):
    if msg.from_user.id == ADMIN_ID:
        admin_state["step"] = "wait_reply"
        await msg.answer("✍️ Введите сообщение пользователю:")

@dp.message(F.text == "⬅️ В меню")
async def to_main(msg: Message):
    admin_state["step"] = None
    await msg.answer("Главное меню", reply_markup=main_menu(msg.from_user.id))

# --- ПРИЕМ ФАЙЛОВ (ЧЕКОВ) ---
@dp.message(F.photo | F.document)
async def handle_docs(msg: Message):
    user = msg.from_user
    reply_targets[ADMIN_ID] = user.id 
    admin_text = f"🧾 <b>Новый чек!</b>\nОт: @{user.username}\nID: <code>{user.id}</code>"
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="✉️ Ответить заливщику")],[KeyboardButton(text="🛠 Админ-панель")]], resize_keyboard=True)
    await bot.send_message(ADMIN_ID, admin_text, parse_mode="HTML", reply_markup=kb)
    await bot.forward_message(ADMIN_ID, msg.chat.id, msg.message_id)
    await msg.answer("✅ Чек получен. Ожидайте проверки.")

# --- ЕДИНЫЙ ОБРАБОТЧИК ТЕКСТА ДЛЯ АДМИНА ---
@dp.message(F.text)
async def admin_worker(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        if msg.text == "⭐ Отзывы":
            await msg.answer(config.get("REVIEWS_CHANNEL", "Канал не указан"))
        elif msg.text == "📤 Залив чека":
            await msg.answer("📤 Отправьте скриншот чека боту.")
        return

    step = admin_state["step"]

    if step == "wait_id":
        admin_state["target_user"] = msg.text
        admin_state["step"] = "wait_amount"
        await msg.answer("2️⃣ Теперь введите <b>Сумму</b> (только цифры):", parse_mode="HTML")
    
    elif step == "wait_amount":
        admin_state["amount"] = msg.text
        admin_state["step"] = "wait_system"
        await msg.answer("3️⃣ Теперь введите <b>Куда</b> (например: Сбербанк, Т-Банк):", parse_mode="HTML")

    elif step == "wait_system":
        user_id = admin_state["target_user"]
        amount = admin_state["amount"]
        system = msg.text
        date_now = datetime.now().strftime("%d.%m.%Y %H:%M")
        
        try:
            cur.execute("INSERT INTO deposits (user_id, amount, card, status, created) VALUES (?, ?, ?, ?, ?)",
                        (user_id, amount, system, "Success", date_now))
            db.commit()
            await msg.answer(f"✅ <b>Залив добавлен!</b>\nЮзер: <code>{user_id}</code>\nСумма: {amount}\nСистема: {system}", parse_mode="HTML", reply_markup=admin_menu())
            # Уведомляем юзера
            try:
                await bot.send_message(user_id, f"✅ <b>Ваш залив на {amount} руб. подтвержден!</b>\nПроверьте раздел «История заливов».", parse_mode="HTML")
            except: pass
        except Exception as e:
            await msg.answer(f"❌ Ошибка БД: {e}", reply_markup=admin_menu())
        
        admin_state["step"] = None

    elif step == "wait_reply":
        target = reply_targets.get(ADMIN_ID)
        if target:
            try:
                await bot.send_message(target, f"<b>📩 Сообщение от админа:</b>\n\n{msg.text}", parse_mode="HTML")
                await msg.answer("✅ Отправлено!", reply_markup=admin_menu())
            except:
                await msg.answer("❌ Не удалось доставить.")
        admin_state["step"] = None

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())