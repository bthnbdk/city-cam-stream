#!/usr/bin/env python3
"""
fetch_earthcam.py — EarthCam kamera dizinini çeker (anahtarsız, herkese açık API).

Kaynak: https://www.earthcam.com/api/mapsearch/get_locations_network.php?r=ecn&a=fetch
        (mapsearch sayfasının kendi kullandığı JSON ucu)
Dönen alanlar: name, url (kamera sayfası), posn [lat,lon], city, state, country, id

Neden 'proxy' türü:
  Akış URL'i kısa ömürlü bir token taşır:  videos-3.earthcam.com/fecnetwork/<id>.flv/playlist.m3u8?t=<token>&td=<YYYYMMDDHHMM>
  Bu yüzden sitede ham URL saklanmaz; kamera SAYFA url'i saklanır ve Netlify Function
  (netlify/functions/stream.mjs) her istekte sayfayı sunucu tarafında çekip taze token'ı
  ayıklar. CDN CORS başlıkları 'Access-Control-Allow-Origin: *' veriyor (ölçüldü) -> hls.js oynatabilir.

Kullanım: python3 discovery/fetch_earthcam.py [--limit 400]
"""
import argparse, json, re, sqlite3, subprocess, sys, html
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "cameras.db"
API = "https://www.earthcam.com/api/mapsearch/get_locations_network.php?r=ecn&a=fetch"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")
STREAM_RE = re.compile(r'"stream":"(https:\\/\\/videos-[^"]+playlist\.m3u8[^"]*)"')
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)


def curl(url, timeout=25):
    r = subprocess.run(["curl", "-sSL", "--compressed", "--max-time", str(timeout), "-A", UA, url],
                       capture_output=True, text=True)
    return r.stdout


def city_slug(s):
    s = (s or "").strip().lower()
    for a, b in (("ı", "i"), ("ş", "s"), ("ğ", "g"), ("ü", "u"), ("ö", "o"), ("ç", "c"), ("é", "e"),
                 (" ", "-"), ("'", ""), (".", "")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9-]+", "-", s).strip("-")


def parse_cam(page):
    """Kamera sayfasından taze akış URL'i + başlık çıkarır (proxy function ile aynı mantık)."""
    m = STREAM_RE.search(page)
    t = TITLE_RE.search(page)
    title = html.unescape(re.sub(r"\s+", " ", t.group(1))).strip() if t else ""
    title = re.sub(r"\s*[-|]\s*EarthCam.*$", "", title, flags=re.I)
    return (m.group(1).replace("\\/", "/") if m else None), title


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=400)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    raw = curl(API, timeout=40)
    d = json.loads(raw)
    places = []
    for grp in d.get("data", []):
        for k, v in grp.items():
            if isinstance(v, list):
                places += v
    seen, items = set(), []
    for p in places:
        u = (p.get("url") or "").strip()
        if not u or u in seen:
            continue
        if not re.search(r"^https?://(www\.)?(my)?earthcam\.com/", u):
            continue  # yalnız EarthCam tarafından barındırılan kameralar
        seen.add(u)
        posn = p.get("posn") or [None, None]
        items.append(dict(
            page=u, name=html.unescape(p.get("name") or "").strip()[:110],
            lat=float(posn[0]) if posn[0] else None,
            lon=float(posn[1]) if posn[1] else None,
            city=p.get("city") or "", state=p.get("state") or "", country=p.get("country") or "",
            ecid=p.get("id") or "",
        ))
    items = items[:a.limit]
    print(f"dizin: {len(items)} EarthCam kamerası (toplam {len(places)} kayıt)")

    # sayfaları çek: taze akış var mı + gerçek başlık
    def probe(it):
        h = curl(it["page"], timeout=20)
        stream, title = parse_cam(h)
        it["stream_now"] = stream
        it["title"] = title or it["name"]
        return it

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        items = list(ex.map(probe, items))
    live = [i for i in items if i["stream_now"]]
    print(f"taze akış bulunan: {len(live)}/{len(items)}")

    sys.path.insert(0, str(ROOT))
    from cam import classify_type, conn, now
    c = conn()
    c.execute("""INSERT OR REPLACE INTO sources
      (key,label,country,city,kind,endpoint,site,licence_class,evidence,contact,notes,verified_at,reachable)
      VALUES ('earthcam','EarthCam kameraları (token yenilemeli HLS)','INT','-','proxy',
      'https://www.earthcam.com/api/mapsearch/get_locations_network.php?r=ecn&a=fetch',
      'earthcam.com','C',
      'EarthCam ToS: yeniden yayın izni yok. Kullanıcı kararı: lisans kısıtı üretim kararına bırakıldı.',
      'support@earthcam.com',
      'Akış URL token ile gelir (td=YYYYMMDDHHMM). netlify/functions/stream.mjs sunucu tarafında tazeler. CDN CORS: *',
      '2026-10-17T16:10:00Z',1)""")
    n = 0
    for it in items:
        city = city_slug(it["city"] or it["state"] or it["country"] or "unknown")
        rec = dict(source_key="earthcam", external_id=it["ecid"] or it["page"][-48:],
                   country=it["country"], city=city, name=it["title"][:110],
                   area=" · ".join(x for x in (it["city"], it["state"], it["country"]) if x)[:70],
                   lat=it["lat"], lon=it["lon"], stream_url=it["page"], snapshot_url=None,
                   kind="proxy", res_w=None, res_h=None, fps=None,
                   cam_type=classify_type(it["title"] + " " + (it["city"] or "")),
                   licence_class="C", first_seen=now(), yayin_havuzu=0,
                   probe_note=("taze akis var" if it["stream_now"] else "sayfada akis yok"))
        cols = ",".join(rec)
        try:
            c.execute(f"INSERT OR IGNORE INTO cameras ({cols}) VALUES ({','.join(':'+k for k in rec)})", rec)
            n += 1
        except sqlite3.Error as e:
            print("DB:", e)
    c.commit(); c.close()
    (ROOT / "data" / "earthcam_dir.json").write_text(json.dumps(items, ensure_ascii=False, indent=1))
    print(f"DB'ye {n} EarthCam kaydı yazıldı (kind=proxy, url=kamera sayfası)")


if __name__ == "__main__":
    main()
