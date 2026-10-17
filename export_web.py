#!/usr/bin/env python3
"""
export_web.py — SQLite kamera veritabanını sitenin okuyacağı JSON dosyalarına döker.

Çıktı:
  site/data/cities.json       şehir dizini (etiket, saat dilimi, merkez, kamera sayısı)
  site/data/<slug>.json       şehir kameraları (yalnız oynatılabilir URL'i olanlar)
  site/data/stats.json        özet istatistikler (rapor sayfası için)

Not: Lisans sınıfı JSON'da görünür kalır; web uygulaması C sınıfı kamerayı
'pool=a' filtresiyle gizler ve her zaman rozet gösterir.
"""
import json, re, sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "cameras.db"
OUT = ROOT / "site" / "data"; OUT.mkdir(parents=True, exist_ok=True)
MAX_PER_CITY = 400

CITY_META = {
    "istanbul": dict(label="Istanbul", country="TR", tz="Europe/Istanbul", lat=41.013, lon=28.978),
    "london": dict(label="London", country="UK", tz="Europe/London", lat=51.507, lon=-0.128),
    "helsinki": dict(label="Helsinki", country="FI", tz="Europe/Helsinki", lat=60.170, lon=24.940),
    "tampere": dict(label="Tampere", country="FI", tz="Europe/Helsinki", lat=61.498, lon=23.760),
    "turku": dict(label="Turku", country="FI", tz="Europe/Helsinki", lat=60.451, lon=22.268),
    "oulu": dict(label="Oulu", country="FI", tz="Europe/Helsinki", lat=65.012, lon=25.465),
    "finland": dict(label="Finland (road cams)", country="FI", tz="Europe/Helsinki", lat=62.5, lon=25.5),
}


def slug(s):
    s = s.lower().replace("ı", "i").replace("ş", "s").replace("ğ", "g").replace("ü", "u")
    s = s.replace("ö", "o").replace("ç", "c").replace("â", "a")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def main():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    rows = c.execute("""
        SELECT id, source_key, city, name, area, lat, lon, stream_url, snapshot_url, kind,
               res_w, res_h, fps, cam_type, licence_class, q_total, reachable, uptime_7d,
               uptime_samples
        FROM cameras
        WHERE (stream_url IS NOT NULL AND stream_url <> '')
           OR (snapshot_url IS NOT NULL AND snapshot_url <> '')
        ORDER BY CASE licence_class WHEN 'A' THEN 0 WHEN 'B' THEN 1 ELSE 2 END,
                 COALESCE(q_total, 0) DESC, id
    """).fetchall()
    cities = {}
    for r in rows:
        key = slug(r["city"] or "diger")
        cities.setdefault(key, []).append(r)
    index, total = [], 0
    for key, items in sorted(cities.items(), key=lambda x: -len(x[1])):
        meta = CITY_META.get(key, dict(label=(key or "?").title(), country="", tz="UTC", lat=0, lon=0))
        keep = items[:MAX_PER_CITY]
        cam_list = [{
            "id": r["id"], "name": r["name"], "area": r["area"] or "",
            "lat": round(r["lat"], 5) if r["lat"] else None,
            "lon": round(r["lon"], 5) if r["lon"] else None,
            "url": r["stream_url"] or r["snapshot_url"],
            "kind": r["kind"] if r["stream_url"] else "snapshot",
            "res": f'{r["res_w"]}x{r["res_h"]}' if r["res_w"] else None,
            "fps": r["fps"], "type": r["cam_type"],
            "src": r["source_key"], "lic": r["licence_class"],
            "score": r["q_total"], "up": r["uptime_7d"],
        } for r in keep]
        doc = dict(city=key, **meta, count=len(cam_list), total_available=len(items),
                   cams=cam_list)
        (OUT / f"{key}.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
        index.append(dict(city=key, label=meta["label"], country=meta["country"],
                          tz=meta["tz"], lat=meta["lat"], lon=meta["lon"],
                          count=len(cam_list), total=len(items)))
        total += len(cam_list)
    (OUT / "cities.json").write_text(json.dumps(
        dict(cities=sorted(index, key=lambda x: -x["total"]),
             licence_note=("A = açık lisans/izinli · B = izin bekliyor · C = izin yok/belirsiz. "
                           "Varsayılan görünüm tüm kameraları gösterir ve lisans rozetini "
                           "ekranda tutar; yayına almadan önce yalnız A/onaylı B kullanın "
                           "(pool=a filtreler).")), ensure_ascii=False, separators=(",", ":")))
    stats = dict(
        kamera=sum(len(v) for v in cities.values()),
        sehir=len(cities),
        kaynaklar=[dict(src=r[0], n=r[1], a=r[2]) for r in c.execute(
            "SELECT source_key, COUNT(*), SUM(CASE WHEN licence_class='A' THEN 1 ELSE 0 END) "
            "FROM cameras GROUP BY 1 ORDER BY 2 DESC")],
        tip_dagilimi=dict(c.execute("SELECT cam_type, COUNT(*) FROM cameras GROUP BY 1 ORDER BY 2 DESC")),
        eksik_uptime_ornegi=c.execute("SELECT COUNT(*) FROM cameras WHERE uptime_samples IS NULL").fetchone()[0],
    )
    (OUT / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1))
    print(f"export: {len(cities)} şehir dosyası, {total} kamera siteye aktarıldı")
    for i in sorted(index, key=lambda x: -x["total"])[:8]:
        print(f"  {i['city']:10s} {i['count']:4d}/{i['total']:<5d} {i['label']}")
    c.close()


if __name__ == "__main__":
    main()
