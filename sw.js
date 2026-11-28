/*
  Service worker de la web (la parte que el navegador deja funcionando en segundo plano).
  - Guarda una copia de la web para que abra aunque no haya conexión.
  - Recibe los avisos push y los muestra como notificación.
  Si cambias la lista de archivos de abajo, sube el número de VERSION.
*/
const VERSION = "v2";
const CACHE = "metropolitano-" + VERSION;
const ARCHIVOS = [
  "./", "index.html", "eventos.json", "manifest.json", "favicon.svg", "apple-touch-icon.png",
  "iconos/icono-192.png", "iconos/icono-512.png", "privacidad.html", "contacto.html",
];

self.addEventListener("install", ev => {
  ev.waitUntil(caches.open(CACHE).then(c => c.addAll(ARCHIVOS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", ev => {
  ev.waitUntil(
    caches.keys()
      .then(nombres => Promise.all(nombres.filter(n => n !== CACHE).map(n => caches.delete(n))))
      .then(() => self.clients.claim()));
});

// Primero la red (para tener siempre los eventos al día); si no hay conexión, la copia guardada.
// Solo para archivos de esta web: las fuentes y el servidor de avisos y contacto van directos.
self.addEventListener("fetch", ev => {
  const url = new URL(ev.request.url);
  if (ev.request.method !== "GET" || url.origin !== location.origin) return;
  ev.respondWith(
    fetch(ev.request)
      .then(resp => {
        if (resp.ok) {
          const copia = resp.clone();
          caches.open(CACHE).then(c => c.put(ev.request, copia));
        }
        return resp;
      })
      .catch(() => caches.match(ev.request, { ignoreSearch: true })
        .then(r => r || (ev.request.mode === "navigate" ? caches.match("index.html") : undefined))
        .then(r => r || Response.error())));
});

// ---- Avisos push ----

self.addEventListener("push", ev => {
  let datos = {};
  try { datos = ev.data ? ev.data.json() : {}; } catch { datos = { body: ev.data && ev.data.text() }; }
  const titulo = datos.title || "Metropolitano";
  ev.waitUntil(self.registration.showNotification(titulo, {
    body: datos.body || "",
    icon: "iconos/icono-192.png",
    badge: "iconos/aviso-96.png",   // silueta para la barra de estado de Android
    tag: datos.tag,              // dos avisos con la misma etiqueta no se duplican
    lang: "es",
    data: { url: datos.url || "./#eventos" },
  }));
});

// Al tocar la notificación: abre la web (o la trae al frente si ya estaba abierta)
self.addEventListener("notificationclick", ev => {
  ev.notification.close();
  const destino = new URL(ev.notification.data?.url || "./", self.registration.scope).href;
  ev.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(ventanas => {
    for (const v of ventanas) {
      if (v.url.startsWith(self.registration.scope) && "focus" in v) {
        v.navigate(destino).catch(() => {});
        return v.focus();
      }
    }
    return self.clients.openWindow(destino);
  }));
});

// Si el navegador renueva la suscripción por su cuenta, se avisa al servidor con la nueva
self.addEventListener("pushsubscriptionchange", ev => {
  ev.waitUntil((async () => {
    const cfg = await fetch("config.json").then(r => r.json());
    if (!cfg.push_api || !cfg.vapid) return;
    const nueva = await self.registration.pushManager.subscribe({
      userVisibleOnly: true, applicationServerKey: claveABytes(cfg.vapid) });
    const api = cfg.push_api.replace(/\/$/, "");
    if (ev.oldSubscription) {
      await fetch(api + "/baja", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ endpoint: ev.oldSubscription.endpoint }) }).catch(() => {});
    }
    await fetch(api + "/suscribir", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(nueva) });
  })());
});

function claveABytes(b64) {
  const s = (b64 + "=".repeat((4 - b64.length % 4) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  return Uint8Array.from(atob(s), c => c.charCodeAt(0));
}
