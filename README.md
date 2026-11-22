# Eventos del Riyadh Air Metropolitano

Recoge los próximos partidos y conciertos del estadio y los muestra en una página web.

## Archivos

| Archivo | Qué es |
|---|---|
| `recoger_eventos.py` | El script que lee las webs y crea `eventos.json` |
| `eventos.json` | Los eventos guardados (se regenera cada vez) |
| `eventos.ics` | Los mismos eventos en formato calendario (Google, Apple, Outlook) |
| `avisar.py` | Envía avisos por email, WhatsApp y/o canal de Telegram cuando hay novedades |
| `index.html` | La página que muestra los eventos |
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

Cada evento lleva **dos avisos**: el día antes a las 10:00 y el mismo día (3 horas antes si
tiene hora; a las 10:00 si la hora está por confirmar). Apple Calendar los respeta; Google
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

### Canal de Telegram (para los visitantes de la web)

El robot publica las novedades en un canal público de Telegram; cualquiera puede unirse
desde el botón de la web, sin dar su teléfono ni ningún dato.

1. En Telegram: menú → **Nuevo canal** → ponle nombre → **Público** → elige el enlace,
   p. ej. `t.me/eventos_metropolitano` (el nombre del canal es lo que va tras `t.me/`).
2. Busca **@BotFather** (el oficial, con el tick azul) → escribe `/newbot` → dale un nombre
   y un usuario terminado en `bot`. Te dará un **token** (algo como `123456:ABC-...`).
   Es una contraseña: no la compartas.
3. En tu canal: **Administradores → Añadir administrador** → busca tu bot → deja activado
   **Publicar mensajes**.
4. En GitHub (**Settings → Secrets and variables → Actions**):
   - pestaña **Secrets** → `TELEGRAM_TOKEN`: el token del paso 2
   - pestaña **Variables** → `TELEGRAM_CANAL`: el nombre del canal con @, p. ej. `@eventos_metropolitano`

   La variable también hace aparecer el botón **"Unirme al canal"** en la web.

### Probar los avisos

Actions → "Actualizar eventos y publicar web" → **Run workflow** → marca
**"Enviar un mensaje de prueba"** → Run workflow. En un par de minutos debería llegarte.
Ojo: si Telegram está configurado, la prueba también se publica en el canal (puedes
borrarla después desde Telegram).

## Contador de visitas

La página usa [GoatCounter](https://www.goatcounter.com), gratuito y sin cookies (no hace falta banner de consentimiento).

1. Crea una cuenta en goatcounter.com y elige un código (por ejemplo `eventos-metropolitano`).
2. En `index.html`, cambia `TU-CODIGO` por ese código.
3. Las visitas se ven en `https://TU-CODIGO.goatcounter.com`. En *Settings* puedes hacer públicas las estadísticas para enseñárselas a anunciantes.
