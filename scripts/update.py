"""
Goleo - actualización diaria de datos.

Trae los partidos de ayer, hoy y mañana desde API-Football, calcula las
probabilidades con el modelo propio (Poisson) y escribe los archivos JSON
que lee la página (site/data/).

Uso:
  API_FOOTBALL_KEY=xxxx python scripts/update.py      -> datos reales
  python scripts/update.py --demo                     -> datos de ejemplo (sin clave)

Variables opcionales:
  MAX_CALLS   límite de consultas a la API por ejecución (por defecto 90)
"""
import json, math, os, random, sys, time, urllib.request, urllib.parse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
DATA = os.path.join(SITE, "data")
CACHE = os.path.join(ROOT, "cache")
TZ = ZoneInfo("America/Bogota")
API = "https://v3.football.api-sports.io"
KEY = os.environ.get("API_FOOTBALL_KEY", "").strip()
MAX_CALLS = int(os.environ.get("MAX_CALLS", "90"))
TEAM_CACHE_DAYS = 6
FINISHED = {"FT", "AET", "PEN"}

calls = 0


# ---------------------------------------------------------------- utilidades
def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def api(endpoint, **params):
    """Llama a API-Football. Devuelve la lista 'response' o None si no hay presupuesto."""
    global calls
    if calls >= MAX_CALLS:
        return None
    url = f"{API}/{endpoint}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"x-apisports-key": KEY})
    for intento in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                calls += 1
                body = json.loads(r.read().decode("utf-8"))
                restantes = r.headers.get("x-ratelimit-requests-remaining")
            break
        except Exception as e:  # red caída, 429, etc.
            print(f"  ! error en {endpoint} ({e}), reintento {intento + 1}")
            time.sleep(3 + intento * 5)
    else:
        return None
    if body.get("errors"):
        print(f"  ! API respondió con error en {endpoint}: {body['errors']}")
        return None
    if restantes is not None and int(restantes) <= 1:
        print("  ! Se acabaron las consultas del día en la API.")
        calls = MAX_CALLS
    time.sleep(0.4)  # respetar el límite por minuto
    return body.get("response")


def num(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


# -------------------------------------------------------------------- modelo
def pois(k, l):
    return math.exp(-l) * l ** k / math.factorial(k)


def shrink(value, n, prior, k=5):
    """Mezcla el promedio del equipo con el de la liga cuando hay pocos partidos."""
    w = n / (n + k)
    return w * value + (1 - w) * prior


def team_profile(stats):
    """Resume /teams/statistics en los números que usa el modelo."""
    fx = stats.get("fixtures", {}).get("played", {})
    g = stats.get("goals", {})
    gf, ga = g.get("for", {}).get("average", {}), g.get("against", {}).get("average", {})
    played = num(fx.get("total"))
    cards = 0.0
    for color in ("yellow", "red"):
        for bucket in (stats.get("cards", {}).get(color) or {}).values():
            cards += num((bucket or {}).get("total"))
    return {
        "n_home": num(fx.get("home")), "n_away": num(fx.get("away")), "n": played,
        "gf_home": num(gf.get("home")), "gf_away": num(gf.get("away")),
        "ga_home": num(ga.get("home")), "ga_away": num(ga.get("away")),
        "gf": num(gf.get("total")), "ga": num(ga.get("total")),
        "cards": cards / played if played else 0.0,
        "form": (stats.get("form") or "")[-5:],
    }


def predict(h, a):
    """Probabilidades del partido a partir de los perfiles de ambos equipos."""
    # goles esperados: ataque del local en casa vs defensa del visitante fuera
    lh = (shrink(h["gf_home"], h["n_home"], 1.45) + shrink(a["ga_away"], a["n_away"], 1.45)) / 2
    la = (shrink(a["gf_away"], a["n_away"], 1.10) + shrink(h["ga_home"], h["n_home"], 1.10)) / 2
    lh, la = max(lh, 0.2), max(la, 0.2)
    lc = shrink(h["cards"], h["n"], 2.3) + shrink(a["cards"], a["n"], 2.3)

    p1 = px = p2 = o15 = o25 = o35 = 0.0
    best = (0, 0, 0.0)
    for i in range(11):
        for j in range(11):
            p = pois(i, lh) * pois(j, la)
            if i > j: p1 += p
            elif i == j: px += p
            else: p2 += p
            if i + j >= 2: o15 += p
            if i + j >= 3: o25 += p
            if i + j >= 4: o35 += p
            if p > best[2]: best = (i, j, p)
    btts = (1 - math.exp(-lh)) * (1 - math.exp(-la))
    c35 = sum(pois(k, lc) for k in range(4, 25))
    c45 = sum(pois(k, lc) for k in range(5, 25))
    opts = [("1", p1), ("2", p2), ("+2.5", o25), ("-2.5", 1 - o25), ("AM", btts)]
    code, prob = max(opts, key=lambda o: o[1])
    r = lambda v: round(v, 3)
    return {
        "xg": [round(lh, 2), round(la, 2)], "cards": round(lc, 1),
        "p": {"1": r(p1), "x": r(px), "2": r(p2), "o15": r(o15), "o25": r(o25), "o35": r(o35),
              "btts": r(btts), "c35": r(c35), "c45": r(c45)},
        "likely": [best[0], best[1]], "pick": {"code": code, "prob": r(prob)},
    }


def consensus(m, h, a):
    """Cuántas de 3 fuentes apoyan el pick: modelo, predicción de la API, historial."""
    code, prob = m["pick"]["code"], m["pick"]["prob"]
    checks = {"modelo": prob >= 0.55, "api": False, "historial": False}
    ap = m.get("api")
    if ap:
        if code in ("1", "2"):
            best = max(("1", "x", "2"), key=lambda k: ap.get(k, 0))
            checks["api"] = best == code
        elif code in ("+2.5", "-2.5"):
            uo = ap.get("uo") or ""
            checks["api"] = uo.startswith(code[0])
        elif code == "AM":
            checks["api"] = (ap.get("uo") or "").startswith("+")
    wins = lambda f: f.count("W")
    if code == "1": checks["historial"] = wins(h["form"]) >= 3
    elif code == "2": checks["historial"] = wins(a["form"]) >= 3
    elif code == "+2.5": checks["historial"] = (h["gf"] + h["ga"] + a["gf"] + a["ga"]) / 2 >= 2.6
    elif code == "-2.5": checks["historial"] = (h["gf"] + h["ga"] + a["gf"] + a["ga"]) / 2 <= 2.4
    elif code == "AM": checks["historial"] = min(h["gf"], a["gf"]) >= 1.1 and min(h["ga"], a["ga"]) >= 1.0
    return checks


def grade(code, gh, ga):
    return {"1": gh > ga, "2": ga > gh, "+2.5": gh + ga >= 3,
            "-2.5": gh + ga <= 2, "AM": gh > 0 and ga > 0}.get(code)


# ------------------------------------------------------------------ fuentes
def fetch_fixtures(date, leagues):
    res = api("fixtures", date=date, timezone="America/Bogota")
    if res is None:
        return None
    out = []
    for f in res:
        if str(f["league"]["id"]) not in leagues:
            continue
        dt = datetime.fromisoformat(f["fixture"]["date"])
        out.append({
            "id": f["fixture"]["id"],
            "league": {"id": f["league"]["id"], "name": leagues[str(f["league"]["id"])]["name"],
                       "country": f["league"]["country"], "season": f["league"]["season"],
                       "logo": f["league"].get("logo")},
            "time": dt.astimezone(TZ).strftime("%H:%M"),
            "status": f["fixture"]["status"]["short"],
            "referee": f["fixture"].get("referee"),
            "home": {"id": f["teams"]["home"]["id"], "name": f["teams"]["home"]["name"], "logo": f["teams"]["home"]["logo"]},
            "away": {"id": f["teams"]["away"]["id"], "name": f["teams"]["away"]["name"], "logo": f["teams"]["away"]["logo"]},
            "score": [f["goals"]["home"], f["goals"]["away"]] if f["goals"]["home"] is not None else None,
        })
    return out


def team_stats(team_id, league_id, season, cache):
    key = f"{league_id}-{season}-{team_id}"
    c = cache.get(key)
    if c and (time.time() - c["t"]) < TEAM_CACHE_DAYS * 86400:
        return c["p"]
    res = api("teams/statistics", league=league_id, season=season, team=team_id)
    if not res:
        return c["p"] if c else None
    prof = team_profile(res)
    cache[key] = {"t": time.time(), "p": prof}
    return prof


def api_prediction(fixture_id):
    res = api("predictions", fixture=fixture_id)
    if not res:
        return None
    pr = res[0].get("predictions", {})
    pct = pr.get("percent", {}) or {}
    p = lambda s: num(str(s or "0").rstrip("%")) / 100
    return {"1": p(pct.get("home")), "x": p(pct.get("draw")), "2": p(pct.get("away")),
            "uo": pr.get("under_over"), "advice": pr.get("advice")}


# ------------------------------------------------------------------ proceso
def build_day(date, leagues, cache, predict_new=True):
    path = os.path.join(DATA, f"{date}.json")
    old = {m["id"]: m for m in load(path, {}).get("matches", [])}
    fixtures = fetch_fixtures(date, leagues)
    if fixtures is None:
        print(f"  sin presupuesto para {date}, se deja como estaba")
        return
    matches = []
    for f in fixtures:
        prev = old.get(f["id"])
        if prev and prev.get("p"):
            m = {**prev, "status": f["status"], "score": f["score"], "time": f["time"]}
        elif predict_new:
            season, lid = f["league"]["season"], f["league"]["id"]
            h = team_stats(f["home"]["id"], lid, season, cache)
            a = team_stats(f["away"]["id"], lid, season, cache)
            if not h or not a:
                print(f"  - sin estadísticas para {f['home']['name']} vs {f['away']['name']}")
                m = {**f}
            else:
                m = {**f, **predict(h, a)}
                m["home"]["form"], m["away"]["form"] = h["form"], a["form"]
                m["api"] = api_prediction(f["id"])
                m["checks"] = consensus(m, h, a)
                m["cons"] = sum(m["checks"].values())
        else:
            m = {**f}
        if m.get("pick") and m.get("score") and m["status"] in FINISHED:
            m["hit"] = grade(m["pick"]["code"], *m["score"])
        matches.append(m)
    matches.sort(key=lambda m: (m["league"]["name"], m["time"]))
    save(path, {"date": date, "updated": datetime.now(TZ).isoformat(timespec="minutes"), "matches": matches})
    print(f"  {date}: {len(matches)} partidos")


# --------------------------------------------------------------------- demo
DEMO_TEAMS = {
    "239": ["Atlético Nacional", "Junior", "Millonarios", "América de Cali", "Deportes Tolima", "Unión Magdalena", "Santa Fe", "Once Caldas"],
    "39": ["Arsenal", "Liverpool", "Manchester City", "Chelsea", "Newcastle", "Aston Villa", "Brentford", "Fulham"],
    "140": ["Real Madrid", "Barcelona", "Atlético Madrid", "Villarreal", "Getafe", "Osasuna"],
    "135": ["Inter", "Napoli", "Atalanta", "Lazio", "Bologna", "Torino"],
    "78": ["Bayern München", "Bayer Leverkusen", "Borussia Dortmund", "Stuttgart", "Mainz", "Augsburg"],
    "13": ["Flamengo", "River Plate", "Palmeiras", "Boca Juniors"],
}


def demo(leagues):
    rnd = random.Random(7)
    today = datetime.now(TZ).date()
    for off in (-1, 0, 1):
        date = (today + timedelta(days=off)).isoformat()
        matches, fid = [], 1000 * (off + 2)
        for lid, teams in DEMO_TEAMS.items():
            if lid not in leagues or rnd.random() < 0.25:
                continue
            t = teams[:]
            rnd.shuffle(t)
            for k in range(0, min(len(t), rnd.choice([2, 4, 6])), 2):
                fid += 1
                mk = lambda: {"n_home": 5, "n_away": 5, "n": 10, "gf_home": rnd.uniform(0.9, 2.4), "gf_away": rnd.uniform(0.6, 1.8),
                              "ga_home": rnd.uniform(0.6, 1.6), "ga_away": rnd.uniform(0.9, 2.0), "gf": rnd.uniform(0.8, 2.1),
                              "ga": rnd.uniform(0.7, 1.8), "cards": rnd.uniform(1.6, 3.0),
                              "form": "".join(rnd.choice("WWDL") for _ in range(5))}
                h, a = mk(), mk()
                m = {"id": fid, "league": {"id": int(lid), "name": leagues[lid]["name"], "country": leagues[lid]["country"]},
                     "time": f"{rnd.choice([7, 9, 11, 13, 14, 16, 18, 20])}:{rnd.choice(['00', '15', '30'])}".zfill(5),
                     "status": "FT" if off < 0 else "NS", "referee": None,
                     "home": {"name": t[k], "form": h["form"]}, "away": {"name": t[k + 1], "form": a["form"]}, "score": None}
                m.update(predict(h, a))
                m["api"] = {"1": m["p"]["1"] + rnd.uniform(-.1, .1), "x": m["p"]["x"], "2": m["p"]["2"], "uo": rnd.choice(["+2.5", "-2.5"])}
                m["checks"] = consensus(m, h, a)
                m["cons"] = sum(m["checks"].values())
                if off < 0:
                    m["score"] = [rnd.choice([0, 1, 1, 2, 2, 3]), rnd.choice([0, 0, 1, 1, 2])]
                    m["hit"] = grade(m["pick"]["code"], *m["score"])
                matches.append(m)
        matches.sort(key=lambda m: (m["league"]["name"], m["time"]))
        save(os.path.join(DATA, f"{date}.json"), {"date": date, "updated": datetime.now(TZ).isoformat(timespec="minutes"),
                                                  "demo": True, "matches": matches})
    write_index(today)
    print("Datos de ejemplo generados.")


def write_index(today):
    days = {"ayer": (today - timedelta(days=1)).isoformat(), "hoy": today.isoformat(), "manana": (today + timedelta(days=1)).isoformat()}
    save(os.path.join(DATA, "index.json"), {"updated": datetime.now(TZ).isoformat(timespec="minutes"), "days": days})
    # borrar archivos de más de 30 días para no llenar el repositorio
    limit = today - timedelta(days=30)
    for fn in os.listdir(DATA):
        try:
            if datetime.strptime(fn[:10], "%Y-%m-%d").date() < limit:
                os.remove(os.path.join(DATA, fn))
        except ValueError:
            pass


def main():
    config = load(os.path.join(SITE, "config.json"), {})
    leagues = {k: v for k, v in config.get("leagues", {}).items() if v.get("on")}
    if "--demo" in sys.argv or not KEY:
        if not KEY:
            print("No hay API_FOOTBALL_KEY: se generan datos de ejemplo.")
        return demo(leagues)
    cache_path = os.path.join(CACHE, "teams.json")
    cache = load(cache_path, {})
    today = datetime.now(TZ).date()
    print(f"Ligas activas: {', '.join(v['name'] for v in leagues.values())}")
    # hoy primero (lo más importante), luego mañana, y ayer solo para resultados
    build_day(today.isoformat(), leagues, cache)
    build_day((today + timedelta(days=1)).isoformat(), leagues, cache)
    build_day((today - timedelta(days=1)).isoformat(), leagues, cache, predict_new=False)
    save(cache_path, cache)
    write_index(today)
    print(f"Listo. Consultas usadas: {calls}/{MAX_CALLS}")


if __name__ == "__main__":
    main()
