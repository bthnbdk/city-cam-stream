#!/usr/bin/env python3
"""Talep ölçümü v2: her şehir için YT 'Canlı' aramasında ilk CANLI yayının
eşzamanlı izleyici sayısını (canlı yayında view_count = eşzamanlı izleyici) ölçer.
Yöntem esc: flat arama -> ilk canlı id -> tam çıkarım (view_count).
Çıktı: /tmp/yt_demand2.jsonl
"""
import json, subprocess, time

CITIES = ["istanbul", "london", "new york", "tokyo", "paris", "rome", "venice",
          "amsterdam", "prague", "helsinki", "dubai", "zurich", "seoul", "hong kong"]
LIVE_FILTER = "&sp=EgJAAQ%253D%253D"
out = open("/tmp/yt_demand2.jsonl", "a", encoding="utf-8")


def run(args, t=150):
    return subprocess.run(args, capture_output=True, text=True, timeout=t)


for city in CITIES:
    rec = {"city": city}
    try:
        url = f"https://www.youtube.com/results?search_query={city.replace(' ', '+')}+live+cam{LIVE_FILTER}"
        p = run(["yt-dlp", "--flat-playlist", "--no-warnings", "--playlist-end", "10",
                 "--print", "%(id)s\t%(is_live)s\t%(title)s", url])
        rows = [r.split("\t") for r in p.stdout.strip().split("\n") if r.count("\t") >= 2]
        rec["n_live_top10"] = sum(1 for r in rows if len(r) > 1 and r[1] == "True")
        live = [r for r in rows if len(r) > 1 and r[1] == "True"]
        if live:
            vid = live[0][0]
            rec["top_live_id"] = vid
            rec["top_live_title"] = live[0][2][:120]
            p2 = run(["yt-dlp", "--no-warnings", "--skip-download",
                      "--print", "%(view_count)s\t%(channel)s\t%(channel_follower_count)s", vid])
            v = p2.stdout.strip().split("\t")
            rec["concurrent_viewers"] = v[0] if v else None
            rec["channel"] = v[1] if len(v) > 1 else None
            rec["channel_subs"] = v[2] if len(v) > 2 else None
    except Exception as e:
        rec["error"] = str(e)[:140]
    out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush()
    print(json.dumps(rec, ensure_ascii=False), flush=True)
    time.sleep(1)
print("BITTI")
