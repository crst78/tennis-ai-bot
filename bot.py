import os
import threading
from flask import Flask

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "8519906766:AAHpXAp6SXm0xLXbWhAmc_by6ION4fjub9s"

web = Flask(__name__)

@web.route("/")
def home():
    return "Bot attivo!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    web.run(host="0.0.0.0", port=port)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎾 Tennis AI Bot attivo!\n\n"
        "Comando disponibile:\n"
        "/match Djokovic Alcaraz"
    )

async def match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            "Uso corretto:\n/match Djokovic Alcaraz"
        )
        return

    player1 = context.args[0]
    player2 = context.args[1]

    risposta = f"""
🎾 MATCH ANALYSIS

👤 {player1} vs {player2}

✅ Miglior giocata tecnica:
Over 22.5 Games

📊 Possibili mercati da valutare:
• Vincente match
• Handicap games
• Over/Under games
• Ace
• Doppi falli

🔥 Match tecnicamente equilibrato.
"""

    await update.message.reply_text(risposta)

def main():
    threading.Thread(target=run_web, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("match", match))

    print("BOT AVVIATO")
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
