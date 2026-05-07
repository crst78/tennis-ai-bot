from flask import Flask, request
import telebot
import requests
import os
import re
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime, timedelta

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

RAPIDAPI_HOST = "tennis-api-atp-wta-itf.p.rapidapi.com"
BASE_URL = f"https://{RAPIDAPI_HOST}"
RENDER_URL = "https://tennis-ai-bot-kbw4.onrender.com"

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

CIRCUITS = ["atp", "wta", "itf"]


def clean_text(text):
    if not text:
        return ""
    text = text.lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def similarity(a, b):
    return SequenceMatcher(None, clean_text(a), clean_text(b)).ratio()


def api_get(path):
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
    }

    try:
        r = requests.get(BASE_URL + path, headers=headers, timeout=30)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


def split_players(text):
    text = text.strip()

    if " vs " in text.lower():
        parts = re.split(r"\s+vs\s+", text, flags=re.IGNORECASE)
        return parts[0].strip(), parts[1].strip()

    return None, None


def is_same_player(input_name, api_name):
    q = clean_text(input_name)
    n = clean_text(api_name)

    if not q or not n:
        return False

    if q == n:
        return True

    if q in n:
        return True

    q_words = q.split()
    n_words = n.split()

    if len(q_words) == 1 and q_words[0] in n_words:
        return True

    if similarity(q, n) >= 0.72:
        return True

    return False


def find_match_from_fixtures(name1, name2):
    today = datetime.utcnow().date()

    dates = []
    for delta in range(-5, 8):
        dates.append((today + timedelta(days=delta)).strftime("%Y-%m-%d"))

    best_match = None
    best_score = 0
    best_circuit = None

    for circuit in CIRCUITS:
        for date in dates:
            paths = [
                f"/tennis/v2/{circuit}/fixtures/date/{date}",
                f"/tennis/v2/{circuit}/fixtures/date-fixtures/{date}",
                f"/tennis/v2/{circuit}/fixtures/{date}",
                f"/tennis/v2/{circuit}/date-fixtures/{date}",
            ]

            for path in paths:
                data = api_get(path)

                if not isinstance(data, dict):
                    continue

                fixtures = data.get("data", [])

                if not fixtures:
                    continue

                for m in fixtures:
                    p1 = m.get("player1", {}) or {}
                    p2 = m.get("player2", {}) or {}

                    p1_name = p1.get("name", "")
                    p2_name = p2.get("name", "")

                    direct_score = 0

                    if is_same_player(name1, p1_name) and is_same_player(name2, p2_name):
                        direct_score = similarity(name1, p1_name) + similarity(name2, p2_name)

                    if is_same_player(name1, p2_name) and is_same_player(name2, p1_name):
                        direct_score = similarity(name1, p2_name) + similarity(name2, p1_name)

                    if direct_score > best_score:
                        best_score = direct_score
                        best_match = m
                        best_circuit = circuit

    if best_match and best_score >= 1.15:
        p1 = best_match.get("player1", {})
        p2 = best_match.get("player2", {})

        return {
            "match": best_match,
            "circuit": best_circuit,
            "player1": {
                "id": p1.get("id") or best_match.get("player1Id"),
                "name": p1.get("name"),
                "country": p1.get("countryAcr", ""),
                "circuit": best_circuit,
            },
            "player2": {
                "id": p2.get("id") or best_match.get("player2Id"),
                "name": p2.get("name"),
                "country": p2.get("countryAcr", ""),
                "circuit": best_circuit,
            },
            "tournamentId": best_match.get("tournamentId"),
        }

    return None


def search_player_name(name):
    paths = [
        f"/tennis/v2/search?search={requests.utils.quote(name)}",
        f"/tennis/v2/misc/search?search={requests.utils.quote(name)}",
        f"/tennis/v2/search/{requests.utils.quote(name)}",
    ]

    for path in paths:
        data = api_get(path)

        if not isinstance(data, dict):
            continue

        groups = data.get("data", [])

        for group in groups:
            category = group.get("category", "")

            if not category.startswith("player_"):
                continue

            circuit = category.replace("player_", "")
            results = group.get("result", [])

            if results:
                best = sorted(
                    results,
                    key=lambda x: similarity(name, x.get("name", "")),
                    reverse=True,
                )[0]

                if similarity(name, best.get("name", "")) >= 0.6:
                    return {
                        "name": best.get("name"),
                        "country": best.get("countryAcr", ""),
                        "circuit": circuit,
                    }

    return None


def find_player_in_recent_fixtures(name):
    today = datetime.utcnow().date()
    dates = []

    for delta in range(-7, 15):
        dates.append((today + timedelta(days=delta)).strftime("%Y-%m-%d"))

    best = None
    best_score = 0

    for circuit in CIRCUITS:
        for date in dates:
            paths = [
                f"/tennis/v2/{circuit}/fixtures/date/{date}",
                f"/tennis/v2/{circuit}/fixtures/{date}",
                f"/tennis/v2/{circuit}/date-fixtures/{date}",
            ]

            for path in paths:
                data = api_get(path)

                if not isinstance(data, dict):
                    continue

                for m in data.get("data", []):
                    for key in ["player1", "player2"]:
                        p = m.get(key, {}) or {}
                        pname = p.get("name", "")

                        score = similarity(name, pname)

                        if is_same_player(name, pname) and score > best_score:
                            best_score = score
                            best = {
                                "id": p.get("id") or m.get(f"{key}Id"),
                                "name": pname,
                                "country": p.get("countryAcr", ""),
                                "circuit": circuit,
                            }

    return best


def find_player(name):
    player = find_player_in_recent_fixtures(name)
    if player:
        return player

    searched = search_player_name(name)
    if searched:
        player = find_player_in_recent_fixtures(searched["name"])
        if player:
            return player

    return None


def get_player_matches(player):
    circuit = player["circuit"]
    pid = player["id"]

    paths = [
        f"/tennis/v2/{circuit}/player/past-matches/{pid}",
        f"/tennis/v2/{circuit}/player/fixtures/{pid}",
        f"/tennis/v2/{circuit}/player/matches/{pid}",
    ]

    for path in paths:
        data = api_get(path)
        if isinstance(data, dict) and data.get("data"):
            return data.get("data", [])

    return []


def get_h2h(player1, player2):
    circuit = player1["circuit"]

    paths = [
        f"/tennis/v2/{circuit}/h2h/fixtures/{player1['id']}/{player2['id']}",
        f"/tennis/v2/{circuit}/h2h/{player1['id']}/{player2['id']}",
        f"/tennis/v2/{circuit}/fixtures/h2h/{player1['id']}/{player2['id']}",
    ]

    for path in paths:
        data = api_get(path)
        if isinstance(data, dict):
            return data.get("data", [])

    return []


def get_surface(circuit, tournament_id):
    if not tournament_id:
        return None

    paths = [
        f"/tennis/v2/{circuit}/tour/info/{tournament_id}",
        f"/tennis/v2/{circuit}/tournament/info/{tournament_id}",
        f"/tennis/v2/{circuit}/tournament/{tournament_id}",
    ]

    for path in paths:
        data = api_get(path)

        if not isinstance(data, dict):
            continue

        d = data.get("data", {})
        court = d.get("court", {})

        if isinstance(court, dict) and court.get("name"):
            return court.get("name")

    return None


def parse_games(result):
    if not result:
        return None

    r = result.lower()

    if "ret" in r or "walkover" in r or "w/o" in r:
        return None

    sets = re.findall(r"(\d+)-(\d+)", r)

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
        "games": games,
        "sets": len(sets),
        "tiebreaks": tiebreaks,
    }


def won(player, match):
    return str(match.get("match_winner")) == str(player["id"])


def analyze_player(player, matches):
    wins = 0
    losses = 0
    valid = 0
    games_total = 0
    over_22 = 0
    over_20 = 0
    long_matches = 0
    tiebreaks = 0

    for m in matches[:10]:
        if won(player, m):
            wins += 1
        else:
            losses += 1

        parsed = parse_games(m.get("result"))

        if parsed:
            valid += 1
            games_total += parsed["games"]

            if parsed["games"] >= 23:
                over_22 += 1

            if parsed["games"] >= 21:
                over_20 += 1

            if parsed["sets"] >= 3:
                long_matches += 1

            tiebreaks += parsed["tiebreaks"]

    avg_games = round(games_total / valid, 1) if valid else 0

    return {
        "wins": wins,
        "losses": losses,
        "valid": valid,
        "avg_games": avg_games,
        "over_22": over_22,
        "over_20": over_20,
        "long_matches": long_matches,
        "tiebreaks": tiebreaks,
    }


def analyze_h2h(p1, p2, matches):
    if not matches:
        return {
            "text": "🤝 H2H: nessun precedente diretto trovato.",
            "p1": 0,
            "p2": 0,
            "avg": 0,
        }

    p1_wins = 0
    p2_wins = 0
    total_games = 0
    valid = 0

    for m in matches[:10]:
        if str(m.get("match_winner")) == str(p1["id"]):
            p1_wins += 1
        elif str(m.get("match_winner")) == str(p2["id"]):
            p2_wins += 1

        parsed = parse_games(m.get("result"))
        if parsed:
            total_games += parsed["games"]
            valid += 1

    avg = round(total_games / valid, 1) if valid else 0

    return {
        "text": f"🤝 H2H: {p1['name']} {p1_wins} - {p2_wins} {p2['name']}",
        "p1": p1_wins,
        "p2": p2_wins,
        "avg": avg,
    }


def choose_favorite(p1, p2, a1, a2, h2h):
    s1 = a1["wins"] * 2 - a1["losses"] + h2h["p1"] * 2
    s2 = a2["wins"] * 2 - a2["losses"] + h2h["p2"] * 2

    if s1 >= s2 + 3:
        return p1["name"], s1, s2

    if s2 >= s1 + 3:
        return p2["name"], s1, s2

    return "Match equilibrato", s1, s2


def market_analysis(a1, a2, h2h):
    combined_avg = round((a1["avg_games"] + a2["avg_games"]) / 2, 1)

    if h2h["avg"]:
        combined_avg = round((combined_avg + h2h["avg"]) / 2, 1)

    over_score = a1["over_22"] + a2["over_22"]
    long_score = a1["long_matches"] + a2["long_matches"]
    tb_score = a1["tiebreaks"] + a2["tiebreaks"]

    if combined_avg >= 24 or over_score >= 9:
        over = "Over 22.5 games interessante"
    elif combined_avg >= 21 or over_score >= 5:
        over = "Over 20.5 / Over games valutabile"
    else:
        over = "Under games più prudente"

    if long_score >= 6:
        handicap = "Handicap positivo sullo sfavorito interessante"
    elif long_score >= 3:
        handicap = "Handicap possibile con prudenza"
    else:
        handicap = "Handicap non prioritario"

    if tb_score >= 4:
        ace = "Ace interessanti: segnali di set tirati/tiebreak"
    else:
        ace = "Ace non prioritari dai dati disponibili"

    doppi_falli = "Doppi falli: dati diretti non disponibili, lettura prudente"

    return combined_avg, over, handicap, ace, doppi_falli


def build_analysis(raw1, raw2):
    fixture_match = find_match_from_fixtures(raw1, raw2)

    if fixture_match:
        p1 = fixture_match["player1"]
        p2 = fixture_match["player2"]
        tournament_id = fixture_match.get("tournamentId")
        circuit = fixture_match["circuit"]
    else:
        p1 = find_player(raw1)
        p2 = find_player(raw2)

        if not p1 or not p2:
            return (
                "⚠️ Non riesco a trovare uno dei due giocatori.\n\n"
                "Prova così:\n"
                "/match Nome Cognome vs Nome Cognome\n\n"
                "Esempio:\n"
                "/match De Minaur vs Arnaldi"
            )

        tournament_id = None
        circuit = p1["circuit"]

    m1 = get_player_matches(p1)
    m2 = get_player_matches(p2)

    a1 = analyze_player(p1, m1)
    a2 = analyze_player(p2, m2)

    h2h_matches = get_h2h(p1, p2)
    h2h = analyze_h2h(p1, p2, h2h_matches)

    surface = get_surface(circuit, tournament_id)
    surface_text = surface if surface else "non rilevata"

    favorite, score1, score2 = choose_favorite(p1, p2, a1, a2, h2h)
    avg, over, handicap, ace, doppi_falli = market_analysis(a1, a2, h2h)

    return f"""
🎾 ANALISI TECNICA MATCH

📌 Match:
{p1['name']} ({p1['circuit'].upper()}) vs {p2['name']} ({p2['circuit'].upper()})

🌍 Paesi:
{p1.get('country', '')} vs {p2.get('country', '')}

🏟 Superficie:
{surface_text}

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

{h2h['text']}

🧠 Lettura tecnica:
- Media games combinata: {avg}
- Favorito tecnico: {favorite}
- Score interno: {p1['name']} {score1} / {p2['name']} {score2}

✅ Vittoria:
{favorite}

📈 Over/Under games:
{over}

📌 Handicap games:
{handicap}

🎾 Ace:
{ace}

⚠️ Doppi falli:
{doppi_falli}

⚠️ Nota:
Analisi basata su Tennis API. Le quote bookmaker non sono ancora collegate.
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
        "/match De Minaur vs Arnaldi"
    )


@bot.message_handler(commands=["match"])
def match(message):
    text = message.text.replace("/match", "").strip()

    if not text:
        bot.reply_to(message, "Scrivi così:\n/match De Minaur vs Arnaldi")
        return

    p1, p2 = split_players(text)

    if not p1 or not p2:
        bot.reply_to(message, "Scrivi usando VS:\n/match De Minaur vs Arnaldi")
        return

    bot.reply_to(message, "🔎 Cerco match e giocatori reali su ATP/WTA/ITF...")

    risposta = build_analysis(p1, p2)
    bot.reply_to(message, risposta)


if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{RENDER_URL}/{TELEGRAM_TOKEN}")

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
