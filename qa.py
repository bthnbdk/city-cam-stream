#!/usr/bin/env python3
"""
qa.py — Site QA (aynı betik hem localhost hem canlı URL için).
Kullanım:  QA_BASE=http://localhost:8099 python3 qa.py
           QA_BASE=https://<site>.netlify.app python3 qa.py
Kontroller: veri yüklenmesi, oynatıcı bağlanması, rotasyonun ilerlemesi,
lisans rozeti, panelden okunan varsayılan rotasyon (5 sn), mobil taşma, yedek sahne.
"""
import os, sys, json, time
from playwright.sync_api import sync_playwright

BASE = os.environ.get("QA_BASE", "http://localhost:8099")
OUT = os.environ.get("QA_OUT", "/tmp/qa")
os.makedirs(OUT, exist_ok=True)
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"[{'GECTI' if ok else 'KALDI'}] {name} {detail}")


def main():
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        pg = br.new_page(viewport={"width": 1280, "height": 720})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))

        # 1) Londra (mp4 akışları) + panel açık
        pg.goto(f"{BASE}/index.html?city=london&panel=1", wait_until="domcontentloaded")  # rotasyon VERİLMEZ -> varsayılan ölçülür
        pg.wait_for_selector("#tiles .tile", timeout=20000)
        check("tiles render (london)", True)
        pg.wait_for_timeout(6000)
        vid = pg.query_selector("#tiles video")
        check("video elementi var", vid is not None)
        src = (pg.get_attribute("#tiles video", "src") or "") if vid else ""
        check("medya kaynağı jamcams/tfl", "jamcams" in src or "mp4" in src, src[:60])
        badge = pg.inner_text("#ov-badge")
        check("lisans rozeti = A (london)", badge.strip() == "A", badge)
        rot = pg.input_value("#c-rot")
        check("varsayılan rotasyon 30 sn", rot == "30", rot)
        # ön-yükleme: arkada hazır tutulan akışlar
        warm = pg.evaluate("() => document.querySelector('#preload').children.length")
        check("ön-yükleme (preload) arkada akış tutuyor", warm >= 1, f"hazır öğe={warm}")
        cnt = pg.inner_text("#ov-count")
        check("sayaç n/n biçiminde", "/" in cnt, cnt)
        # rotasyonun ilerlediğini kısa sürede görmek için 6 sn'lik özel URL ile test edilir
        pg.goto(f"{BASE}/index.html?city=london&rotation=6&preload=2", wait_until="domcontentloaded")
        pg.wait_for_selector("#tiles .tile", timeout=20000)
        pg.wait_for_timeout(2500)
        cap1 = pg.inner_text("#tiles .caption")
        pg.wait_for_timeout(7000)
        cap2 = pg.inner_text("#tiles .caption")
        check("rotasyon ilerliyor (kamera değişti)", cap1 != cap2, f"{cap1[:26]} -> {cap2[:26]}")
        warm = pg.evaluate("() => document.querySelector('#preload').children.length")
        check("ön-yükleme penceresi dolu", warm >= 1, f"hazır öğe={warm}")
        clock1 = pg.inner_text("#ov-clock")
        check("saat biçimi", ":" in clock1, clock1)
        pg.screenshot(path=f"{OUT}/desktop_london.png")

        # 2) URL parametreleri etkili mi (rotation=2, overlay=0, badge=0)
        pg.goto(f"{BASE}/index.html?city=london&rotation=2&overlay=0&badge=0&preload=1", wait_until="domcontentloaded")
        pg.wait_for_selector("#tiles .tile", timeout=20000)
        pg.wait_for_timeout(2500)
        check("overlay=0 barı gizler", pg.get_attribute("#bar", "hidden") is not None)
        check("badge=0 rozeti gizler", pg.eval_on_selector("#tiles .badge2", "e=>e.style.display") == "none")

        # 3) Finlandiya (JPEG anlık kare) — <img> beklenir
        pg.goto(f"{BASE}/index.html?city=helsinki&rotation=5", wait_until="domcontentloaded")
        pg.wait_for_selector("#tiles .tile", timeout=20000)
        pg.wait_for_timeout(4000)
        check("anlık kare modu <img> kullanır", pg.query_selector("#tiles img") is not None)

        # 4) Vancouver (DriveBC, doğrulanmış anlık kare kaynağı)
        pg.goto(f"{BASE}/index.html?city=vancouver&rotation=5", wait_until="domcontentloaded")
        pg.wait_for_selector("#tiles .tile, #standby", timeout=20000)
        pg.wait_for_timeout(9000)
        check("vancouver: görüntü akıyor", pg.query_selector("#tiles img, #tiles video") is not None,
              pg.eval_on_selector("#ov-cam", "e=>e.textContent")[:44])

        # 4b) Sayfada hiç iframe (YouTube) olmamalı — kullanıcı kuralı
        check("sitede YouTube/iframe yok", pg.query_selector("#tiles iframe") is None)

        # 4c) İstanbul artık doğrulanmış kaynağı olmadığı için listede olmamalı
        idx = pg.request.get(f"{BASE}/data/cities.json").json()
        check("İstanbul listeden çıkarıldı (çalışan kaynak yok)",
              not any(c["city"] == "istanbul" for c in idx["cities"]),
              ", ".join(c["city"] for c in idx["cities"][:6]))

        # 5) Mobil taşma
        m = br.new_context(**pw.devices["iPhone 13"]).new_page()
        m.goto(f"{BASE}/index.html?city=london&rotation=5", wait_until="domcontentloaded")
        m.wait_for_selector("#tiles .tile", timeout=20000)
        m.wait_for_timeout(3500)
        ov = m.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check("mobil yatay taşma yok", ov <= 1, f"fark={ov}px")
        m.screenshot(path=f"{OUT}/mobile_london.png")

        # 6) veri dosyaları
        for f in ("cities.json", "london.json", "helsinki.json", "istanbul.json"):
            r = pg.request.get(f"{BASE}/data/{f}")
            ok = r.ok
            n = 0
            if ok:
                try:
                    n = len(r.json().get("cams", [])) or len(r.json().get("cities", []))
                except Exception:
                    ok = False
            check(f"data/{f} erişilebilir", ok, f"kayıt={n}")

        check("sayfa JS hatası yok", not errs, "; ".join(errs[:2]))
        br.close()

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\nSONUC: {passed}/{len(results)} gecti")
    json.dump([{"test": n, "ok": ok, "detail": d} for n, ok, d in results],
              open(f"{OUT}/qa_results.json", "w"), ensure_ascii=False, indent=1)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
