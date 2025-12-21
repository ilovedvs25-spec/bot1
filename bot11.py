import telebot
import pyscreenshot as ImageGrab

BOT_TOKEN = "токен твого бота"   

bot = telebot.TeleBot(BOT_TOKEN)


@bot.message_handler(commands=['start'])
def start(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn = telebot.types.KeyboardButton("📸 Зробити скріншот")
    markup.add(btn)
    bot.send_message(message.chat.id, "Привіт! Натисни кнопку, щоб зробити скріншот.", reply_markup=markup)


@bot.message_handler(func=lambda m: m.text == "📸 Зробити скріншот")
def screenshot(message):
    bot.send_message(message.chat.id, "⏳ Роблю скріншот...")

    screenshot = ImageGrab.grab()     
    screenshot.save("screen.png")     

    
    with open("screen.png", "rb") as img:
        bot.send_photo(message.chat.id, img)

bot.polling(none_stop=True)
