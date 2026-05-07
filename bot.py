from flask import Flask, request
import telebot
import requests
import os
import re
from difflib import SequenceMatcher

TELEGRAM_TOKEN = "8519906766:AAEPthY8VimdwLrQTVfGYi7pUhbKTRyqiss"
RAPIDAPI_KEY = "f83bb28b29mshe277024278f5591p108cabjsn16d1261fcb66"

RAPIDAPI_HOST = "tennis-api-atp-wta-itf.p.rapidapi.com"
BASE_URL = f"https://{RAPIDAPI_HOST}"
RENDER_URL = "https://tennis-ai-bot-kbw4.onrender.com"

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

CIRCUITS = ["atp", "wta", "itf"]
PLAYERS_CACHE = {}


def api_get(path):
    url = BASE_URL + path
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST
    }

    try:
        r = requests.get(url, headers=headers, timeout=25)
        return r.status_code, r.json()
    except Exception as e:
        return 500, {"error": str(e)}


def similarity(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def get_players(circuit):
    if circuit in PLAYERS_CACHE:
        return PLAYERS_CACHE[circuit]

    status, data = api_get(f"/tennis/v2/{circuit}/player/")

    if status == 200 and "data" in data:
        PLAYERS_CACHE[circuit] = data["data"]
        return data["data"]

    return []


def find_player(name):
    name = name.lower().strip()
    best_match = None
    best_score = 0

    for circuit in CIRCUITS:
        players = get_players(circuit)

        for p in players:
            api_name = p.get("name", "")
            if not api_name:
                continue

            api_name_low = api_name.lower()

            if name == api_name_low or name in api_name_low:
                return {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "country": p.get("countryAcr", ""),
                    "circuit": circuit
                }

            score = similarity(name, api_name_low)

            if score > best_score:
                best_score = score
                best_match = {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "country": p.get("countryAcr", ""),
                    "circuit": circuit
                }

    if best_score >= 0.55:
        return best_match

    return None


def get_past_matches(player):
    path = f"/tennis/v2/{player['circuit']}/player/past-matches/{player['id']}"
    status, data = api_get(path)

    if status == 200 and "data" in data:
        return data["data"]

    return []


def parse_games(result):
    if not result:
        return None

    result = result.lower()

    if "ret" in result or "walkover" in result or "w/o" in result:
        return None

    sets = re.findall(r"(\d+)-(\d+)", result)

    if not sets:
        return None

    total_games = 0
    tie_breaks = 0

    for a, b in sets:
        a = int(a)
        b = int(b)
        total_games += a + b

        if a == 7 or b == 7:
            tie_breaks += 1

    return {
        "sets": len(sets),
        "games": total_games,
        "tie_breaks": tie_breaks
    }


def analyze_player(player, matches):
    wins = 0
    losses = 0
    total_games = 0
    valid = 0
    over_22 = 0
    long_matches = 0
    tie_breaks = 0

    for m in matches[:10]:
        if m.get("match_winner") == player["id"]:
            wins += 1
        else:
            losses += 1

        parsed = parse_games(m.get("result"))

        if parsed:
            valid += 1
            total_games += parsed["games"]

            if parsed["games"] >= 23:
                over_22 += 1

            if parsed["sets"] >= 3:
                long_matches += 1

            tie_breaks += parsed["tie_breaks"]

    avg_games = round(total_games / valid, 1) if valid else 0

    return {
        "wins": wins,
        "losses": losses,
        "avg_games": avg_games,
        "over_22": over_22,
        "long_matches": long_matches,
        "tie_breaks": tie_breaks
    }


def build_prediction(a1, a2):
    combined_avg = round((a1["avg_games"] + a2["avg_games"]) / 2, 1)
    over_score = a1["over_22"] + a2["over_22"]
    long_score = a1["long_matches"] + a2["long_matches"]
    tie_score = a1["tie_breaks"] + a2["tie_breaks"]

    if combined_avg >= 24 or over_score >= 10:
        over = "Over 22.5 games molto interessante"
    elif combined_avg >= 21 or over_score >= 6:
        over = "Over games interessante ma non fortissimo"
    else:
        over = "Under/No Over prioritario"

    if long_score >= 7:
        handicap = "Handicap positivo sullo sfavorito interessante"
    else:
        handicap = "Handicap da valutare con prudenza"

    if tie_score >= 4:
        ace = "Possibile match con molti turni di servizio e ace"
    else:
        ace = "Ace non prioritario dai dati recenti"

    if a1["wins"] > a2["wins"]:
        favorito = "leggero vantaggio tecnico primo giocatore"
    elif a2["wins"] > a1["wins"]:
        favorito = "leggero vantaggio tecnico secondo giocatore"
    else:
        favorito = "match equilibrato"

    return favorito, over, handicap, ace, combined_avg


def build_analysis(player1_name, player2_name):
    p1 = find_player(player1_name)
    p2 = find_player(player2_name)

    if not p1 or not p2:
        return (
            "⚠️ Non riesco a trovare uno dei due giocatori.\n\n"
            "Prova con il cognome esatto.\n"
            "Esempio:\n/match Djokovic Sinner"
        )

    m1 = get_past_matches(p1)
    m2 = get_past_matches(p2)

    a1 = analyze_player(p1, m1)
    a2 = analyze_player(p2, m2)

    favorito, over, handicap, ace, combined_avg = build_prediction(a1, a2)

    return f"""
🎾 ANALISI TECNICA REALE

📌 Match:
{p1['name']} ({p1['circuit'].upper()}) vs {p2['name']} ({p2['circuit'].upper()})

🌍 Paesi:
{p1.get('country', '')} vs {p2.get('country', '')}

📊 Ultime 10 partite:

{p1['name']}
✅ Vittorie: {a1['wins']}
❌ Sconfitte: {a1['losses']}
🎯 Media games: {a1['avg_games']}
📈 Over 22.5: {a1['over_22']}/10
🔥 Match lunghi: {a1['long_matches']}/10
🎾 Tiebreak/set tirati: {a1['tie_breaks']}

{p2['name']}
✅ Vittorie: {a2['wins']}
❌ Sconfitte: {a2['losses']}
🎯 Media games: {a2['avg_games']}
📈 Over 22.5: {a2['over_22']}/10
🔥 Match lunghi: {a2['long_matches']}/10
🎾 Tiebreak/set tirati: {a2['tie_breaks']}

🧠 Lettura tecnica:
- Media games combinata: {combined_avg}
- Valutazione match: {favorito}

✅ Migliore giocata tecnica:
{over}

📌 Handicap:
{handicap}

🎾 Ace:
{ace}

⚠️ Nota:
Analisi basata su dati reali Tennis API.
Non considera quote bookmaker.
"""


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
        "Scrivi:\n"
        "/match Djokovic Sinner\n\n"
        "Funziona con ATP, WTA e ITF se i dati sono presenti nella API."
    )


@bot.message_handler(commands=["match"])
def match(message):
    text = message.text.replace("/match", "").strip()

    if not text:
        bot.reply_to(message, "Scrivi così:\n/match Djokovic Sinner")
        return

    parts = text.split()

    if len(parts) < 2:
        bot.reply_to(message, "Inserisci due giocatori.\nEsempio:\n/match Djokovic Sinner")
        return

    player1 = parts[0]
    player2 = parts[1]

    bot.reply_to(message, "🔎 Analisi reale in corso su ATP/WTA/ITF...")

    risposta = build_analysis(player1, player2)
    bot.reply_to(message, risposta)


if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{RENDER_URL}/{TELEGRAM_TOKEN}")

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
