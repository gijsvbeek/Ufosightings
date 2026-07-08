# UFO-kaart — Waarnemingslogboek 1900–heden

Interactieve wereldkaart van alle geocodeerbare UFO-meldingen uit de database van
[NUFORC](https://nuforc.org) (ruim 160.000 meldingen, doorlopend bijgewerkt), met vier weergaven:

- **Jaar** — meldingen per jaar, scrubben via de tijdlijn
- **T/m dit jaar** — cumulatieve opbouw
- **Totaal** — alle meldingen, elk jaar een eigen kleur (histogram = kleurlegenda)
- **☉ Kosmos** — filter op de baanpositie van de aarde rond de zon, met meteorenzwerm-zones,
  live binomiale toets (ratio + p-waarde, Bonferroni-gecorrigeerd) en waarschuwingen voor
  menselijke pieken (4 juli, jaarwisseling)

Daarnaast een **lijstweergave** (knop rechtsboven): doorzoekbare index per jaar met
vrije-tekstzoek en filters op vorm en land — inclusief de meldingen zonder coördinaten
die niet op de kaart staan — met per rij een sprong naar de kaart en de NUFORC-bron.
De ondergrond is schakelbaar tussen **echte satellietbeelden** (Esri World Imagery,
inzoombaar tot straatniveau) en de gestileerde donkere kaart.

Elke melding is klikbaar: datum, tijdstip, vorm, maanfase, baanpositie, eventuele aardse
verklaring en een directe bronlink naar het NUFORC-rapport.

## Structuur

```
index.html               de complete applicatie (Leaflet + eigen canvas-puntenlaag, geen build)
data/points.json         alle gegeocodeerde meldingen, compact:
                         [nuforcId, jaar, maand, dag, lat, lon, vormIdx, zonlengte×10, maanfase]
data/details/YYYYMM.json details per maand (popup + lijstweergave), on demand geladen:
                         {id:[dag,tijd,plaats,regio,land,vorm,uitleg,samenvatting]}
data/slhist.json         meldingen per graad zonlengte (volledige dataset)
data/yearhist.json       meldingen per jaar (volledige dataset)
data/showers.json        herberekende statistiek: zwerm-ratio's, p-waarden, maanfase-χ²
data/world.json          landgrenzen (Natural Earth, vereenvoudigd)
```

## Datapipeline

De site is statisch; de data komt uit `pipeline/` (Python, alleen standaardbibliotheek):

```
python pipeline/scrape_nuforc.py   # haalt alle maandindexen op via het NUFORC-AJAX-endpoint
                                   # (hervatbaar; cache in pipeline/raw/)
python pipeline/build_db.py        # raw → pipeline/ufo.db: parsen, ontdubbelen,
                                   # geocoderen (GeoNames cities500), zonlengte + maanfase
python pipeline/export.py          # ufo.db → data/*.json (incl. herberekende statistiek)
```

Voor `build_db.py` zijn drie GeoNames-bestanden nodig in `pipeline/geonames/`:
[cities500.zip](https://download.geonames.org/export/dump/cities500.zip) (uitgepakt),
[admin1CodesASCII.txt](https://download.geonames.org/export/dump/admin1CodesASCII.txt) en
[countryInfo.txt](https://download.geonames.org/export/dump/countryInfo.txt).

De SQLite-database (`pipeline/ufo.db`) is de ingest-/beheerlaag: nieuwe bronnen naast NUFORC
krijgen hier hun eigen `source`, waarna dezelfde export alles samenvoegt. Raw scrape,
GeoNames en de database staan bewust niet in git (zie `.gitignore`) — alles is herbouwbaar.

## Verversen

Opnieuw `scrape_nuforc.py` draaien haalt alleen nieuwe/gewijzigde maanden op
(complete maanden worden uit cache overgeslagen — verwijder recente
`pipeline/raw/2026*.json` om lopende maanden te verversen), daarna
`build_db.py` + `export.py` en de gewijzigde `data/`-bestanden committen.

## Deployen

Statische site, geen build stap. Importeer deze repo op [vercel.com/new](https://vercel.com/new)
(framework preset: **Other**) of serveer de map met elke statische webserver.

## Bronnen

Meldingen: National UFO Reporting Center (NUFORC). Geocoding: GeoNames (cities500 +
landbestanden US/CA/GB/AU). Satellietbeelden: Esri World Imagery (Esri, Maxar,
Earthstar Geographics). Landgrenzen: Natural Earth. Astronomie (zonlengte, maanfase): berekend met standaard
benaderingsformules. Meteorenzwerm-pieken: IMO-kalender; ratio's en p-waarden worden
bij elke export herberekend op de volledige dataset.
