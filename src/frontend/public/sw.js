const ASSETS = "__BUILD_ASSETS__";
const CACHE = "hs-react-" + ASSETS.join(",").replace(/[^a-zA-Z0-9,-]/g, "");
const SHELL = [
  "/",
  "/manifest.webmanifest",
  "/icons/icon.svg",
  "/fonts/bricolage-grotesque-latin-wght-normal.woff2",
  ...ASSETS,
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter(
              (key) =>
                key !== CACHE &&
                (key.startsWith("hs-react-") || key.startsWith("hs-shell-")),
            )
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (
    request.method !== "GET" ||
    url.origin !== self.location.origin ||
    url.pathname === "/api" ||
    url.pathname.startsWith("/api/")
  )
    return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(async () =>
        (await caches.open(CACHE))
          .match("/")
          .then((hit) => hit || Response.error()),
      ),
    );
  } else if (SHELL.includes(url.pathname)) {
    event.respondWith(
      caches
        .open(CACHE)
        .then((cache) => cache.match(url.pathname))
        .then((hit) => hit || fetch(request)),
    );
  }
});
