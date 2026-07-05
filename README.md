# UFO-kaart — Waarnemingslogboek 1930–2014

Interactieve wereldkaart van 5.198 UFO-meldingen (steekproef uit de 80.324 gegeocodeerde
meldingen van [NUFORC](https://nuforc.org)), met vier weergaven:

- **Jaar** — meldingen per jaar, scrubben via de tijdlijn
- **T/m dit jaar** — cumulatieve opbouw
- **Totaal** — alle meldingen, elk jaar een eigen kleur (histogram = kleurlegenda)
- **☉ Kosmos** — filter op de baanpositie van de aarde rond de zon, met meteorenzwerm-zones,
  live binomiale toets (ratio + p-waarde, Bonferroni-gecorrigeerd) en waarschuwingen voor
  menselijke pieken (4 juli, jaarwisseling)

Elke melding is klikbaar: datum, tijdstip, duur, vorm, maanfase, baanpositie en een
bronlink naar de NUFORC-maandindex.

## Structuur

```
index.html            de complete applicatie (Leaflet, geen build nodig)
data/sightings.json   meldingen: [jaar, maand, dag, tijd, lat, lon, plaats, vorm, duur, tekst, zonlengte, maanfase]
data/slhist.json      meldingen per graad zonlengte (volledige dataset)
data/yearhist.json    meldingen per jaar (volledige dataset)
data/world.json       landgrenzen (Natural Earth, vereenvoudigd)
```

## Deployen

Statische site, geen build stap. Importeer deze repo op [vercel.com/new](https://vercel.com/new)
(framework preset: **Other**) of serveer de map met elke statische webserver.

## Bronnen

Meldingen: National UFO Reporting Center (NUFORC), gegeocodeerde dataset 1930–2014.
Landgrenzen: Natural Earth. Astronomie (zonlengte, maanfase): berekend met standaard
benaderingsformules. Meteorenzwerm-pieken: IMO-kalender.
