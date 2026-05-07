from telegram.ext import Updater, CommandHandler
from telegram import Update
from telegram.ext.callbackcontext import CallbackContext

TOKEN = "8519906766:AAHpXAp6Sm0xLXbWhAmc_by6ION4fjub9s"

def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "🎾 Tennis AI Bot Attivo!\n\n"
        "Comando disponibile:\n"
        "/match Djokovic Alcaraz"
    )

def match(update: Update, context: CallbackContext):

    try:
        player1 = context.args[0]
        player2 = context.args[1]
    except:
        update.message.reply_text(
            "Uso corretto:\n/match Djokovic Alcaraz"
        )
        return

    risposta = f"""
🎾 ANALISI TECNICA

👤 {player1}
vs
👤 {player2}

✅ Migliori mercati:
• Vincente Match
• Handicap Games
• Over/Under Games
• Ace
• Doppi Falli

📊 Analisi tecnica in corso...
"""

    update.message.reply_text(risposta)

updater = Updater(TOKEN, use_context=True)

dispatcher = updater.dispatcher

dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("match", match))

updater.start_polling()
updater.idle()
