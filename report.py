#!/usr/bin/env python3
"""report.py — Şehir kamerası hattı için mobil-öncelikli HTML rapor üretir."""
import json, sqlite3, shutil, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "cameras.db"
OUT = ROOT / "data" / "report"; OUT.mkdir(parents=True, exist_ok=True)
ASSETS = OUT / "assets"; ASSETS.mkdir(exist_ok=True)


def esc(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def load_demand():
    rows = {}
    for f in ("/tmp/yt_demand2.jsonl", "/tmp/yt_demand.jsonl"):
        p = Path(f)
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(line)
                    if r.get("city"):
                        rows.setdefault(r["city"], {}).update({k: v for k, v in r.items() if v is not None})
                except Exception:
                    pass
    return rows


def build():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    src = c.execute("SELECT * FROM sources ORDER BY licence_class, key").fetchall()
    counts = c.execute("""SELECT source_key, city, licence_class, COUNT(*) n, SUM(reachable) er,
                          ROUND(AVG(q_total),2) ort FROM cameras GROUP BY 1,2,3 ORDER BY n DESC""").fetchall()
    ibb = c.execute("""SELECT name, cam_type, res_w, res_h, fps, probe_note, q_total
                       FROM cameras WHERE city='istanbul' ORDER BY id LIMIT 14""").fetchall()
    ibb_total = c.execute("SELECT COUNT(*) FROM cameras WHERE city='istanbul'").fetchone()[0]
    ibb_ok = c.execute("SELECT COUNT(*) FROM cameras WHERE city='istanbul' AND reachable=1").fetchone()[0]
    scores = c.execute("""SELECT source_key, ROUND(AVG(q_total),2) ort, COUNT(*) n,
                          SUM(CASE WHEN reachable=1 THEN 1 ELSE 0 END) er
                          FROM cameras WHERE q_total IS NOT NULL GROUP BY source_key""").fetchall()
    typ = dict(c.execute("SELECT cam_type, COUNT(*) FROM cameras GROUP BY 1").fetchall())
    c.close()
    cities = json.loads((ROOT / "data" / "cities.json").read_text(encoding="utf-8"))
    demand = load_demand()
    meta = json.loads((ROOT / "data" / "istanbul" / "youtube_meta_istanbul.json").read_text(encoding="utf-8"))
    for m in ("montage_london_tfl.png", "montage_helsinki_fi.png", "montage_istanbul_ibb.png"):
        p = ROOT / "data" / m
        if p.exists():
            shutil.copy(p, ASSETS / m)

    def demand_cell(city):
        d = demand.get(city.lower(), {})
        if d.get("concurrent_viewers") and d["concurrent_viewers"] != "NA":
            return f"{d['concurrent_viewers']} eşzamanlı (top canlı)"
        if d.get("n_live_in_top12") is not None:
            return f"{d['n_live_in_top12']}/12 canlı sonuç"
        if d.get("n_live_top10") is not None:
            return f"{d['n_live_top10']}/10 canlı sonuç"
        return "ölçülmedi"

    src_rows = "".join(f"""<tr><td><b>{esc(s['site'])}</b><div class="muted">{esc(s['label'])}</div></td>
      <td><span class="badge {s['licence_class']}">{s['licence_class']}</span></td>
      <td class="ev">{esc(s['evidence'][:420])}</td></tr>""" for s in src)

    count_rows = "".join(f"""<tr><td>{esc(r['source_key'])}</td><td>{esc(r['city'])}</td>
      <td><span class="badge {r['licence_class']}">{r['licence_class']}</span></td>
      <td class="num">{r['n']}</td><td class="num">{r['er'] if r['er'] is not None else '-'}</td>
      <td class="num">{r['ort'] if r['ort'] is not None else '-'}</td></tr>""" for r in counts)

    ibb_rows = "".join(f"""<tr><td>{esc(r['name'])}</td><td>{esc(r['cam_type'])}</td>
      <td class="num">{r['res_w'] or '-'}×{r['res_h'] or '-'}</td><td class="num">{r['fps'] or '-'}</td>
      <td class="muted">{esc(r['probe_note'])}</td></tr>""" for r in ibb)

    score_rows = "".join(f"""<tr><td>{esc(r['source_key'])}</td><td class="num">{r['n']}</td>
      <td class="num">{r['er']}/{r['n']}</td><td class="num">{r['ort']}</td></tr>""" for r in scores)

    city_rows = "".join(
        f'<tr><td class="num">{x["sira"]}</td><td><b>{esc(x["sehir"])}</b>'
        f'<div class="muted">{esc(x["ulke"])}</div></td><td>{esc(x["kamera_kaynagi"])}</td>'
        f'<td><span class="badge {x["lisans_durumu"][:1]}">{esc(x["lisans_durumu"].split(":")[0])}</span></td>'
        f'<td>{esc(x["olcum"])}</td><td class="risk">{esc(x["risk"])}</td>'
        f'<td>{esc(x["sonraki_adim"])}</td><td>{esc(demand_cell(x["sehir"]))}</td></tr>'
        for x in cities["aday_sehirler"])

    typ_rows = "".join(f"<li>{esc(k)}: <b>{v}</b></li>" for k, v in sorted(typ.items(), key=lambda x: -x[1]))

    demand_rows = "".join(
        f'<tr><td><b>{esc(d["sehir"])}</b></td><td>{esc(d["kamera"])}</td>'
        f'<td class="num">{d["eszamanli_izleyici"]:,}</td><td class="num">{d["kanal_abone"]:,}</td>'
        f'<td class="num">{d["canli_sonuc_top10"]}/10</td></tr>'
        for d in cities.get("talep_olcumleri", []))

    html = f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Canlı Şehir Kamerası Yayın Sistemi — Pilot: İstanbul (Keşif & Tasarım)</title>
<style>
:root{{--bg:#0c1116;--card:#141b23;--fg:#e8eef5;--mut:#93a2b3;--acc:#4cc2ff;--warn:#ffb020;--bad:#ff5c5c;--ok:#3ddc84}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}}
.wrap{{max-width:1100px;margin:0 auto;padding:18px 14px 60px}}
h1{{font-size:26px;line-height:1.25;margin:6px 0 4px}}
h2{{font-size:20px;margin:34px 0 10px;padding-bottom:6px;border-bottom:1px solid #24303c}}
h3{{font-size:17px;margin:20px 0 6px;color:var(--acc)}}
.sub{{color:var(--mut);font-size:14px}}
.card{{background:var(--card);border:1px solid #223040;border-radius:14px;padding:14px;margin:12px 0}}
.badge{{display:inline-block;min-width:26px;text-align:center;font-weight:700;border-radius:8px;padding:2px 8px;color:#06121a}}
.badge.A{{background:var(--ok)}} .badge.B{{background:var(--warn)}} .badge.C{{background:var(--bad);color:#fff}}
.badge.D,.badge.d,.badge.K,.badge.T{{background:#7f8fa3;color:#fff}}
table{{width:100%;border-collapse:collapse;font-size:14px;display:block;overflow-x:auto;white-space:nowrap}}
th,td{{border-bottom:1px solid #223040;padding:8px 10px;text-align:left;vertical-align:top}}
th{{color:var(--mut);font-weight:600;font-size:13px;text-transform:uppercase;letter-spacing:.03em}}
td.ev{{white-space:normal;max-width:520px;font-size:13px;color:#c8d6e5}}
td.risk{{white-space:normal;max-width:380px;color:#ffd9a0}}
.muted{{color:var(--mut);font-size:13px}}
.num{{font-variant-numeric:tabular-nums;text-align:right}}
.kpi{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}}
.kpi div{{background:#101821;border:1px solid #223040;border-radius:12px;padding:12px}}
.kpi b{{display:block;font-size:24px;color:var(--acc)}}
.alert{{border-left:4px solid var(--warn);background:#1d1a12}}
.danger{{border-left:4px solid var(--bad);background:#1e1414}}
.good{{border-left:4px solid var(--ok);background:#101e16}}
img{{max-width:100%;border-radius:10px;border:1px solid #223040}}
code{{background:#0a1219;padding:2px 6px;border-radius:6px;font-size:13px;word-break:break-all}}
ul{{padding-left:20px}} li{{margin:4px 0}}
.foot{{color:var(--mut);font-size:13px;margin-top:40px;border-top:1px solid #223040;padding-top:12px}}
</style></head><body><div class="wrap">
<h1>Şehir Bazlı 24/7 Canlı Kamera Yayın Sistemi</h1>
<div class="sub">Keşif + tasarım raporu · Pilot şehir: <b>İstanbul</b> · Üretim: {dt.datetime.now().strftime('%d.%m.%Y %H:%M')}<br>
<b>Durum: HİÇBİR YAYIN AÇILMADI, KANAL OLUŞTURULMADI.</b> Bu rapor yalnızca yapılabilirlik ve ölçüm sonuçlarını içerir.</div>

<h2>1. Yönetici özeti</h2>
<div class="card danger"><b>En kritik bulgu:</b> İstanbul için <b>lisans sınıfı A (açıkça izinli)</b> manzaralı kamera <b>bulunamadı</b>.
Belediyenin resmî trafik kamerası servisi teknik olarak erişilebilir ama lisans beyanı yok; ticari webcam siteleri (SkylineWebcams vb.)
sözleşmelerinde yeniden yayını <u>açıkça yasaklıyor</u>. Rakip kanal (6.899 eşzamanlı izleyici) bu nedenle <b>hukuki risk taşıyor</b>.</div>
<div class="card good"><b>Talep doğrulandı:</b> İstanbul'da canlı kamera formatı çalışıyor — ölçülen tek yayın 1080p30,
<b>6.899 eşzamanlı izleyici</b>. Sorun talep değil, <b>kaynak hakkı</b>.</div>
<div class="card"><b>Önerilen yol:</b> (1) İBB'den yazılı izin (kamu kurumu, açık veri talebi), (2) B sınıfı kamera sahipleriyle
(otel/liman/turizm ofisi) anlaşma, (3) <b>kendi PTZ kameran</b> — uzun vadede tek tam kontrol edilebilir A sınıfı kaynak.
A sınıfı açık lisanslı havuz (Finlandiya CC BY 4.0, Londra OGL) <i>gerçek</i> ama teknik kalitesi/formatı 24/7 manzara yayınına uygun değil.</div>

<h2>2. Ölçülen teknik bulgular (bu koşuda test edildi)</h2>
<div class="kpi">
 <div><span class="muted">DB'ye yazılan kamera</span><b>{sum(r['n'] for r in counts)}</b></div>
 <div><span class="muted">İBB kamera kaydı</span><b>{ibb_total}</b></div>
 <div><span class="muted">İBB medya erişimi</span><b>{ibb_ok}/22</b></div>
 <div><span class="muted">Lisans sınıfı A kutu</span><b>2279</b></div>
</div>
<div class="card"><h3>İBB TKM (İstanbul) — ölçüm</h3>
<ul>
<li>Endpoint: <code>sehirharitasigateway.ibb.gov.tr/api/DUoq/api/Tkm/trafikKameralari</code> (anonim token: <code>/auth/anonim?lang=tr</code>) → <b>635 kamera</b>, GeoJSON.</li>
<li>Akış: <code>hls.ibb.gov.tr/tkm{{1,2,4}}/hls/{{id}}.stream/playlist.m3u8</code>. Erişim testi: <b>3/22</b> → dakikalar içinde <b>0/24</b> → <b>0/3</b>. Yani <u>oynak/kararsız erişim</u>.</li>
<li>Anlık kare ucu (<code>CameraImage.ashx</code>): HTTP 200 ama <b>4/4 "kamera yok" yer tutucu görüntüsü</b> (hepsi tam 7933 bayt).</li>
<li>Çalışan örnekler: 352×288 @12 fps, 640×352 @10 fps, 640×352 @7 fps → <b>1080p değil</b>.</li>
<li>İçerik: adlandırmada meydan/sahil/skyline neredeyse yok (GALATA 0, SULTANAHMET 0, KIZ KULESİ 1, BOĞAZ 3) → <b>trafik odaklı, turistik değil</b>.</li>
</ul></div>
<div class="card"><h3>A sınıfı havuz (karşılaştırma)</h3>
<ul>
<li><b>Fintraffic / Digitraffic (Finlandiya)</b> — CC BY 4.0, ticari kullanım serbest (kanıtlı). 2.279 preset, <b>1280×720 JPEG</b>, 6/6 erişilebilir. Ancak bu <b>video değil</b>, aralıklı kare akışı.</li>
<li><b>TfL JamCams (Londra)</b> — OGL v2 tabanlı TfL Transport Data Service lisansı. 890 kamera, 811 aktif, 10/10 erişildi; ölçülen <b>352×288 @25 fps, ~10 sn klip</b>.</li>
</ul></div>

<h2>3. Kalite skoru ve görsel puanlama</h2>
<div class="card alert"><b>Ölçüm yöntemi uyarısı (confound):</b> Vision puanı, montaj hücresi 960×540'a
<i>büyütülerek</i> üretildi; bu <b>netlik puanını yukarı çeker</b>. Bu yüzden q_total içinde çözünürlük bileşeni
<b>ölçülen gerçek piksele</b> göre hesaplanır, vision'a ağırlık %15 verilir. Kesin karar için native çözünürlükte puanlama gerekir.</div>
<table><tr><th>Kaynak</th><th class="num">Kamera</th><th class="num">Erişilebilir</th><th class="num">Ort. q_total</th></tr>{score_rows}</table>
<p class="muted">Vision puanları (data/vision_scores.json): TfL Piccadilly Circus 7,5 · TfL ortalama 7 · Digitraffic ortalama 7 (bir kare 2: sadece asfalt).</p>
<img src="assets/montage_london_tfl.png" alt="TfL Londra montajı">
<p class="muted">TfL montajı — 352×288 kaynak; montajda büyütüldüğü için bulanıklık gizleniyor.</p>
<img src="assets/montage_helsinki_fi.png" alt="Finlandiya montajı">
<p class="muted">Digitraffic Helsinki montajı — 1280×720 kaynak (A sınıfı, CC BY 4.0).</p>

<h2>4. Kamera veritabanı</h2>
<table><tr><th>Kaynak</th><th>Şehir</th><th>Sınıf</th><th class="num">Kamera</th><th class="num">Erişilebilir</th><th class="num">Ort. skor</th></tr>{count_rows}</table>
<h3>İstanbul pilot — ilk kayıtlar</h3>
<table><tr><th>Kamera</th><th>Tip</th><th class="num">Ölçülen çözünürlük</th><th class="num">fps</th><th>Not</th></tr>{ibb_rows}</table>
<h3>Kamera tip dağılımı (tüm DB)</h3><ul>{typ_rows}</ul>

<h2>5. Lisans filtresi (kanıtlı)</h2>
<table><tr><th>Kaynak</th><th>Sınıf</th><th>Kanıt / gerekçe</th></tr>{src_rows}</table>
<div class="card"><b>Kural:</b> Yayın havuzuna YALNIZCA <span class="badge A">A</span> ve yazılı izni alınmış
<span class="badge B">B</span> kameralar girer. <span class="badge C">C</span> = kullanılmaz. Kanıt metni olmayan kaynak
otomatik C'ye düşer (koddaki <code>Source.__post_init__</code>).</div>

<h2>6. OBS yayın tasarımı</h2>
<div class="card"><h3>Sahne yapısı (şablondan üretildi)</h3>
<ul>
<li><b>{{Şehir}} · Tam Kamera</b> — ana akış tam ekran + overlay bar (şehir adı, yerel saat, hava, gün batımı, kamera etiketi).</li>
<li><b>{{Şehir}} · PiP (Ana+Köşe)</b> — ana kamera tam ekran, ikinci kamera sağ altta %25 ölçek.</li>
<li><b>{{Şehir}} · 2x2 Grid</b> — dört kamera 960×540 hücrelerde.</li>
<li><b>STANDBY</b> — tüm kameralar düşerse otomatik geçilen bekleme kartı (kırmızı nokta + "yeniden bağlanıyor").</li>
</ul>
<h3>Rotasyon ve dayanıklılık (<code>rotate.py</code>)</h3>
<ul>
<li>Varsayılan kalma süresi <b>5 sn</b>, geçiş <b>Fade 800 ms</b> (obs-websocket v5: <code>SetCurrentSceneTransition</code>).</li>
<li>Her <b>45 sn</b>'de akış sağlığı kontrol edilir (<code>#EXTM3U</code> başlığı / HTTP 200). Kopan kamera kara listeye alınır, sıradakine geçilir.</li>
<li>Tüm kameralar düşerse <b>STANDBY</b> sahnesine geçilir, 30 sn'de bir yeniden denenir.</li>
<li>Overlay etiketi her geçişte URL parametresiyle güncellenir (<code>?cam=Galata</code>).</li>
</ul>
<h3>Ses</h3>
<ul><li>Kamera sesi <b>kapalı</b> (<code>mixers</code> kısık) — telifsiz ambient müzik ayrı kaynaktan; müzik lisansı yayın öncesi yazılı olarak arşivlenir.</li></ul>
<h3>Overlay verisi (ücretsiz API)</h3>
<ul><li>Yerel saat (tarayıcı), hava + gün batımı: <b>Open-Meteo</b> (anahtarsız, ücretsiz). Döviz kuru isteğe bağlı.</li></ul>
</div>

<h2>7. YouTube metadata şablonu</h2>
<div class="card"><h3>Başlık</h3><code>{esc(meta['baslik_secenekleri'][0])}</code>
<ul>{''.join(f'<li>{esc(x)}</li>' for x in meta['baslik_kurallari'])}</ul>
<h3>Etiketler</h3><p class="muted">{esc(', '.join(meta['etiketler']))}</p>
<h3>Hashtag</h3><p>{esc(' '.join(meta['hashtagler']))}</p>
<ul>{''.join(f'<li>{esc(x)}</li>' for x in meta['hashtag_kurallari'])}</ul>
<h3>Thumbnail brief</h3><p>{esc(meta['thumbnail']['metin']).replace(chr(10),' / ')} — {esc(meta['thumbnail']['olcu'])}</p>
<ul>{''.join(f'<li>{esc(x)}</li>' for x in meta['thumbnail']['kurallar'])}</ul>
<h3>Açıklama (tam metin dosyası: data/istanbul/youtube_aciklama_istanbul.txt)</h3>
<pre style="white-space:pre-wrap;font-size:13px;color:#c8d6e5">{esc(meta['aciklama'][:900])}</pre></div>

<h2>8. Ölçekleme: 10 aday şehir ve risk notları</h2>
<div class="card good"><b>Talep ölçümü (17.10.2026):</b> {esc(cities.get('kritik_icgoru',''))}</div>
<div class="card alert"><b>Ölçüm uyarısı:</b> {esc(cities.get('olcum_uyarisi',''))}</div>
<table><tr><th>Şehir</th><th>Kamera</th><th class="num">Eşzamanlı izleyici</th><th class="num">Kanal abone</th><th class="num">Canlı sonuç (top10)</th></tr>
{demand_rows}</table>
<table><tr><th>#</th><th>Şehir</th><th>Kamera kaynağı</th><th>Lisans</th><th>Ölçüm</th><th>Risk</th><th>Sonraki adım</th><th>Talep (YT)</th></tr>{city_rows}</table>
<div class="card"><b>Elennenler:</b><ul>{''.join(f'<li>{esc(x)}</li>' for x in cities['elenenler'])}</ul></div>

<h2>9. Ölçekleme mimarisi (parametrik)</h2>
<div class="card"><pre style="white-space:pre-wrap;font-size:13px">python3 cam.py discover --city &lt;şehir&gt;   # kaynak çekimi → SQLite
python3 cam.py probe   --city &lt;şehir&gt;    # gerçek çözünürlük/fps ölçümü
python3 cam.py uptime                     # periyodik sağlık turu (cron)
python3 cam.py score                      # ölçülen verilerden kalite skoru
python3 cam.py obs    --city &lt;şehir&gt;      # OBS sahne koleksiyonu + rotate.py + overlay
python3 cam.py meta   --city &lt;şehir&gt;      # YouTube metadata
python3 cam.py report                     # bu rapor</pre>
Yeni şehir eklemek için <code>discovery/sources.py</code>'a kanıt metniyle kaynak eklenir; lisans sınıfı kanıtsızsa otomatik C olur.</div>

<h2>10. Açık maddeler (henüz doğrulanmadı)</h2>
<div class="card alert"><ul>
<li><b>İBB yazılı izni</b> — alınmadı. İzin olmadan yayın açılması önerilmez.</li>
<li><b>7 günlük uptime</b> — henüz toplanmadı; cron kuruldu, ilk anlamlı sonuç 7 gün sonra.</li>
<li><b>TR tabanlı ingest</b> — bu makineden İBB HLS erişimi oynak; kesin ölçüm için TR IP gerekir.</li>
<li><b>TfL lisans kapsamı</b> — JamCam'in "Transport Data Service" kapsamında olduğu yazılı teyit edilmedi.</li>
<li><b>Müzik lisansı</b> — ambiyans parçalarının ticari yayın lisansı henüz arşivlenmedi.</li>
<li><b>VPS bütçesi</b> — 24/7 yeniden kodlama için CPU/bant genişliği hesabı yapılacak (henüz hesap yok, iddia edilmiyor).</li>
<li><b>Vision puanı çözünürlük confound'u</b> — native çözünürlükte yeniden puanlama yapılacak.</li>
</ul></div>

<div class="foot">Üretim: Hermes · Pilot: İstanbul · Veri: data/cameras.db ({sum(r['n'] for r in counts)} kayıt) ·
Kaynak dosyaları: discovery/sources.py, cam.py, obspack.py, ytmeta.py · Hiçbir yayın açılmadı.</div>
</div></body></html>"""
    p = OUT / "pilot_istanbul.html"
    p.write_text(html, encoding="utf-8")
    print("rapor:", p, f"({len(html)//1024} KB)")


if __name__ == "__main__":
    build()
