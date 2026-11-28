# Eventos del Riyadh Air Metropolitano

Recoge los próximos partidos y conciertos del estadio y los muestra en una página web.

## Archivos

| Archivo | Qué es |
|---|---|
| `recoger_eventos.py` | El script que lee las webs y crea `eventos.json` |
| `eventos.json` | Los eventos guardados (se regenera cada vez) |
| `eventos.ics` | Los mismos eventos en formato calendario (Google, Apple, Outlook) |
| `avisar.py` | Envía avisos por email y/o WhatsApp cuando hay novedades, y los avisos al móvil |
| `index.html` | La página que muestra los eventos |
| `manifest.json`, `sw.js`, `iconos/` | Lo que convierte la web en una app instalable (PWA) |
| `privacidad.html` | Política de privacidad (enlazada al pie de la página) |
| `contacto.html` | Formulario de contacto y publicidad (enlazado al pie de la página) |
| `avisos_push.py` | Envía los avisos al móvil (lo llama `avisar.py`) |
| `generar_claves_vapid.py` | Crea las claves de los avisos al móvil (solo una vez) |
| `worker/` | El pequeño servidor (Cloudflare) que guarda quién quiere avisos y envía el formulario de contacto |
| `requirements.txt` | Librerías de Python que necesita el script |

## Cómo usarlo

Abre una terminal en esta carpeta.

1. **Solo la primera vez**, instala las librerías:

   ```bash
   pip install -r requirements.txt
   ```

2. **Actualizar los eventos** (cuando quieras):

   ```bash
   python3 recoger_eventos.py
   ```

3. **Ver la página**: arranca un pequeño servidor y abre http://localhost:8000 en el navegador.

   ```bash
   python3 -m http.server 8000
   ```

   (Hace falta porque, por seguridad, el navegador no deja que una página abierta con
   doble clic lea otros archivos como `eventos.json`.) Para pararlo: `Ctrl + C`.

## Cómo funciona

- **esmadrid.com**: busca "metropolitano" en su agenda, abre cada resultado y lee los
  datos estructurados de la página (título, fechas, lugar), la hora del apartado
  "Horarios" y el tipo del apartado "Tipo". Solo guarda lo que es en el Metropolitano y
  todavía no ha pasado.
  La agenda de esmadrid incluye todos los partidos del Atlético en el Metropolitano.
  (La web del club no se usa: tiene una protección anti-robots para impedir la lectura
  automática.)
- **Sin duplicados**: dos eventos son el mismo si coinciden tipo, fecha y título
  (sin contar mayúsculas ni tildes); dos partidos el mismo día cuentan como uno.
  Si un evento aparece repetido, se combinan sus datos (por ejemplo, la hora).
- Si una web falla un día, se conservan los eventos que ya estaban guardados.

## Limitaciones conocidas

- Muchas horas de LaLiga salen como "por confirmar": la Liga las fija pocas semanas antes.
  Basta con volver a ejecutar el script más adelante.
- En conciertos de varios días, esmadrid solo da el rango (p. ej. 24–27 junio), no qué
  días exactos hay concierto.
- Si esmadrid cambia el diseño de su web, el script podría dejar de encontrar datos.

## Actualización automática (GitHub)

El archivo `.github/workflows/actualizar.yml` le dice a GitHub que, **cada día a las 10:00
(hora de Madrid, también en verano)**, ejecute el script, guarde el `eventos.json` nuevo,
vuelva a publicar la web en GitHub Pages y envíe los avisos. GitHub puede retrasar unos
minutos las tareas programadas.

Al subir cambios de código, el robot actualiza la web pero **no** envía avisos.

- **Ver si ha funcionado**: pestaña **Actions** del repositorio. Verde = bien, rojo = error.
- **Actualizar ahora mismo**: Actions → "Actualizar eventos y publicar web" → **Run workflow**.
- **Cambiar la hora**: en el archivo hay dos líneas `cron` (va en hora UTC, sin horario de
  verano): `0 8` es las 10:00 de Madrid en verano y `0 9` en invierno. Si las cambias,
  cambia también esas mismas horas en el paso "comprobar" del archivo.

## Calendario

En la web, el recuadro **"Suscríbete al calendario"** añade todos los eventos a tu
calendario y los mantiene al día solos (Google Calendar puede tardar hasta un día en
refrescar). Cada evento tiene además botones para añadirlo suelto.

Cada evento lleva **dos avisos**: 24 horas antes y 3 horas antes. Si la hora está por
confirmar, a las 10:00 del día anterior y a las 10:00 del mismo día. Apple Calendar los respeta; Google
Calendar suele ignorar los avisos de calendarios suscritos (en ese caso, ponlos a mano en
la configuración de ese calendario dentro de Google Calendar).

## Avisos por email y WhatsApp

`avisar.py` manda un mensaje cuando aparece un **evento nuevo**, cuando se **confirma o
cambia una hora**, el día antes de cada evento (**"Mañana en el Metropolitano"**) y el
mismo día (**"Hoy en el Metropolitano"**), siempre a las 10:00.
Si no hay nada que contar, no manda nada.

Las llaves se guardan como **Secrets** del repositorio (nunca en el código):
**Settings → Secrets and variables → Actions → New repository secret**.
Cada canal funciona solo si tiene sus secrets; puedes activar uno, otro o los dos.

### Email (Gmail)

1. Tu cuenta de Google necesita la **verificación en dos pasos** activada.
2. Crea una **contraseña de aplicación** en https://myaccount.google.com/apppasswords
   (ponle de nombre "Metropolitano"). Google te dará 16 letras.
3. Crea estos secrets:
   - `EMAIL_USUARIO`: tu dirección de Gmail
   - `EMAIL_CLAVE`: las 16 letras (sin espacios)
   - `EMAIL_DESTINO` (opcional): otra dirección a la que enviar; si no, te llega a ti misma

### WhatsApp (CallMeBot)

CallMeBot es un servicio gratuito para avisos personales (no oficial de WhatsApp; ve el
texto de los mensajes, que aquí son solo eventos públicos).

1. Sigue las instrucciones de https://www.callmebot.com/blog/free-api-whatsapp-messages/
   (añadir su número a tus contactos y enviarle un mensaje de activación).
2. Te responderá con tu **apikey**.
3. Crea estos secrets:
   - `WHATSAPP_TELEFONO`: tu número con prefijo, p. ej. `+34600111222`
   - `WHATSAPP_APIKEY`: el número que te ha dado

### Probar los avisos

Actions → "Actualizar eventos y publicar web" → **Run workflow** → marca
**"Enviar un mensaje de prueba"** → Run workflow. En un par de minutos debería llegarte.

## Dominio

La web se publica en **https://eventosmadridmetropolitano.es** (GitHub Pages con dominio propio).

- **DNS (en Hostalia):** 4 registros A (`185.199.108.153` … `185.199.111.153`) y 4 AAAA
  (`2606:50c0:8000::153` … `8003::153`) en el dominio principal, un CNAME `www` →
  `<tu-usuario>.github.io`, y el TXT `_github-pages-challenge-<tu-usuario>` que verifica el dominio
  en GitHub (no lo borres). Los registros MX, SPF y `mx` son del correo.
- **GitHub:** Settings → Pages → Custom domain = `eventosmadridmetropolitano.es`, con
  **Enforce HTTPS** marcado. `www` y la dirección antigua de `github.io` redirigen solas.
- **No lo cambies más:** las apps instaladas y las suscripciones a los avisos van ligadas al
  dominio; si cambia, todos tendrían que volver a instalar y a activar los avisos.

## App en el móvil y avisos push

La web se puede **instalar como una app** (icono en la pantalla de inicio, se abre a pantalla
completa y funciona sin conexión con los últimos eventos guardados):

- **Android (Chrome):** aparece el botón **"Instalar app"** en la portada.
- **iPhone (Safari):** Apple no permite un botón; sale un aviso que explica
  **Compartir → Añadir a pantalla de inicio**. Desaparece al instalarla o al cerrarlo con la ×.

Con la app instalada (en Android también desde el navegador) aparece **"Activar avisos"**:
cada día a las 10:00 se manda a los suscriptores un aviso por cada evento del día siguiente,
p. ej. *"Mañana hay Atlético de Madrid - Viking FK en el Metropolitano a las 21:00"*.
En iPhone hace falta **iOS 16.4 o posterior** y abrir la web **desde su icono**.

### Cómo funciona

```
Móvil ──"Activar avisos"──▶ Worker de Cloudflare (guarda la suscripción en KV)
                                     ▲
GitHub Actions 10:00 ── avisar.py ───┘ pide la lista, envía con las claves VAPID
                                       y borra las suscripciones que dan error 404/410
```

Qué eventos se avisan lo decide `avisar.py`;
`avisos_push.py` solo se encarga de enviarlos.

### Ponerlo en marcha (una sola vez)

**1. Claves VAPID.** En tu ordenador, en esta carpeta:

```bash
pip install -r requirements.txt
```

```bash
python3 generar_claves_vapid.py
```

Muestra dos claves. No las guardes en ningún archivo del proyecto.

**2. El servidor de suscripciones (Cloudflare Worker, gratis).** Crea una cuenta en
https://dash.cloudflare.com y, en la carpeta `worker`:

```bash
cd worker
```

```bash
npx wrangler login
```

```bash
npx wrangler kv namespace create SUSCRIPCIONES
```

Copia el `id` que te da y pégalo en `worker/wrangler.toml` (en `PEGA_AQUI_EL_ID`).
Después inventa una contraseña larga para que GitHub pueda leer la lista (por ejemplo, la que
genera `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`) y guárdala en el Worker:

```bash
npx wrangler secret put ADMIN_TOKEN
```

Y publícalo:

```bash
npx wrangler deploy
```

Te dirá su dirección, algo como `https://eventos-metropolitano-avisos.TU-CUENTA.workers.dev`.
(Si cambias de dominio, cambia `ALLOWED_ORIGINS` en `wrangler.toml`
y vuelve a hacer `deploy`.)

**3. En GitHub** (**Settings → Secrets and variables → Actions**):

| Dónde | Nombre | Valor |
|---|---|---|
| Secrets | `VAPID_PRIVATE_KEY` | la clave privada del paso 1 |
| Secrets | `PUSH_ADMIN_TOKEN` | la misma contraseña que pusiste en `ADMIN_TOKEN` |
| Variables | `VAPID_PUBLIC_KEY` | la clave pública del paso 1 |
| Variables | `PUSH_API` | la dirección del Worker del paso 2 |

**4.** Actions → "Actualizar eventos y publicar web" → **Run workflow** para publicar la web con
el botón de avisos. El botón solo aparece cuando `PUSH_API` y `VAPID_PUBLIC_KEY` están puestas.

### Probarlo en tu móvil

**Android (Chrome):**
1. Abre la web en Chrome → pulsa **Instalar app** (o menú ⋮ → *Instalar aplicación*).
2. Abre la app desde el icono → **Activar avisos** → **Permitir**.
3. En GitHub: Actions → Run workflow → marca **"Enviar un mensaje de prueba"**. En un par de
   minutos llega *"Mensaje de prueba: los avisos en el móvil funcionan"*.

**iPhone (iOS 16.4 o posterior):**
1. Abre la web en **Safari** → botón **Compartir** (cuadrado con flecha) → **Añadir a pantalla
   de inicio** → Añadir.
2. Abre la app **desde el icono** (no desde Safari) → **Activar avisos** → **Permitir**.
3. Lanza la prueba desde GitHub igual que en Android.

Ojo: la prueba llega a **todos** los suscriptores.

**Si no llega:** en el móvil, revisa que las notificaciones de "Metropolitano" estén permitidas
(Ajustes → Notificaciones) y que el modo Concentración/No molestar no las oculte. En GitHub, el
paso "Enviar avisos" muestra cuántos avisos se enviaron y si hubo errores. Para ver o borrar las
suscripciones guardadas: panel de Cloudflare → Storage & Databases → KV → SUSCRIPCIONES.

**Para darse de baja:** botón **Desactivar** en la propia web, o quitar el permiso de
notificaciones, o borrar la app (en esos dos casos la suscripción se borra sola en el siguiente
envío, cuando el servicio de push responde 404/410).

## Formulario de contacto

`contacto.html` (enlazada al pie, «Contacto y publicidad») envía los mensajes al mismo Worker de los
avisos (ruta `/contacto`), que los manda por correo a `contacto@eventosmadridmetropolitano.es` usando
el SMTP de ese buzón. El correo llega con **Responder a** = el email de quien escribe, así que basta
con darle a *Responder*.

Contra el spam: un campo oculto que solo rellenan los robots y un máximo de 5 mensajes por hora y
dirección IP (de la IP solo se guarda un resumen cifrado, y se borra a la hora).

**Ponerlo en marcha (una vez):**

1. En `worker/wrangler.toml`, rellena `SMTP_HOST` con el servidor de **correo saliente (SMTP)** de
   tu proveedor (lo encuentras en su panel o en la configuración del buzón en el móvil) y, si hace
   falta, `SMTP_PUERTO` (`465` con SSL o `587` con STARTTLS).
2. En la carpeta `worker`, guarda el usuario (la dirección completa del buzón) y su contraseña:

   ```bash
   npx wrangler secret put SMTP_USUARIO
   ```

   ```bash
   npx wrangler secret put SMTP_CLAVE
   ```

3. Publica el Worker:

   ```bash
   npx wrangler deploy
   ```

4. Prueba a enviar un mensaje desde https://eventosmadridmetropolitano.es/contacto.html.
   Si falla, `npx wrangler tail` muestra el error del servidor de correo.

## Afluencia y zona complicada

Cada evento lleva una **afluencia estimada** (🟢 normal, 🟠 mucha gente, 🔴 lleno total) y la
**franja en la que la zona está complicada** para aparcar o circular. Es una estimación con reglas
sencillas (rival, competición, ronda, concierto), no un dato oficial. Las reglas y las horas antes y
después están al principio de la sección «Afluencia estimada» de `recoger_eventos.py`, por si
quieres ajustarlas (por ejemplo, añadir un rival a `RIVALES_LLENO`).
