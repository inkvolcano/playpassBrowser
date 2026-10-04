// Play Pass Browser's service worker: once the page has been opened (or installed as an app) it opens
// quickly and works offline. The page itself comes from the network first, so the monthly update
// shows straight away, and from the saved copy when there's no connection or the network is very
// slow. Details files, fonts and icons come from the cache and are refreshed in the background; the
// screenshots, icons and trailer stills you've seen are kept too, up to MAX_IMAGES.
const VERSION = "v1";
const PAGE = `ppb-page-${VERSION}`, FILES = `ppb-files-${VERSION}`, IMAGES = `ppb-images-${VERSION}`;
const MAX_IMAGES = 800;
const SLOW = 5000;  // ms to wait for the network before showing the saved page
const HOME = new URL("./", self.registration.scope).href;
const IMAGE_HOSTS = ["play-lh.googleusercontent.com", "i.ytimg.com"];

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    await (await caches.open(PAGE)).add(HOME).catch(() => { /* saved on the next visit */ });
    await (await caches.open(FILES)).addAll(["manifest.webmanifest", "icons/icon-192.png", "icons/icon-512.png"]).catch(() => {});
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) if (![PAGE, FILES, IMAGES].includes(key)) await caches.delete(key);
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin === location.origin) {
    if (req.mode === "navigate") {
      if (url.href.split(/[?#]/)[0] === HOME || url.pathname.endsWith("/index.html")) event.respondWith(page(event));
    } else if (!url.pathname.endsWith("/sw.js")) {
      event.respondWith(fresh(event, req, false));
    }
  } else if (/(^|\.)fonts\.(googleapis|gstatic)\.com$/.test(url.hostname)) {
    event.respondWith(fresh(event, req, true));
  } else if (IMAGE_HOSTS.includes(url.hostname)) {
    event.respondWith(image(event, req));
  }
});

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// The page: the network's copy (saved for next time), else the saved one.
async function page(event) {
  const cache = await caches.open(PAGE);
  const network = fetch(event.request).then(async (res) => {
    if (res.ok) await cache.put(HOME, res.clone());
    return res;
  });
  event.waitUntil(network.catch(() => {}));
  const saved = await cache.match(HOME);
  if (!saved) return network;
  return Promise.race([network.then((res) => (res.ok ? res : saved), () => saved), wait(SLOW).then(() => saved)]);
}

// Files: the saved copy straight away, refreshed in the background (fetched from the network the
// first time). Google's font host allows cross-origin reads, so its files are fetched in CORS mode
// and stored as ordinary responses.
async function fresh(event, req, cors) {
  const cache = await caches.open(FILES);
  const saved = await cache.match(req, { ignoreVary: true });
  const network = fetch(cors ? new Request(req.url, { mode: "cors", credentials: "omit" }) : req).then(async (res) => {
    if (res.ok) await cache.put(req, res.clone());
    return res;
  });
  event.waitUntil(network.catch(() => {}));
  return saved || network;
}

// Images: kept once seen. Both image hosts allow cross-origin reads; fetching in CORS mode keeps the
// stored copies ordinary responses rather than opaque ones (which browsers count as several MB each).
let added = 0;
async function image(event, req) {
  const cache = await caches.open(IMAGES);
  const saved = await cache.match(req.url);
  if (saved) return saved;
  let res;
  try {
    res = await fetch(req.url, { mode: "cors", credentials: "omit" });
  } catch (e) {
    return fetch(req);  // offline, or the host stopped allowing CORS: a plain request, not kept
  }
  if (res.ok) event.waitUntil(cache.put(req.url, res.clone()).then(() => (++added % 50 ? null : trim(cache))).catch(() => {}));
  return res;
}
async function trim(cache) {
  const keys = await cache.keys();  // oldest first
  for (const key of keys.slice(0, Math.max(0, keys.length - MAX_IMAGES))) await cache.delete(key);
}
