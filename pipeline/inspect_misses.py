import sqlite3
from pathlib import Path
con = sqlite3.connect(Path(__file__).parent / "ufo.db")
print("-- missers per land --")
for r in con.execute("""SELECT country_code, COUNT(*) c FROM sightings
                        WHERE lat IS NULL AND country_code IS NOT NULL AND city != ''
                        GROUP BY 1 ORDER BY c DESC LIMIT 12"""):
    print("|".join(str(x) for x in r))
print("-- meest voorkomende missers --")
for r in con.execute("""SELECT city, region, country_code, COUNT(*) c
                        FROM sightings WHERE lat IS NULL AND country_code IS NOT NULL
                        GROUP BY 1,2,3 ORDER BY c DESC LIMIT 25"""):
    print("|".join(str(x) for x in r))
