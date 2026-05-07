from flask import Flask, request
import telebot
import os

TOKEN = "8519906766:AAEPthY8VimdwLrQTVfGYi7pUhbKTRyqiss"

bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)

# COMANDO START
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "🎾 Tennis AI Bot online!")

# COMANDO MATCH
@bot.message_handler(commands=['match'])
def match_command(message):
    try:
        text = message.text.replace("/match", "").strip()

        if text == "":
            bot.reply_to(message, "Scrivi un match.\nEsempio:\n/match Sinner Djokovic")
            return

        risposta = f"""
🎾 Match richiesto:

{text}

✅ Analisi esempio:
- Favorito: primo giocatore
- Value bet: Over games
- Confidenza: 72%
"""

        bot.reply_to(message, risposta)

    except Exception as e:
        bot.reply_to(message, f"Errore: {e}")

# WEBHOOK
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("UTF-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200

# HOME
@app.route("/")
def home():
    return "Bot online!"

# START SERVER
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(
        url=f"https://tennis-ai-bot-kbw4.onrender.com/{TOKEN}"
    )

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
