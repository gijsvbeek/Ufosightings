"""Bouw de SQLite-ingestlaag uit de raw NUFORC-scrape.

  raw/*.json  →  ufo.db (tabel sightings)

Stappen: parsen, ontdubbelen op NUFORC-id, geocoderen via GeoNames (cities500),
zonlengte + maanfase berekenen. Hervatbaar en idempotent: de tabel wordt per run
opnieuw opgebouwd uit alle aanwezige raw-bestanden.

Gebruik:  python build_db.py
"""
import html
import json
import math
import re
import sqlite3
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
RAW_DIR = HERE / "raw"
GEO_DIR = HERE / "geonames"
DB_PATH = HERE / "ufo.db"

# ---------------------------------------------------------------- normalisatie
def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")

def norm_city(s: str) -> str:
    s = re.sub(r"\(.*?\)", " ", s)          # "(west of)" e.d. weg
    s = s.split("/")[0].split(",")[0]        # "A/B" of "A, B" -> A
    s = strip_accents(s.lower())
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\b(st|ste)\b\.?", "saint", s)
    return re.sub(r"\s+", " ", s).strip()

def norm_plain(s: str) -> str:
    return re.sub(r"\s+", " ", strip_accents(s.lower())).strip()

# NUFORC-landnamen die afwijken van countryInfo.txt
COUNTRY_ALIAS = {
    "usa": "US", "united states": "US", "united states of america": "US",
    "uk": "GB", "united kingdom": "GB", "england": "GB", "scotland": "GB",
    "wales": "GB", "northern ireland": "GB", "great britain": "GB",
    "viet nam": "VN", "vietnam": "VN", "south korea": "KR", "north korea": "KP",
    "republic of korea": "KR", "korea": "KR",
    "russian federation": "RU", "russia": "RU",
    "iran": "IR", "syria": "SY", "czech republic": "CZ", "czechia": "CZ",
    "the netherlands": "NL", "netherlands": "NL", "holland": "NL",
    "bolivia": "BO", "venezuela": "VE", "tanzania": "TZ", "moldova": "MD",
    "macedonia": "MK", "north macedonia": "MK", "laos": "LA", "brunei": "BN",
    "cape verde": "CV", "ivory coast": "CI", "cote d ivoire": "CI",
    "democratic republic of the congo": "CD", "republic of the congo": "CG",
    "congo": "CD", "burma": "MM", "myanmar": "MM", "palestine": "PS",
    "east timor": "TL", "swaziland": "SZ", "eswatini": "SZ",
    "turkey": "TR", "turkiye": "TR", "taiwan": "TW", "hong kong": "HK",
    "puerto rico": "PR", "virgin islands": "VI", "us virgin islands": "VI",
    "trinidad": "TT", "trinidad and tobago": "TT", "tobago": "TT",
    "bahamas": "BS", "the bahamas": "BS", "gambia": "GM",
    "vatican city": "VA", "slovak republic": "SK",
    # historische / afwijkende benamingen
    "korea south": "KR", "korea north": "KP", "netherlands the": "NL",
    "west germany": "DE", "east germany": "DE", "yugoslavia": "RS",
    "czechoslovakia": "CZ", "ussr": "RU", "soviet union": "RU",
    "azores": "PT", "tenerife": "ES", "canary islands": "ES",
    "zaire": "CD", "rhodesia": "ZW", "new guinea": "PG",
    "luxemburg": "LU", "nederland": "NL", "belgie": "BE", "duitsland": "DE",
}

CA_PROV = {"AB": "01", "BC": "02", "MB": "03", "NB": "04", "NL": "05",
           "NT": "13", "NS": "07", "NU": "14", "ON": "08", "PE": "09",
           "QC": "10", "SK": "11", "YT": "12"}

US_STATES = set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD "
                "MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC "
                "SD TN TX UT VT VA WA WV WI WY DC PR VI GU AS MP".split())

# ---------------------------------------------------------------- geonames
ASCII_NAME = re.compile(r"^[A-Za-z .'-]{3,}$")

def load_geonames():
    """Bouw lookups: (land, admin1, stad) en (land, stad) -> (lat, lon), hoogste populatie wint.

    Officiële namen (name/asciiname) krijgen voorrang; ASCII-alternatieven
    (endoniemen, oude namen) vullen alleen ontbrekende sleutels aan.
    """
    by_admin, by_country = {}, {}
    alt_admin, alt_country = {}, {}
    with open(GEO_DIR / "cities500.txt", encoding="utf-8") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            name, asciiname, alts = p[1], p[2], p[3]
            lat, lon, cc, a1, pop = float(p[4]), float(p[5]), p[8], p[10], int(p[14] or 0)
            names = {norm_city(name), norm_city(asciiname)}
            names.discard("")
            for nm in names:
                for key, table in (((cc, a1, nm), by_admin), ((cc, nm), by_country)):
                    cur = table.get(key)
                    if cur is None or pop > cur[2]:
                        table[key] = (lat, lon, pop)
            if alts:
                alt_names = {norm_city(a) for a in alts.split(",")[:20]
                             if ASCII_NAME.match(a)} - names
                alt_names.discard("")
                for nm in alt_names:
                    for key, table in (((cc, a1, nm), alt_admin), ((cc, nm), alt_country)):
                        cur = table.get(key)
                        if cur is None or pop > cur[2]:
                            table[key] = (lat, lon, pop)
    # alternatieven alleen waar geen officiële naam bestaat
    for src, dst in ((alt_admin, by_admin), (alt_country, by_country)):
        for k, v in src.items():
            dst.setdefault(k, v)
    # laagste prioriteit: volledige landbestanden (ook gehuchten < 500 inwoners)
    for cf in sorted(GEO_DIR.glob("??.txt")):
        cc_file = cf.stem
        with open(cf, encoding="utf-8") as f:
            for line in f:
                p = line.rstrip("\n").split("\t")
                if len(p) < 15 or p[6] != "P":
                    continue
                lat, lon, cc, a1, pop = float(p[4]), float(p[5]), p[8], p[10], int(p[14] or 0)
                names = {norm_city(p[1]), norm_city(p[2])}
                names.discard("")
                for nm in names:
                    by_admin.setdefault((cc, a1, nm), (lat, lon, pop))
                    by_country.setdefault((cc, nm), (lat, lon, pop))
    countries = {}
    with open(GEO_DIR / "countryInfo.txt", encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                continue
            p = line.split("\t")
            if len(p) > 4:
                countries[norm_plain(p[4])] = p[0]
    return by_admin, by_country, countries

def resolve_country(raw: str, state: str, countries: dict) -> str | None:
    n = norm_plain(re.sub(r"\(.*?\)", " ", raw or ""))
    if n in COUNTRY_ALIAS:
        return COUNTRY_ALIAS[n]
    if n in countries:
        return countries[n]
    if not n and state and state.upper() in US_STATES:
        return "US"
    return None

PREFIXES = ("village of ", "town of ", "city of ", "township of ", "borough of ")
SUFFIXES = (" township", " village", " borough", " county")

def name_variants(nm: str):
    yield nm
    for pre in PREFIXES:
        if nm.startswith(pre):
            yield nm[len(pre):]
    for suf in SUFFIXES:
        if nm.endswith(suf) and len(nm) > len(suf) + 2:
            yield nm[: -len(suf)]
    if nm == "new york":
        yield "new york city"

def geocode(city, state, cc, by_admin, by_country):
    nm = norm_city(city or "")
    if not nm or not cc:
        return None
    st = (state or "").strip().upper()
    admin1 = None
    if cc == "US" and st in US_STATES:
        admin1 = st
    elif cc == "CA" and st in CA_PROV:
        admin1 = CA_PROV[st]
    for v in name_variants(nm):
        if admin1:
            hit = by_admin.get((cc, admin1, v))
            if hit:
                return hit[0], hit[1], "admin1"
        hit = by_country.get((cc, v))
        if hit:
            return hit[0], hit[1], "country"
    return None

# ---------------------------------------------------------------- astronomie
def julian_day(y, mo, d):
    a = (14 - mo) // 12
    Y, M = y + 4800 - a, mo + 12 * a - 3
    return d + (153 * M + 2) // 5 + 365 * Y + Y // 4 - Y // 100 + Y // 400 - 32045

def sun_longitude(y, mo, d):
    n = julian_day(y, mo, d) - 2451545.0
    L = 280.460 + 0.9856474 * n
    g = math.radians((357.528 + 0.9856003 * n) % 360)
    return round((L + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g)) % 360, 1)

def moon_phase(y, mo, d):
    frac = ((julian_day(y, mo, d) - 2451550.1) / 29.530588853) % 1.0
    return int(frac * 8 + 0.5) % 8

# ---------------------------------------------------------------- ingest
ROW_RE = re.compile(r"id=(\d+)")
DATE_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})(?:\s+(\d{2}:\d{2}))?")

def clean(s):
    return html.unescape(s).strip() if isinstance(s, str) else ""

def main():
    files = sorted(RAW_DIR.glob("*.json"))
    if not files:
        sys.exit("geen raw-bestanden gevonden; draai eerst scrape_nuforc.py")
    print(f"{len(files)} raw-maandbestanden", flush=True)
    print("GeoNames laden…", flush=True)
    by_admin, by_country, countries = load_geonames()

    con = sqlite3.connect(DB_PATH)
    con.executescript("""
      DROP TABLE IF EXISTS sightings;
      CREATE TABLE sightings(
        source      TEXT NOT NULL DEFAULT 'nuforc',
        source_id   INTEGER NOT NULL,
        year        INTEGER, month INTEGER, day INTEGER, time TEXT,
        city        TEXT, region TEXT, country TEXT, country_code TEXT,
        shape       TEXT, summary TEXT, reported TEXT,
        media       TEXT, explanation TEXT,
        lat REAL, lon REAL, geo_quality TEXT,
        sun_lon REAL, moon_phase INTEGER,
        PRIMARY KEY (source, source_id)
      );
    """)

    n = dup = nodate = nogeo = nocountry = 0
    unmatched_countries = defaultdict(int)
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        for row in data["rows"]:
            link, occurred, city, state, country, shape, summary, reported = (
                [clean(x) for x in row[:8]] + [""] * max(0, 8 - len(row)))
            media = clean(row[8]) if len(row) > 8 else ""
            expl = clean(row[9]) if len(row) > 9 else ""
            m = ROW_RE.search(link)
            if not m:
                continue
            sid = int(m.group(1))
            dm = DATE_RE.search(occurred)
            if not dm:
                nodate += 1
                continue
            mo, d, y = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
            t = dm.group(4) or ""
            if not (1 <= mo <= 12 and 1 <= d <= 31):
                nodate += 1
                continue
            cc = resolve_country(country, state, countries)
            if cc is None and country:
                unmatched_countries[country] += 1
                nocountry += 1
            lat = lon = None
            gq = None
            if cc:
                hit = geocode(city, state, cc, by_admin, by_country)
                if hit:
                    lat, lon, gq = hit
                else:
                    nogeo += 1
            sl = sun_longitude(y, mo, d)
            mp = moon_phase(y, mo, d)
            try:
                con.execute(
                    "INSERT INTO sightings VALUES('nuforc',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (sid, y, mo, d, t, city, state, country, cc, shape, summary,
                     reported, media, expl, lat, lon, gq, sl, mp))
                n += 1
            except sqlite3.IntegrityError:
                dup += 1
    con.commit()

    geocoded = con.execute("SELECT COUNT(*) FROM sightings WHERE lat IS NOT NULL").fetchone()[0]
    print(f"ingevoerd: {n}  (duplicaten: {dup}, zonder datum: {nodate})")
    print(f"gegeocodeerd: {geocoded}/{n} ({geocoded/max(n,1)*100:.1f}%)  "
          f"— zonder land: {nocountry}, land ok maar stad niet gevonden: {nogeo}")
    top = sorted(unmatched_countries.items(), key=lambda kv: -kv[1])[:15]
    if top:
        print("niet-herkende landen (top):", ", ".join(f"{k}×{v}" for k, v in top))
    con.close()

if __name__ == "__main__":
    main()
