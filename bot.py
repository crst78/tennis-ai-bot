from flask import Flask, request
import telebot
import requests
import os
import re
from difflib import SequenceMatcher

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "INSERISCI_TOKEN_TELEGRAM")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "INSERISCI_RAPIDAPI_KEY")

RAPIDAPI_HOST = "tennis-api-atp-wta-itf.p.rapidapi.com"
BASE_URL = f"https://{RAPIDAPI_HOST}"
RENDER_URL = "https://tennis-ai-bot-kbw4.onrender.com"

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

CIRCUITS = ["atp", "wta", "itf"]
PLAYERS_CACHE = {}


def api_get(path):
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST
    }

    try:
        r = requests.get(BASE_URL + path, headers=headers, timeout=30)
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


def find_player(player_name):
    query = player_name.lower().strip()
    best_player = None
    best_score = 0

    for circuit in CIRCUITS:
        players = get_players(circuit)

        for p in players:
            name = p.get("name", "")
            if not name:
                continue

            name_low = name.lower()

            if query == name_low or query in name_low:
                return {
                    "id": p.get("id"),
                    "name": name,
                    "country": p.get("countryAcr", ""),
                    "circuit": circuit
                }

            score = similarity(query, name_low)

            if score > best_score:
                best_score = score
                best_player = {
                    "id": p.get("id"),
                    "name": name,
                    "country": p.get("countryAcr", ""),
                    "circuit": circuit
                }

    if best_score >= 0.55:
        return best_player

    return None


def get_past_matches(player):
    status, data = api_get(
        f"/tennis/v2/{player['circuit']}/player/past-matches/{player['id']}"
    )

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

    games = 0
    tiebreaks = 0

    for a, b in sets:
        a = int(a)
        b = int(b)
        games += a + b

        if a == 7 or b == 7:
            tiebreaks += 1

    return {
        "sets": len(sets),
        "games": games,
        "tiebreaks": tiebreaks
    }


def analyze_player(player, matches):
    wins = 0
    losses = 0
    valid_matches = 0
    total_games = 0
    over_22 = 0
    long_matches = 0
    tiebreaks = 0

    for m in matches[:10]:
        if m.get("match_winner") == player["id"]:
            wins += 1
        else:
            losses += 1

        parsed = parse_games(m.get("result"))

        if parsed:
            valid_matches += 1
            total_games += parsed["games"]

            if parsed["games"] >= 23:
                over_22 += 1

            if parsed["sets"] >= 3:
                long_matches += 1

            tiebreaks += parsed["tiebreaks"]

    avg_games = round(total_games / valid_matches, 1) if valid_matches else 0

    return {
        "wins": wins,
        "losses": losses,
        "avg_games": avg_games,
        "over_22": over_22,
        "long_matches": long_matches,
        "tiebreaks": tiebreaks
    }


def split_players(text):
    text = text.strip()

    if " vs " in text.lower():
        parts = re.split(r"\s+vs\s+", text, flags=re.IGNORECASE)
        return parts[0].strip(), parts[1].strip()

    words = text.split()

    if len(words) == 2:
        return words[0], words[1]

    middle = len(words) // 2
    return " ".join(words[:middle]), " ".join(words[middle:])


def build_analysis(name1, name2):
    p1 = find_player(name1)
    p2 = find_player(name2)

    if not p1 or not p2:
        return (
            "⚠️ Non riesco a trovare uno dei due giocatori.\n\n"
            "Scrivi così:\n"
            "/match Djokovic vs Sinner\n\n"
            "Oppure usa cognomi più precisi."
        )

    m1 = get_past_matches(p1)
    m2 = get_past_matches(p2)

    a1 = analyze_player(p1, m1)
    a2 = analyze_player(p2, m2)

    combined_avg = round((a1["avg_games"] + a2["avg_games"]) / 2, 1)
    over_score = a1["over_22"] + a2["over_22"]
    long_score = a1["long_matches"] + a2["long_matches"]
    tie_score = a1["tiebreaks"] + a2["tiebreaks"]

    if combined_avg >= 24 or over_score >= 10:
        over_pick = "Over 22.5 games molto interessante"
    elif combined_avg >= 21 or over_score >= 6:
        over_pick = "Over games interessante ma non fortissimo"
    else:
        over_pick = "Under/No Over prioritario"

    if long_score >= 7:
        handicap_pick = "Handicap positivo sullo sfavorito interessante"
    else:
        handicap_pick = "Handicap da valutare con prudenza"

    if tie_score >= 4:
        ace_pick = "Possibile match con molti turni di servizio / ace interessanti"
    else:
        ace_pick = "Ace non prioritario dai dati recenti"

    if a1["wins"] > a2["wins"]:
        favorito = p1["name"]
    elif a2["wins"] > a1["wins"]:
        favorito = p2["name"]
    else:
        favorito = "Match equilibrato"

    return f"""
🎾 ANALISI TECNICA REALE

📌 Match:
{p1['name']} ({p1['circuit'].upper()}) vs {p2['name']} ({p2['circuit'].upper()})

🌍 Paesi:
{p1['country']} vs {p2['country']}

📊 Ultime 10 partite:

{p1['name']}
✅ Vittorie: {a1['wins']}
❌ Sconfitte: {a1['losses']}
🎯 Media games: {a1['avg_games']}
📈 Over 22.5: {a1['over_22']}/10
🔥 Match lunghi: {a1['long_matches']}/10
🎾 Tiebreak/set tirati: {a1['tiebreaks']}

{p2['name']}
✅ Vittorie: {a2['wins']}
❌ Sconfitte: {a2['losses']}
🎯 Media games: {a2['avg_games']}
📈 Over 22.5: {a2['over_22']}/10
🔥 Match lunghi: {a2['long_matches']}/10
🎾 Tiebreak/set tirati: {a2['tiebreaks']}

🧠 Lettura tecnica:
- Media games combinata: {combined_avg}
- Vantaggio forma recente: {favorito}

✅ Migliore giocata tecnica:
{over_pick}

📌 Handicap:
{handicap_pick}

🎾 Ace:
{ace_pick}

⚠️ Nota:
Analisi basata sui risultati recenti reali della Tennis API.
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
        "Scrivi così:\n"
        "/match Djokovic vs Sinner"
    )


@bot.message_handler(commands=["match"])
def match(message):
    text = message.text.replace("/match", "").strip()

    if not text:
        bot.reply_to(message, "Scrivi così:\n/match Djokovic vs Sinner")
        return

    player1, player2 = split_players(text)

    bot.reply_to(message, "🔎 Analisi reale in corso su ATP/WTA/ITF...")

    risposta = build_analysis(player1, player2)
    bot.reply_to(message, risposta)


if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{RENDER_URL}/{TELEGRAM_TOKEN}")

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
