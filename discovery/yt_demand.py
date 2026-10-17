#!/usr/bin/env python3
"""Şehir bazlı canlı kamera talebi ölçümü (proxy).
Yöntem: YouTube 'Canlı' filtreli aramada ilk CANLI sonucun eşzamanlı izleyici sayısı.
Bu bir vekil (proxy) ölçümdür: kanalın o anki izleyici hacmi. Arama hacmi değildir.
Çıktı: /tmp/yt_demand.jsonl  (her satır: city, title, channel, viewers, id)
"""
import json, subprocess, sys, time

CITIES = [
    "istanbul", "london", "new york", "tokyo", "paris", "rome", "venice",
    "amsterdam", "prague", "helsinki", "dubai", "barcelona", "zurich", "vienna",
    "hong kong", "seoul", "sydney", "lisbon", "athens", "cairo",
]
LIVE_FILTER = "&sp=EgJAAQ%253D%253D"

out = open("/tmp/yt_demand.jsonl", "a", encoding="utf-8")
for city in CITIES:
    q = f"{city} live cam".replace(" ", "+")
    url = f"https://www.youtube.com/results?search_query={q}{LIVE_FILTER}"
    try:
        p = subprocess.run(
            ["yt-dlp", "--flat-playlist", "--no-warnings", "--playlist-end", "12",
             "--print", "%(title)s\t%(channel)s\t%(id)s\t%(view_count)s\t%(is_live)s", url],
            capture_output=True, text=True, timeout=120)
        rows = [r.split("\t") for r in p.stdout.strip().split("\n") if r.count("\t") >= 4]
        live = [r for r in rows if len(r) > 4 and r[4] == "True"]
        pick = live[0] if live else (rows[0] if rows else None)
        rec = {"city": city, "n_live_in_top12": len(live),
               "title": pick[0] if pick else None,
               "channel": pick[1] if pick else None,
               "id": pick[2] if pick else None,
               "viewers": pick[3] if pick else None,
               "is_live": pick[4] if pick and len(pick) > 4 else None}
    except Exception as e:
        rec = {"city": city, "error": str(e)[:120]}
    out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush()
    print(json.dumps(rec, ensure_ascii=False), flush=True)
    time.sleep(1)
out.close()
print("BITTI")
