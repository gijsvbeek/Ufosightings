"""Exporteer ufo.db naar de statische bestanden die de site gebruikt.

  data/points.json          compact: alle gegeocodeerde meldingen (kaartpunten)
                            {"minYear","maxYear","shapes":[...],
                             "points":[[id,jaar,maand,dag,lat,lon,vormIdx,zonlengte*10,maanfase],...]}
  data/details/YYYYMM.json  details per maand (popup + lijstweergave):
                            {id:[dag,tijd,plaats,regio,land,vorm,uitleg,samenvatting]}
  data/slhist.json          meldingen per graad zonlengte (alle meldingen met datum)
  data/yearhist.json        {"min","max","counts":[...]} per jaar (alle meldingen met datum)
  data/showers.json         herberekende statistiek: zwerm-ratio's + p-waarden,
                            maanfase-chi-kwadraat, menselijke piekdagen

Gebruik:  python export.py
"""
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
DB_PATH = HERE / "ufo.db"
DATA = HERE.parent / "data"
MIN_Y, MAX_Y = 1900, 2026

# vormnamen normaliseren (NUFORC bevat tikfouten en synoniemen)
SHAPE_CANON = {
    "cirlce": "Circle", "circel": "Circle", "cirle": "Circle",
    "triangular": "Triangle", "changed": "Changing", "unknown": "Unknown",
    "other": "Other", "": "Unknown",
}
def canon_shape(s: str) -> str:
    key = (s or "").strip().lower()
    return SHAPE_CANON.get(key, (s or "Unknown").strip().capitalize()
                           if key else "Unknown")


def main():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    DATA.mkdir(exist_ok=True)
    (DATA / "details").mkdir(exist_ok=True)

    # --- vormen inventariseren ---
    shapes = {}
    def shape_idx(s):
        c = canon_shape(s)
        if c not in shapes:
            shapes[c] = len(shapes)
        return shapes[c]

    # --- punten + details ---
    points = []
    details = defaultdict(dict)
    rows = con.execute("""SELECT source_id, year, month, day, time, city, region,
                                 country, shape, summary, explanation,
                                 lat, lon, sun_lon, moon_phase
                          FROM sightings
                          WHERE year BETWEEN ? AND ? ORDER BY year, month, day""",
                       (MIN_Y, MAX_Y))
    n_all = n_geo = 0
    for r in rows:
        n_all += 1
        ym = f"{r['year']:04d}{r['month']:02d}"
        details[ym][r["source_id"]] = [
            r["day"], r["time"], r["city"], r["region"], r["country"],
            canon_shape(r["shape"]), r["explanation"], r["summary"],
        ]
        if r["lat"] is None:
            continue
        n_geo += 1
        points.append([
            r["source_id"], r["year"], r["month"], r["day"],
            round(r["lat"], 2), round(r["lon"], 2),
            shape_idx(r["shape"]),
            int(round(r["sun_lon"] * 10)), r["moon_phase"],
        ])

    shape_list = [s for s, _ in sorted(shapes.items(), key=lambda kv: kv[1])]
    out = {"minYear": MIN_Y, "maxYear": MAX_Y, "shapes": shape_list, "points": points}
    (DATA / "points.json").write_text(
        json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    for ym, d in details.items():
        (DATA / "details" / f"{ym}.json").write_text(
            json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # --- histogrammen over ALLE meldingen met datum (ook niet-gegeocodeerd) ---
    sl = [0] * 360
    for r in con.execute("SELECT CAST(sun_lon AS INT) d, COUNT(*) c FROM sightings "
                         "WHERE year BETWEEN ? AND ? GROUP BY 1", (MIN_Y, MAX_Y)):
        sl[min(r["d"], 359)] = r["c"]
    (DATA / "slhist.json").write_text(json.dumps(sl), encoding="utf-8")

    counts = [0] * (MAX_Y - MIN_Y + 1)
    for r in con.execute("SELECT year, COUNT(*) c FROM sightings "
                         "WHERE year BETWEEN ? AND ? GROUP BY 1", (MIN_Y, MAX_Y)):
        counts[r["year"] - MIN_Y] = r["c"]
    (DATA / "yearhist.json").write_text(
        json.dumps({"min": MIN_Y, "max": MAX_Y, "counts": counts}), encoding="utf-8")

    # --- zwermstatistiek herberekenen op de volledige nieuwe dataset ---
    write_showers(con, sl)

    mb = (DATA / "points.json").stat().st_size / 1e6
    print(f"punten: {n_geo}/{n_all} gegeocodeerd · points.json {mb:.1f} MB · "
          f"{len(details)} detailmaanden · vormen: {len(shape_list)}")


# ------------------------------------------------------------------ statistiek
WIN = 4  # venster ±4° zonlengte, zoals in de app

# piek-zonlengte + datumlabel per zwerm; kwalitatieve noten blijven redactioneel
SHOWERS = [
    ("Quadrantiden",  283.2, "3 jan",  "overlapt met de jaarwisseling: vuurwerk vertekent dit venster"),
    ("Lyriden",        32.3, "22 apr", None),
    ("η-Aquariiden",   45.5, "6 mei",  None),
    ("δ-Aquariiden",  127.0, "30 jul", None),
    ("Perseïden",     140.0, "12 aug", "historisch de meest robuuste piek in de meldingen"),
    ("Orioniden",     208.0, "21 okt", None),
    ("Z-Tauriden",    223.0, "5 nov",  None),
    ("Leoniden",      235.3, "17 nov", "topjaar 1999 — het jaar van de Leonidenstorm"),
    ("Geminiden",     262.2, "14 dec", None),
]

def circ(a, b):
    return min(abs(a - b), 360 - abs(a - b))

def binom_window(sl_hist, center):
    """Zelfde toets als de app: venster ±WIN° vs baseline ring 5–15°."""
    w = b = 0
    for d in range(360):
        c = circ(d + 0.5, center)
        if c <= WIN:
            w += sl_hist[d]
        elif WIN + 1 <= c <= 15:
            b += sl_hist[d]
    wd, bd = 2 * WIN + 1, 2 * (15 - WIN)
    tot, p0 = w + b, (2 * WIN + 1) / (2 * WIN + 1 + 2 * (15 - WIN))
    if tot == 0:
        return 1.0, 1.0
    z = (w - tot * p0) / math.sqrt(tot * p0 * (1 - p0))
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    ratio = (w / wd) / (b / bd) if b else float("inf")
    return ratio, p

def fmt_p(p):
    return "< 0,001" if p < 0.001 else f"{p:.3f}".replace(".", ",")

def write_showers(con, sl_hist):
    alpha = 0.05 / len(SHOWERS)  # Bonferroni
    showers = []
    for name, sl_peak, dat, note in SHOWERS:
        ratio, p = binom_window(sl_hist, sl_peak)
        showers.append({"n": name, "sl": sl_peak, "dat": dat,
                        "ratio": round(ratio, 2), "p": fmt_p(p),
                        "sig": bool(p < alpha), **({"note": note} if note else {})})

    # maanfase: chi-kwadraat over 8 gelijke bakken
    obs = [0] * 8
    for r in con.execute("SELECT moon_phase, COUNT(*) FROM sightings "
                         "WHERE year BETWEEN ? AND ? GROUP BY 1", (MIN_Y, MAX_Y)):
        obs[r[0]] = r[1]
    tot = sum(obs)
    exp = tot / 8
    chi2 = sum((o - exp) ** 2 / exp for o in obs)
    moon = {"chi2": round(chi2, 1), "sig": bool(chi2 > 24.32),  # p<0,001 bij df=7
            "peakPhase": max(range(8), key=lambda i: obs[i])}

    # menselijke piekdagen: factor t.o.v. een gemiddelde dag
    per_day = {(r[0], r[1]): r[2] for r in con.execute(
        "SELECT month, day, COUNT(*) FROM sightings WHERE year BETWEEN ? AND ? "
        "GROUP BY 1,2", (MIN_Y, MAX_Y))}
    avg = sum(per_day.values()) / 365.25
    def factor(mo, d):
        return round(per_day.get((mo, d), 0) / avg, 1)
    human = [
        {"n": "4 juli (VS): vuurwerk", "sl": 102.7,
         "x": f"4 jul is {str(factor(7, 4)).replace('.', ',')}× een gemiddelde dag"},
        {"n": "jaarwisseling: vuurwerk & wensballonnen", "sl": 280.5,
         "x": f"1 jan is {str(factor(1, 1)).replace('.', ',')}× een gemiddelde dag"},
    ]
    (DATA / "showers.json").write_text(
        json.dumps({"showers": showers, "moon": moon, "human": human, "total": tot},
                   ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    main()
