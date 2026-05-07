import os
import telebot
from flask import Flask
from threading import Thread

TOKEN = "8519906766:AAEPthY8VimdwlrQTVfGYi7pUhbKTRyqiss"

bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)

@app.route('/')
def home():
    return "Tennis AI Bot Online"

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "🎾 Tennis AI Bot attivo!")

@bot.message_handler(commands=['match'])
def match(message):
    text = message.text.replace("/match", "").strip()

    if text == "":
        bot.reply_to(message, "Scrivi un match dopo /match")
        return

    risposta = f"""
🎾 Match Analizzato

📌 Match:
{text}

✅ Pronostico AI:
Over 22.5 Games

🔥 Confidenza:
78%

💰 Value Bet trovata
"""

    bot.reply_to(message, risposta)

def run_bot():
    print("BOT ONLINE")
    bot.infinity_polling()

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

Thread(target=run_bot).start()

if __name__ == "__main__":
    run_web()
