/**
 * SignConnect Service Worker
 * Strategy:
 *   - Static assets   → Cache-first (fast, versioned by CACHE_NAME)
 *   - API / frames    → Network-only (never cache dynamic data)
 *   - Pages           → Network-first, fall back to cache for offline
 */

const CACHE_NAME   = "signconnect-v1";
const OFFLINE_URL  = "/";

// Assets to pre-cache on SW install.
// These mirror the resources loaded by base.html so the app shell is
// available offline after a single page visit.
const PRECACHE = [
  "/",
  "/translator",
  "/history",
  "/static/css/design.css",
  "/static/css/home.css",
  "/static/css/pages.css",
  "/static/js/i18n.js",
  "/static/js/app.js",
  "/static/manifest.json",
  "/static/icons/icon-192.png",
];

// Requests that must NEVER be served from cache
const NETWORK_ONLY_PATTERNS = [
  /^\/api\//,
  /\/camera_frame/,
  /\/video_feed/,
  /\/socket\.io\//,
];

// ── Install ─────────────────────────────────────────────────────────────────
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      Promise.allSettled(PRECACHE.map((url) => cache.add(url)))
    )
  );
  self.skipWaiting();
});

// ── Activate — clean old caches ─────────────────────────────────────────────
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

// ── Fetch ────────────────────────────────────────────────────────────────────
self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Only handle same-origin GET requests
  if (request.method !== "GET" || url.origin !== self.location.origin) return;

  // Network-only: API, camera, socket.io
  if (NETWORK_ONLY_PATTERNS.some((re) => re.test(url.pathname))) return;

  // Static assets: cache-first
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(request).then(
        (cached) => cached || fetch(request).then((res) => {
          if (res.ok) {
            const clone = res.clone();
            caches.open(CACHE_NAME).then((c) => c.put(request, clone));
          }
          return res;
        })
      )
    );
    return;
  }

  // HTML pages: network-first, fall back to cache
  event.respondWith(
    fetch(request)
      .then((res) => {
        if (res.ok) {
          const clone = res.clone();
          caches.open(CACHE_NAME).then((c) => c.put(request, clone));
        }
        return res;
      })
      .catch(() => caches.match(request).then((cached) => cached || caches.match(OFFLINE_URL)))
  );
});
