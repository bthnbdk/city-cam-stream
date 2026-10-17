#!/usr/bin/env python3
"""Kamera kaynak kayıt defteri + LİSANS SINIFLANDIRMA kuralları (kanıt zorunlu).

Sınıflar:
  A = Yeniden yayına açıkça izin var (açık lisans / kamu verisi / "restream allowed")
  B = Sahibinden izin alınabilir (iletişim + e-posta taslağı hazır) -> İZİN BEKLİYOR
  C = İzin yok / belirsiz / ToS yasaklıyor -> KULLANMA

Kural: Bir kaynak A sayılabilmesi için kanıt metni (evidence) ZORUNLUDUR.
Kanıt yoksa otomatik olarak C'ye düşer (izin yok varsayımı).
"""
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Source:
    key: str
    label: str
    country: str
    city: str
    kind: str              # hls | mp4 | snapshot | embed | directory
    endpoint: str          # teknik uç nokta (keşifte kullanılır)
    site: str              # kaynak site (künye)
    licence_class: str     # A | B | C
    evidence: str          # lisans sınıfının KANITI (alıntı/URL) - zorunlu
    contact: Optional[str] = None      # B sınıfı için izin adresi
    notes: str = ""
    verified_at: str = ""              # erişim testi zamanı (ISO)
    reachable: Optional[bool] = None   # bu makineden erişilebildi mi (test edildi)

    def __post_init__(self):
        if self.licence_class in ("A", "B") and not self.evidence.strip():
            self.licence_class = "C"
            self.notes += " [KANITSIZ -> C'ye düşürüldü]"


# ---------------------------------------------------------------------------
# PİLOT: İSTANBUL
# ---------------------------------------------------------------------------
SOURCES = [
    Source(
        key="ibb_tkm", label="İBB Trafik Kameraları (TKM)", country="TR", city="istanbul",
        kind="hls", endpoint="https://sehirharitasigateway.ibb.gov.tr/api/DUoq/api/Tkm/trafikKameralari",
        site="harita.istanbul (İstanbul Büyükşehir Belediyesi)",
        licence_class="C",  # belirsiz -> izin yok varsayımı
        evidence=("Açık lisans beyanı YOK. Servis kamuya açık İBB web servisi; "
                  "kullanım şartları/atıf zorunluluğu yayınlanmamış. İzin alınmadan yeniden yayın = belirsiz risk."),
        contact="İBB Bilgi İşlem Dairesi / Açık Veri: https://acikveri.ibb.istanbul ; basin@ibb.istanbul",
        notes=("635 kamera. videoUrl: https://hls.ibb.gov.tr/tkm{2,4}/hls/{id}.stream/playlist.m3u8 ; "
               "anlık kare: https://tkmservices.ibb.gov.tr/web/Handlers/CameraImage.ashx?pno=0..2&cno={id} (340x213 PNG). "
               "B SINIFINA ADAY: kamu kurumu, açık veri talebi karşılanabilir -> yazılı izin taslağı hazır."),
        verified_at="2026-10-17T14:20:00Z", reachable=False,
    ),
    Source(
        key="tfl_jamcam", label="TfL JamCams (Londra Trafik Kameraları)", country="UK", city="london",
        kind="mp4", endpoint="https://api.tfl.gov.uk/Place/Type/JamCam",
        site="Transport for London (tfl.gov.uk)",
        licence_class="A",
        evidence=("'These terms and conditions apply to TfL's free Transport Data Service. These licence terms and "
                  "conditions apply to TfL's free transport data service and are based on version 2.0 of the Open "
                  "Government Licence with specific amendments for Transport for London (the Licence).' "
                  "— https://tfl.gov.uk/corporate/terms-and-conditions/transport-data-service (17.10.2026). "
                  "OGL v2 ticari kullanıma izin verir, atıf şartı vardır."),
        contact="TfL Open Data: datastore@tfl.gov.uk",
        notes=("890 kamera (811'i 'available'), 352x288 mp4 (~10.7 sn klip, 25fps, ~98 kbps). "
               "AÇIK MADDE: JamCam video/karelerinin bu 'Transport Data Service' lisansı kapsamında olduğu "
               "TfL'den yazılı teyit edilmeli (tek satırlık e-posta). Çözünürlük 24/7 FHD yayına uygun DEĞİL."),
        verified_at="2026-10-17T14:10:00Z", reachable=True,
    ),
    Source(
        key="digitraffic", label="Fintraffic Digitraffic (Finlandiya Yol Kameraları)", country="FI", city="helsinki",
        kind="snapshot", endpoint="https://tie.digitraffic.fi/api/weathercam/v1/stations",
        site="digitraffic.fi (Fintraffic)",
        licence_class="A",
        evidence=("'Fintraffic's open data is licensed under the Creative Commons 4.0 By license. "
                  "It gives the right to distribute, remix, tweak, and build upon our data, even commercially, "
                  "as long as you credit the source.' — https://www.digitraffic.fi/en/terms-of-service/ (17.10.2026)"),
        contact="digitraffic@fintraffic.fi",
        notes=("1280x720 JPEG anlık kare (akış değil, ~dakikalar aralıklı). A sınıfı ama FORMAT kısıtı: "
               "gerçek video değil -> 'near-live' modu / PiP / hava katmanı için uygun."),
        verified_at="2026-10-17T14:12:00Z", reachable=True,
    ),
    Source(
        key="skylinewebcams", label="SkylineWebcams (VisioRay)", country="INT", city="-",
        kind="embed", endpoint="https://www.skylinewebcams.com/en/webcam.html",
        site="skylinewebcams.com",
        licence_class="C",
        evidence=("ToS: '...it cannot be used, modified, adapted, reformatted, downloaded, reproduced (even in partial form), "
                  "transmitted, published, transferred, copied, sold, exploited, used to create videos and/or montages...' ve "
                  "'It is, furthermore, prohibited to reproduce frames that are generated by the webcams...' "
                  "Paylaşım yalnızca sitenin kendi paylaşım linkleriyle. — https://www.skylinewebcams.com/en/terms-of-use.html"),
        contact="info@skylinewebcams.com (ticari lisans görüşmesi mümkün)",
        notes="İstanbul'da yalnızca 1 kamera kaldı (Marmara bölgesi: Nilüfer/Bursa). Ticari lisans = B'ye dönüşebilir ama ücretli.",
        verified_at="2026-10-17T14:15:00Z", reachable=True,
    ),
    Source(
        key="windy", label="Windy Webcams API v3", country="INT", city="-",
        kind="directory", endpoint="https://api.windy.com/webcams/api/v3/webcams",
        site="windy.com",
        licence_class="C",
        evidence=("Anahtarsız çağrı 403: 'Missing Header x-windy-api-key'. Lisans/atıf koşulları anahtar kullanıcı sözleşmesine bağlı; "
                  "kamera içeriği yükleyen kullanıcıya ait -> yeniden yayın izni ayrıca alınmalı. Kanıt yok -> C."),
        contact="support@windy.com",
        notes=("ÜCRETSİZ API anahtarı kaydı ile erişilir (ücretli plan şart değil). Küresel en geniş webcam dizini; "
               "her kayıt için player/url alanları döner. Kritik izin adımı: kamera sahibinden yazılı onay."),
        verified_at="2026-10-17T14:05:00Z", reachable=False,
    ),
    Source(
        key="webcamtaxi", label="WebcamTaxi (dizin)", country="INT", city="-",
        kind="directory", endpoint="https://www.webcamtaxi.com/en/turkey/istanbul.html",
        site="webcamtaxi.com",
        licence_class="C",
        evidence="Dizin sitesi; yayın hakları ilgili kamera sahibinde. Sitede açık yeniden yayın izni yok. Kanıt yok -> C.",
        contact="-",
        notes="İstanbul için listelenen örnek: 'Arise Hotel Golden Horn, Istanbul' (otel kamerası -> doğrudan otelden izin alınabilir, B adayı).",
        verified_at="2026-10-17T14:08:00Z", reachable=True,
    ),
    Source(
        key="youtube_live", label="YouTube 24/7 canlı kamera kanalları (rakip/istek ölçümü)", country="INT", city="-",
        kind="embed", endpoint="https://www.youtube.com/results?search_query=live+cam",
        site="youtube.com",
        licence_class="C",
        evidence=("YouTube ToS: başka bir yayıncının canlı yayınını yeniden yayınlamak (restream) izin gerektirir; "
                  "üçüncü taraf içeriğinin kopyalanması yasak. Kanıt yok -> C."
                  " ANCAK: yayıncı ile anlaşma = B yolu."),
        contact="-",
        notes=("İstanbul örneği (canlı, ölçüldü 17.10.2026): 'Istanbul: Golden Horn Live: Galata & Kız Kulesi' — "
               "1080p30, 6.899 eşzamanlı izleyici. TALEP KANITI. Bu kanallar büyük olasılıkla İBB HLS'ini yeniden yayınlıyor."),
        verified_at="2026-10-17T14:25:00Z", reachable=True,
    ),
]


def as_dicts():
    return [asdict(s) for s in SOURCES]


def by_key(k):
    for s in SOURCES:
        if s.key == k:
            return s
    return None
