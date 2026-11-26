/*
  Servidor de suscripciones a los avisos push (Cloudflare Worker + KV).

  Solo guarda y borra suscripciones; el envío de los avisos lo hace avisar.py en GitHub Actions.

  Rutas públicas (las usa la web):
    POST /suscribir   cuerpo: la suscripción del navegador (endpoint + keys)
    POST /baja        cuerpo: { "endpoint": "..." }

  Rutas privadas (las usa avisar.py; necesitan la cabecera "Authorization: Bearer <ADMIN_TOKEN>"):
    GET  /suscripciones   lista todas las suscripciones
    POST /borrar          cuerpo: { "endpoints": ["...", ...] }  (las que ya no existen: error 404/410)

  Configuración:
    SUSCRIPCIONES      espacio KV (wrangler.toml)
    ALLOWED_ORIGINS    webs que pueden suscribirse, separadas por comas (wrangler.toml)
    ADMIN_TOKEN        secreto: `npx wrangler secret put ADMIN_TOKEN`
*/

// Servicios de push de los navegadores. Así nadie puede usar este servidor para guardar otras direcciones.
const SERVICIOS_PUSH = [
  "fcm.googleapis.com",              // Chrome, Edge y Android
  "android.googleapis.com",
  "push.services.mozilla.com",      // Firefox (updates.push.services.mozilla.com)
  "push.apple.com",                 // Safari e iPhone (web.push.apple.com)
  "notify.windows.com",             // Edge antiguo (*.notify.windows.com)
];
const MAX_CUERPO = 4096;

export default {
  async fetch(peticion, env) {
    const url = new URL(peticion.url);
    const origen = peticion.headers.get("Origin") || "";
    const permitidos = (env.ALLOWED_ORIGINS || "").split(",").map(s => s.trim()).filter(Boolean);
    const cors = permitidos.includes(origen) ? {
      "Access-Control-Allow-Origin": origen,
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Max-Age": "86400",
      "Vary": "Origin",
    } : { "Vary": "Origin" };
    const responder = (cuerpo, estado = 200) => new Response(JSON.stringify(cuerpo), {
      status: estado, headers: { "Content-Type": "application/json", ...cors } });

    try {
      // --- Rutas privadas (avisar.py) ---
      if (url.pathname === "/suscripciones" || url.pathname === "/borrar") {
        if (!(await tokenValido(peticion, env))) return responder({ error: "no autorizado" }, 401);
        if (url.pathname === "/suscripciones" && peticion.method === "GET") {
          return responder({ suscripciones: await listar(env) });
        }
        if (url.pathname === "/borrar" && peticion.method === "POST") {
          const { endpoints } = await leerJSON(peticion);
          if (!Array.isArray(endpoints)) return responder({ error: "faltan endpoints" }, 400);
          await Promise.all(endpoints.map(async e => env.SUSCRIPCIONES.delete(await clave(String(e)))));
          return responder({ borradas: endpoints.length });
        }
        return responder({ error: "método no permitido" }, 405);
      }

      // --- Rutas públicas (la web) ---
      if (url.pathname !== "/suscribir" && url.pathname !== "/baja") return responder({ error: "no encontrado" }, 404);
      if (!permitidos.includes(origen)) return responder({ error: "origen no permitido" }, 403);
      if (peticion.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
      if (peticion.method !== "POST") return responder({ error: "método no permitido" }, 405);

      const datos = await leerJSON(peticion);
      if (url.pathname === "/suscribir") {
        const sub = validar(datos);
        if (!sub) return responder({ error: "suscripción no válida" }, 400);
        // La suscripción va en los metadatos de la clave: así el listado no necesita una lectura por cada una
        await env.SUSCRIPCIONES.put(await clave(sub.endpoint), "1", { metadata: sub });
        return responder({ ok: true }, 201);
      }
      // /baja
      if (typeof datos.endpoint !== "string" || !endpointValido(datos.endpoint)) {
        return responder({ error: "endpoint no válido" }, 400);
      }
      await env.SUSCRIPCIONES.delete(await clave(datos.endpoint));
      return responder({ ok: true });
    } catch (e) {
      if (e instanceof ErrorCuerpo) return responder({ error: e.message }, 400);
      console.error(e);
      return responder({ error: "error interno" }, 500);
    }
  },
};

class ErrorCuerpo extends Error {}

async function leerJSON(peticion) {
  const texto = await peticion.text();
  if (texto.length > MAX_CUERPO) throw new ErrorCuerpo("demasiado grande");
  try { return JSON.parse(texto); } catch { throw new ErrorCuerpo("JSON no válido"); }
}

function endpointValido(endpoint) {
  let u;
  try { u = new URL(endpoint); } catch { return false; }
  return u.protocol === "https:" && endpoint.length <= 600 &&
    SERVICIOS_PUSH.some(h => u.hostname === h || u.hostname.endsWith("." + h));
}

// Se queda solo con los campos necesarios y comprueba su formato
function validar(d) {
  if (!d || typeof d !== "object" || !d.keys || typeof d.keys !== "object") return null;
  const { endpoint } = d, { p256dh, auth } = d.keys;
  const b64url = /^[A-Za-z0-9_-]+={0,2}$/;
  if (typeof endpoint !== "string" || !endpointValido(endpoint)) return null;
  if (typeof p256dh !== "string" || !b64url.test(p256dh) || p256dh.length < 80 || p256dh.length > 100) return null;
  if (typeof auth !== "string" || !b64url.test(auth) || auth.length < 16 || auth.length > 32) return null;
  return { endpoint, keys: { p256dh, auth } };
}

// La clave en KV es el SHA-256 del endpoint (los endpoints son largos y tienen caracteres raros)
async function clave(endpoint) {
  const hash = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(endpoint));
  return "sub:" + [...new Uint8Array(hash)].map(b => b.toString(16).padStart(2, "0")).join("");
}

async function listar(env) {
  const todas = [];
  let cursor;
  do {
    const pagina = await env.SUSCRIPCIONES.list({ prefix: "sub:", cursor });
    for (const k of pagina.keys) if (k.metadata) todas.push(k.metadata);
    cursor = pagina.list_complete ? undefined : pagina.cursor;
  } while (cursor);
  return todas;
}

// Compara el token en tiempo constante
async function tokenValido(peticion, env) {
  const recibido = (peticion.headers.get("Authorization") || "").replace(/^Bearer\s+/i, "");
  if (!env.ADMIN_TOKEN || !recibido) return false;
  const enc = new TextEncoder();
  const [a, b] = await Promise.all([recibido, env.ADMIN_TOKEN].map(t => crypto.subtle.digest("SHA-256", enc.encode(t))));
  const x = new Uint8Array(a), y = new Uint8Array(b);
  let dif = 0;
  for (let i = 0; i < x.length; i++) dif |= x[i] ^ y[i];
  return dif === 0;
}
