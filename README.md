# City Cam Stream

A discovery + design + delivery pipeline for **city-based 24/7 live camera streams**:
find public cameras, classify their **licence** (A/B/C), measure real quality, then generate
OBS scenes, a rotation script and YouTube metadata — plus a web player for previewing a
city's rotation from URL parameters.

**Nothing here starts a broadcast.** The repo produces scenes, metadata and a dashboard;
going live is a separate, explicit decision.

## Why licence classes come first

| Class | Meaning | May be broadcast? |
|---|---|---|
| **A** | Open licence / public data / explicit restream permission | ✅ yes (attribution kept) |
| **B** | Permission obtainable from the owner (contact + draft ready) | ⏳ pending written permission |
| **C** | No permission / unknown / ToS forbids | ❌ never |

`Source.__post_init__` in `discovery/sources.py` **downgrades any A/B entry that has no
evidence text to C**. Classification is evidence-driven, not claim-driven.
Private/security cameras, window interiors and close-up faces are excluded up front.

## Layout

```
cam.py                     CLI: discover | probe | score | uptime | stats | obs | meta | report
discovery/sources.py       source registry + licence rules (evidence required)
discovery/yt_demand*.py    demand measurement (YouTube live cam audience)
scoring/vision_sample.py   frame sampling + montage for visual scoring
obspack.py                 OBS scene collection + rotate.py + overlay HTML generator
ytmeta.py                  YouTube title/description/tags/thumbnail template
report.py                  mobile-first HTML report
export_web.py              SQLite -> site/data/*.json
site/                      static web player (Netlify)
data/cities.json           candidate cities, measured demand, risk notes
```

## Usage

```bash
python3 cam.py discover --city all      # fetch sources (IBB 635, TfL 890, Digitraffic 2279)
python3 cam.py probe --city istanbul --limit 22
python3 cam.py uptime --limit 150       # cron: every 10 min, silent
python3 cam.py score
python3 cam.py obs  --city istanbul --cams 4
python3 cam.py meta --city istanbul
python3 cam.py report
python3 export_web.py                   # refresh the web player data
```

## Web player (this site)

`site/index.html` rotates a city's cameras and takes everything from the URL:

```
?city=istanbul&rotation=5&mode=full&pool=all&lim=40&overlay=1&badge=1&sound=0
```

- `city` — city slug from `data/cities.json` (istanbul, london, helsinki, tampere, turku, oulu, finland)
- `rotation` — seconds per camera, **default 5**
- `mode` — `full` | `pip` | `grid` (2×2)
- `pool` — `all` (badge shown) | `a` (open-licence cameras only)
- `lim` — max cameras in the rotation
- `overlay` / `badge` / `sound` — `1`/`0`
- `cam=12,13` — force specific camera ids · `statik=1` — freeze · `panel=1` — open controls

Each tile checks its own stream: on a fatal HLS/media error it is marked dead and replaced
with the next healthy camera; if everything dies, a standby card appears. The overlay shows
city, local time (Open-Meteo for weather + sunset) and the camera's **licence class**, so a
class-C feed is never mistaken for a cleared one.

For OBS: add the URL as a **Browser Source** with `overlay=0`.

## Known limits (measured, not assumed)

- **Istanbul (IBB TKM):** 635 traffic cameras exposed through the municipal gateway, but
  HLS reachability from this host was unstable (3/22 → 0/24 → 0/3 within minutes) and the
  snapshot endpoint returned "no camera" placeholders. Cameras are traffic-oriented, not
  scenic. A Turkish-based ingest node plus written permission are prerequisites.
- **No class-A scenic camera exists for Istanbul.** Tourism webcam operators (SkylineWebcams/
  VisioRay) explicitly forbid reproduction and redistribution in their terms.
- **Class-A open pools are technically weak:** TfL JamCams are 352×288 ~10 s clips;
  Fintraffic Digitraffic is 1280×720 but snapshot-based, not video.
- Vision scoring in this run used upscaled montage tiles, which inflates sharpness — the
  quality score keeps a low vision weight for that reason.

## Licence

Code: MIT. Camera imagery belongs to its owners — publishing this repo grants no rights to
any camera feed.
