#!/usr/bin/env python3
"""
fetch_ytlive.py — Şehir başına YouTube 24/7 CANLI kamera yayınlarını bulur ve
embed edilebilirliğini ölçer (oEmbed 200 = gömülebilir). kind='youtube'.

Bu kaynak "başkasının yayınını yeniden yayınlamak" DEĞİL, gömme (embed) yoludur:
oynatıcı YouTube iframe'idir, yayın sahibinin kendi player'ı kullanılır.

Ölçüm: her video için
  - oEmbed: https://www.youtube.com/oembed?url=...&format=json  (200 -> gömülebilir)
  - canlılık: yt-dlp is_live
Şehir uyumu: başlık/kanal adında şehir adı geçmeyen sonuçlar elenir
(arama kirliliği: Heathrow kamerası her şehirde çıkıyor).

Kullanım: python3 discovery/fetch_ytlive.py [--per-city 4] [--cities istanbul,paris]
"""
import argparse, json, re, sqlite3, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "cameras.db"
META = ROOT / "data" / "city_meta.json"
LIVE_FILTER = "&sp=EgJAAQ%253D%253D"   # YouTube "Canlı" filtresi
EMBED = "https://www.youtube.com/embed/{id}?autoplay=1&mute=1&playsinline=1&controls=0&modestbranding=1&rel=0"

CITIES = {
    "istanbul": ("Istanbul", "Istanbul", "TR", 41.013, 28.978, "Europe/Istanbul"),
    "ankara": ("Ankara", "Ankara", "TR", 39.933, 32.859, "Europe/Istanbul"),
    "izmir": ("Izmir", "Izmir", "TR", 38.423, 27.142, "Europe/Istanbul"),
    "antalyaturkey": ("Antalya", "Antalya", "TR", 36.897, 30.713, "Europe/Istanbul"),
    "paris": ("Paris", "Paris", "FR", 48.857, 2.352, "Europe/Paris"),
    "london": ("London", "London", "GB", 51.507, -0.128, "Europe/London"),
    "rome": ("Rome", "Rome", "IT", 41.893, 12.483, "Europe/Rome"),
    "venice": ("Venice", "Venice", "IT", 45.440, 12.316, "Europe/Rome"),
    "barcelona": ("Barcelona", "Barcelona", "ES", 41.383, 2.177, "Europe/Madrid"),
    "amsterdam": ("Amsterdam", "Amsterdam", "NL", 52.373, 4.892, "Europe/Amsterdam"),
    "prague": ("Prague", "Prague", "CZ", 50.076, 14.437, "Europe/Prague"),
    "vienna": ("Vienna", "Vienna", "AT", 48.208, 16.373, "Europe/Vienna"),
    "newyork": ("New York", "New York", "US", 40.713, -74.006, "America/New_York"),
    "losangeles": ("Los Angeles", "Los Angeles", "US", 34.052, -118.244, "America/Los_Angeles"),
    "miami": ("Miami", "Miami", "US", 25.762, -80.192, "America/New_York"),
    "tokyo": ("Tokyo", "Tokyo", "JP", 35.690, 139.692, "Asia/Tokyo"),
    "kyoto": ("Kyoto", "Kyoto", "JP", 35.011, 135.768, "Asia/Tokyo"),
    "seoul": ("Seoul", "Seoul", "KR", 37.566, 126.978, "Asia/Seoul"),
    "hongkong": ("Hong Kong", "Hong Kong", "HK", 22.319, 114.169, "Asia/Hong_Kong"),
    "dubai": ("Dubai", "Dubai", "AE", 25.205, 55.271, "Asia/Dubai"),
    "sydney": ("Sydney", "Sydney", "AU", -33.869, 151.209, "Australia/Sydney"),
    "riodejaneiro": ("Rio de Janeiro", "Rio de Janeiro", "BR", -22.907, -43.173, "America/Sao_Paulo"),
    "madrid": ("Madrid", "Madrid", "ES", 40.417, -3.704, "Europe/Madrid"),
    "lisbon": ("Lisbon", "Lisbon", "PT", 38.717, -9.139, "Europe/Lisbon"),
    "athens": ("Athens", "Athens", "GR", 37.984, 23.728, "Europe/Athens"),
    "zurich": ("Zurich", "Zurich", "CH", 47.377, 8.541, "Europe/Zurich"),
    "cairo": ("Cairo", "Cairo", "EG", 30.044, 31.236, "Africa/Cairo"),
    "shanghai": ("Shanghai", "Shanghai", "CN", 31.230, 121.474, "Asia/Shanghai"),
    "singapore": ("Singapore", "Singapore", "SG", 1.352, 103.820, "Asia/Singapore"),
    "berlin": ("Berlin", "Berlin", "DE", 52.520, 13.405, "Europe/Berlin"),
    "tokyoshinjuku": ("Shinjuku", "Shinjuku Tokyo", "JP", 35.690, 139.700, "Asia/Tokyo"),
    "osaka": ("Osaka", "Osaka", "JP", 34.694, 135.502, "Asia/Tokyo"),
    "kyotocity": ("Kyoto", "Kyoto Japan", "JP", 35.011, 135.768, "Asia/Tokyo"),
    "vancouver": ("Vancouver", "Vancouver", "CA", 49.283, -123.121, "America/Vancouver"),
    "toronto": ("Toronto", "Toronto", "CA", 43.653, -79.383, "America/Toronto"),
    "chicago": ("Chicago", "Chicago", "US", 41.878, -87.630, "America/Chicago"),
    "lasvegas": ("Las Vegas", "Las Vegas", "US", 36.170, -115.140, "America/Los_Angeles"),
    "sanfrancisco": ("San Francisco", "San Francisco", "US", 37.775, -122.419, "America/Los_Angeles"),
    "honolulu": ("Honolulu", "Honolulu Hawaii", "US", 21.307, -157.858, "Pacific/Honolulu"),
    "mexicocity": ("Mexico City", "Mexico City", "MX", 19.433, -99.133, "America/Mexico_City"),
    "buenosaires": ("Buenos Aires", "Buenos Aires", "AR", -34.604, -58.382, "America/Argentina/Buenos_Aires"),
    "saopaulo": ("Sao Paulo", "Sao Paulo", "BR", -23.551, -46.633, "America/Sao_Paulo"),
    "reykjavik": ("Reykjavik", "Reykjavik", "IS", 64.147, -21.942, "Atlantic/Reykjavik"),
    "dublin": ("Dublin", "Dublin", "IE", 53.350, -6.260, "Europe/Dublin"),
    "edinburgh": ("Edinburgh", "Edinburgh", "GB", 55.953, -3.189, "Europe/London"),
    "manchester": ("Manchester", "Manchester", "GB", 53.481, -2.242, "Europe/London"),
    "brussels": ("Brussels", "Brussels", "BE", 50.847, 4.352, "Europe/Brussels"),
    "copenhagen": ("Copenhagen", "Copenhagen", "DK", 55.677, 12.568, "Europe/Copenhagen"),
    "stockholm": ("Stockholm", "Stockholm", "SE", 59.329, 18.069, "Europe/Stockholm"),
    "oslo": ("Oslo", "Oslo", "NO", 59.913, 10.752, "Europe/Oslo"),
    "warsaw": ("Warsaw", "Warsaw", "PL", 52.230, 21.012, "Europe/Warsaw"),
    "budapest": ("Budapest", "Budapest", "HU", 47.498, 19.040, "Europe/Budapest"),
    "krakow": ("Krakow", "Krakow", "PL", 50.062, 19.937, "Europe/Warsaw"),
    "pragueold": ("Prague", "Prague Old Town", "CZ", 50.087, 14.421, "Europe/Prague"),
    "munich": ("Munich", "Munich", "DE", 48.137, 11.575, "Europe/Berlin"),
    "frankfurt": ("Frankfurt", "Frankfurt", "DE", 50.110, 8.682, "Europe/Berlin"),
    "hamburg": ("Hamburg", "Hamburg", "DE", 53.551, 9.993, "Europe/Berlin"),
    "geneva": ("Geneva", "Geneva", "CH", 46.204, 6.143, "Europe/Zurich"),
    "milan": ("Milan", "Milan", "IT", 45.464, 9.190, "Europe/Rome"),
    "naples": ("Naples", "Naples", "IT", 40.852, 14.268, "Europe/Rome"),
    "florence": ("Florence", "Florence", "IT", 43.770, 11.256, "Europe/Rome"),
    "bari": ("Bari", "Bari", "IT", 41.125, 16.869, "Europe/Rome"),
    "palermo": ("Palermo", "Palermo", "IT", 38.116, 13.361, "Europe/Rome"),
    "valencia": ("Valencia", "Valencia Spain", "ES", 39.470, -0.376, "Europe/Madrid"),
    "seville": ("Seville", "Seville", "ES", 37.389, -5.984, "Europe/Madrid"),
    "porto": ("Porto", "Porto", "PT", 41.150, -8.610, "Europe/Lisbon"),
    "brussels2": ("Antwerp", "Antwerp", "BE", 51.221, 4.400, "Europe/Brussels"),
    "telaviv": ("Tel Aviv", "Tel Aviv", "IL", 32.085, 34.781, "Asia/Jerusalem"),
    "istanbulbosphorus": ("Istanbul Bosphorus", "Bosphorus Istanbul", "TR", 41.085, 29.055, "Europe/Istanbul"),
    "capetown": ("Cape Town", "Cape Town", "ZA", -33.925, 18.424, "Africa/Johannesburg"),
    "marrakech": ("Marrakech", "Marrakech", "MA", 31.630, -7.981, "Africa/Casablanca"),
    "nairobi": ("Nairobi", "Nairobi", "KE", -1.286, 36.817, "Africa/Nairobi"),
    "bangkok": ("Bangkok", "Bangkok", "TH", 13.756, 100.502, "Asia/Bangkok"),
    "mumbai": ("Mumbai", "Mumbai", "IN", 19.076, 72.877, "Asia/Kolkata"),
    "dohacity": ("Doha", "Doha", "QA", 25.286, 51.531, "Asia/Qatar"),
    "kualalumpur": ("Kuala Lumpur", "Kuala Lumpur", "MY", 3.139, 101.687, "Asia/Kuala_Lumpur"),
    "auckland": ("Auckland", "Auckland", "NZ", -36.849, 174.763, "Pacific/Auckland"),
}
QUERY_HINT = {  # aramada kullanılacak ad (İngilizce)
    "antalyaturkey": "Antalya Turkey",
}


def run(cmd, t=180):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=t)


def oembed_ok(vid):
    r = run(["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "15",
             f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={vid}&format=json"])
    return r.stdout.strip() == "200"


EXTRA_QUERIES = {
    "istanbul": ["Istanbul live cam", "bosphorus live cam", "istanbul live webcam",
                 "taksim live cam", "galata tower live cam", "istanbul canli kamera",
                 "istanbul traffic live cam", "kiz kulesi live"],
    "london": ["London live cam", "Thames live cam"],
    "paris": ["Paris live cam", "Paris live webcam"],
    "newyork": ["New York live cam", "Times Square live cam"],
    "tokyo": ["Tokyo live cam", "Shibuya live cam"],
    "dubai": ["Dubai live cam", "Dubai skyline live cam"],
    "rome": ["Rome live cam", "Rome webcam live"],
    "venice": ["Venice live cam", "Venice canal live cam"],
    "amsterdam": ["Amsterdam live cam", "Amsterdam canal live cam"],
}


def queries_for(slug, label):
    base = [f"{QUERY_HINT.get(slug, label)} live cam", f"{QUERY_HINT.get(slug, label)} live webcam"]
    if slug in EXTRA_QUERIES:
        return list(dict.fromkeys(EXTRA_QUERIES[slug]))
    return list(dict.fromkeys([f"{label} live cam", f"{label} live webcam", f"{label} live"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-city", type=int, default=4)
    ap.add_argument("--cities", default="all")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    want = list(CITIES) if a.cities == "all" else [c.strip() for c in a.cities.split(",")]
    meta = json.loads(META.read_text()) if META.exists() else {}
    from concurrent.futures import ThreadPoolExecutor

    def one(slug):
        out = []
        label, qname, cc, lat, lon, tz = CITIES[slug]
        meta.setdefault(slug, dict(label=label, country=cc, lat=lat, lon=lon, tz=tz))
        cand = []
        for query in queries_for(slug, label):
            q = query.replace(" ", "+")
            try:
                p = run(["yt-dlp", "--flat-playlist", "--no-warnings", "--playlist-end", "14",
                         "--print", "%(id)s\t%(title)s\t%(channel)s\t%(is_live)s",
                         f"https://www.youtube.com/results?search_query={q}{LIVE_FILTER}"])
            except subprocess.TimeoutExpired:
                continue
            cand += [l for l in p.stdout.strip().split("\n") if l.count("\t") >= 3]
        found = 0
        for line in dict.fromkeys(cand):
            parts = line.split("\t")
            if len(parts) < 4 or parts[3] != "True":
                continue
            vid, title, chan = parts[0], parts[1], parts[2]
            hay = f"{title} {chan}".lower()
            keys = [label.lower()] + [w for w in label.lower().split()]
            if slug == "antalyaturkey":
                keys = ["antalya"]
            if not any(k in hay for k in keys):
                continue
            if not oembed_ok(vid):
                continue
            out.append(dict(source_key="yt_live", external_id=vid, country=cc, city=slug,
                             name=re.sub(r"\s+", " ", title)[:110], area=f"YouTube · {chan}"[:60],
                             lat=lat, lon=lon, stream_url=EMBED.format(id=vid),
                             snapshot_url=f"https://i.ytimg.com/vi/{vid}/maxresdefault.jpg",
                             kind="youtube", cam_type="canli_yayin", licence_class="C",
                             first_seen="2026-10-17T15:40:00Z", yayin_havuzu=0))
            found += 1
            if found >= a.per_city:
                break
        print(f"  {label:16s} {found} canlı yayın (embed doğrulandı)", flush=True)
        return out

    rows = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for res in ex.map(one, want):
            rows += (res or [])
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=1))

    sys.path.insert(0, str(ROOT))
    from cam import conn
    c = conn()
    c.execute("""INSERT OR REPLACE INTO sources
      (key,label,country,city,kind,endpoint,site,licence_class,evidence,contact,notes,verified_at,reachable)
      VALUES ('yt_live','YouTube 24/7 canlı kamera yayınları (embed)','INT','-','youtube',
      'https://www.youtube.com/results?search_query=live+cam','youtube.com','C',
      'Yeniden yayın (restream) izin gerektirir; bu kaynak YALNIZCA sahibinin iframe oynatıcısını gömer.',
      '-','oEmbed 200 = gömülebilir doğrulaması yapılmıştır.','2026-10-17T15:40:00Z',1)""")
    n = 0
    for r in rows:
        cols = ",".join(r)
        try:
            c.execute(f"INSERT OR IGNORE INTO cameras ({cols}) VALUES ({','.join(':'+k for k in r)})", r)
            n += 1
        except sqlite3.Error as e:
            print("DB:", e)
    c.commit(); c.close()
    print(f"yt_live: {n} yayın DB'ye yazıldı ({len(set(r['city'] for r in rows))} şehir)")


if __name__ == "__main__":
    main()
