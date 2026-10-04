/* AGame service worker. Keeps the last successful snapshot available offline.
   The build only swaps dist/ after a successful build, so whatever this worker caches
   is always a complete, validated snapshot. API calls and health records are never cached. */
const CACHE = "agame-__CACHE_VERSION__";
const SHELL = ["./fitness_dashboard.html", "./manifest.webmanifest", "./icons/icon-192.png", "./icons/icon-512.png", "./icons/apple-touch-icon.png"];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith("agame-") && k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});

function isPrivateOrApi(url) {
  return url.pathname.includes("/api/") || url.pathname.includes("/auth/") || url.pathname.includes("/records/");
}

self.addEventListener("fetch", event => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin || isPrivateOrApi(url)) return;
  const isPage = req.mode === "navigate" || url.pathname.endsWith("fitness_dashboard.html") || url.pathname.endsWith("/");
  if (isPage) {
    // network first: newest successful build when online, last snapshot when offline
    event.respondWith(fetch(req).then(res => {
      if (res.ok && res.headers.get("content-type") && res.headers.get("content-type").includes("text/html") && !res.redirected) {
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put("./fitness_dashboard.html", copy));
      }
      return res;
    }).catch(() => caches.match("./fitness_dashboard.html")));
    return;
  }
  event.respondWith(caches.match(req).then(hit => hit || fetch(req).then(res => {
    if (res.ok && (url.pathname.includes("/icons/") || url.pathname.endsWith(".webmanifest"))) {
      const copy = res.clone();
      caches.open(CACHE).then(c => c.put(req, copy));
    }
    return res;
  })));
});
