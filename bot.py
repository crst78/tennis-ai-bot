from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes
)

from flask import Flask
from threading import Thread
import os

TOKEN = "8519906766:AAEPthY8VimdwLrQTVfGYi7pUhbKTRyqiss"

# -------- FLASK SERVER --------

app_flask = Flask(__name__)

@app_flask.route("/")
def home():
    return "Tennis AI Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_flask.run(host="0.0.0.0", port=port)

# -------- TELEGRAM COMMANDS --------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎾 Tennis AI Bot attivo!\n\n"
        "Comando disponibile:\n"
        "/match Djokovic Alcaraz"
    )

async def match(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if len(context.args) < 2:
        await update.message.reply_text(
            "Uso corretto:\n"
            "/match Djokovic Alcaraz"
        )
        return

    player1 = context.args[0]
    player2 = context.args[1]

    risposta = f"""
🎾 Match Analysis

{player1} vs {player2}

Probabilità vittoria:
• {player1}: 52%
• {player2}: 48%

Analisi:
Match molto equilibrato.
Possibile over games.
"""

    await update.message.reply_text(risposta)

# -------- MAIN --------

def main():

    # Avvia Flask
    Thread(target=run_web).start()

    # Avvia Telegram Bot
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("match", match))

    print("Bot avviato!")

    application.run_polling()

if __name__ == "__main__":
    main()
