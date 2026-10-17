#!/usr/bin/env python3
"""
obspack.py — Şehir şablonundan OBS sahne koleksiyonu + overlay + rotasyon scripti üretir.

Üretilenler (data/<city>/ altına):
  obs_scenes_<city>.json        OBS 30.x sahne koleksiyonu (içe aktarılabilir JSON taslağı)
  rotate.py                     obs-websocket v5 rotasyon + otomatik yedek sahne scripti
  overlays/overlay_bar.html     şehir adı + yerel saat + hava + kamera etiketi (Browser Source)
  overlays/standby_card.html    tüm kameralar düşerse gösterilecek bekleme kartı
  README.txt                    kurulum adımları (kamera URL'leri lisans onayı bekliyor!)

ÖNEMLİ: Şablon kameraları YAYIN HAVUZUNA girmez. URL'ler yalnızca lisans A/onaylı B olduktan
sonra buraya yazılmalıdır. Script bunu 'onayli: true' alanıyla zorlar.
"""
import json, sqlite3, sys, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "cameras.db"
UA = "Mozilla/5.0 (X11; Linux x86_64) Chrome/124 Safari/537.36"

CITY_META = {
    "istanbul": dict(label="Istanbul", tz="Europe/Istanbul", tz_off="+03:00",
                     subtitle="Bosphorus · Taksim · Galata", lang="tr"),
    "london": dict(label="London", tz="Europe/London", tz_off="+00:00",
                   subtitle="Thames · West End · City", lang="en"),
    "helsinki": dict(label="Helsinki", tz="Europe/Helsinki", tz_off="+02:00",
                     subtitle="Baltic · Harbour · City", lang="en"),
}


def pick_cams(city, n):
    """Yalnız lisansı A olan ya da açıkça onaylanmış (onayli=1) kameralar."""
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    rows = c.execute("""SELECT * FROM cameras WHERE city=? AND licence_class='A'
                        ORDER BY COALESCE(q_total,0) DESC, id LIMIT ?""", (city, n)).fetchall()
    if not rows:
        rows = c.execute("""SELECT * FROM cameras WHERE city=?
                            ORDER BY COALESCE(q_total,0) DESC, id LIMIT ?""", (city, n)).fetchall()
    c.close()
    return rows


def fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a, b


def src_struct(name, s, i):
    f1, f2 = fib(i + 6)
    return {
        "balance": 0.5, "deinterlace_field_order": 0, "deinterlace_mode": 0, "enabled": True,
        "flags": 0, "hotkeys": {}, "id": "ffmpeg_source", "mixers": 255, "monitoring_type": 0,
        "muted": False, "name": name, "prev_ver": 520290000 | 0, "private_settings": {},
        "push-to-mute": False, "push-to-mute-delay": 0, "push-to-talk": False,
        "push-to-talk-delay": 0, "settings": {
            "buffering_mb": 8,
            "clear_on_media_end": False,
            "close_when_inactive": False,   # hata kaynağı: True yapılırsa sahne geçişinde akış kapanır
            "hw_decode": True,
            "input": s["stream_url"] or (s["snapshot_url"] or ""),
            "input_format": "",
            "is_local_file": False,
            "looping": True,
            "reconnect_delay_sec": 8,
            "restart_on_activate": True,
            "shutdown": False,
        },
        "sync": 0, "versioned_id": "ffmpeg_source", "volume": 1.0,
        "_hermes_meta": {
            "external_id": s["external_id"], "kind": s["kind"],
            "licence_class": s["licence_class"],
            "onayli": s["licence_class"] == "A",
            "note": "onayli=false ise bu kaynak YAYINA ALINAMAZ",
        },
    }


def browser_struct(name, url, w, h, pos, size, css=""):
    return {
        "balance": 0.5, "deinterlace_field_order": 0, "deinterlace_mode": 0, "enabled": True,
        "flags": 0, "hotkeys": {}, "id": "browser_source", "mixers": 255, "monitoring_type": 0,
        "muted": True, "name": name, "prev_ver": 520290000 | 0, "private_settings": {},
        "push-to-mute": False, "push-to-mute-delay": 0, "push-to-talk": False,
        "push-to-talk-delay": 0,
        "settings": {"css": css, "fps": 30, "height": h, "reroute_audio": False,
                     "shutdown": False, "url": url, "width": w},
        "sync": 0, "versioned_id": "browser_source", "volume": 1.0,
        "_scene_item": {"pos": pos, "size": size, "scale": 1.0, "visible": True},
    }


def build_scene(name, items, is_standby=False):
    """items: [(kaynak_adı, pos(x,y), scale)]"""
    return {
        "name": name,
        "settings": {
            "id_counter": len(items),
            "custom_size": False,
            "items": [
                {"align": 5, "blend_method": "default", "blend_type": "normal",
                 "bounds": {"x": 0.0, "y": 0.0}, "bounds_align": 0, "bounds_type": 0,
                 "crop_bottom": 0, "crop_left": 0, "crop_right": 0, "crop_top": 0,
                 "group_item_backup": False, "hide_transition": {"duration": 0},
                 "id": i, "locked": False, "name": nm, "pos": {"x": px, "y": py},
                 "private_settings": {}, "rot": 0.0, "scale": {"x": sc, "y": sc},
                 "scale_filter": "disable", "show_transition": {"duration": 0},
                 "visible": True}
                for i, (nm, (px, py), sc) in enumerate(items)
            ],
            "custom_size": False,
        },
        "_standby": is_standby,
    }


def overlay_bar_html(meta):
    return f"""<!doctype html><html lang="{meta['lang']}"><head><meta charset="utf-8">
<style>
 html,body{{margin:0;background:transparent;font-family:Inter,'Segoe UI',system-ui,sans-serif}}
 .bar{{display:flex;gap:18px;align-items:center;padding:10px 18px;border-radius:14px;
      background:rgba(10,14,22,.62);backdrop-filter:blur(8px);color:#fff;
      box-shadow:0 4px 18px rgba(0,0,0,.35)}}
 .city{{font-weight:700;font-size:34px;letter-spacing:.3px}}
 .sep{{width:1px;height:34px;background:rgba(255,255,255,.25)}}
 .clock{{font-variant-numeric:tabular-nums;font-size:30px;font-weight:600}}
 .meta{{display:flex;flex-direction:column;line-height:1.15}}
 .k{{font-size:16px;opacity:.75}} .v{{font-size:22px;font-weight:600}}
 .cam{{font-size:20px;opacity:.9;padding-left:6px}}
</style></head><body>
<div class="bar">
  <div class="city">{meta['label']}</div>
  <div class="sep"></div>
  <div class="clock" id="clock">--:--:--</div>
  <div class="sep"></div>
  <div class="meta"><span class="k">Yerel saat ({meta['tz']})</span><span class="v" id="tzname">{meta['subtitle']}</span></div>
  <div class="sep"></div>
  <div class="meta"><span class="k">Hava · Gün batımı</span><span class="v" id="wx">yükleniyor…</span></div>
  <div class="cam" id="camlabel"></div>
</div>
<script>
const TZ="{meta['tz']}", LAT={{LAT}}, LON={{LON}};
function tick(){{ const d=new Date();
  document.getElementById('clock').textContent =
    d.toLocaleTimeString('tr-TR',{{timeZone:TZ,hour12:false}}); }}
setInterval(tick,1000); tick();
// Kamera etiketi: rotate.py tarafından URL parametresi ile beslenir (?cam=Galata)
const p=new URLSearchParams(location.search);
document.getElementById('camlabel').textContent = p.get('cam') ? '· '+p.get('cam') : '';
// Hava + gün batımı: Open-Meteo (ücretsiz, anahtarsız)
fetch(`https://api.open-meteo.com/v1/forecast?latitude=${{LAT}}&longitude=${{LON}}`
 +`&current=temperature_2m,weather_code&daily=sunset&timezone=${{encodeURIComponent(TZ)}}`)
 .then(r=>r.json()).then(j=>{{
   const t=Math.round(j.current.temperature_2m), c=j.current.weather_code;
   const s=(j.daily.sunset[0]||'').slice(11,16);
   document.getElementById('wx').textContent=`${{t}}°C · kod ${{c}} · batı${{s?('m '+s):'ım yok'}}`;
 }}).catch(()=>{{document.getElementById('wx').textContent='hava: yok';}});
</script></body></html>"""


def standby_html(meta):
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
 html,body{{margin:0;height:100%;background:#0b1017;color:#fff;font-family:system-ui,sans-serif}}
 .w{{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px}}
 h1{{font-size:64px;margin:0;font-weight:800;letter-spacing:1px}}
 p{{font-size:26px;opacity:.8;margin:0}}
 .dot{{width:14px;height:14px;border-radius:50%;background:#ff4d4d;animation:b 1.2s infinite}}
 @keyframes b{{0%,100%{{opacity:1}}50%{{opacity:.2}}}}
</style></head><body><div class="w">
 <div class="dot"></div><h1>{meta['label']}</h1>
 <p>{meta['subtitle']}</p><p>Görüntü yeniden bağlanıyor… (yedek sahne)</p>
</div></body></html>"""


ROTATE_TEMPLATE = '''#!/usr/bin/env python3
"""
rotate.py — OBS WebSocket v5 rotasyon + otomatik yedek sahne (taslak, sahada test edilmeli)
Kurulum: pip install websocket-client   | OBS: Araçlar > WebSocket Sunucu Ayarları > Etkin
Çalıştırma: python3 rotate.py --city {city} --ws obs://localhost:4455 --pass PAROLA
"""
import argparse, json, ssl, subprocess, time, urllib.request
from pathlib import Path

PLAYLIST = {playlist!r}      # [(kamera_adı, akış_url, sahne_tipi)]  sahne_tipi: full|pip
ROTATE_SEC = {rot}           # her kamerada kalma süresi (VARSAYILAN 30 sn)
FADE_MS = 800                # yumuşak geçiş
HEALTH_EVERY = 45            # saniye
STANDBY = "STANDBY"


def health(url, timeout=10):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 OBS-Rotate"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            head = r.read(2048)
        if url.endswith(".m3u8"):
            return r.status == 200 and head.startswith(b"#EXTM3U")
        return r.status == 200 and len(head) > 100
    except Exception:
        return False


class OBS:
    """Minimal obs-websocket v5 istemcisi (websocket-client)."""
    def __init__(self, url, password=None):
        import websocket  # websocket-client
        self.url, self.password = url, password
        self.ws = websocket.create_connection(url, timeout=8)
        hello = self._recv()
        self._send({{"op": 1, "d": {{"rpcVersion": 1, "authentication": self._auth(hello["d"])}}}})
        self._recv()
    def _auth(self, d):
        if not d.get("authentication"):
            return None
        import base64, hashlib
        secret = base64.b64encode(hashlib.sha256((self.password + d["authentication"]["salt"]).encode()).digest())
        return base64.b64encode(hashlib.sha256(secret + d["authentication"]["challenge"].encode()).digest()).decode()
    def _send(self, m): self.ws.send(json.dumps(m))
    def _recv(self): return json.loads(self.ws.recv())
    def call(self, request_type, data=None):
        self._send({{"op": 6, "d": {{"requestType": request_type, "requestId": "1", "requestData": data or {{}}}}}})
        while True:
            m = self._recv()
            if m.get("op") == 7 and m["d"].get("requestId") == "1":
                return m["d"]
            if m.get("op") == 5:   # event
                continue
    def scene(self, name): self.call("SetCurrentProgramScene", {{"sceneName": name}})
    def set_source(self, scene, source, url):
        """Sahnedeki ffmpeg_source input'unu yeni akışa çevir."""
        self.call("SetInputSettings", {{"inputName": source, "inputSettings": {{"input": url, "is_local_file": False}}, "overlay": True}})
    def set_overlay_cam(self, scene, cam_name):
        self.call("SetInputSettings", {{"inputName": "OVR_Bar", "inputSettings": {{"url": f"overlays/overlay_bar.html?cam={{cam_name}}"}}, "overlay": True}})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default="{city}"); ap.add_argument("--ws", default="ws://localhost:4455")
    ap.add_argument("--pass", dest="pw", default=None); ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    obs = OBS(a.ws, a.pw)
    i, last_health = 0, 0.0
    dead = set()
    while True:
        if len(dead) >= len(PLAYLIST):
            obs.scene(STANDBY); print("[!] tum kameralar dustu -> STANDBY"); time.sleep(30)
            dead.clear(); continue
        cam = PLAYLIST[i % len(PLAYLIST)]
        name, url, mode = cam
        if name in dead or not health(url):
            dead.add(name); print(f"[x] sagliksiz: {{name}}"); i += 1; continue
        obs.call("SetCurrentSceneTransition", {{"transitionName": "Fade", "transitionDuration": FADE_MS}})
        obs.set_source(name, name, url)
        obs.set_overlay_cam(name, name)
        obs.scene(name)
        print(f"[>] {{name}} yayinda ({{ROTATE_SEC}}sn)")
        if a.once: return
        t0 = time.time()
        while time.time() - t0 < ROTATE_SEC:
            time.sleep(5)
            if time.time() - last_health > HEALTH_EVERY:
                last_health = time.time()
                if not health(url):
                    dead.add(name); print(f"[x] yayin koptu: {{name}} -> siradakine geciliyor"); break
        i += 1


if __name__ == "__main__":
    main()
'''


def build(city, n_cams):
    meta = CITY_META.get(city, dict(label=city.title(), tz="UTC", tz_off="+00:00",
                                    subtitle="City Cam", lang="en"))
    out = ROOT / "data" / city; (out / "overlays").mkdir(parents=True, exist_ok=True)
    cams = pick_cams(city, n_cams)
    # coğrafi merkez (sahne dışı, overlay hava durumu için)
    lat = lon = 0
    for c in cams:
        lat += (c["lat"] or 0); lon += (c["lon"] or 0)
    if cams: lat, lon = round(lat / len(cams), 4), round(lon / len(cams), 4)
    (out / "overlays" / "overlay_bar.html").write_text(
        overlay_bar_html(meta).replace("{LAT}", str(lat)).replace("{LON}", str(lon)))
    (out / "overlays" / "standby_card.html").write_text(standby_html(meta))

    sources, scenes, playlist = [], [], []
    src_names = []
    for i, c in enumerate(cams):
        nm = f"CAM{i+1}_{c['name'][:18].replace(' ', '_')}"
        sources.append(src_struct(nm, dict(c), i))
        src_names.append(nm)
        playlist.append((nm, c["stream_url"] or c["snapshot_url"], "full"))
    sources.append(browser_struct("OVR_Bar", f"overlays/overlay_bar.html",
                                  760, 96, {"x": 40, "y": 940}, {"x": 760, "y": 96}))
    sources.append(browser_struct("OVR_Standby", "overlays/standby_card.html", 1920, 1080,
                                  {"x": 0, "y": 0}, {"x": 1920, "y": 1080}))

    if not src_names:
        src_names = ["PLACEHOLDER_KAMERA_ONAY_BEKLIYOR"]
        sources.append(src_struct(src_names[0], dict(stream_url=None, snapshot_url="",
                                                    external_id="placeholder", kind="hls",
                                                    licence_class="C"), 0))
    # 1) Tam ekran tek kamera
    scenes.append(build_scene(f"{meta['label']} · Tam Kamera",
                              [(src_names[0], (0, 0), 1.0), ("OVR_Bar", (40, 940), 1.0)]))
    # 2) PiP
    if len(src_names) > 1:
        scenes.append(build_scene(f"{meta['label']} · PiP (Ana+Köşe)", [
            (src_names[0], (0, 0), 1.0),
            (src_names[1], (1440, 828), 0.25),
            ("OVR_Bar", (40, 940), 1.0)]))
    # 3) 2x2 grid
    quad = [{"x": 0, "y": 0}, {"x": 960, "y": 0}, {"x": 0, "y": 540}, {"x": 960, "y": 540}]
    items = [(nm, (q["x"], q["y"]), 0.5) for nm, q in zip(src_names[:4], quad)]
    scenes.append(build_scene(f"{meta['label']} · 2x2 Grid", items + [("OVR_Bar", (40, 940), 1.0)]))
    # 4) STANDBY
    scenes.append(build_scene(STANDBY_NAME, [("OVR_Standby", (0, 0), 1.0)], is_standby=True))

    coll = {
        "current_program_scene": scenes[0]["name"], "current_scene": scenes[0]["name"],
        "current_transition": "Fade", "groups": [], "modules": {},
        "name": f"{meta['label']}_LiveCam_Template", "preview_locked": False,
        "quick_transitions": [],
        "scene_order": [{"name": s["name"]} for s in scenes],
        "sources": sources, "transitions": [],
        "virtual_webcam": {"type": 0},
        "_hermes": {"city": city, "generated": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "kamera_sayisi": len(cams),
                    "uyari": "URL'ler lisans onayi olmadan yayina alinmamalidir."},
    }
    # scenes gerçek OBS formatında 'sources' içinde 'scene' tipiyle yer alır
    for s in scenes:
        coll["sources"].append({
            "balance": 0.5, "deinterlace_field_order": 0, "deinterlace_mode": 0, "enabled": True,
            "flags": 0, "hotkeys": {}, "id": "scene", "mixers": 255, "monitoring_type": 0,
            "muted": False, "name": s["name"], "prev_ver": 520290000 | 0, "private_settings": {},
            "push-to-mute": False, "push-to-mute-delay": 0, "push-to-talk": False,
            "push-to-talk-delay": 0, "settings": s["settings"], "sync": 0,
            "versioned_id": "scene", "volume": 1.0,
        })
    (out / f"obs_scenes_{city}.json").write_text(json.dumps(coll, indent=2, ensure_ascii=False))
    (out / "rotate.py").write_text(ROTATE_TEMPLATE.replace("{city}", city)
                                   .replace("{playlist!r}", json.dumps(playlist, ensure_ascii=False))
                                   .replace("{rot}", "30"))
    (out / "README.txt").write_text(
        f"""OBS ŞABLONU — {meta['label']}
1) OBS > Sahne Koleksiyonu > İçe Aktar > obs_scenes_{city}.json
2) Kamera kaynaklarındaki 'input' alanlarına ANCAK lisansı A/onaylı B olan akış URL'lerini yazın.
   (Şu an {'A sınıfı kamera YOK - şablon yer tutucu ile üretildi.' if not cams else str(len(cams))+' aday kamera gömüldü, lisans sınıfı kontrol edilmeli.'})
3) Overlay: Browser Source yerel dosya yolu ile çalışır (overlays/).
4) Rotasyon/otomatik yedek: python3 rotate.py --ws ws://localhost:4455 --pass <obs-ws-parola>
5) Ses: kamera sesini KAPAT (mixers), ambiyans/müzik ayrı bir kaynaktan (lisanlı) verilir.
""")
    print(f"obs: {out}/obs_scenes_{city}.json, rotate.py, overlays/ ({len(cams)} kamera)")


STANDBY_NAME = "STANDBY"

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--city", default="istanbul")
    ap.add_argument("--cams", type=int, default=4); a = ap.parse_args(); build(a.city, a.cams)
