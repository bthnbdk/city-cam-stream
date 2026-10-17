#!/usr/bin/env python3
"""
vision_sample.py — Erişilebilen kameralardan kare örnekleyip montaj üretir (vision puanlaması için).

Ne yapar:
 1) Verilen filtrelere uyan kameralardan anlık kare indirir (snapshot_url veya mp4'ten tek kare).
 2) 2x2 / 3x3 montaj PNG üretir (etiketli, indeksli).
 3) data/vision_frames.json içine {indeks: camera_pk} eşlemesini yazar.

Sonra montaj karesi bir vision modeline gösterilir; dönen 0-10 puanları
data/vision_scores.json içine {camera_pk: {"q_visual": 7, "not": "..."}} olarak yazılır.
'cam.py score' bu dosyayı okuyup q_visual kolonunu doldurur.
"""
import argparse, json, subprocess, sys, sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "cameras.db"
TMP = ROOT / "data" / "frames"; TMP.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (X11; Linux x86_64) Chrome/124 Safari/537.36"


def grab(url, out, kind):
    if kind == "hls":
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-rw_timeout", "15000000",
               "-i", url, "-frames:v", "1", "-q:v", "3", str(out)]
    elif kind == "mp4":
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", "2", "-i", url,
               "-frames:v", "1", "-q:v", "3", str(out)]
    else:  # snapshot
        cmd = ["curl", "-sSL", "--compressed", "--max-time", "20", "-A", UA, "-o", str(out), url]
    r = subprocess.run(cmd, capture_output=True)
    return out.exists() and out.stat().st_size > 2000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default="istanbul")
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--name-like", default=None, help="isim filtresi (örn. TAKSİM,MEYDAN)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    where, params = "city=?", [a.city]
    order = "COALESCE(q_total,0) DESC, id"
    if a.name_like:
        likes = " OR ".join("name LIKE ?" for _ in a.name_like.split(","))
        where += f" AND ({likes})"
        params += [f"%{k.strip()}%" for k in a.name_like.split(",")]
        order = "id"
    rows = c.execute(f"SELECT * FROM cameras WHERE {where} ORDER BY {order} LIMIT ?",
                     params + [a.n]).fetchall()
    frames, index = [], {}
    for r in rows:
        url = r["snapshot_url"] or r["stream_url"]
        if not url:
            continue
        kind = "snapshot" if r["snapshot_url"] else r["kind"]
        p = TMP / f"cam_{r['id']}.jpg"
        if grab(url, p, kind):
            frames.append(p); index[str(len(frames) - 1)] = r["id"]
            print(f"  kare alindi: [{len(frames)-1}] {r['name'][:34]} ({r['source_key']})")
        else:
            print(f"  ATLANDI (kare alinamadi): {r['name'][:34]}")
    if not frames:
        print("montaj icin kare yok."); return
    outp = Path(a.out) if a.out else ROOT / "data" / f"montage_{a.city}.png"
    # 2x2 grid, her hücre 960x540
    n = min(4, len(frames))
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for f in frames[:n]:
        cmd += ["-i", str(f)]
    # ölçek + etiket + xstack
    filters = []
    for i in range(n):
        filters.append(f"[{i}:v]scale=960:540:force_original_aspect_ratio=decrease,"
                       f"pad=960:540:(ow-iw)/2:(oh-ih)/2:color=black,"
                       f"drawtext=text='{i}':x=18:y=14:fontsize=64:fontcolor=yellow:"
                       f"box=1:boxcolor=black@0.6:boxborderw=10,"
                       f"setsar=1[v{i}]")
    if n == 1:
        filters.append("[v0]null[out]")
    else:
        layout = {1: "0_0", 2: "0_0|960_0", 3: "0_0|960_0|0_540", 4: "0_0|960_0|0_540|960_540"}[n]
        filters.append("".join(f"[v{i}]" for i in range(n)) + f"xstack=inputs={n}:layout={layout}[out]")
    cmd += ["-filter_complex", ";".join(filters), "-map", "[out]", "-frames:v", "1", str(outp)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    (ROOT / "data" / "vision_frames.json").write_text(json.dumps(index, indent=2))
    print("montaj:", outp, "| rc:", r.returncode, "| esleme: data/vision_frames.json")
    if r.returncode != 0:
        print(r.stderr[-500:])


if __name__ == "__main__":
    main()
