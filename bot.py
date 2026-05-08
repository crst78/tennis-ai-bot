from flask import Flask, request
import telebot
import requests
import os
import re
import unicodedata
from datetime import datetime, timedelta
from difflib import SequenceMatcher

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

RAPIDAPI_HOST = "tennis-api-atp-wta-itf.p.rapidapi.com"
BASE_URL = f"https://{RAPIDAPI_HOST}"
RENDER_URL = "https://tennis-ai-bot-kbw4.onrender.com"

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

TOURS = ["atp", "wta", "itf"]


def api_get(path):
    headers = {
        "x-rapidapi-host": RAPIDAPI_HOST,
        "x-rapidapi-key": RAPIDAPI_KEY,
        "Content-Type": "application/json"
    }

    try:
        r = requests.get(BASE_URL + path, headers=headers, timeout=25)
        if r.status_code != 200:
            print("API ERROR", r.status_code, path, r.text[:200])
            return None
        return r.json()
    except Exception as e:
        print("REQUEST ERROR", path, e)
        return None


def clean(text):
    text = str(text or "").lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def similarity(a, b):
    return SequenceMatcher(None, clean(a), clean(b)).ratio()


def name_match(user_name, api_name):
    u = clean(user_name)
    a = clean(api_name)

    if not u or not a:
        return False

    if u == a or u in a:
        return True

    u_words = u.split()
    a_words = a.split()

    if u_words and u_words[-1] in a_words:
        return True

    return similarity(u, a) >= 0.68


def split_players(text):
    if " vs " not in text.lower():
        return None, None

    parts = re.split(r"\s+vs\s+", text.strip(), flags=re.IGNORECASE)

    if len(parts) != 2:
        return None, None

    return parts[0].strip(), parts[1].strip()


def get_fixtures(tour, date):
    data = api_get(f"/tennis/v2/{tour}/fixtures/{date}")

    if isinstance(data, dict):
        return data.get("data", [])

    return []


def find_match(player_a, player_b):
    today = datetime.utcnow().date()
    best = None
    best_score = 0
    best_reverse = False
    best_tour = None

    for tour in TOURS:
        for delta in range(-3, 15):
            date = (today + timedelta(days=delta)).strftime("%Y-%m-%d")
            fixtures = get_fixtures(tour, date)

            for m in fixtures:
                p1 = m.get("player1", {}) or {}
                p2 = m.get("player2", {}) or {}

                name1 = p1.get("name", "")
                name2 = p2.get("name", "")

                if "/" in name1 or "/" in name2:
                    continue

                direct = 0
                reverse = 0

                if name_match(player_a, name1) and name_match(player_b, name2):
                    direct = similarity(player_a, name1) + similarity(player_b, name2)

                if name_match(player_a, name2) and name_match(player_b, name1):
                    reverse = similarity(player_a, name2) + similarity(player_b, name1)

                score = max(direct, reverse)

                if score > best_score:
                    best = m
                    best_score = score
                    best_reverse = reverse > direct
                    best_tour = tour

    if not best or best_score < 1.05:
        return None

    p1_raw = best.get("player1", {}) or {}
    p2_raw = best.get("player2", {}) or {}

    p1 = {
        "id": p1_raw.get("id") or best.get("player1Id"),
        "name": p1_raw.get("name", ""),
        "country": p1_raw.get("countryAcr", ""),
        "tour": best_tour
    }

    p2 = {
        "id": p2_raw.get("id") or best.get("player2Id"),
        "name": p2_raw.get("name", ""),
        "country": p2_raw.get("countryAcr", ""),
        "tour": best_tour
    }

    if best_reverse:
        p1, p2 = p2, p1

    return {
        "match": best,
        "tour": best_tour,
        "player1": p1,
        "player2": p2,
        "tournamentId": best.get("tournamentId")
    }


def get_past_matches(player):
    data = api_get(f"/tennis/v2/{player['tour']}/player/past-matches/{player['id']}")

    if isinstance(data, dict):
        return data.get("data", [])

    return []


def get_h2h(p1, p2):
    data = api_get(f"/tennis/v2/{p1['tour']}/fixtures/h2h/{p1['id']}/{p2['id']}")

    if isinstance(data, dict):
        return data.get("data", [])

    return []


def get_match_stats(player):
    data = api_get(f"/tennis/v2/{player['tour']}/player/match-stats/{player['id']}")

    if isinstance(data, dict):
        return data.get("data", data)

    return {}


def get_surface_summary(player):
    data = api_get(f"/tennis/v2/{player['tour']}/player/surface-summary/{player['id']}")

    if isinstance(data, dict):
        return data.get("data", data)

    return {}


def parse_score(result):
    if not result:
        return None

    r = result.lower()

    if "ret" in r or "w/o" in r or "walkover" in r:
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
        "sets": len(sets),
        "games": games,
        "tiebreaks": tiebreaks
    }


def player_won(player, match):
    return str(match.get("match_winner")) == str(player["id"])


def analyze_recent(player, matches):
    wins = 0
    losses = 0
    valid = 0
    games_total = 0
    over_22 = 0
    over_20 = 0
    long_matches = 0
    tiebreaks = 0

    for m in matches[:10]:
        if m.get("match_winner") is None:
            continue

        if player_won(player, m):
            wins += 1
        else:
            losses += 1

        parsed = parse_score(m.get("result"))

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
        "tiebreaks": tiebreaks
    }


def analyze_h2h(p1, p2, matches):
    p1_wins = 0
    p2_wins = 0
    valid = 0
    games_total = 0

    for m in matches[:10]:
        if str(m.get("match_winner")) == str(p1["id"]):
            p1_wins += 1

        if str(m.get("match_winner")) == str(p2["id"]):
            p2_wins += 1

        parsed = parse_score(m.get("result"))

        if parsed:
            valid += 1
            games_total += parsed["games"]

    avg = round(games_total / valid, 1) if valid else 0

    return {
        "p1": p1_wins,
        "p2": p2_wins,
        "avg": avg
    }


def extract_numbers(obj, keywords):
    found = []

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                key = clean(k)
                if any(word in key for word in keywords):
                    if isinstance(v, (int, float)):
                        found.append(float(v))
                    elif isinstance(v, str):
                        nums = re.findall(r"\d+\.?\d*", v)
                        for n in nums:
                            found.append(float(n))
                walk(v)

        elif isinstance(x, list):
            for item in x:
                walk(item)

    walk(obj)
    return found


def stats_reading(stats):
    aces = extract_numbers(stats, ["ace"])
    dfs = extract_numbers(stats, ["double fault", "doublefault", "fault"])

    ace_avg = round(sum(aces) / len(aces), 1) if aces else None
    df_avg = round(sum(dfs) / len(dfs), 1) if dfs else None

    return ace_avg, df_avg


def surface_text(summary):
    raw = str(summary)

    surfaces = []

    for s in ["Hard", "Clay", "Grass", "Indoor"]:
        if s.lower() in raw.lower():
            surfaces.append(s)

    if not surfaces:
        return "Dati superficie non dettagliati"

    return ", ".join(surfaces)


def choose_favorite(p1, p2, a1, a2, h2h):
    s1 = a1["wins"] * 2 - a1["losses"] + h2h["p1"] * 2
    s2 = a2["wins"] * 2 - a2["losses"] + h2h["p2"] * 2

    if s1 >= s2 + 3:
        fav = p1["name"]
    elif s2 >= s1 + 3:
        fav = p2["name"]
    else:
        fav = "Match equilibrato"

    return fav, s1, s2


def market_reading(a1, a2, h2h, ace1, ace2, df1, df2):
    avg_games = round((a1["avg_games"] + a2["avg_games"]) / 2, 1)

    if h2h["avg"]:
        avg_games = round((avg_games + h2h["avg"]) / 2, 1)

    over_score = a1["over_22"] + a2["over_22"]
    long_score = a1["long_matches"] + a2["long_matches"]
    tb_score = a1["tiebreaks"] + a2["tiebreaks"]

    if avg_games >= 24 or over_score >= 9:
        over = "Over 22.5 games interessante"
    elif avg_games >= 21 or over_score >= 5:
        over = "Over 20.5 games valutabile"
    else:
        over = "Under games più prudente"

    if long_score >= 6:
        handicap = "Handicap positivo sullo sfavorito interessante"
    elif long_score >= 3:
        handicap = "Handicap possibile ma con prudenza"
    else:
        handicap = "Handicap non prioritario"

    if ace1 is not None or ace2 is not None:
        ace = f"Ace: {ace1 if ace1 is not None else 'N/D'} vs {ace2 if ace2 is not None else 'N/D'}"
    elif tb_score >= 4:
        ace = "Ace interessanti: segnali indiretti da tiebreak/set tirati"
    else:
        ace = "Ace non prioritari dai dati disponibili"

    if df1 is not None or df2 is not None:
        doppi = f"Doppi falli: {df1 if df1 is not None else 'N/D'} vs {df2 if df2 is not None else 'N/D'}"
    else:
        doppi = "Doppi falli: dati non presenti nella risposta API"

    return avg_games, over, handicap, ace, doppi


def build_analysis(raw1, raw2):
    found = find_match(raw1, raw2)

    if not found:
        return (
            "⚠️ Non riesco a trovare il match nei fixture ATP/WTA/ITF.\n\n"
            "Scrivi così:\n"
            "/match Nome Cognome vs Nome Cognome\n\n"
            "Esempio:\n"
            "/match Denis Shapovalov vs Mariano Navone"
        )

    p1 = found["player1"]
    p2 = found["player2"]

    m1 = get_past_matches(p1)
    m2 = get_past_matches(p2)

    a1 = analyze_recent(p1, m1)
    a2 = analyze_recent(p2, m2)

    h2h_matches = get_h2h(p1, p2)
    h2h = analyze_h2h(p1, p2, h2h_matches)

    stats1 = get_match_stats(p1)
    stats2 = get_match_stats(p2)

    ace1, df1 = stats_reading(stats1)
    ace2, df2 = stats_reading(stats2)

    surf1 = surface_text(get_surface_summary(p1))
    surf2 = surface_text(get_surface_summary(p2))

    fav, score1, score2 = choose_favorite(p1, p2, a1, a2, h2h)
    avg_games, over, handicap, ace, doppi = market_reading(a1, a2, h2h, ace1, ace2, df1, df2)

    confidence = abs(score1 - score2)

    if confidence >= 8:
        risk = "Basso/medio"
    elif confidence >= 4:
        risk = "Medio"
    else:
        risk = "Alto / match equilibrato"

    return f"""
🎾 ANALISI TECNICA MATCH

📌 Match:
{p1['name']} ({p1['tour'].upper()}) vs {p2['name']} ({p2['tour'].upper()})

🌍 Paesi:
{p1.get('country', '')} vs {p2.get('country', '')}

📊 Forma ultime 10 partite:

{p1['name']}
✅ Vittorie: {a1['wins']}
❌ Sconfitte: {a1['losses']}
🎯 Media games: {a1['avg_games']}
📈 Over 22.5: {a1['over_22']}/10
🔥 Match lunghi: {a1['long_matches']}/10
🎾 Tiebreak/set tirati: {a1['tiebreaks']}
🏟 Superfici dati: {surf1}

{p2['name']}
✅ Vittorie: {a2['wins']}
❌ Sconfitte: {a2['losses']}
🎯 Media games: {a2['avg_games']}
📈 Over 22.5: {a2['over_22']}/10
🔥 Match lunghi: {a2['long_matches']}/10
🎾 Tiebreak/set tirati: {a2['tiebreaks']}
🏟 Superfici dati: {surf2}

🤝 H2H:
{p1['name']} {h2h['p1']} - {h2h['p2']} {p2['name']}
Media games H2H: {h2h['avg']}

🧠 Lettura tecnica:
- Favorito tecnico: {fav}
- Score interno: {p1['name']} {score1} / {p2['name']} {score2}
- Rischio: {risk}

✅ Vittoria:
{fav}

📈 Over/Under games:
{over}
Media games combinata: {avg_games}

📌 Handicap games:
{handicap}

🎾 Ace:
{ace}

⚠️ Doppi falli:
{doppi}

⚠️ Nota:
Analisi tecnica basata su Tennis API. Non considera quote bookmaker.
"""


@app.route("/")
def home():
    return "Tennis AI Bot Online"


@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(request.get_data().decode("UTF-8"))
    bot.process_new_updates([update])
    return "OK", 200


@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(
        message,
        "🎾 Tennis AI Bot online!\n\n"
        "Scrivi così:\n"
        "/match Denis Shapovalov vs Mariano Navone"
    )


@bot.message_handler(commands=["match"])
def match(message):
    text = message.text.replace("/match", "").strip()

    p1, p2 = split_players(text)

    if not p1 or not p2:
        bot.reply_to(message, "Scrivi usando VS:\n/match Denis Shapovalov vs Mariano Navone")
        return

    bot.reply_to(message, "🔎 Analisi in corso con endpoint verificati...")

    answer = build_analysis(p1, p2)
    bot.reply_to(message, answer)


if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{RENDER_URL}/{TELEGRAM_TOKEN}")

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
