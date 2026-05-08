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
        "Content-Type": "application/json",
    }

    try:
        r = requests.get(BASE_URL + path, headers=headers, timeout=25)
        print("API:", r.status_code, path)

        if r.status_code != 200:
            print("API ERROR:", r.text[:300])
            return None

        return r.json()
    except Exception as e:
        print("REQUEST ERROR:", path, e)
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

    return similarity(u, a) >= 0.66


def split_players(text):
    parts = re.split(r"\s+vs\s+", text.strip(), flags=re.IGNORECASE)

    if len(parts) != 2:
        return None, None

    return parts[0].strip(), parts[1].strip()


def send_long(chat_id, text):
    max_len = 3900
    for i in range(0, len(text), max_len):
        bot.send_message(chat_id, text[i:i + max_len])


def search_player_name(name):
    data = api_get(f"/tennis/v2/search?search={requests.utils.quote(name)}")

    if not isinstance(data, dict):
        return None

    best = None
    best_score = 0

    for group in data.get("data", []):
        category = str(group.get("category", "")).lower()

        if not category.startswith("player_"):
            continue

        tour = category.replace("player_", "")

        for p in group.get("result", []):
            pname = p.get("name", "")
            score = similarity(name, pname)

            if name_match(name, pname) and score > best_score:
                best_score = score
                best = {
                    "name": pname,
                    "country": p.get("countryAcr", ""),
                    "tour": tour,
                    "id": p.get("id"),
                }

    return best


def get_fixtures(tour, date):
    data = api_get(f"/tennis/v2/{tour}/fixtures/{date}")

    if isinstance(data, dict) and isinstance(data.get("data"), list):
        return data["data"]

    return []


def fixture_score(input_a, input_b, api_p1, api_p2):
    p1 = api_p1.get("name", "")
    p2 = api_p2.get("name", "")

    direct = 0
    reverse = 0

    if name_match(input_a, p1) and name_match(input_b, p2):
        direct = similarity(input_a, p1) + similarity(input_b, p2)

    if name_match(input_a, p2) and name_match(input_b, p1):
        reverse = similarity(input_a, p2) + similarity(input_b, p1)

    if reverse > direct:
        return reverse, True

    return direct, False


def find_match_in_fixtures(player_a, player_b):
    today = datetime.utcnow().date()

    best_match = None
    best_score = 0
    best_tour = None
    best_reverse = False

    for tour in TOURS:
        for delta in range(-10, 46):
            date = (today + timedelta(days=delta)).strftime("%Y-%m-%d")
            fixtures = get_fixtures(tour, date)

            for match in fixtures:
                p1 = match.get("player1", {}) or {}
                p2 = match.get("player2", {}) or {}

                name1 = p1.get("name", "")
                name2 = p2.get("name", "")

                if not name1 or not name2:
                    continue

                if "/" in name1 or "/" in name2:
                    continue

                score, reverse = fixture_score(player_a, player_b, p1, p2)

                if score > best_score:
                    best_score = score
                    best_match = match
                    best_tour = tour
                    best_reverse = reverse

    if not best_match or best_score < 1.05:
        return None

    raw1 = best_match.get("player1", {}) or {}
    raw2 = best_match.get("player2", {}) or {}

    p1 = {
        "id": raw1.get("id") or best_match.get("player1Id"),
        "name": raw1.get("name", ""),
        "country": raw1.get("countryAcr", ""),
        "tour": best_tour,
    }

    p2 = {
        "id": raw2.get("id") or best_match.get("player2Id"),
        "name": raw2.get("name", ""),
        "country": raw2.get("countryAcr", ""),
        "tour": best_tour,
    }

    if best_reverse:
        p1, p2 = p2, p1

    return {
        "match": best_match,
        "tour": best_tour,
        "player1": p1,
        "player2": p2,
        "tournamentId": best_match.get("tournamentId"),
        "date": best_match.get("date", ""),
    }


def get_past_matches(player):
    data = api_get(f"/tennis/v2/{player['tour']}/player/past-matches/{player['id']}")

    if isinstance(data, dict) and isinstance(data.get("data"), list):
        return data["data"]

    return []


def get_h2h(p1, p2):
    data = api_get(f"/tennis/v2/{p1['tour']}/fixtures/h2h/{p1['id']}/{p2['id']}")

    if isinstance(data, dict) and isinstance(data.get("data"), list):
        return data["data"]

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

    result = str(result).lower()

    if "ret" in result or "w/o" in result or "walkover" in result:
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
        "games": games,
        "sets": len(sets),
        "tiebreaks": tiebreaks,
    }


def player_won(player, match):
    winner = match.get("match_winner") or match.get("winnerId") or match.get("winner_id")
    return str(winner) == str(player["id"])


def analyze_recent(player, matches):
    wins = 0
    losses = 0
    valid_scores = 0
    games_total = 0
    over_22 = 0
    over_20 = 0
    long_matches = 0
    tiebreaks = 0

    for match in matches[:10]:
        winner = match.get("match_winner") or match.get("winnerId") or match.get("winner_id")

        if winner is not None:
            if player_won(player, match):
                wins += 1
            else:
                losses += 1

        parsed = parse_score(match.get("result"))

        if parsed:
            valid_scores += 1
            games_total += parsed["games"]

            if parsed["games"] >= 23:
                over_22 += 1

            if parsed["games"] >= 21:
                over_20 += 1

            if parsed["sets"] >= 3:
                long_matches += 1

            tiebreaks += parsed["tiebreaks"]

    avg_games = round(games_total / valid_scores, 1) if valid_scores else 0

    return {
        "wins": wins,
        "losses": losses,
        "avg_games": avg_games,
        "over_22": over_22,
        "over_20": over_20,
        "long_matches": long_matches,
        "tiebreaks": tiebreaks,
    }


def analyze_h2h(p1, p2, matches):
    p1_wins = 0
    p2_wins = 0
    valid = 0
    games_total = 0

    for match in matches[:10]:
        winner = match.get("match_winner") or match.get("winnerId") or match.get("winner_id")

        if str(winner) == str(p1["id"]):
            p1_wins += 1

        if str(winner) == str(p2["id"]):
            p2_wins += 1

        parsed = parse_score(match.get("result"))

        if parsed:
            valid += 1
            games_total += parsed["games"]

    avg = round(games_total / valid, 1) if valid else 0

    return {
        "p1": p1_wins,
        "p2": p2_wins,
        "avg": avg,
        "count": len(matches),
    }


def extract_numbers(obj, keywords):
    values = []

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                key = clean(k)

                if any(word in key for word in keywords):
                    if isinstance(v, (int, float)):
                        values.append(float(v))

                    elif isinstance(v, str):
                        for n in re.findall(r"\d+\.?\d*", v):
                            values.append(float(n))

                walk(v)

        elif isinstance(x, list):
            for item in x:
                walk(item)

    walk(obj)
    return values


def stat_average(stats, keywords):
    nums = extract_numbers(stats, keywords)
    return round(sum(nums) / len(nums), 1) if nums else None


def surface_reading(summary):
    text = str(summary).lower()
    found = []

    for s in ["hard", "clay", "grass", "indoor"]:
        if s in text:
            found.append(s.capitalize())

    return ", ".join(found) if found else "Dati superficie disponibili ma non leggibili nel formato API"


def choose_favorite(p1, p2, a1, a2, h2h):
    s1 = a1["wins"] * 2 - a1["losses"] + h2h["p1"] * 2
    s2 = a2["wins"] * 2 - a2["losses"] + h2h["p2"] * 2

    if s1 >= s2 + 4:
        fav = p1["name"]
    elif s2 >= s1 + 4:
        fav = p2["name"]
    else:
        fav = "Match equilibrato"

    return fav, s1, s2


def market_analysis(a1, a2, h2h, ace1, ace2, df1, df2):
    combined_avg = round((a1["avg_games"] + a2["avg_games"]) / 2, 1)

    if h2h["avg"]:
        combined_avg = round((combined_avg + h2h["avg"]) / 2, 1)

    over_score = a1["over_22"] + a2["over_22"]
    long_score = a1["long_matches"] + a2["long_matches"]
    tb_score = a1["tiebreaks"] + a2["tiebreaks"]

    if combined_avg >= 24 or over_score >= 9:
        over = "Over 22.5 games interessante"
    elif combined_avg >= 21 or over_score >= 5:
        over = "Over 20.5 games valutabile"
    else:
        over = "Under games più prudente"

    if long_score >= 6:
        handicap = "Handicap positivo sullo sfavorito interessante"
    elif long_score >= 3:
        handicap = "Handicap possibile, ma con prudenza"
    else:
        handicap = "Handicap non prioritario"

    if ace1 is not None or ace2 is not None:
        ace = f"{ace1 if ace1 is not None else 'N/D'} vs {ace2 if ace2 is not None else 'N/D'}"
    elif tb_score >= 4:
        ace = "Possibili ace/tiebreak: dati indiretti positivi"
    else:
        ace = "Ace non prioritari dai dati disponibili"

    if df1 is not None or df2 is not None:
        doppi = f"{df1 if df1 is not None else 'N/D'} vs {df2 if df2 is not None else 'N/D'}"
    else:
        doppi = "Dati doppi falli non presenti o non leggibili nella risposta API"

    return combined_avg, over, handicap, ace, doppi


def build_analysis(raw1, raw2):
    found = find_match_in_fixtures(raw1, raw2)

    if not found:
        s1 = search_player_name(raw1)
        s2 = search_player_name(raw2)

        extra = ""

        if s1 or s2:
            extra = "\n\n🔎 Nomi trovati da search:\n"
            if s1:
                extra += f"- {raw1} → {s1['name']} ({s1['tour'].upper()})\n"
            if s2:
                extra += f"- {raw2} → {s2['name']} ({s2['tour'].upper()})\n"

        return (
            "⚠️ Non trovo questo match nei fixture dell’API nei prossimi 45 giorni.\n\n"
            "Posso analizzare solo match presenti nei fixture, perché l’endpoint `search` "
            "trova il nome ma non fornisce l’ID numerico necessario per statistiche, H2H e superficie."
            f"{extra}\n"
            "Prova con un match presente nel calendario API."
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

    ace1 = stat_average(stats1, ["ace"])
    ace2 = stat_average(stats2, ["ace"])

    df1 = stat_average(stats1, ["double fault", "doublefault"])
    df2 = stat_average(stats2, ["double fault", "doublefault"])

    surf1 = surface_reading(get_surface_summary(p1))
    surf2 = surface_reading(get_surface_summary(p2))

    fav, score1, score2 = choose_favorite(p1, p2, a1, a2, h2h)
    avg_games, over, handicap, ace, doppi = market_analysis(a1, a2, h2h, ace1, ace2, df1, df2)

    risk_gap = abs(score1 - score2)

    if risk_gap >= 8:
        risk = "Basso/medio"
    elif risk_gap >= 4:
        risk = "Medio"
    else:
        risk = "Alto / match equilibrato"

    return f"""
🎾 ANALISI TECNICA MATCH

📌 Match:
{p1['name']} ({p1['tour'].upper()}) vs {p2['name']} ({p2['tour'].upper()})

📅 Data fixture:
{found.get('date')}

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
🏟 Superficie summary: {surf1}

{p2['name']}
✅ Vittorie: {a2['wins']}
❌ Sconfitte: {a2['losses']}
🎯 Media games: {a2['avg_games']}
📈 Over 22.5: {a2['over_22']}/10
🔥 Match lunghi: {a2['long_matches']}/10
🎾 Tiebreak/set tirati: {a2['tiebreaks']}
🏟 Superficie summary: {surf2}

🤝 H2H:
{p1['name']} {h2h['p1']} - {h2h['p2']} {p2['name']}
Precedenti trovati: {h2h['count']}
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
Analisi basata sugli endpoint reali RapidAPI forniti.
Non include quote bookmaker.
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
        "/match Nome Cognome vs Nome Cognome"
    )


@bot.message_handler(commands=["match"])
def match(message):
    text = message.text.replace("/match", "").strip()

    p1, p2 = split_players(text)

    if not p1 or not p2:
        bot.reply_to(message, "Scrivi usando VS:\n/match Nome Cognome vs Nome Cognome")
        return

    bot.reply_to(message, "🔎 Analisi in corso con endpoint verificati...")

    answer = build_analysis(p1, p2)
    send_long(message.chat.id, answer)


if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{RENDER_URL}/{TELEGRAM_TOKEN}")

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
