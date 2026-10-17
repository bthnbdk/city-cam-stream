#!/usr/bin/env python3
"""
cam.py — Şehir bazlı canlı kamera hattı (keşif / veritabanı / kalite skoru / uptime)

Kullanım:
  python3 cam.py discover [--city istanbul|london|helsinki|all]
  python3 cam.py probe    [--limit 40] [--city istanbul]
  python3 cam.py score
  python3 cam.py uptime                       # bir tur ölçüm (cron ile periyodik)
  python3 cam.py stats
  python3 cam.py obs      [--city istanbul] [--cams 4]
  python3 cam.py meta     [--city istanbul]
  python3 cam.py report

Tasarım ilkeleri:
 - Sadece LİSANS SINIFI A veya onaylanmış B kameralar 'yayin_havuzu=1' olur.
 - Kalite skoru ÖLÇÜLEN verilerden üretilir (isim/iddia değil): çözünürlük, fps, erişilebilirlik.
 - Vision puanı (q_visual) montaj karesi elle/modele puanlatıldıktan sonra 'vision_scores.json'
   ile enjekte edilir; yoksa NULL kalır (uydurulmaz).
"""
import argparse, json, os, sqlite3, subprocess, sys, time, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"; DATA.mkdir(exist_ok=True)
DB = DATA / "cameras.db"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")
sys.path.insert(0, str(ROOT / "discovery"))
import sources as SRC  # noqa: E402

# ---------------------------------------------------------------------------
# Şema
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS cameras (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_key TEXT NOT NULL,
  external_id TEXT,
  country TEXT, city TEXT, name TEXT, area TEXT,
  lat REAL, lon REAL,
  stream_url TEXT, snapshot_url TEXT, kind TEXT,
  res_w INTEGER, res_h INTEGER, fps REAL,
  has_audio INTEGER, cam_type TEXT,
  night_quality TEXT,
  licence_class TEXT, licence_evidence TEXT, licence_notes TEXT,
  q_res REAL, q_flow REAL, q_reliability REAL, q_visual REAL, q_total REAL,
  reachable INTEGER, probe_note TEXT,
  first_seen TEXT, last_checked TEXT,
  uptime_7d REAL, uptime_samples INTEGER,
  yayin_havuzu INTEGER DEFAULT 0,
  UNIQUE(source_key, external_id)
);
CREATE TABLE IF NOT EXISTS uptime (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  camera_pk INTEGER, ts TEXT, ok INTEGER, http_code INTEGER,
  latency_ms INTEGER, bytes INTEGER, note TEXT
);
CREATE INDEX IF NOT EXISTS idx_up_cam ON uptime(camera_pk, ts);
CREATE TABLE IF NOT EXISTS sources (
  key TEXT PRIMARY KEY, label TEXT, country TEXT, city TEXT, kind TEXT,
  endpoint TEXT, site TEXT, licence_class TEXT, evidence TEXT,
  contact TEXT, notes TEXT, verified_at TEXT, reachable INTEGER
);
"""

CAM_TYPE_RULES = [
    ("kopru", ["köprü", "kopru", "bridge", "halic", "haliç", "bosphorus", "boğaz"]),
    ("meydan", ["meydan", "square", "taksim", "sultanahmet", "plaza"]),
    ("sahil", ["sahil", "beach", "plaj", "kıyı", "kiyi", "liman", "port", "iskele"]),
    ("skyline", ["skyline", "panorama", "manzara", "view", "tepe", "hill"]),
    ("tren", ["tren", "train", "istasyon", "station", "metro", "ray"]),
    ("trafik", ["kavşak", "kavsak", "trafik", "tunnel", "tünel", "gişe", "otoyol", "highway",
                "road", "cadde", "sokak", "street", "junction"]),
    ("hava", ["hava", "weather", "meteoroloji", "weathercam"]),
]


def classify_type(name: str) -> str:
    n = (name or "").lower()
    for label, kws in CAM_TYPE_RULES:
        if any(k in n for k in kws):
            return label
    return "diger"


def now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def conn():
    c = sqlite3.connect(DB)
    c.executescript(SCHEMA)
    c.row_factory = sqlite3.Row
    return c


def http_get(url, headers=None, timeout=30, extra=()):
    cmd = ["curl", "-sSL", "--compressed", "--max-time", str(timeout), "-A", UA,
           "-w", "\n__HTTP__%{http_code} %{size_download} %{time_total}", url]
    for k, v in (headers or {}).items():
        cmd[1:1] = ["-H", f"{k}: {v}"]
    cmd[1:1] = list(extra)
    r = subprocess.run(cmd, capture_output=True)
    body = r.stdout
    code, size, t = 0, 0, 0.0
    if b"__HTTP__" in body:
        body, meta = body.rsplit(b"__HTTP__", 1)
        try:
            code, size, t = meta.split()
            code, size = int(code), int(size)
            t = float(t)
        except Exception:
            pass
    return body, code, size, t


# ---------------------------------------------------------------------------
# Kaynak çekicileri
# ---------------------------------------------------------------------------
def _grp(g):
    """İBB 'group' alanı bazen [{'name':..}] bazen ['..'] gelir."""
    if not g:
        return ""
    first = g[0]
    return (first.get("name") if isinstance(first, dict) else str(first)) or ""


def fetch_ibb():
    """İBB TKM: anonim token + trafik kameraları (GeoJSON)."""
    out = []
    body, code, _, _ = http_get(
        "https://sehirharitasigateway.ibb.gov.tr/auth/anonim?lang=tr",
        headers={"Origin": "https://harita.istanbul", "Referer": "https://harita.istanbul/"})
    if code != 200:
        print(f"  ! IBB auth alinamadi (http={code})"); return out
    cfg = json.loads(body)
    token = cfg.get("ABC-3903258-571632")
    svc = (cfg.get("generalServices") or {}).get("Trafik Kameraları", {}).get("url")
    if not (token and svc):
        print("  ! IBB token/servis bulunamadi"); return out
    body, code, _, _ = http_get(svc, headers={"ABC-3903258-571632": token,
                                              "Origin": "https://harita.istanbul",
                                              "Referer": "https://harita.istanbul/"})
    if code != 200:
        print(f"  ! IBB kamera listesi alinamadi (http={code})"); return out
    feats = json.loads(body).get("features", [])
    for f in feats:
        p = f.get("properties", {})
        cid = str(p.get("id"))
        coord = (f.get("geometry") or {}).get("coordinates") or [None, None]
        imgs = p.get("images") or []
        out.append(dict(
            source_key="ibb_tkm", external_id=cid,
            country="TR", city="istanbul", name=(p.get("name") or "").strip(),
            area=_grp(p.get("group")),
            lat=coord[1], lon=coord[0],
            stream_url=p.get("videoUrlSsl") or p.get("videoUrl"),
            snapshot_url=imgs[0] if imgs else None, kind="hls"))
    print(f"  ibb_tkm: {len(out)} kamera")
    return out


def fetch_tfl():
    out = []
    body, code, _, _ = http_get("https://api.tfl.gov.uk/Place/Type/JamCam")
    if code != 200:
        print(f"  ! TfL alinamadi (http={code})"); return out
    for plc in json.loads(body):
        aps = {a["key"]: a["value"] for a in plc.get("additionalProperties", [])}
        cid = plc.get("id", "").replace("JamCams_", "")
        out.append(dict(
            source_key="tfl_jamcam", external_id=cid,
            country="UK", city="london", name=plc.get("commonName", ""),
            area=aps.get("view", ""),
            lat=(plc.get("lat") or 0), lon=(plc.get("lon") or 0),
            stream_url=aps.get("videoUrl"), snapshot_url=aps.get("imageUrl"), kind="mp4"))
    print(f"  tfl_jamcam: {len(out)} kamera (available={sum(1 for p in json.loads(body) if any(a['key']=='available' and a['value']=='true' for a in p.get('additionalProperties',[])))})")
    return out


def fetch_digitraffic():
    out = []
    body, code, _, _ = http_get(
        "https://tie.digitraffic.fi/api/weathercam/v1/stations",
        headers={"Digitraffic-User": "hermes-camresearch/1.0", "Accept-Encoding": "gzip"})
    if code != 200:
        print(f"  ! Digitraffic alinamadi (http={code})"); return out
    for f in json.loads(body).get("features", []):
        p = f.get("properties", {})
        coord = (f.get("geometry") or {}).get("coordinates") or [None, None]
        for pre in p.get("presets", []):
            pid = pre.get("id")
            out.append(dict(
                source_key="digitraffic", external_id=pid,
                country="FI", city=_fi_city(coord[1], coord[0]), name=f"{p.get('name','')} ({pid})",
                area=p.get("name", ""), lat=coord[1], lon=coord[0],
                stream_url=None,
                snapshot_url=f"https://weathercam.digitraffic.fi/{pid}.jpg", kind="snapshot"))
    print(f"  digitraffic: {len(out)} kamera/preset (A sinifi, CC BY 4.0)")
    return out


FI_CITIES = [("helsinki", 60.17, 24.94, 35), ("tampere", 61.50, 23.76, 30),
             ("turku", 60.45, 22.27, 30), ("oulu", 65.01, 25.47, 30)]


def _fi_city(lat, lon):
    if lat is None or lon is None:
        return "finland"
    for name, clat, clon, km in FI_CITIES:
        if abs(lat - clat) <= km / 111 and abs(lon - clon) <= km / (111 * 0.5):
            return name
    return "finland"


FETCHERS = {"istanbul": [fetch_ibb], "london": [fetch_tfl], "helsinki": [fetch_digitraffic]}
FETCHERS["all"] = [fetch_ibb, fetch_tfl, fetch_digitraffic]


def cmd_discover(args):
    cities = [args.city] if args.city != "all" else ["all"]
    c = conn()
    for s in SRC.as_dicts():
        c.execute("INSERT OR REPLACE INTO sources VALUES (:key,:label,:country,:city,:kind,:endpoint,"
                  ":site,:licence_class,:evidence,:contact,:notes,:verified_at,:reachable)", s)
    total = 0
    for city in cities:
        for fn in FETCHERS.get(city, []):
            for rec in fn():
                src = SRC.by_key(rec["source_key"])
                rec.update(area=rec.get("area") or "", cam_type=classify_type(rec["name"]),
                           licence_class=src.licence_class, licence_evidence=src.evidence,
                           licence_notes=src.notes, first_seen=now(),
                           yayin_havuzu=1 if src.licence_class == "A" else 0)
                cols = ",".join(rec.keys())
                ph = ",".join(":" + k for k in rec)
                try:
                    c.execute(f"INSERT OR IGNORE INTO cameras ({cols}) VALUES ({ph})", rec)
                    total += 1
                except sqlite3.Error as e:
                    print("   DB hata:", e, rec.get("external_id"))
    c.commit()
    # Kaynak kaydındaki lisans sınıfı sonradan değişmiş olabilir (INSERT OR IGNORE
    # eski satırları korur) -> kameraları kaynak kaydıyla senkronla.
    c.execute("""
        UPDATE cameras SET
          licence_class  = (SELECT s.licence_class  FROM sources s WHERE s.key = cameras.source_key),
          licence_evidence = (SELECT s.evidence     FROM sources s WHERE s.key = cameras.source_key),
          licence_notes  = (SELECT s.notes          FROM sources s WHERE s.key = cameras.source_key),
          yayin_havuzu   = CASE WHEN (SELECT s.licence_class FROM sources s
                                      WHERE s.key = cameras.source_key) = 'A' THEN 1 ELSE 0 END
    """)
    c.commit()
    n = c.execute("SELECT COUNT(*) FROM cameras").fetchone()[0]
    print(f"discover bitti. DB'de toplam {n} kamera (lisans siniflari senkronlandi).")
    c.close()


# ---------------------------------------------------------------------------
# Teknik ölçüm (probe)
# ---------------------------------------------------------------------------
def probe_stream(url, kind, timeout=25):
    """Gerçek ölçüm: ffprobe ile çözünürlük/fps. Hata -> reachable=0 + hata notu."""
    if not url:
        return dict(res_w=None, res_h=None, fps=None, reachable=0, note="stream_url yok")
    if kind == "snapshot":
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "stream=width,height", "-of", "csv=p=0", url],
                           capture_output=True, text=True, timeout=timeout)
        if r.returncode == 0 and "," in r.stdout.strip():
            w, h = r.stdout.strip().split(",")[:2]
            return dict(res_w=int(w), res_h=int(h), fps=None, reachable=1, note="JPEG anlik kare")
        return dict(res_w=None, res_h=None, fps=None, reachable=0, note=f"ffprobe rc={r.returncode}")
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height,avg_frame_rate,codec_name",
                        "-show_entries", "format=duration",
                        "-of", "json", url], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        msg = (r.stderr or "").strip().split("\n")[-1][:110]
        return dict(res_w=None, res_h=None, fps=None, reachable=0, note=f"erisilemedi: {msg}")
    j = json.loads(r.stdout or "{}")
    st = (j.get("streams") or [{}])[0]
    fps = None
    if st.get("avg_frame_rate") and "/" in st["avg_frame_rate"]:
        a, b = st["avg_frame_rate"].split("/")
        fps = round(float(a) / float(b), 2) if float(b) else None
    dur = float((j.get("format") or {}).get("duration") or 0)
    note = f"{st.get('codec_name')}"
    if kind == "mp4" and dur:
        note += f", klip {dur:.1f}sn (video degil, kisa dongu)"
    return dict(res_w=st.get("width"), res_h=st.get("height"), fps=fps, reachable=1, note=note)


def cmd_probe(args):
    c = conn()
    q = "SELECT id, name, city, stream_url, snapshot_url, kind FROM cameras"
    p = []
    if args.city:
        q += " WHERE city=?"; p.append(args.city)
    q += " ORDER BY (kind='hls') DESC, id LIMIT ?"
    p.append(args.limit)
    rows = c.execute(q, p).fetchall()
    ok = 0
    for r in rows:
        tgt = r["stream_url"] or r["snapshot_url"]
        k = r["kind"] if r["stream_url"] else "snapshot"
        res = probe_stream(tgt, k)
        ok += res["reachable"]
        c.execute("UPDATE cameras SET res_w=?, res_h=?, fps=?, reachable=?, probe_note=?, "
                  "last_checked=? WHERE id=?",
                  (res["res_w"], res["res_h"], res["fps"], res["reachable"], res["note"], now(), r["id"]))
        print(f"  [{r['city']:9s}] {r['name'][:32]:32s} {res['reachable']} "
              f"{str(res['res_w'])}x{str(res['res_h'])} @{res['fps']} {res['note'][:40]}")
    c.commit()
    print(f"probe: {ok}/{len(rows)} erisilebilir")
    c.close()


# ---------------------------------------------------------------------------
# Kalite skoru — ÖLÇÜLEN verilerden
# ---------------------------------------------------------------------------
def q_resolution(w, h, kind):
    """Yalnız ölçülmüş piksel sayısı. Anlık kare (snapshot) video akıcılığı sağlamaz."""
    if not w or not h:
        return None
    px = w * h
    if px >= 1920 * 1080: s = 10
    elif px >= 1280 * 720: s = 8
    elif px >= 960 * 540:  s = 6
    elif px >= 640 * 360:  s = 4
    elif px >= 320 * 240:  s = 2
    else: s = 1
    if kind in ("mp4", "snapshot"):
        s = max(1, s - 3)  # süreksiz/kısa klip -> 24/7 akış için zayıf
    return s


def q_flow(fps, kind):
    if fps is None:
        return None
    if kind in ("mp4", "snapshot"):
        return 3.0
    if fps >= 25: return 10
    if fps >= 15: return 7
    return 4


def q_reliability(uptime_pct, samples):
    if uptime_pct is None or not samples:
        return None
    return round(uptime_pct / 10.0, 2)


def cmd_score(args):
    c = conn()
    vis = {}
    vf = DATA / "vision_scores.json"
    if vf.exists():
        vis = json.loads(vf.read_text())
    for r in c.execute("SELECT * FROM cameras").fetchall():
        a = q_resolution(r["res_w"], r["res_h"], r["kind"])
        b = q_flow(r["fps"], r["kind"])
        d = q_reliability(r["uptime_7d"], r["uptime_samples"])
        v = (vis.get(str(r["id"])) or {}).get("q_visual")
        parts = [(a, .35), (b, .25), (d, .25), (v, .15)]
        have = [(x, w) for x, w in parts if x is not None]
        total = round(sum(x * w for x, w in have) / sum(w for _, w in have), 2) if have else None
        c.execute("UPDATE cameras SET q_res=?, q_flow=?, q_reliability=?, q_visual=?, q_total=? WHERE id=?",
                  (a, b, d, v, total, r["id"]))
    c.commit()
    print("skorlar hesaplandi (q_total yalniz OLCULEN bilesenlerden).")
    c.close()


# ---------------------------------------------------------------------------
# Uptime turu
# ---------------------------------------------------------------------------
def _check_one(r):
    """Tek kamera sağlık kontrolü (paralel çalışır)."""
    url = r["stream_url"] or r["snapshot_url"]
    t0 = time.time()
    body, code, size, _ = http_get(url, timeout=12)
    lat = int((time.time() - t0) * 1000)
    ok = 1 if (code == 200 and size > 200) else 0
    if r["kind"] == "hls" and body[:7] != b"#EXTM3U":
        ok = 0
    return (r["id"], now(), ok, code, lat, size)


def cmd_uptime(args):
    from concurrent.futures import ThreadPoolExecutor
    limit = getattr(args, "limit", 150) or 150
    c = conn()
    rows = c.execute("""SELECT id, name, stream_url, snapshot_url, kind FROM cameras
                        WHERE stream_url IS NOT NULL OR snapshot_url IS NOT NULL
                        ORDER BY CASE WHEN licence_class='A' THEN 0 ELSE 1 END,
                                 CASE WHEN reachable=1 THEN 0 ELSE 1 END,
                                 (id + CAST(strftime('%s','now') AS INT)/600) % 997
                        LIMIT ?""", (limit,)).fetchall()
    with ThreadPoolExecutor(max_workers=12) as ex:
        results = list(ex.map(_check_one, rows))
    c.executemany("INSERT INTO uptime (camera_pk, ts, ok, http_code, latency_ms, bytes) "
                  "VALUES (?,?,?,?,?,?)", results)
    c.execute("""UPDATE cameras SET
        uptime_samples = (SELECT COUNT(*) FROM uptime WHERE camera_pk=cameras.id),
        uptime_7d = (SELECT 100.0*SUM(ok)/COUNT(*) FROM uptime
                     WHERE camera_pk=cameras.id AND ts > datetime('now','-7 day'))""")
    c.commit()
    ok = sum(1 for r in results if r[2] == 1)
    print(f"uptime turu: {len(rows)} kamera olculdu, {ok} saglikli -> {now()}")
    c.close()


def cmd_stats(args):
    c = conn()
    print("kamera sayilari (kaynak/sehir):")
    for r in c.execute("SELECT source_key, city, licence_class, COUNT(*) n, SUM(reachable) er, "
                       "ROUND(AVG(q_total),2) ort FROM cameras GROUP BY 1,2,3 ORDER BY n DESC"):
        print(f"  {r['source_key']:14s} {r['city']:10s} sinif={r['licence_class']} n={r['n']:4d} "
              f"erisilebilir={r['er']} ort_skor={r['ort']}")
    print("yayin havuzuna uygun (A):", c.execute("SELECT COUNT(*) FROM cameras WHERE yayin_havuzu=1").fetchone()[0])
    print("tip dagilimi:", dict(c.execute("SELECT cam_type, COUNT(*) FROM cameras GROUP BY 1").fetchall()))
    c.close()


def cmd_obs(args):
    import obspack
    obspack.build(args.city, args.cams)


def cmd_meta(args):
    import ytmeta
    ytmeta.build(args.city)


def cmd_report(args):
    import report
    report.build()


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("discover"); d.add_argument("--city", default="all"); d.set_defaults(f=cmd_discover)
    p = sub.add_parser("probe"); p.add_argument("--limit", type=int, default=40); p.add_argument("--city"); p.set_defaults(f=cmd_probe)
    s = sub.add_parser("score"); s.set_defaults(f=cmd_score)
    u = sub.add_parser("uptime"); u.add_argument("--limit", type=int, default=150); u.set_defaults(f=cmd_uptime)
    st = sub.add_parser("stats"); st.set_defaults(f=cmd_stats)
    o = sub.add_parser("obs"); o.add_argument("--city", default="istanbul"); o.add_argument("--cams", type=int, default=4); o.set_defaults(f=cmd_obs)
    m = sub.add_parser("meta"); m.add_argument("--city", default="istanbul"); m.set_defaults(f=cmd_meta)
    r = sub.add_parser("report"); r.set_defaults(f=cmd_report)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
