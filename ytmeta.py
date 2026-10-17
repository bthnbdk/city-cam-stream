#!/usr/bin/env python3
"""
ytmeta.py — YouTube metadata şablonu üretici (şehir parametrik).

Kurallar (kullanıcı tercihleri):
 - Başlıkta Türkçe karakter kullanılabilir; hashtağlerde Türkçe karakter/emoji YOK.
 - Kamera kaynakları açıklamada ATIF ile listelenir (yalnız A / onaylı B kameralar).
 - Kanallar arası/tutarlı hashtag ve etiket yapısı; linkler düz (redirect yok).
 - Thumbnail: 1280x720, büyük punto, görselde Türkçe karakter KULLANMA, emoji yok.
"""
import json, sqlite3, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "cameras.db"

CITY = {
    "istanbul": dict(label="Istanbul", country="Turkey",
                     spots=["Bosphorus", "Taksim", "Galata Tower", "Maiden's Tower",
                            "Golden Horn", "Hagia Sophia"],
                     tz="Istanbul (UTC+03:00)"),
    "london": dict(label="London", country="United Kingdom",
                   spots=["Thames", "Tower Bridge", "West End", "The City", "Westminster"],
                   tz="London (UTC+00:00)"),
    "helsinki": dict(label="Helsinki", country="Finland",
                     spots=["Baltic Sea", "South Harbour", "Market Square"],
                     tz="Helsinki (UTC+02:00)"),
}


def attribution_block(city):
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    rows = c.execute("""SELECT DISTINCT c.source_key, s.site, s.contact, c.licence_class
                        FROM cameras c JOIN sources s ON s.key=c.source_key
                        WHERE c.city=? AND c.licence_class IN ('A','B')""", (city,)).fetchall()
    c.close()
    if not rows:
        return ("Kamera kaynakları: yayın izni süreci devam ediyor. "
                "Bu yayındaki görüntüler yalnızca izinli kaynaklardan alınır.\n"
                "(NOT: İstanbul pilotunda ölçüm anında A sınıfı kamera yok; metin yer tutucudur.)")
    lines = []
    for r in rows:
        prefix = "Açık lisanslı veri" if r["licence_class"] == "A" else "İzinli kaynak"
        lines.append(f"- {prefix}: {r['site']}")  
    return "\n".join(lines)


def build(city):
    m = CITY.get(city, dict(label=city.title(), country="", spots=[city.title()], tz="UTC"))
    spots = ", ".join(m["spots"][:3])
    out = {
        "city": city,
        "baslik_secenekleri": [
            f"🔴 {m['label']} Live Cam 24/7 | {spots}",
            f"{m['label']} LIVE | {m['spots'][0]} & {m['spots'][1]} City Camera Stream",
            f"🔴 LIVE {m['label']} — {m['spots'][0]} View | 24/7 City Cam",
        ],
        "baslik_formulu": "{emoji} {City} Live Cam 24/7 | {Spot1}, {Spot2}, {Spot3}",
        "baslik_kurallari": [
            "İlk 45 karakterde şehir + 'Live Cam' geçmeli (mobil kesme).",
            "24/7 ibaresi ilk 60 karakterde.",
            "Spesifik semt/simge adı (Taksim, Bosphorus) arama niyetini yakalar.",
            "Yıllık başlık değişimi (örn. '2026') YAPILMAZ - URL/izlenme sürekliliği bozulur.",
        ],
        "aciklama": "\n".join([
            f"{m['label']} canlı şehir kamerası — {spots} ve daha fazlası, 24 saat kesintisiz.",
            "",
            "Bu yayın birden fazla kamerayı {rot} saniyede bir yumuşak geçişle döndürür. "
            "Yerel saat, hava durumu ve gün batımı bilgisi ekranda gösterilir.".format(rot=240),
            "",
            "⏱️ Bölümler",
            "00:00 Canlı görüntü",
            "",
            "📍 Kamera konumları",
            "- " + "\n- ".join(m["spots"]),
            "",
            "📷 Kaynaklar ve atıflar (ATTRIBUTION)",
            attribution_block(city),
            "",
            "Yerel saat dilimi: " + m["tz"],
            "",
            "Bu yayın bir şehir manzarası yayınıdır; kişisel veri içermez. "
            "Görüntülerde insanların yakın plan yüzü gösterilmez.",
        ]),
        "etiketler": [
            f"{m['label'].lower()} live cam", f"{m['label'].lower()} live", "live cam 24/7",
            "city cam", "live stream", "webcam", f"{m['label'].lower()} webcam",
            m["country"].lower(), "travel", "city view", f"{m['label'].lower()} 4k",
        ],
        "hashtagler": ["#LiveCam", "#24_7", "#CityView"],
        "hashtag_kurallari": [
            "3 adet; Türkçe karakter YOK (örn. #CanliKamera değil #LiveCam).",
            "Emoji YOK. Alt satırda kanal/kaynak tanıtımı YOK.",
        ],
        "thumbnail": {
            "olcu": "1280x720 (16:9, <2 MB)",
            "metin": f"{m['label'].upper()}\nLIVE",
            "kurallar": ["En fazla 2-3 kelime, punto BÜYÜK (ekranın ~%25 yüksekliği).",
                         "Görselde Türkçe karakter ve emoji KULLANILMAZ.",
                         "Kırmızı 'LIVE' noktası + şehir silüeti; her yıl sabit kalır (marka tutarlılığı)."],
        },
        "meta_urun_alanlari": {
            "kategori": "Travel & Events",
            "dil": "tr" if city == "istanbul" else "en",
            "yapim_yili": "",
            "lisans": "Standart YouTube lisansı",
            "yorumlar": "Açık (moderasyon: küfür/bağlantı filtresi)",
            "yas_kisiti": "Yok",
        },
        "_uyari": "Açıklamadaki kaynak atıfları YALNIZCA lisansı A veya onaylı B olan kameralar için üretilir.",
    }
    outdir = ROOT / "data" / city; outdir.mkdir(parents=True, exist_ok=True)
    p = outdir / f"youtube_meta_{city}.json"
    p.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    (outdir / f"youtube_aciklama_{city}.txt").write_text(out["aciklama"])
    print(f"meta: {p}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--city", default="istanbul")
    build(ap.parse_args().city)
