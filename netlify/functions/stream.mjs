// stream.mjs — token yenileme proxy'si (Netlify Function)
//
// Neden var: bazı kamera sağlayıcıları (EarthCam) akış URL'ini kısa ömürlü bir token ile verir:
//   https://videos-3.earthcam.com/fecnetwork/<id>.flv/playlist.m3u8?t=<token>&td=<YYYYMMDDHHMM>
// Token'ı tarayıcıda üretmek mümkün değil (kameralar sayfasını sunucu tarafında çekmek gerekir,
// CORS engeli). Bu fonksiyon sayfayı çeker, taze akış URL'ini ayıklar ve JSON döner.
//
// Kullanım:  GET /.netlify/functions/stream?page=https://www.earthcam.com/world/england/london/abbeyroad/
// Yanıt:     { ok, url, title, resolution, cacheSeconds }
//
// Güvenlik: yalnız izin verilen hostlar (SSRF koruması) ve yalnız https.

const ALLOWED_HOSTS = [
  "www.earthcam.com", "earthcam.com", "myearthcam.com", "www.myearthcam.com",
];

const HLS_RE = /"stream":"(https:\\?\/\\?\/[^"]+playlist\.m3u8[^"]*)"/;
const TITLE_RE = /<title>([\s\S]*?)<\/title>/i;

export default async (req) => {
  const url = new URL(req.url);
  const page = url.searchParams.get("page");
  if (!page) return json(400, { ok: false, error: "page parametresi gerekli" });

  let target;
  try {
    target = new URL(page);
  } catch {
    return json(400, { ok: false, error: "gecersiz page url" });
  }
  if (!ALLOWED_HOSTS.includes(target.hostname)) {
    return json(403, { ok: false, error: `izin verilmeyen host: ${target.hostname}` });
  }

  try {
    const res = await fetch(target.href, {
      headers: {
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
        "accept-language": "en",
      },
      redirect: "follow",
    });
    if (!res.ok) return json(502, { ok: false, error: `kaynak sayfa ${res.status}` });
    const html = await res.text();
    const m = html.match(HLS_RE);
    if (!m) return json(404, { ok: false, error: "sayfada canli akis bulunamadi" });
    const streamUrl = m[1].replace(/\\\//g, "/");
    const t = html.match(TITLE_RE);
    const title = t ? t[1].replace(/\s+/g, " ").replace(/\s*[-|]\s*EarthCam.*$/i, "").trim() : "";

    // Taze token -> kısa süre cache'le (CDN'e yük olmasın)
    return json(200, { ok: true, url: streamUrl, title, page: target.href, cacheSeconds: 240 }, 180);
  } catch (e) {
    return json(500, { ok: false, error: String(e).slice(0, 200) });
  }
};

function json(status, body, cacheSeconds = 0) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json",
      "cache-control": cacheSeconds ? `public, max-age=${cacheSeconds}` : "no-store",
      "access-control-allow-origin": "*",
    },
  });
}

export const config = { path: "/api/stream" };
