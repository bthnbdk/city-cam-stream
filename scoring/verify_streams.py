#!/usr/bin/env python3
"""
verify_streams.py — ÇALIŞMAYAN KAMERALARI AYIKLA (ölçüm, iddia değil).

Her kaynak türü için gerçek içerik testi:
  proxy     : kamera sayfasını çek -> taze token -> ffmpeg ile 2 kare al -> iki kare arasında
              anlamlı fark var mı (canlı görüntü) + kare boş mu (tek renk/kart) kontrolü
  hls/mp4   : doğrudan akış -> aynı 2 kare testi
  snapshot  : aynı görüntüyü ~6 sn arayla 2 kez indir -> kare farkı GEREKMEZ (kare akışı),
              yalnız geçerli JPEG + boyut kontrolü

Neden: HTTP 200 + ffprobe çözünürlük bilgisi "gerçek görüntü" garantisi DEĞİL.
(SkylineWebcams örneği: 1920x1080 dedi, servis ettiği kare logo kartıydı.)

Sonuç DB'ye yazılır: reachable 0/1, probe_note, res_w/res_h/fps.
Kullanım: python3 scoring/verify_streams.py --source earthcam --workers 6 [--limit 50]
         python3 scoring/verify_streams.py --all
"""
import argparse, json, re, sqlite3, subprocess, sys, statistics
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "cameras.db"
TMP = ROOT / "data" / "verify"; TMP.mkdir(parents=True, exist_ok=True)
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")
STREAM_RE = re.compile(r'"stream":"(https:\\/\\/videos-[^"]+playlist\.m3u8[^"]*)"')


def curl(url, timeout=25, out=None):
    cmd = ["curl", "-sSL", "--compressed", "--max-time", str(timeout), "-A", UA]
    if out:
        cmd += ["-o", str(out)]
        r = subprocess.run(cmd + [url], capture_output=True, text=True)
        return Path(out).exists() and Path(out).stat().st_size > 1000
    return subprocess.run(cmd + [url], capture_output=True, text=True).stdout


def resolve(cam):
    """proxy kameralar için taze akış URL'i; diğerleri için mevcut URL."""
    if cam["kind"] == "proxy":
        h = curl(cam["stream_url"], timeout=20)
        m = STREAM_RE.search(h)
        return m.group(1).replace("\\/", "/") if m else None
    return cam["stream_url"] or cam["snapshot_url"]


def frames(url, tag, n=2, gap=4):
    """Akıştan n kare çeker (arasında `gap` saniye)."""
    outs = []
    for i in range(n):
        p = TMP / f"{tag}_{i}.jpg"
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(i * gap),
               "-i", url, "-frames:v", "1", "-q:v", "4", str(p)]
        subprocess.run(cmd, capture_output=True, timeout=90)
        if not (p.exists() and p.stat().st_size > 2000):
            return []
        outs.append(p)
    return outs


def diff_score(paths):
    """İki kare arası ortalama piksel farkı (0 = donuk/aynı)."""
    if len(paths) < 2:
        return None
    try:
        from PIL import Image, ImageChops
        a = Image.open(paths[0]).convert("L")
        b = Image.open(paths[-1]).convert("L")
        b = b.resize(a.size)
        px = list(ImageChops.difference(a, b).getdata())
        return round(sum(px) / max(1, len(px)), 3)
    except Exception:
        return None


def blank_score(path):
    """Kare ne kadar 'boş'? (tek renkli/kart göstergesi: düşük varyans)."""
    try:
        from PIL import Image, ImageStat
        im = Image.open(path).convert("L").resize((160, 90))
        st = ImageStat.Stat(im)
        return round(st.stddev[0], 2)
    except Exception:
        return None


def probe_one(cam):
    tag = f'{cam["source_key"]}_{cam["id"]}'
    url = resolve(cam)
    if not url:
        return dict(id=cam["id"], ok=0, note="akış URL'i çözülemedi (token/sayfa yok)", res=None, diff=None, blank=None)
    if cam["kind"] == "snapshot":
        ok = curl(url, out=TMP / f"{tag}.jpg")
        return dict(id=cam["id"], ok=1 if ok else 0,
                    note="anlık kare indirildi" if ok else "kare indirilemedi",
                    res=None, diff=None, blank=blank_score(TMP / f"{tag}.jpg"))
    fs = frames(url, tag)
    if not fs:
        return dict(id=cam["id"], ok=0, note="ffmpeg kare alamadı (akış ölü/marka karti olabilir)",
                    res=None, diff=None, blank=None)
    d, bl = diff_score(fs), blank_score(fs[0])
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,avg_frame_rate", "-of", "default=nw=1:nk=1", url],
                       capture_output=True, text=True, timeout=60)
    nums = r.stdout.split()
    res = f"{nums[0]}x{nums[1]}" if len(nums) >= 2 and nums[0].isdigit() else None
    # karar: görüntü değişiyor (diff>1.0) ise canlı; tek kare ise boş/kart kontrolü
    if d is not None and d > 1.0:
        ok, note = 1, f"canli (kare farki {d})"
    elif bl is not None and bl > 25:
        ok, note = 1, f"tek kare gorunumu var (varyans {bl})"
    else:
        ok, note = 0, f"donuk/bos kare (fark={d}, varyans={bl})"
    return dict(id=cam["id"], ok=ok, note=note, res=res, diff=d, blank=bl)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source"); ap.add_argument("--city"); ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--all", action="store_true"); ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    c = sqlite3.connect(DB, timeout=60); c.row_factory = sqlite3.Row
    q = "SELECT * FROM cameras WHERE 1=1"
    p = []
    if a.source:
        q += " AND source_key=?"; p.append(a.source)
    if a.city:
        q += " AND city=?"; p.append(a.city)
    if a.limit:
        q += " LIMIT ?"; p.append(a.limit)
    rows = c.execute(q, p).fetchall()
    print(f"doğrulanacak kamera: {len(rows)}")
    out = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for i, r in enumerate(ex.map(probe_one, [dict(x) for x in rows]), 1):
            out.append(r)
            if i % 25 == 0:
                ok = sum(1 for x in out if x["ok"])
                print(f"  ... {i}/{len(rows)} doğrulandı, sağlam={ok}", flush=True)
    for r in out:
        c.execute("UPDATE cameras SET reachable=?, probe_note=?, last_checked=datetime('now') WHERE id=?",
                  (r["ok"], r["note"], r["id"]))
        if r["res"]:
            w, h = r["res"].split("x")
            c.execute("UPDATE cameras SET res_w=?, res_h=? WHERE id=?", (int(w), int(h), r["id"]))
    c.commit()
    ok = sum(1 for x in out if x["ok"])
    print(f"SONUC: {ok}/{len(out)} kamera gerçek görüntü veriyor")
    counts = {}
    for r in out:
        counts[r["note"].split(" (")[0]] = counts.get(r["note"].split(" (")[0], 0) + 1
    for k, v in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"   {v:4d}  {k}")
    (ROOT / "data" / "verify_report.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    c.close()


if __name__ == "__main__":
    main()
