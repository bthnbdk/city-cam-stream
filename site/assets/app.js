/* City Cam Stream — URL parametreli kamera rotasyon oynatıcısı
   Parametreler:
     city=istanbul        şehir slug'ı (data/cities.json içinden)
     rotation=30          kamerada kalma süresi (saniye) — VARSAYILAN 30
     mode=full|pip|grid   görünüm
     pool=all|a           kamera havuzu (a = yalnız açık lisanslı)
     lim=40               rotasyona girecek en fazla kamera
     preload=2            arkada ısıtılacak (hazır tutulacak) kamera sayısı
     overlay=1|0          alt bilgi barı      badge=1|0  lisans rozeti
     sound=1|0            ses (varsayılan kapalı)
     cam=12,13            belirli kamera id'leri     statik=1  rotasyonu durdur
     panel=1              kontrol paneli açık    h=1 ile panel açılır/kapanır   */
(() => {
  const q = new URLSearchParams(location.search);
  const num = (v, d) => (Number.isFinite(Number(v)) && Number(v) > 0 ? Number(v) : d);
  const cfg = {
    city: q.get('city') || 'istanbul',
    rotation: num(q.get('rotation'), 30),           // VARSAYILAN 30 SANİYE
    mode: ['full', 'pip', 'grid'].includes(q.get('mode')) ? q.get('mode') : 'full',
    pool: q.get('pool') === 'a' ? 'a' : 'all',
    lim: num(q.get('lim'), 40),
    preload: Math.min(6, num(q.get('preload'), 2)), // arkada hazır tutulacak kamera
    overlay: q.get('overlay') !== '0',
    badge: q.get('badge') !== '0',
    sound: q.get('sound') === '1',
    cams: (q.get('cam') || '').split(',').map(s => Number(s.trim())).filter(Boolean),
    static: q.get('statik') === '1' || q.get('static') === '1',
  };

  const $ = id => document.getElementById(id);
  const tilesEl = $('tiles'), standby = $('standby'), bar = $('bar'), preEl = $('preload');
  let cityDoc = null, playlist = [], base = 0, timer = null;
  const dead = new Set();          // akışı ölmüş kameralar
  const warm = new Map();          // camId -> {cam, el, hls}  (arkada oynayan hazır akışlar)
  const onScreen = new Set();      // şu an ekranda gösterilen kamera id'leri

  /* ---------- veri ---------- */
  async function boot() {
    const idx = await fetch('data/cities.json', { cache: 'no-store' }).then(r => r.json());
    const sel = $('c-city');
    sel.innerHTML = idx.cities.map(c =>
      `<option value="${c.city}">${c.label} — ${c.total} cameras</option>`).join('');
    sel.value = cfg.city;
    if (!idx.cities.some(c => c.city === cfg.city)) cfg.city = idx.cities[0]?.city;
    cityDoc = await fetch(`data/${cfg.city}.json`, { cache: 'no-store' }).then(r => r.json());
    document.title = `${cityDoc.label} — City Cam Stream`;
  }

  function buildPlaylist() {
    let list = cityDoc.cams;
    if (cfg.cams.length) list = cityDoc.cams.filter(c => cfg.cams.includes(c.id));
    if (cfg.pool === 'a') list = list.filter(c => c.lic === 'A');
    playlist = list.slice(0, cfg.lim);
    dead.clear(); onScreen.clear(); clearWarm(); base = 0;
  }

  const at = i => playlist[(i % playlist.length + playlist.length) % playlist.length];
  const slots = () => (cfg.mode === 'grid' ? 4 : cfg.mode === 'pip' ? 2 : 1);
  const step = () => (cfg.mode === 'grid' ? 4 : 1);

  /* ---------- medya öğesi üretimi (tek yer) ---------- */
  function mediaFor(cam) {
    const el = document.createElement(cam.kind === 'snapshot' ? 'img' : 'video');
    let hls = null;
    if (cam.kind === 'snapshot') {
      el.alt = cam.name; el.loading = 'eager'; el.decoding = 'async';
      el.src = cam.url + (cam.url.includes('?') ? '&' : '?') + 't=' + Date.now();
      el.onerror = () => markDead(cam);
      return { el, hls };
    }
    el.playsInline = true; el.autoplay = true; el.muted = !cfg.sound;
    el.setAttribute('muted', cfg.sound ? '' : ''); el.loop = cam.kind === 'mp4';
    el.addEventListener('error', () => markDead(cam));
    if (cam.kind === 'hls' && window.Hls && Hls.isSupported()) {
      hls = new Hls({ lowLatencyMode: false, maxBufferLength: 12, manifestLoadingTimeOut: 12000,
                      manifestLoadingMaxRetry: 1, fragLoadingMaxRetry: 2 });
      hls.loadSource(cam.url); hls.attachMedia(el);
      hls.on(Hls.Events.ERROR, (_, d) => { if (d.fatal) markDead(cam); });
    } else {
      el.src = cam.url;
    }
    el.play && el.play().catch(() => {});
    return { el, hls };
  }

  function dropWarm(id) {
    const w = warm.get(id);
    if (!w) return;
    try { w.hls && w.hls.destroy(); } catch (e) {}
    w.el.remove();
    warm.delete(id);
  }

  function clearWarm() {
    for (const id of [...warm.keys()]) dropWarm(id);
  }

  function markDead(cam) {
    if (dead.has(cam.id)) return;
    dead.add(cam.id);
    dropWarm(cam.id);
    // Ekranda ölen kamera varsa hemen sıradakine geç
    if (onScreen.has(cam.id)) advanceFrom(cam.id);
  }

  /* ---------- arkada ısıtma (siyah ekran olmasın) ---------- */
  function warmWindow() {
    const need = slots() + cfg.preload;
    const wanted = new Set();
    for (let k = 0; k < need; k++) {
      const cam = at(base + k);
      if (!cam) continue;
      wanted.add(cam.id);
      if (dead.has(cam.id) || warm.has(cam.id) || onScreen.has(cam.id)) continue;
      const m = mediaFor(cam);
      warm.set(cam.id, { cam, el: m.el, hls: m.hls });
      preEl.appendChild(m.el);
    }
    // pencerenin dışına çıkan hazır akışları boşalt (kaynak israfı olmasın)
    for (const id of [...warm.keys()]) if (!wanted.has(id)) dropWarm(id);
    // ekranda olmayan ama pencerede hiç öğe kalmadıysa ısıtmayı tetikle
    if (![...warm.keys()].length && playlist.length > slots()) setTimeout(warmWindow, 1500);
  }

  /* ---------- sahneler ---------- */
  function tileFor(cam, cls) {
    const tile = document.createElement('div');
    tile.className = 'tile' + (cls ? ' ' + cls : '');
    const cap = document.createElement('div'); cap.className = 'caption';
    const bd = document.createElement('div'); bd.className = 'badge2';
    cap.textContent = `${cam.name}${cam.area ? ' · ' + cam.area : ''}`;
    bd.textContent = cam.lic; bd.className = 'badge2 ' + cam.lic;
    bd.style.display = cfg.badge ? '' : 'none';
    tile.append(cap, bd);
    // hazır (ısıtılmış) öğe varsa onu taşı; yoksa yeni üret
    const w = warm.get(cam.id);
    if (w) {
      warm.delete(cam.id);
      tile.appendChild(w.el);
      if (w.hls) tile._hls = w.hls;
    } else {
      const m = mediaFor(cam);
      tile.appendChild(m.el);
      if (m.hls) tile._hls = m.hls;
    }
    tile._cam = cam;
    return tile;
  }

  function cleanupTiles(list) {
    list.forEach(t => {
      if (t._cam) onScreen.delete(t._cam.id);
      try { t._hls && t._hls.destroy(); } catch (e) {}
      t.remove();
    });
  }

  function render() {
    const mode = cfg.mode;
    tilesEl.className = mode === 'grid' ? 'grid' : (mode === 'pip' ? 'float' : '');
    if (!playlist.length) return standbyOn('No playable camera for this city/pool.');
    const n = slots(), fresh = [], seen = new Set();
    for (let k = 0; k < n; k++) {
      let cam = at(base + k), guard = 0;
      // ölü / ekranda olan / tekrar eden kamerayı atla
      while (cam && (dead.has(cam.id) || seen.has(cam.id)) && guard++ < playlist.length) {
        cam = at(base + k + guard);
      }
      if (!cam || dead.has(cam.id) || seen.has(cam.id)) continue;
      seen.add(cam.id);
      fresh.push(tileFor(cam, mode === 'pip' && k > 0 ? 'pip' : ''));
    }
    onScreen.clear();
    seen.forEach(id => onScreen.add(id));
    if (!fresh.length) return standbyOn();
    const old = [...tilesEl.children];
    if (mode === 'grid') {
      // ısıtılmış öğeler zaten oynuyor -> tek karede değiştir (siyahlık görünmez)
      tilesEl.innerHTML = '';
      tilesEl.append(...fresh);
      cleanupTiles(old);
    } else {
      // yeni kare eskisinin ÜSTÜNE biner, 1.2 sn sonra eskisi kaldırılır
      tilesEl.append(...fresh);
      old.forEach(t => { t.style.transition = 'opacity .6s'; t.style.opacity = '0'; });
      setTimeout(() => cleanupTiles(old), 1200);
    }
    standby.hidden = true;
    const cur = at(base);
    $('ov-cam').textContent = cur.name;
    $('ov-count').textContent = `${playlist.length - dead.size}/${playlist.length}`;
    if (cfg.badge) {
      $('ov-badge').hidden = false;
      $('ov-badge').textContent = cur.lic;
      $('ov-badge').className = 'badge ' + cur.lic;
    } else $('ov-badge').hidden = true;
    warmWindow();
  }

  function advanceFrom(deadCamId) {
    // Ekrandaki ölü kamerayı ısıtılmış sıradaki sağlam kamerayla değiştir
    [...tilesEl.children].filter(t => t._cam && t._cam.id === deadCamId).forEach(t => {
      let next = null;
      for (let k = 1; k <= playlist.length; k++) {
        const c = at(base + k);
        if (!dead.has(c.id) && !onScreen.has(c.id)) { next = c; break; }
      }
      if (!next) return standbyOn();
      onScreen.delete(deadCamId);
      t.replaceWith(tileFor(next, t.className.includes('pip') ? 'pip' : ''));
      onScreen.add(next.id);
      warmWindow();
    });
  }

  function standbyOn(msg) {
    standby.hidden = false;
    $('sb-city').textContent = cityDoc ? cityDoc.label : 'City';
    $('sb-msg').textContent = msg || 'All cameras unreachable — retrying…';
    setTimeout(() => { dead.clear(); render(); }, 8000);
  }

  function tick() {
    if (cfg.static || playlist.length <= slots()) return;
    base += step();
    render();
  }

  /* ---------- overlay ---------- */
  function overlayStart() {
    bar.hidden = !cfg.overlay;
    if (!cfg.overlay) return;
    $('ov-city').textContent = cityDoc.label + (cityDoc.country ? ' · ' + cityDoc.country : '');
    $('ov-tzlabel').textContent = 'local time · ' + cityDoc.tz;
    const clk = () => {
      try {
        $('ov-clock').textContent = new Date().toLocaleTimeString('tr-TR',
          { timeZone: cityDoc.tz, hour12: false });
      } catch (e) { $('ov-clock').textContent = new Date().toLocaleTimeString(); }
    };
    clk(); setInterval(clk, 1000);
    fetch(`https://api.open-meteo.com/v1/forecast?latitude=${cityDoc.lat}&longitude=${cityDoc.lon}` +
          `&current=temperature_2m,weather_code&daily=sunset&timezone=${encodeURIComponent(cityDoc.tz)}`)
      .then(r => r.json()).then(j => {
        const t = Math.round(j.current.temperature_2m);
        const s = (j.daily.sunset?.[0] || '').slice(11, 16);
        $('ov-wx').textContent = `${t}°C · code ${j.current.weather_code}` + (s ? ` · sunset ${s}` : '');
      }).catch(() => { $('ov-wx').textContent = 'weather: unavailable'; });
  }

  /* ---------- kontrol paneli ---------- */
  function panelInit() {
    const p = $('panel');
    p.hidden = q.get('panel') !== '1';
    $('c-rot').value = cfg.rotation;
    $('c-mode').value = cfg.mode;
    $('c-pool').value = cfg.pool;
    $('c-lim').value = cfg.lim;
    $('c-overlay').checked = cfg.overlay;
    $('c-badge').checked = cfg.badge;
    $('c-sound').checked = cfg.sound;
    $('c-pre').value = cfg.preload;
    p.addEventListener('change', () => {
      const u = new URL(location.href);
      u.searchParams.set('city', $('c-city').value);
      u.searchParams.set('rotation', String(Math.max(1, Number($('c-rot').value) || 30)));
      u.searchParams.set('mode', $('c-mode').value);
      u.searchParams.set('pool', $('c-pool').value);
      u.searchParams.set('lim', String(Math.max(1, Number($('c-lim').value) || 40)));
      u.searchParams.set('preload', String(Math.max(0, Math.min(6, Number($('c-pre').value) || 0))));
      u.searchParams.set('overlay', $('c-overlay').checked ? '1' : '0');
      u.searchParams.set('badge', $('c-badge').checked ? '1' : '0');
      u.searchParams.set('sound', $('c-sound').checked ? '1' : '0');
      u.searchParams.set('panel', '1');
      location.href = u.toString();
    });
    addEventListener('keydown', e => { if (e.key === 'h' || e.key === 'H') p.hidden = !p.hidden; });
  }

  /* ---------- başlat ---------- */
  boot().then(() => {
    buildPlaylist();
    panelInit(); overlayStart(); render();
    if (!cfg.static) timer = setInterval(tick, cfg.rotation * 1000);  // varsayılan 30 sn
    addEventListener('resize', () => render());
  }).catch(e => { standbyOn('Failed to load data: ' + e.message); });
})();
