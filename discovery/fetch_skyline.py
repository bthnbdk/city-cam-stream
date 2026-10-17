#!/usr/bin/env python3
"""
fetch_skyline.py — SkylineWebcams kamera dizinini tarar, GERÇEK HLS akış URL'lerini toplar.

Yöntem (doğrulanmış 17.10.2026):
  Kamera sayfası kaynağında Clappr player şu şekilde başlar:
      source:'livee.m3u8?a=<TOKEN>'
  Gerçek yayın adresi:  https://hd-auth.skylinewebcams.com/livee.m3u8?a=<TOKEN>
  (Token kamera başına farklıdır; host adı sabittir.)

Sayfa yapısı: /en/webcam/<ülke>.html → /en/webcam/<ülke>/<bölge>.html →
              /en/webcam/<ülke>/<bölge>[/<şehir>]/<kamera>.html
Ülke listesi ana sayfadan alınır (69 ülke).

Çıktı: data/cameras.db (source_key='skyline_live', kind='hls')
       data/city_meta.json  (şehir etiketi + Open-Meteo geocoding ile lat/lon/tz)
Kullanım:
  python3 discovery/fetch_skyline.py --pages 1400 --probe 25
"""
import argparse, json, re, sqlite3, sys, time, unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import subprocess

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "cameras.db"
META = ROOT / "data" / "city_meta.json"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")
BASE = "https://www.skylinewebcams.com"
HLS_HOST = "https://hd-auth.skylinewebcams.com/"
# Kamera kartları GÖRELİ link kullanır (başında / YOK): href="en/webcam/italia/lazio/roma/x.html"
ROOT_RE = re.compile(r'href="(?:/)?(en/webcam/[^"#?]+\.html)"')
TOKEN_RE = re.compile(r"source:'([^']*\.m3u8[^']*)'")
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)

COUNTRY_LABEL = {
    "italia": "Italy", "espana": "Spain", "ellada": "Greece", "deutschland": "Germany",
    "schweiz": "Switzerland", "hrvatska": "Croatia", "norge": "Norway", "brasil": "Brazil",
    "united-kingdom": "United Kingdom", "united-states": "United States",
    "czech-republic": "Czechia", "netherlands": "Netherlands", "portugal": "Portugal",
    "austria": "Austria", "france": "France", "hungary": "Hungary", "poland": "Poland",
    "romania": "Romania", "bulgaria": "Bulgaria", "slovenija": "Slovenia", "turkey": "Turkey",
    "malta": "Malta", "cyprus": "Cyprus", "ireland": "Ireland", "iceland": "Iceland",
    "jordan": "Jordan", "israel": "Israel", "thailand": "Thailand", "vietnam": "Vietnam",
    "philippines": "Philippines", "sri-lanka": "Sri Lanka", "maldives": "Maldives",
    "mauritius": "Mauritius", "seychelles": "Seychelles", "kenya": "Kenya",
    "zanzibar": "Zanzibar", "south-africa": "South Africa", "morocco": "Morocco",
    "canada": "Canada", "mexico": "Mexico", "costa-rica": "Costa Rica",
    "dominican-republic": "Dominican Republic", "puerto-rico": "Puerto Rico",
    "el-salvador": "El Salvador", "honduras": "Honduras", "panama": "Panama",
    "argentina": "Argentina", "chile": "Chile", "peru": "Peru", "uruguay": "Uruguay",
    "bolivia": "Bolivia", "ecuador": "Ecuador", "colombia": "Colombia",
    "australia": "Australia", "china": "China", "malaysia": "Malaysia",
    "new-zealand": "New Zealand", "albania": "Albania", "bosnia-and-herzegovina": "Bosnia",
    "luxembourg": "Luxembourg", "belize": "Belize", "bermuda": "Bermuda",
    "cabo-verde": "Cabo Verde", "faroe-islands": "Faroe Islands", "grenada": "Grenada",
    "guadeloupe": "Guadeloupe", "martinique": "Martinique", "sint-maarten": "Sint Maarten",
    "caribbean-netherlands": "Caribbean Netherlands", "us-virgin-islands": "US Virgin Islands",
    "zambia": "Zambia", "senegal": "Senegal", "japan": "Japan",
}
CITY_ALIAS = {
    "roma": "Rome", "venezia": "Venice", "firenze": "Florence", "milano": "Milan",
    "napoli": "Naples", "torino": "Turin", "genova": "Genoa", "bologna": "Bologna",
    "palermo": "Palermo", "catania": "Catania", "bari": "Bari", "verona": "Verona",
    "london": "London", "paris": "Paris", "amsterdam": "Amsterdam", "barcelona": "Barcelona",
    "madrid": "Madrid", "lisboa": "Lisbon", "lisbon": "Lisbon", "praha": "Prague",
    "wien": "Vienna", "budapest": "Budapest", "athina": "Athens", "istanbul": "Istanbul",
    "new-york": "New York", "miami": "Miami", "tokyo": "Tokyo", "dubai": "Dubai",
    "rio-de-janeiro": "Rio de Janeiro", "sydney": "Sydney", "zurich": "Zurich",
    "munchen": "Munich", "berlin": "Berlin", "kobenhavn": "Copenhagen",
    "stockholm": "Stockholm", "oslo": "Oslo", "helsinki": "Helsinki", "dublin": "Dublin",
    "edinburgh": "Edinburgh", "bruges": "Bruges", "porto": "Porto", "sevilla": "Seville",
    "valencia": "Valencia", "santorini": "Santorini", "mykonos": "Mykonos",
    "positano": "Positano", "capri": "Capri", "cinque-terre": "Cinque Terre",
    "kotor": "Kotor", "dubrovnik": "Dubrovnik", "split": "Split", "zadar": "Zadar",
}


def curl(url, timeout=25):
    r = subprocess.run(["curl", "-sSL", "--compressed", "-A", UA, "--max-time", str(timeout),
                        "-H", "Accept-Language: en", url], capture_output=True)
    return r.stdout.decode("utf-8", "ignore")


def slug_to_label(s):
    if s in CITY_ALIAS:
        return CITY_ALIAS[s]
    s = s.replace("-and-", " & ")
    return " ".join(w.capitalize() for w in s.split("-"))


def parse_cam(html, path):
    m = TOKEN_RE.search(html)
    if not m:
        return None
    parts = [p for p in path.strip("/").split("/") if p and p != "en" and p != "webcam"]
    # parts: <ülke>/<bölge>[/<şehir>]/<kamera>.html
    if len(parts) < 3:
        return None
    country = parts[0]
    cam_slug = parts[-1].replace(".html", "")
    city_slug = parts[-2] if len(parts) >= 4 else parts[-2]
    region = parts[1]
    t = TITLE_RE.search(html)
    name = t.group(1) if t else cam_slug
    name = re.sub(r"^【[^】]*】\s*", "", name)
    name = re.sub(r"\s*[|•]\s*SkylineWebcams.*$", "", name, flags=re.I)
    name = re.sub(r"^\s*(Live )?Webcam\s*", "", name, flags=re.I).strip()
    return dict(
        token=m.group(1), path=path, country=country,
        country_label=COUNTRY_LABEL.get(country, slug_to_label(country)),
        region=slug_to_label(region), city_slug=city_slug,
        city_label=slug_to_label(city_slug), cam_slug=cam_slug,
        name=name[:110] or cam_slug, url=HLS_HOST + m.group(1),
    )


CATEGORY_URLS = [
    "/en/live-cams-category/city-cams.html", "/en/live-cams-category/beach-cams.html",
    "/en/live-cams-category/nature-mountain-cams.html", "/en/live-cams-category/lake-cams.html",
    "/en/live-cams-category/seaport-cams.html", "/en/live-cams-category/ski-cams.html",
    "/en/live-cams-category/unesco-cams.html", "/en/live-cams-category/volcanoes-cams.html",
    "/en/live-cams-category/animals-cams.html", "/en/live-cams-category/live-web-cams.html",
    "/en/top-live-cams.html", "/en/new-livecams.html",
]
CAM_LINK_RE = re.compile(r'href="(?:/)?(en/webcam/[a-z0-9-]+/[a-z0-9-]+/[a-z0-9-]+(?:/[a-z0-9-]+)?\.html)"')


def probe_cam(c):
    """Gerçek çözünürlük/fps ölçümü (çok satırlı ffprobe çıktısına dayanıklı)."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,avg_frame_rate", "-of", "default=nw=1:nk=1",
                        c["url"]], capture_output=True, text=True, timeout=40)
    nums = [x for x in r.stdout.replace(",", "\n").split() if x.strip()]
    try:
        w, h = int(nums[0]), int(nums[1])
        c["res_w"], c["res_h"] = w, h
        if len(nums) > 2 and "/" in nums[2]:
            a, b = nums[2].split("/")
            c["fps"] = round(float(a) / max(1.0, float(b)), 1)
        return True
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=2000, help="indirilecek kamera sayfası üst sınırı")
    ap.add_argument("--per-country", type=int, default=60)
    ap.add_argument("--probe", type=int, default=25, help="gerçek çözünürlük ölçülecek kamera sayısı")
    ap.add_argument("--workers", type=int, default=10)
    a = ap.parse_args()

    home = curl(BASE + "/en/webcam.html")
    countries = sorted({m.split("/")[-1][:-5] for m in ROOT_RE.findall(home) if m.count("/") == 2})
    print(f"ülke sayısı: {len(countries)}")
    index_pages = CATEGORY_URLS + [f"/en/webcam/{c}.html" for c in countries]
    print(f"indeks sayfası: {len(index_pages)}")

    links = set()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for html in ex.map(lambda p: curl(BASE + p), index_pages):
            for m in CAM_LINK_RE.findall(html):
                links.add("/" + m)
    print(f"kamera sayfası linki: {len(links)}")

    links = sorted(links)[:a.pages]
    cams = {}
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for path, html in zip(links, ex.map(lambda p: curl(BASE + p), links)):
            cam = parse_cam(html, path)
            if cam:
                cams[cam["token"]] = cam
            if len(cams) and len(cams) % 150 == 0 and len(cams) != getattr(main, "_last", 0):
                main._last = len(cams)
                print(f"  ... {len(cams)} kamera (/{len(links)} sayfa)", flush=True)
    print(f"{len(links)} kamera sayfası tarandı, {len(cams)} gerçek HLS akış bulundu")

    # ağ/şehir başına dağılım
    by_city = {}
    for c in cams.values():
        by_city.setdefault(c["city_slug"], 0)
        by_city[c["city_slug"]] += 1
    print(f"şehir sayısı: {len(by_city)} | en kalabalık: "
          + ", ".join(f"{k}({v})" for k, v in sorted(by_city.items(), key=lambda x: -x[1])[:10]))

    # ham crawl önbelleği (çökme durumunda kaybı önler)
    (ROOT / "data" / "skyline_cams.json").write_text(
        json.dumps(list(cams.values()), ensure_ascii=False, indent=1))

    # --- ölçüm: örnek kameralarda gerçek çözünürlük (ilk N)
    sample = list(cams.values())[:a.probe]
    with ThreadPoolExecutor(max_workers=6) as ex:
        for ok, c in zip(ex.map(probe_cam, sample), sample):
            if ok:
                print(f"  ölçüm {c['city_label']:14s} {c['name'][:28]:28s} {c['res_w']}x{c['res_h']} @{c.get('fps')}")

    # --- DB (ölçümden ÖNCE yazılır ki çökme veri kaybettirmesin)
    sys.path.insert(0, str(ROOT))
    from cam import classify_type, conn, now
    conn_ = conn()
    n = 0
    for c in cams.values():
        rec = dict(source_key="skyline_live", external_id=c["token"][:64],
                   country=c["country_label"], city=c["city_slug"], name=c["name"],
                   area=f'{c["region"]} · {c["city_label"]}', lat=None, lon=None,
                   stream_url=c["url"], snapshot_url=None, kind="hls",
                   res_w=c.get("res_w"), res_h=c.get("res_h"), fps=c.get("fps"),
                   cam_type=classify_type(c["name"] + " " + c["cam_slug"]),
                   licence_class="C", first_seen=now(), yayin_havuzu=0)
        cols = ",".join(rec)
        try:
            conn_.execute(f"INSERT OR IGNORE INTO cameras ({cols}) VALUES ({','.join(':'+k for k in rec)})", rec)
            n += 1
        except sqlite3.Error as e:
            print("DB:", e)
    conn_.commit()
    # lisans notu (kaynak kaydı yoksa oluştur, sonra senkron çalışacak)
    conn_.execute("""INSERT OR REPLACE INTO sources
        (key,label,country,city,kind,endpoint,site,licence_class,evidence,contact,notes,verified_at,reachable)
        VALUES ('skyline_live','SkylineWebcams canlı kameralar (token''lı HLS)','INT','-','hls',
        'https://www.skylinewebcams.com/en/webcam.html','skylinewebcams.com','C',
        'ToS yeniden yayını yasaklıyor (kullanıcı kararı: lisans kısıtı üretim kararına bırakıldı).',
        'info@skylinewebcams.com','Token kamera başına; gerçek akış: hd-auth.skylinewebcams.com/livee.m3u8?a=<token>',
        '2026-10-17T15:20:00Z',1)""")
    conn_.commit()

    # --- şehir meta (etiket + Open-Meteo geocoding)
    meta = json.loads(META.read_text()) if META.exists() else {}
    cities = {}
    for c in cams.values():
        cities.setdefault(c["city_slug"], dict(label=c["city_label"], country=c["country_label"]))
    todo = [s for s in cities if not (meta.get(s) or {}).get("lat")]
    print(f"geocoding: {len(todo)} şehir")
    for slug in todo:
        info = cities[slug]
        try:
            r = subprocess.run(["curl", "-sS", "--max-time", "15",
                                "https://geocoding-api.open-meteo.com/v1/search?name="
                                f"{info['label'].replace(' ', '+')}&count=1&language=en"],
                               capture_output=True, text=True)
            res = (json.loads(r.stdout or "{}").get("results") or [{}])[0]
            meta[slug] = dict(label=info["label"], country=info["country"],
                              lat=res.get("latitude"), lon=res.get("longitude"),
                              tz=res.get("timezone") or "UTC")
        except Exception:
            meta[slug] = dict(label=info["label"], country=info["country"], lat=None, lon=None, tz="UTC")
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    conn_.close()
    print(f"DB'ye {n} kamera yazıldı. Şehir meta: {len(meta)} kayıt (data/city_meta.json)")


if __name__ == "__main__":
    main()
