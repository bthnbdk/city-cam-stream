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
# ÖLÇÜMLE ELENEN KAYNAKLAR (sitede yayınlanmaz) — hepsi kare bazlı doğrulama ile:
#   skyline_live : segment adı 'copyright_violation-*.ts'; karede gerçek görüntü değil logo kartı
#   yt_live      : kullanıcı kararı — YouTube hiç kullanılmayacak
#   earthcam     : 304 kameranın 291'i ffmpeg ile kare vermedi (2/100 tarayıcıda oynadı)
EXCLUDED_SOURCES = {"skyline_live", "yt_live", "earthcam"}

# Yayın kapısı: yalnızca ÖLÇÜMLE "gerçekten oynuyor" çıkan kameralar siteye girer
# (reachable=1). Doğrulanmamış kayıtlar DB'de kalır, yayına çıkmaz.

CITY_META = {
    "istanbul": dict(label="Istanbul", country="TR", tz="Europe/Istanbul", lat=41.013, lon=28.978),
    "london": dict(label="London", country="UK", tz="Europe/London", lat=51.507, lon=-0.128),
    "helsinki": dict(label="Helsinki", country="FI", tz="Europe/Helsinki", lat=60.170, lon=24.940),
    "tampere": dict(label="Tampere", country="FI", tz="Europe/Helsinki", lat=61.498, lon=23.760),
    "turku": dict(label="Turku", country="FI", tz="Europe/Helsinki", lat=60.451, lon=22.268),
    "oulu": dict(label="Oulu", country="FI", tz="Europe/Helsinki", lat=65.012, lon=25.465),
    "finland": dict(label="Finland (road cams)", country="FI", tz="Europe/Helsinki", lat=62.5, lon=25.5),
}


META_FILE = ROOT / "data" / "city_meta.json"


def load_city_meta():
    """Toplayıcıların yazdığı şehir meta verisi (etiket + lat/lon/tz) koda göre önceliklidir."""
    if META_FILE.exists():
        try:
            return json.loads(META_FILE.read_text())
        except Exception:
            return {}
    return {}


def slug(s):
    s = s.lower().replace("ı", "i").replace("ş", "s").replace("ğ", "g").replace("ü", "u")
    s = s.replace("ö", "o").replace("ç", "c").replace("â", "a")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def main():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    rows = c.execute("""
        SELECT c.id, c.source_key, c.city, c.name, c.area, c.lat, c.lon, c.stream_url,
               c.snapshot_url, c.kind, c.res_w, c.res_h, c.fps, c.cam_type, c.licence_class,
               c.q_total, c.reachable, c.uptime_7d, c.uptime_samples,
               COALESCE(s.reachable, 0) AS src_reachable
        FROM cameras c LEFT JOIN sources s ON s.key = c.source_key
        WHERE c.source_key NOT IN ('skyline_live','yt_live','earthcam')
          AND c.reachable = 1
          AND ((c.stream_url IS NOT NULL AND c.stream_url <> '')
               OR (c.snapshot_url IS NOT NULL AND c.snapshot_url <> ''))
        ORDER BY src_reachable DESC,
                 CASE WHEN c.reachable = 1 THEN 0 WHEN c.reachable IS NULL THEN 1 ELSE 2 END,
                 CASE c.licence_class WHEN 'A' THEN 0 WHEN 'B' THEN 1 ELSE 2 END,
                 COALESCE(c.q_total, 0) DESC, c.id
    """).fetchall()
    CM = load_city_meta()
    cities = {}
    for r in rows:
        key = slug(r["city"] or "diger")
        cities.setdefault(key, []).append(r)
    index, total = [], 0
    for key, items in sorted(cities.items(), key=lambda x: -len(x[1])):
        meta = dict(CM.get(key) or CITY_META.get(
            key, dict(label=(key or "?").title(), country="", tz="UTC", lat=0, lon=0)))
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

    # --- şehir dizini sayfası (site/cities.html)
    rows_html = "".join(
        f'<tr><td><a href="index.html?city={c["city"]}&rotation=5" style="color:#4cc2ff;'
        f'text-decoration:none">{c["label"]}</a></td><td>{c["country"]}</td>'
        f'<td class="n">{c["total"]}</td><td>{c["tz"]}</td>'
        f'<td><code>?city={c["city"]}&amp;rotation=5</code></td></tr>'
        for c in sorted(index, key=lambda x: -x["total"]))
    (ROOT / "site" / "cities.html").write_text(f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Available cities — City Cam Stream</title>
<style>
body{{margin:0;background:#0c1116;color:#e8eef5;font:15px/1.5 system-ui,-apple-system,'Segoe UI',sans-serif}}
.wrap{{max-width:900px;margin:0 auto;padding:22px 14px 60px}}
h1{{font-size:22px;margin:0 0 4px}} p.sub{{color:#93a2b3;margin:0 0 16px}}
table{{width:100%;border-collapse:collapse;font-size:14px}}
th,td{{border-bottom:1px solid #223040;padding:7px 9px;text-align:left}}
th{{color:#93a2b3;font-size:12px;text-transform:uppercase;letter-spacing:.04em}}
td.n{{text-align:right;font-variant-numeric:tabular-nums;color:#4cc2ff;font-weight:600}}
code{{background:#0a1219;padding:1px 5px;border-radius:5px}}
a.back{{color:#4cc2ff;text-decoration:none}}
</style></head><body><div class="wrap">
<h1>Available cities</h1>
<p class="sub">{len(index)} cities · {total} cameras. Click a city to open the rotation player
(default rotation 5 s). Add <code>&amp;mode=grid</code>, <code>&amp;pool=a</code> or
<code>&amp;sound=1</code> to the URL. <a class="back" href="index.html?city={index[0]['city']}&rotation=5">open player →</a></p>
<table><tr><th>City</th><th>Country</th><th class="n">Cameras</th><th>Timezone</th><th>URL parameter</th></tr>
{rows_html}</table></div></body></html>""", encoding="utf-8")

    # artık yayında olmayan şehir dosyalarını sil (ölü kaynak kalmasın)
    live = {f"{i['city']}.json" for i in index}
    for f in OUT.glob("*.json"):
        if f.name not in live and f.name not in ("cities.json", "stats.json"):
            f.unlink()
    print(f"export: {len(cities)} şehir dosyası, {total} kamera siteye aktarıldı (+ cities.html)")
    for i in sorted(index, key=lambda x: -x["total"])[:8]:
        print(f"  {i['city']:10s} {i['count']:4d}/{i['total']:<5d} {i['label']}")
    c.close()


if __name__ == "__main__":
    main()
