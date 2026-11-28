/*
  Servidor de la web (Cloudflare Worker + KV): suscripciones a los avisos push y formulario de contacto.

  Solo guarda y borra suscripciones; el envío de los avisos lo hace avisar.py en GitHub Actions.

  Rutas públicas (las usa la web):
    POST /suscribir   cuerpo: la suscripción del navegador (endpoint + keys)
    POST /baja        cuerpo: { "endpoint": "..." }
    POST /contacto    cuerpo: { "nombre", "email", "motivo", "mensaje", "web" (trampa para robots) }
                      Envía el mensaje por correo (SMTP) a CONTACTO_DESTINO.

  Rutas privadas (las usa avisar.py; necesitan la cabecera "Authorization: Bearer <ADMIN_TOKEN>"):
    GET  /suscripciones   lista todas las suscripciones
    POST /borrar          cuerpo: { "endpoints": ["...", ...] }  (las que ya no existen: error 404/410)

  Configuración:
    SUSCRIPCIONES      espacio KV (wrangler.toml)
    ALLOWED_ORIGINS    webs que pueden suscribirse, separadas por comas (wrangler.toml)
    ADMIN_TOKEN        secreto: `npx wrangler secret put ADMIN_TOKEN`
    Formulario de contacto:
    SMTP_HOST, SMTP_PUERTO, CONTACTO_DESTINO   (wrangler.toml)
    SMTP_USUARIO, SMTP_CLAVE                   secretos: `npx wrangler secret put SMTP_USUARIO` (y SMTP_CLAVE)
*/

import { connect } from "cloudflare:sockets";

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
      if (!["/suscribir", "/baja", "/contacto"].includes(url.pathname)) return responder({ error: "no encontrado" }, 404);
      if (!permitidos.includes(origen)) return responder({ error: "origen no permitido" }, 403);
      if (peticion.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
      if (peticion.method !== "POST") return responder({ error: "método no permitido" }, 405);

      const datos = await leerJSON(peticion);
      if (url.pathname === "/contacto") return await contacto(datos, peticion, env, responder);
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

// ---------------------------------------------------------------------------
// Formulario de contacto
// ---------------------------------------------------------------------------
const MOTIVOS = { contacto: "Contacto", publicidad: "Publicidad / anunciarse", otro: "Otro" };
const MAX_POR_HORA = 5;   // mensajes por dirección IP y hora (contra el spam)

async function contacto(d, peticion, env, responder) {
  if (!d || typeof d !== "object") return responder({ error: "datos no válidos" }, 400);
  // Campo trampa: está oculto en la web, solo lo rellenan los robots. Se finge que todo fue bien.
  if (d.web) return responder({ ok: true });

  const limpiar = (v, max) => (typeof v === "string" ? v : "").replace(/\r\n?/g, "\n").trim().slice(0, max);
  const nombre = limpiar(d.nombre, 100).replace(/[\n\t]+/g, " ");
  const email = limpiar(d.email, 200);
  const mensaje = limpiar(d.mensaje, 3000);
  const motivo = MOTIVOS[d.motivo] ? d.motivo : "otro";
  if (!nombre) return responder({ error: "Escribe tu nombre." }, 400);
  if (!/^[^\s@<>"(),;:]+@[^\s@<>"(),;:]+\.[A-Za-z]{2,}$/.test(email)) return responder({ error: "El email no parece válido." }, 400);
  if (mensaje.length < 10) return responder({ error: "El mensaje es demasiado corto." }, 400);

  if (!env.SMTP_HOST || !env.SMTP_USUARIO || !env.SMTP_CLAVE) {
    console.error("Contacto: falta configurar SMTP_HOST, SMTP_USUARIO o SMTP_CLAVE");
    return responder({ error: "El formulario no está disponible ahora mismo." }, 503);
  }

  // Límite de envíos por IP (se guarda solo un resumen cifrado de la IP, durante una hora)
  const ip = peticion.headers.get("CF-Connecting-IP") || "";
  const claveIp = "contacto:" + (await sha256(ip)).slice(0, 32);
  const enviados = Number(await env.SUSCRIPCIONES.get(claveIp)) || 0;
  if (enviados >= MAX_POR_HORA) return responder({ error: "Has enviado muchos mensajes. Inténtalo más tarde." }, 429);
  await env.SUSCRIPCIONES.put(claveIp, String(enviados + 1), { expirationTtl: 3600 });

  const texto = `${MOTIVOS[motivo]}\n\nNombre: ${nombre}\nEmail: ${email}\n\n${mensaje}\n\n` +
    "-- \nEnviado desde el formulario de contacto de la web. Responde a este correo para contestar.";
  await enviarCorreo(env, {
    asunto: `[Web] ${MOTIVOS[motivo]}: ${nombre}`,
    texto,
    responderA: email,
  });
  return responder({ ok: true });
}

// Envío por SMTP con el buzón de la web. Puerto 465 (TLS directo) o 587 (STARTTLS).
async function enviarCorreo(env, { asunto, texto, responderA }) {
  const puerto = Number(env.SMTP_PUERTO) || 465;
  const usuario = env.SMTP_USUARIO;
  const destino = env.CONTACTO_DESTINO || usuario;
  let socket = connect({ hostname: env.SMTP_HOST, port: puerto },
    { secureTransport: puerto === 465 ? "on" : "starttls", allowHalfOpen: false });
  let lector = socket.readable.getReader(), escritor = socket.writable.getWriter();
  const enc = new TextEncoder(), dec = new TextDecoder();
  let pendiente = "";

  // Lee una respuesta completa del servidor (puede ocupar varias líneas: "250-..." y al final "250 ...")
  async function leer(esperado) {
    for (;;) {
      const lineas = pendiente.split("\r\n");
      for (let i = 0; i < lineas.length - 1; i++) {
        if (/^\d{3}( |$)/.test(lineas[i])) {
          const respuesta = lineas.slice(0, i + 1).join("\n");
          pendiente = lineas.slice(i + 1).join("\r\n");
          if (!String(lineas[i]).startsWith(String(esperado))) throw new Error("SMTP: " + respuesta);
          return respuesta;
        }
      }
      const { value, done } = await lector.read();
      if (done) throw new Error("SMTP: conexión cerrada");
      pendiente += dec.decode(value, { stream: true });
    }
  }
  const enviar = (linea) => escritor.write(enc.encode(linea + "\r\n"));
  const orden = async (linea, esperado) => { await enviar(linea); return leer(esperado); };
  const dominio = usuario.split("@")[1] || "localhost";

  try {
    await leer(220);
    await orden("EHLO " + dominio, 250);
    if (puerto !== 465) {
      await orden("STARTTLS", 220);
      lector.releaseLock(); escritor.releaseLock();
      socket = socket.startTls();
      lector = socket.readable.getReader(); escritor = socket.writable.getWriter();
      await orden("EHLO " + dominio, 250);
    }
    await orden("AUTH LOGIN", 334);
    await orden(b64(usuario), 334);
    await orden(b64(env.SMTP_CLAVE), 235);
    await orden(`MAIL FROM:<${usuario}>`, 250);
    await orden(`RCPT TO:<${destino}>`, 250);
    await orden("DATA", 354);
    const cuerpo = b64(texto.replace(/\n/g, "\r\n")).replace(/.{76}/g, "$&\r\n");
    const cabeceras = [
      `From: =?UTF-8?B?${b64("Web Eventos Madrid Metropolitano")}?= <${usuario}>`,
      `To: <${destino}>`,
      `Reply-To: <${responderA}>`,
      `Subject: =?UTF-8?B?${b64(asunto)}?=`,
      `Date: ${new Date().toUTCString().replace("GMT", "+0000")}`,
      `Message-ID: <${crypto.randomUUID()}@${dominio}>`,
      "MIME-Version: 1.0",
      "Content-Type: text/plain; charset=UTF-8",
      "Content-Transfer-Encoding: base64",
    ];
    // El cuerpo va en base64, así que ninguna línea puede empezar por "." (no hace falta escaparlas)
    await orden(cabeceras.join("\r\n") + "\r\n\r\n" + cuerpo + "\r\n.", 250);
    await enviar("QUIT").catch(() => {});
  } finally {
    socket.close().catch(() => {});
  }
}

function b64(texto) {
  let bin = "";
  for (const b of new TextEncoder().encode(texto)) bin += String.fromCharCode(b);
  return btoa(bin);
}

async function sha256(texto) {
  const hash = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(texto));
  return [...new Uint8Array(hash)].map(b => b.toString(16).padStart(2, "0")).join("");
}
