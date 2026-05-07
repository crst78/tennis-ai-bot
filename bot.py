from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes
)

from flask import Flask
from threading import Thread
import os
import asyncio

TOKEN = "8519906766:AAEPthY8VimdwLrQTVfGYi7pUhbKTRyqiss"

# ---------- FLASK ----------

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot online!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ---------- TELEGRAM ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎾 Tennis AI Bot attivo!\n\n"
        "Comandi:\n"
        "/match Djokovic Alcaraz"
    )

async def match(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if len(context.args) < 2:
        await update.message.reply_text(
            "Uso corretto:\n"
            "/match Djokovic Alcaraz"
        )
        return

    p1 = context.args[0]
    p2 = context.args[1]

    text = f"""
🎾 Match Analysis

{p1} vs {p2}

Probabilità vittoria:
• {p1}: 52%
• {p2}: 48%

Analisi:
Match equilibrato.
Possibile over games.
"""

    await update.message.reply_text(text)

# ---------- MAIN ----------

async def main():

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("match", match))

    print("Bot avviato!")

    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":

    Thread(target=run_web).start()

    asyncio.run(main())
