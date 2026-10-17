/* City Cam Stream — URL parametreli kamera rotasyon oynatıcısı
   Parametreler:
     city=istanbul      şehir slug'ı (data/cities.json içinden)
     rotation=5         kamerada kalma süresi (saniye) — VARSAYILAN 5
     mode=full|pip|grid görünüm
     pool=all|a         kamera havuzu (a = yalnız açık lisanslı)
     lim=40             rotasyona girecek en fazla kamera
     overlay=1|0        alt bilgi barı
     badge=1|0          lisans rozeti
     sound=1|0          ses (varsayılan kapalı)
     cam=12,13,14       belirli kamera id'leri (şehir listesini geçersiz kılar)
     panel=1            kontrol paneli açık başlar
     statik=1           rotasyonu durdur (tek kamera / ilk kare)            */
(() => {
  const q = new URLSearchParams(location.search);
  const num = (v, d) => (Number.isFinite(Number(v)) && Number(v) > 0 ? Number(v) : d);
  const cfg = {
    city: q.get('city') || 'istanbul',
    rotation: num(q.get('rotation'), 5),            // VARSAYILAN 5 SANİYE
    mode: ['full', 'pip', 'grid'].includes(q.get('mode')) ? q.get('mode') : 'full',
    pool: q.get('pool') === 'a' ? 'a' : 'all',
    lim: num(q.get('lim'), 40),
    overlay: q.get('overlay') !== '0',
    badge: q.get('badge') !== '0',
    sound: q.get('sound') === '1',
    cams: (q.get('cam') || '').split(',').map(s => Number(s.trim())).filter(Boolean),
    static: q.get('statik') === '1' || q.get('static') === '1',
  };

  const $ = id => document.getElementById(id);
  const tilesEl = $('tiles'), standby = $('standby'), bar = $('bar');
  let cityDoc = null, playlist = [], base = 0, timer = null, dead = new Set(), hlsInstances = [];

  /* ---------- veri ---------- */
  async function boot() {
    const idx = await fetch('data/cities.json', { cache: 'no-store' }).then(r => r.json());
    const sel = $('c-city');
    sel.innerHTML = idx.cities.map(c =>
      `<option value="${c.city}">${c.label} — ${c.count} kamera</option>`).join('');
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
    dead.clear(); base = 0;
  }

  /* ---------- oynatıcı ---------- */
  const alive = () => playlist.filter(c => !dead.has(c.id));
  const at = i => playlist[i % playlist.length];

  function makeTile(cls) {
    const d = document.createElement('div');
    d.className = 'tile' + (cls ? ' ' + cls : '');
    d.innerHTML = `<div class="caption"></div><div class="badge2"></div>`;
    tilesEl.appendChild(d);
    return d;
  }

  function mount(tile, cam, refreshKey) {
    const cap = tile.querySelector('.caption'), bd = tile.querySelector('.badge2');
    const old = tile.querySelector('video,img');
    if (old) old.remove();
    hlsInstances = hlsInstances.filter(h => { try { h.destroy(); } catch (e) {} return false; });
    cap.textContent = `${cam.name}${cam.area ? ' · ' + cam.area : ''}` +
      (cam.lic === 'C' ? '  ⚠ licence: not cleared for broadcast' : '');
    bd.textContent = cam.lic; bd.className = 'badge2 ' + cam.lic;
    bd.style.display = cfg.badge ? '' : 'none';

    if (cam.kind === 'snapshot') {
      const img = document.createElement('img');
      img.alt = cam.name;
      img.onerror = () => fail(cam);
      img.src = cam.url + (cam.url.includes('?') ? '&' : '?') + 't=' + Date.now();
      tile.appendChild(img);
      tile._refresh = () => { img.src = cam.url + (cam.url.includes('?') ? '&' : '?') + 't=' + Date.now(); };
      return;
    }
    const v = document.createElement('video');
    v.playsInline = true; v.autoplay = true; v.muted = !cfg.sound; v.loop = cam.kind === 'mp4';
    v.setAttribute('muted', cfg.sound ? '' : '');
    v.onerror = () => fail(cam);
    tile.appendChild(v);
    tile._refresh = null;
    if (cam.kind === 'hls' && window.Hls && Hls.isSupported()) {
      const h = new Hls({ lowLatencyMode: false, maxBufferLength: 10, manifestLoadingTimeOut: 12000,
                          manifestLoadingMaxRetry: 1, fragLoadingMaxRetry: 2 });
      h.loadSource(cam.url); h.attachMedia(v);
      h.on(Hls.Events.ERROR, (_, data) => { if (data.fatal) fail(cam); });
      hlsInstances.push(h);
    } else {
      v.src = cam.url;
    }
    v.play().catch(() => {});
  }

  function fail(cam) {
    if (dead.has(cam.id)) return;
    dead.add(cam.id);
    const tiles = [...tilesEl.children];
    const idx = tiles.findIndex(t => t._cam && t._cam.id === cam.id);
    if (idx === -1) return;
    const next = nextAlive();
    if (!next) return standbyOn();
    mount(tiles[idx], next);
  }

  function nextAlive() {
    for (let k = 1; k <= playlist.length; k++) {
      const c = at(base + k);
      if (!dead.has(c.id)) return c;
    }
    return null;
  }

  function render() {
    const mode = cfg.mode;
    tilesEl.className = mode === 'grid' ? 'grid' : (mode === 'pip' ? 'float' : '');
    tilesEl.innerHTML = '';
    if (!playlist.length) return standbyOn('No playable camera for this city/pool.');
    const n = mode === 'grid' ? 4 : (mode === 'pip' ? 2 : 1);
    let shown = 0;
    for (let k = 0; k < n; k++) {
      const cam = at(base + k);
      if (!cam || dead.has(cam.id)) continue;
      const tile = makeTile(mode === 'pip' && k > 0 ? 'pip' : '');
      tile._cam = cam;
      mount(tile, cam);
      shown++;
    }
    if (!shown) return standbyOn();
    standby.hidden = true;
    const cur = at(base);
    $('ov-cam').textContent = cur.name;
    $('ov-count').textContent = `${alive().length}/${playlist.length}`;
    if (cfg.badge) { $('ov-badge').hidden = false; $('ov-badge').textContent = cur.lic; $('ov-badge').className = 'badge ' + cur.lic; }
    else $('ov-badge').hidden = true;
  }

  function standbyOn(msg) {
    standby.hidden = false;
    $('sb-city').textContent = cityDoc ? cityDoc.label : 'City';
    $('sb-msg').textContent = msg || 'All cameras are unreachable — reconnecting…';
    dead.clear();
  }

  function tick() {
    if (cfg.static || playlist.length <= 1) return;
    base += cfg.mode === 'grid' ? 4 : 1;
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
        $('ov-wx').textContent = `${t}°C · kod ${j.current.weather_code}` + (s ? ` · batım ${s}` : '');
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
    const apply = () => {
      const u = new URL(location.href);
      u.searchParams.set('city', $('c-city').value);
      u.searchParams.set('rotation', String(Math.max(1, Number($('c-rot').value) || 5)));
      u.searchParams.set('mode', $('c-mode').value);
      u.searchParams.set('pool', $('c-pool').value);
      u.searchParams.set('lim', String(Math.max(1, Number($('c-lim').value) || 40)));
      u.searchParams.set('overlay', $('c-overlay').checked ? '1' : '0');
      u.searchParams.set('badge', $('c-badge').checked ? '1' : '0');
      u.searchParams.set('sound', $('c-sound').checked ? '1' : '0');
      u.searchParams.set('panel', '1');
      location.href = u.toString();
    };
    p.addEventListener('change', apply);
    addEventListener('keydown', e => { if (e.key === 'h' || e.key === 'H') p.hidden = !p.hidden; });
  }

  /* ---------- başlat ---------- */
  boot().then(() => {
    buildPlaylist();
    panelInit(); overlayStart(); render();
    if (!cfg.static) timer = setInterval(tick, cfg.rotation * 1000);  // varsayılan 5 sn
    addEventListener('resize', () => render());
  }).catch(e => { standbyOn('Failed to load data: ' + e.message); });
})();
