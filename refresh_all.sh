#!/usr/bin/env bash
# Tüm kaynakları tazele + ölç: sırayla çalışır (DB kilit çakışması olmasın)
set -uo pipefail
cd /home/batu/canli-kamera
echo "== skyline (kalan sayfalar)"; python3 discovery/fetch_skyline.py --pages 3400 --probe 0 --workers 10
echo "== yt_live (tüm şehirler)";  python3 discovery/fetch_ytlive.py --per-city 5
echo "== probe: skyline";  python3 cam.py probe --source skyline_live --limit 500
echo "== probe: digitraffic (helsinki)"; python3 cam.py probe --city helsinki --limit 12
echo "== probe: tfl";      python3 cam.py probe --source tfl_jamcam --limit 12
echo "== score";           python3 cam.py score
echo "BITTI"
