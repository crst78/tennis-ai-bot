from flask import Flask, request
import telebot
import requests
import os

TELEGRAM_TOKEN = "8519906766:AAEPthY8VimdwLrQTVfGYi7pUhbKTRyqiss"

RAPIDAPI_KEY = "f83bb28b29mshe277024278f5591p108cabjsn16d1261fcb66"
RAPIDAPI_HOST = "tennis-api-atp-wta-itf.p.rapidapi.com"
BASE_URL = f"https://{RAPIDAPI_HOST}"

RENDER_URL = "https://tennis-ai-bot-kbw4.onrender.com"

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)


def rapidapi_get(path):
    url = BASE_URL + path
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST
    }

    try:
        r = requests.get(url, headers=headers, timeout=20)
        return r.status_code, r.json()
    except Exception as e:
        return 500, {"error": str(e)}


def search_player(name):
    possible_paths = [
        f"/tennis/v2/search/{name}",
        f"/tennis/v2/players/search/{name}",
        f"/tennis/v2/player/search/{name}",
        f"/tennis/v2/players?search={name}",
    ]

    for path in possible_paths:
        status, data = rapidapi_get(path)

        if status == 200 and data:
            return data

    return None


def technical_analysis(player1, player2):
    p1_data = search_player(player1)
    p2_data = search_player(player2)

    analysis = f"""
🎾 ANALISI TECNICA MATCH

📌 Match:
{player1} vs {player2}

📊 Dati API:
"""

    if p1_data:
        analysis += f"\n✅ Dati trovati per {player1}"
    else:
        analysis += f"\n⚠️ Dati non trovati per {player1}"

    if p2_data:
        analysis += f"\n✅ Dati trovati per {player2}"
    else:
        analysis += f"\n⚠️ Dati non trovati per {player2}"

    analysis += """

🧠 Lettura tecnica preliminare:
- Valutare superficie
- Forma recente
- Ranking
- H2H
- Percentuale servizio
- Ace / doppi falli
- Tendenza over/under games

🎯 Mercati tecnici da valutare:
- Over/Under games
- Handicap games
- Ace
- Doppi falli

⚠️ Nota:
Questa è la prima versione collegata alla API.
Ora possiamo perfezionare gli endpoint corretti per avere analisi sempre più precise.
"""

    return analysis


@app.route("/")
def home():
    return "Tennis AI Bot Online"


@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("UTF-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200


@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(
        message,
        "🎾 Tennis AI Bot online!\n\n"
        "Usa:\n"
        "/match Sinner Alcaraz"
    )


@bot.message_handler(commands=["match"])
def match(message):
    text = message.text.replace("/match", "").strip()

    if text == "":
        bot.reply_to(
            message,
            "Scrivi il match così:\n"
            "/match Sinner Alcaraz"
        )
        return

    parts = text.split()

    if len(parts) < 2:
        bot.reply_to(
            message,
            "Inserisci due giocatori.\n"
            "Esempio:\n"
            "/match Sinner Alcaraz"
        )
        return

    player1 = parts[0]
    player2 = parts[1]

    bot.reply_to(message, "🔎 Sto analizzando il match con la Tennis API...")

    risposta = technical_analysis(player1, player2)

    bot.reply_to(message, risposta)


if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{RENDER_URL}/{TELEGRAM_TOKEN}")

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
