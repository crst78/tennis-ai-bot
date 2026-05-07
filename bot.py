from flask import Flask, request
import telebot
import requests
import os
import re
import unicodedata
from difflib import SequenceMatcher

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

RAPIDAPI_HOST = "tennis-api-atp-wta-itf.p.rapidapi.com"
BASE_URL = f"https://{RAPIDAPI_HOST}"
RENDER_URL = "https://tennis-ai-bot-kbw4.onrender.com"

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

CIRCUITS = ["atp", "wta", "itf"]

KNOWN_PLAYERS = {
    "djokovic": {"id": 5992, "name": "Novak Djokovic", "country": "SRB", "circuit": "atp"},
    "sinner": {"id": 47275, "name": "Jannik Sinner", "country": "ITA", "circuit": "atp"},
    "alcaraz": {"id": 68074, "name": "Carlos Alcaraz", "country": "ESP", "circuit": "atp"},
    "zverev": {"id": 41830, "name": "Alexander Zverev", "country": "GER", "circuit": "atp"},
    "medvedev": {"id": 10633, "name": "Daniil Medvedev", "country": "RUS", "circuit": "atp"},
    "rublev": {"id": 25332, "name": "Andrey Rublev", "country": "RUS", "circuit": "atp"},
    "musetti": {"id": 63572, "name": "Lorenzo Musetti", "country": "ITA", "circuit": "atp"},
    "draper": {"id": 63017, "name": "Jack Draper", "country": "GBR", "circuit": "atp"},
    "medjedovic": {"id": 63770, "name": "Hamad Medjedovic", "country": "SRB", "circuit": "atp"},
    "royer": {"id": 61604, "name": "Valentin Royer", "country": "FRA", "circuit": "atp"},
    "sonego": {"id": 17624, "name": "Lorenzo Sonego", "country": "ITA", "circuit": "atp"},
    "andreeva": {"id": 112742, "name": "Mirra Andreeva", "country": "RUS", "circuit": "wta"},
    "sabalenka": {"id": 47388, "name": "Aryna Sabalenka", "country": "BLR", "circuit": "wta"},
    "paolini": {"id": 54853, "name": "Jasmine Paolini", "country": "ITA", "circuit": "wta"},
}

def clean_text(text):
    text = text.lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]", "", text)

def api_get(path):
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
    }
    try:
        r = requests.get(BASE_URL + path, headers=headers, timeout=25)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None

def similarity(a, b):
    return SequenceMatcher(None, clean_text(a), clean_text(b)).ratio()

def get_players(circuit):
    data = api_get(f"/tennis/v2/{circuit}/player/")
    if isinstance(data, dict):
        return data.get("data", [])
    return []

def find_player(name):
    query = clean_text(name)

    if query in KNOWN_PLAYERS:
        return KNOWN_PLAYERS[query]

    best = None
    best_score = 0

    for circuit in CIRCUITS:
        players = get_players(circuit)

        for p in players:
            pname = p.get("name", "")
            if not pname:
                continue

            pname_clean = clean_text(pname)

            if query == pname_clean or query in pname_clean or pname_clean in query:
                return {
                    "id": p.get("id"),
                    "name": pname,
                    "country": p.get("countryAcr", ""),
                    "circuit": circuit,
                }

            score = similarity(query, pname_clean)
            if score > best_score:
                best_score = score
                best = {
                    "id": p.get("id"),
                    "name": pname,
                    "country": p.get("countryAcr", ""),
                    "circuit": circuit,
                }

    if best_score >= 0.62:
        return best

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
        f"/tennis/v2/{circuit}/h2h/{player1['id']}/{player2['id']}",
        f"/tennis/v2/{circuit}/fixtures/h2h/{player1['id']}/{player2['id']}",
        f"/tennis/v2/{circuit}/h2h/fixtures/{player1['id']}/{player2['id']}",
    ]

    for path in paths:
        data = api_get(path)
        if isinstance(data, dict):
            return data.get("data", [])

    return []

def get_tournament_surface(circuit, tournament_id):
    if not tournament_id:
        return None

    paths = [
        f"/tennis/v2/{circuit}/tour/info/{tournament_id}",
        f"/tennis/v2/{circuit}/tournament/info/{tournament_id}",
        f"/tennis/v2/{circuit}/tournament/{tournament_id}",
    ]

    for path in paths:
        data = api_get(path)
        if isinstance(data, dict):
            d = data.get("data", {})
            court = d.get("court", {})
            if isinstance(court, dict):
                return court.get("name")
            if d.get("courtName"):
                return d.get("courtName")

    return None

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
    tiebreaks = 0

    for a, b in sets:
        a = int(a)
        b = int(b)
        total_games += a + b
        if a == 7 or b == 7:
            tiebreaks += 1

    return {
        "sets": len(sets),
        "games": total_games,
        "tiebreaks": tiebreaks,
    }

def player_won_match(player, match):
    winner = match.get("match_winner")
    if winner is None:
        return False
    return str(winner) == str(player["id"])

def analyze_player(player, matches, wanted_surface=None):
    wins = 0
    losses = 0
    valid = 0
    total_games = 0
    over_22 = 0
    over_20 = 0
    long_matches = 0
    tiebreaks = 0
    same_surface_matches = 0

    selected = matches[:10]

    for m in selected:
        if player_won_match(player, m):
            wins += 1
        else:
            losses += 1

        parsed = parse_games(m.get("result"))
        if parsed:
            valid += 1
            total_games += parsed["games"]

            if parsed["games"] >= 23:
                over_22 += 1
            if parsed["games"] >= 21:
                over_20 += 1
            if parsed["sets"] >= 3:
                long_matches += 1
            tiebreaks += parsed["tiebreaks"]

        court_name = ""
        tournament = m.get("tournament", {})
        if isinstance(tournament, dict):
            court = tournament.get("court", {})
            if isinstance(court, dict):
                court_name = court.get("name", "")

        if wanted_surface and court_name and clean_text(court_name) == clean_text(wanted_surface):
            same_surface_matches += 1

    avg_games = round(total_games / valid, 1) if valid else 0

    return {
        "wins": wins,
        "losses": losses,
        "valid": valid,
        "avg_games": avg_games,
        "over_22": over_22,
        "over_20": over_20,
        "long_matches": long_matches,
        "tiebreaks": tiebreaks,
        "same_surface_matches": same_surface_matches,
    }

def analyze_h2h(player1, player2, h2h):
    if not h2h:
        return {
            "text": "🤝 H2H: nessun precedente diretto trovato.",
            "p1_wins": 0,
            "p2_wins": 0,
            "avg_games": 0,
        }

    p1_wins = 0
    p2_wins = 0
    total_games = 0
    valid = 0

    for m in h2h[:10]:
        if str(m.get("match_winner")) == str(player1["id"]):
            p1_wins += 1
        elif str(m.get("match_winner")) == str(player2["id"]):
            p2_wins += 1

        parsed = parse_games(m.get("result"))
        if parsed:
            valid += 1
            total_games += parsed["games"]

    avg = round(total_games / valid, 1) if valid else 0

    return {
        "text": f"🤝 H2H: {player1['name']} {p1_wins} - {p2_wins} {player2['name']}",
        "p1_wins": p1_wins,
        "p2_wins": p2_wins,
        "avg_games": avg,
    }

def choose_favorite(p1, p2, a1, a2, h2h):
    score1 = 0
    score2 = 0

    score1 += a1["wins"] * 2
    score2 += a2["wins"] * 2

    score1 -= a1["losses"]
    score2 -= a2["losses"]

    score1 += h2h["p1_wins"] * 2
    score2 += h2h["p2_wins"] * 2

    if score1 > score2 + 2:
        return p1["name"], score1, score2
    if score2 > score1 + 2:
        return p2["name"], score1, score2

    return "Match equilibrato", score1, score2

def betting_reading(a1, a2, h2h):
    combined_avg = round((a1["avg_games"] + a2["avg_games"]) / 2, 1)

    over_score = a1["over_22"] + a2["over_22"]
    long_score = a1["long_matches"] + a2["long_matches"]
    tie_score = a1["tiebreaks"] + a2["tiebreaks"]

    if h2h["avg_games"]:
        combined_avg = round((combined_avg + h2h["avg_games"]) / 2, 1)

    if combined_avg >= 24 or over_score >= 10:
        over = "Over 22.5 games interessante"
    elif combined_avg >= 21 or over_score >= 6:
        over = "Over 20.5 / Over games valutabile"
    else:
        over = "Under games più prudente"

    if long_score >= 7:
        handicap = "Handicap positivo sullo sfavorito interessante"
    elif long_score >= 4:
        handicap = "Handicap possibile ma con prudenza"
    else:
        handicap = "Handicap non prioritario"

    if tie_score >= 4:
        ace = "Ace potenzialmente interessanti: match con servizi/tiebreak"
    else:
        ace = "Ace non prioritari dai dati disponibili"

    doppi_falli = "Doppi falli: dati reali non disponibili, valutazione prudente"

    return combined_avg, over, handicap, ace, doppi_falli

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
            "Oppure prova con nome e cognome completo."
        )

    m1 = get_player_matches(p1)
    m2 = get_player_matches(p2)

    tournament_id = None
    if m1:
        tournament_id = m1[0].get("tournamentId")
    elif m2:
        tournament_id = m2[0].get("tournamentId")

    surface = get_tournament_surface(p1["circuit"], tournament_id)

    a1 = analyze_player(p1, m1, surface)
    a2 = analyze_player(p2, m2, surface)

    h2h_matches = get_h2h(p1, p2)
    h2h = analyze_h2h(p1, p2, h2h_matches)

    favorite, score1, score2 = choose_favorite(p1, p2, a1, a2, h2h)
    combined_avg, over, handicap, ace, doppi_falli = betting_reading(a1, a2, h2h)

    surface_text = surface if surface else "non rilevata"

    return f"""
🎾 ANALISI TECNICA MATCH

📌 Match:
{p1['name']} ({p1['circuit'].upper()}) vs {p2['name']} ({p2['circuit'].upper()})

🌍 Paesi:
{p1.get('country', '')} vs {p2.get('country', '')}

🏟 Superficie:
{surface_text}

📊 Ultime partite disponibili:

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
- Media games combinata: {combined_avg}
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
Analisi basata su dati reali Tennis API.
Le quote bookmaker non sono ancora collegate.
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
