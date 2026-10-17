#!/usr/bin/env python3
"""
fetch_drivebc.py — DriveBC (British Columbia, Kanada) resmî kamera ağı. ANAHTARSIZ.

Kaynak: https://www.drivebc.ca/api/webcams/   (herkese açık JSON, 1000+ kamera)
Alanlar: id, name, caption, links.imageDisplay, location.coordinates, region_name, highway,
         update_period_mean, is_on, should_appear, marked_stale

Tür: anlık kare (kind='snapshot') — görüntü periyodik güncellenir, video akışı yoktur.
Bu yüzden Finlandiya (Digitraffic) gibi 'near-live' kategorisindedir; stabil ve token'sızdır.

Kullanım: python3 discovery/fetch_drivebc.py [--limit 1100]
"""
import argparse, json, re, sqlite3, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "cameras.db"
API = "https://www.drivebc.ca/api/webcams/"
BASE = "https://www.drivebc.ca"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

# BC'de şehir ataması için yakınlık merkezleri (km yarıçap)
BC_CITIES = [
    ("vancouver", 49.283, -123.121, 35), ("victoria", 48.428, -123.365, 30),
    ("kelowna", 49.888, -119.496, 35), ("kamloops", 50.675, -120.340, 35),
    ("prince-george", 53.917, -122.750, 40), ("whistler", 50.117, -122.955, 30),
    ("nanaimo", 49.166, -123.940, 30), ("abbotsford", 49.050, -122.305, 25),
    ("surrey", 49.105, -122.800, 20), ("cranbrook", 49.512, -115.769, 35),
    ("fort-st-john", 56.252, -120.846, 45), ("terrace", 54.518, -128.600, 40),
]


def city_for(lat, lon, region):
    if lat is None or lon is None:
        return "british-columbia"
    for name, clat, clon, km in BC_CITIES:
        if abs(lat - clat) <= km / 111.0 and abs(lon - clon) <= km / (111.0 * 0.62):
            return name
    return "british-columbia"


def curl(url, timeout=25):
    return subprocess.run(["curl", "-sSL", "--compressed", "--max-time", str(timeout), "-A", UA, url],
                          capture_output=True, text=True).stdout


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--limit", type=int, default=1100)
    a = ap.parse_args()
    d = json.loads(curl(API, timeout=45))
    print(f"DriveBC API: {len(d)} kamera")
    sys.path.insert(0, str(ROOT))
    from cam import classify_type, conn, now
    c = conn()
    c.execute("""INSERT OR REPLACE INTO sources
      (key,label,country,city,kind,endpoint,site,licence_class,evidence,contact,notes,verified_at,reachable)
      VALUES ('drivebc','DriveBC — British Columbia resmî yol kameraları (Kanada)','CA','-','snapshot',
      'https://www.drivebc.ca/api/webcams/','drivebc.ca','A',
      'Devlet (BC Ministry of Transportation) kamuya açık veri servisi; anahtarsız, doğrudan kare ucu.',
      'drivebc@gov.bc.ca','kind=snapshot; links.imageDisplay goreli yol -> https://www.drivebc.ca + yol',
      '2026-10-17T16:40:00Z',1)""")
    n = 0
    for x in d[:a.limit]:
        if not x.get("should_appear", True) or x.get("marked_stale"):
            continue
        coord = ((x.get("location") or {}).get("coordinates") or [None, None])
        lon, lat = (coord + [None, None])[:2] if coord else (None, None)
        img = ((x.get("links") or {}).get("imageDisplay") or "")
        if not img:
            continue
        url = img if img.startswith("http") else BASE + img
        city = city_for(lat, lon, x.get("region_name"))
        rec = dict(source_key="drivebc", external_id=str(x.get("id")),
                   country="Canada", city=city,
                   name=(x.get("name_override") or x.get("name") or "")[:110],
                   area=((x.get("highway_description") or x.get("highway") or "") + " · " +
                         (x.get("region_name") or ""))[:70],
                   lat=lat, lon=lon, stream_url=None, snapshot_url=url, kind="snapshot",
                   res_w=None, res_h=None, fps=None,
                   cam_type=classify_type((x.get("name") or "") + " " + (x.get("highway_description") or "")),
                   licence_class="A", first_seen=now(), yayin_havuzu=1)
        cols = ",".join(rec)
        try:
            c.execute(f"INSERT OR IGNORE INTO cameras ({cols}) VALUES ({','.join(':'+k for k in rec)})", rec)
            n += 1
        except sqlite3.Error as e:
            print("DB:", e)
    c.commit(); c.close()
    print(f"DB'ye {n} DriveBC kamerası yazıldı (kind=snapshot, lisans A)")


if __name__ == "__main__":
    main()
