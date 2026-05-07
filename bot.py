from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "8519906766:AAHpXAp6Sm0xLXbWhAmc_by6ION4fjub9s"

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
🎾 Match Analysis

{player1} vs {player2}

✅ Miglior giocata tecnica:
Over 22.5 Games

📊 Possibile valore:
Tie-break nel match

🔥 Match equilibrato tecnicamente.
"""

    await update.message.reply_text(risposta)

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("match", match))

print("BOT AVVIATO")

app.run_polling()
