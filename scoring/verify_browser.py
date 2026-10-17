#!/usr/bin/env python3
"""
verify_browser.py — Yayın ortamının KENDİSİNDE doğrulama (headless Chromium + hls.js).

Neden: ffmpeg bazı akışları açamıyor ama tarayıcı + hls.js açabiliyor (İBB örneği: ffmpeg
"erişilemedi" derken Chromium readyState=4 ile oynattı). Teslim kanalı tarayıcı olduğu için
doğrulama da tarayıcıda yapılır.

Yöntem: tek bir HTML koşum takımı (hls.js ile) sırayla her akışı yükler, 6-8 sn bekler,
readyState>=2 ve currentTime>0.4 ise "canli" sayar. Paralel N sekme.

Kullanım: python3 scoring/verify_browser.py --source ibb_tkm --limit 80 --tabs 3
"""
import argparse, json, sqlite3, subprocess, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "cameras.db"
HARNESS = ROOT / "data" / "verify_harness.html"

HARNESS.write_text("""<!doctype html><meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/hls.js@1.5.17/dist/hls.min.js"></script>
<video id="v" muted playsinline autoplay style="width:320px"></video>
<script>
window.__res = {}; window.__idx = -1;
window.runBatch = (urls, waitMs) => new Promise(async (resolve) => {
  for (let i = 0; i < urls.length; i++) {
    const u = urls[i]; window.__idx = i;
    await new Promise((done) => {
      const v = document.getElementById('v');
      let killed = false;
      const finish = (ok, note) => { if (killed) return; killed = true;
        try { h && h.destroy(); } catch(e){} v.removeAttribute('src'); v.load();
        window.__res[u] = { ok: ok?1:0, note, ready: v.readyState, t: +v.currentTime.toFixed(2),
                            res: (v.videoWidth||0)+'x'+(v.videoHeight||0) };
        done(); };
      let h = null;
      if (window.Hls && Hls.isSupported()) {
        h = new Hls({ manifestLoadingTimeOut: 9000, manifestLoadingMaxRetry: 0, fragLoadingMaxRetry: 1 });
        h.on(Hls.Events.ERROR, (_, d) => { if (d.fatal) finish(false, 'hls hata: ' + d.details); });
        h.loadSource(u); h.attachMedia(v);
      } else { v.src = u; v.onerror = () => finish(false, 'medya hatasi'); }
      setTimeout(() => {
        const ok = v.readyState >= 2 && v.currentTime > 0.4;
        finish(ok, ok ? 'canli' : 'yuklenemedi (ready=' + v.readyState + ')');
      }, waitMs);
    });
  }
  resolve(true);
});
</script>""")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source"); ap.add_argument("--city"); ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--tabs", type=int, default=3); ap.add_argument("--wait", type=int, default=7000)
    a = ap.parse_args()
    c = sqlite3.connect(DB, timeout=60); c.row_factory = sqlite3.Row
    q = "SELECT id,name,stream_url,snapshot_url,kind FROM cameras WHERE kind='hls'"
    p = []
    if a.source:
        q += " AND source_key=?"; p.append(a.source)
    if a.city:
        q += " AND city=?"; p.append(a.city)
    q += " LIMIT ?"; p.append(a.limit)
    rows = [dict(r) for r in c.execute(q, p).fetchall()]
    rows = [r for r in rows if r["stream_url"]]
    print(f"tarayıcıda doğrulanacak: {len(rows)} HLS akışı ({a.tabs} sekme, {a.wait} ms)")
    chunks = [rows[i::a.tabs] for i in range(a.tabs)]
    results = {}
    with sync_playwright() as pw:
        br = pw.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        pages = []
        for _ in chunks:
            pg = br.new_page()
            pg.goto("file://" + str(HARNESS))
            pages.append(pg)
        for pg, ch in zip(pages, chunks):
            if ch:
                pg.evaluate("([urls,w]) => window.runBatch(urls,w)",
                            [ch, a.wait]) if False else None
        # paralel koşum: her sayfa kendi partisini çalıştırır
        for pg, ch in zip(pages, chunks):
            if ch:
                pg.evaluate("([urls,w]) => { window.__batch = window.runBatch(urls,w); }", [ch, a.wait])
        done = [False] * len(pages)
        t0 = time.time()
        while not all(done) and time.time() - t0 < (len(rows) / max(1, a.tabs)) * (a.wait / 1000.0) + 240:
            for i, pg in enumerate(pages):
                if done[i] or not chunks[i]:
                    done[i] = True; continue
                try:
                    if pg.evaluate("() => !!window.__res && Object.keys(window.__res).length >= "
                                   + str(len(chunks[i]))):
                        done[i] = True
                except Exception:
                    pass
            time.sleep(3)
        for pg in pages:
            try:
                results.update(pg.evaluate("() => window.__res || {}"))
            except Exception:
                pass
        br.close()

    up = 0
    for r in rows:
        v = results.get(r["stream_url"])
        if not v:
            c.execute("UPDATE cameras SET reachable=0, probe_note=? WHERE id=?",
                      ("tarayıcı doğrulaması yapılamadı", r["id"])); continue
        c.execute("UPDATE cameras SET reachable=?, probe_note=?, last_checked=datetime('now') WHERE id=?",
                  (v["ok"], f'tarayıcı: {v["note"]} (ready={v["ready"]}, t={v["t"]}, {v["res"]})', r["id"]))
        if v["ok"] and v.get("res", "0x0").split("x")[0].isdigit():
            w, h = v["res"].split("x")
            if int(w) > 0:
                c.execute("UPDATE cameras SET res_w=?, res_h=? WHERE id=?", (int(w), int(h), r["id"]))
        up += v["ok"]
    c.commit()
    print(f"SONUÇ: {up}/{len(rows)} akış tarayıcıda gerçekten oynadı")
    c.close()


if __name__ == "__main__":
    main()
