"""Scrape alle NUFORC-meldingen via het wpDataTables AJAX-endpoint.

Werkwijze:
  1. haal een maandpagina op voor een verse wdtNonce
  2. haal de maandindex op (alle beschikbare YYYYMM-waarden)
  3. per maand: POST naar admin-ajax.php, pagineer tot recordsFiltered bereikt is
  4. schrijf per maand een JSON-bestand naar pipeline/raw/ (hervatbaar: bestaande
     complete bestanden worden overgeslagen)

Gebruik:  python scrape_nuforc.py [--limit N]
"""
import json
import re
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

BASE = "https://nuforc.org"
RAW_DIR = Path(__file__).parent / "raw"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ufosightings-kaart (contact: gijsvbeek@gmail.com)"
DELAY = 0.35  # seconden tussen requests
PAGE_LEN = 1000


def http_get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="replace")


def http_post(url: str, data: dict) -> dict:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, headers={
        "User-Agent": UA,
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "XMLHttpRequest",
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def fetch_nonce() -> str:
    html = http_get(f"{BASE}/subndx/?id=e202506")
    m = re.search(r'wdtNonceFrontendServerSide_1"\s+name="[^"]+"\s+value="([0-9a-f]+)"', html)
    if not m:
        raise RuntimeError("wdtNonce niet gevonden op maandpagina")
    return m.group(1)


def fetch_months() -> list[str]:
    html = http_get(f"{BASE}/ndx/?id=event")
    months = sorted(set(re.findall(r"id=e(\d{6})", html)))
    if len(months) < 500:
        raise RuntimeError(f"verdacht weinig maanden gevonden: {len(months)}")
    return months


def fetch_month(month: str, nonce: str) -> dict:
    """Alle rijen van één maand, gepagineerd."""
    url = (f"{BASE}/wp-admin/admin-ajax.php?action=get_wdtable"
           f"&table_id=1&wdt_var1=YearMonth&wdt_var2={month}")
    rows, total, start, draw = [], None, 0, 1
    while True:
        for attempt in range(5):
            try:
                resp = http_post(url, {
                    "draw": draw, "start": start, "length": PAGE_LEN, "wdtNonce": nonce,
                })
                break
            except Exception as e:
                wait = 2 ** attempt * 2
                print(f"  {month}: poging {attempt+1} mislukt ({e}), wacht {wait}s", flush=True)
                time.sleep(wait)
        else:
            raise RuntimeError(f"{month}: opgegeven na 5 pogingen")
        total = int(resp["recordsFiltered"])
        rows.extend(resp["data"])
        start += PAGE_LEN
        draw += 1
        if len(rows) >= total or not resp["data"]:
            break
        time.sleep(DELAY)
    return {"month": month, "total": total, "rows": rows}


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    RAW_DIR.mkdir(exist_ok=True)
    print("nonce ophalen…", flush=True)
    nonce = fetch_nonce()
    print("maandindex ophalen…", flush=True)
    months = fetch_months()
    print(f"{len(months)} maanden beschikbaar", flush=True)
    if limit:
        months = months[-limit:]

    done = skipped = failed = n_rows = 0
    for i, month in enumerate(months):
        out = RAW_DIR / f"{month}.json"
        if out.exists():
            try:
                cached = json.loads(out.read_text(encoding="utf-8"))
                if len(cached["rows"]) >= cached["total"]:
                    skipped += 1
                    n_rows += len(cached["rows"])
                    continue
            except Exception:
                pass  # kapot cachebestand: opnieuw ophalen
        try:
            data = fetch_month(month, nonce)
        except Exception as e:
            print(f"  FOUT {month}: {e}", flush=True)
            failed += 1
            continue
        out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        done += 1
        n_rows += len(data["rows"])
        if (i + 1) % 50 == 0 or i == len(months) - 1:
            print(f"[{i+1}/{len(months)}] opgehaald={done} cache={skipped} "
                  f"fout={failed} rijen={n_rows}", flush=True)
        time.sleep(DELAY)

    print(f"KLAAR: {done} opgehaald, {skipped} uit cache, {failed} mislukt, "
          f"{n_rows} rijen totaal", flush=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
