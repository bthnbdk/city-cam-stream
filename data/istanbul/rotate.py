#!/usr/bin/env python3
"""
rotate.py — OBS WebSocket v5 rotasyon + otomatik yedek sahne (taslak, sahada test edilmeli)
Kurulum: pip install websocket-client   | OBS: Araçlar > WebSocket Sunucu Ayarları > Etkin
Çalıştırma: python3 rotate.py --city istanbul --ws obs://localhost:4455 --pass PAROLA
"""
import argparse, json, ssl, subprocess, time, urllib.request
from pathlib import Path

PLAYLIST = [["CAM1_S._YOLU_ATAKÖY_1", "https://hls.ibb.gov.tr/tkm1/hls/8.stream/playlist.m3u8", "full"], ["CAM2_ATATÜRK_HAVALİMANI", "https://hls.ibb.gov.tr/tkm1/hls/13.stream/playlist.m3u8", "full"], ["CAM3_BAKIRKÖY_İSTANBUL_", "https://hls.ibb.gov.tr/tkm1/hls/27.stream/playlist.m3u8", "full"], ["CAM4_AKOM", "https://hls.ibb.gov.tr/tkm4/hls/2.stream/playlist.m3u8", "full"]]      # [(kamera_adı, akış_url, sahne_tipi)]  sahne_tipi: full|pip
ROTATE_SEC = 30           # her kamerada kalma süresi (VARSAYILAN 30 sn)
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
    ap.add_argument("--city", default="istanbul"); ap.add_argument("--ws", default="ws://localhost:4455")
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
