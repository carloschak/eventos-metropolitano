# Eventos del Riyadh Air Metropolitano

Recoge los próximos partidos y conciertos del estadio y los muestra en una página web.

## Archivos

| Archivo | Qué es |
|---|---|
| `recoger_eventos.py` | El script que lee las webs y crea `eventos.json` |
| `eventos.json` | Los eventos guardados (se regenera cada vez) |
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
- **atleticodemadrid.com**: el script lo intenta, pero la web tiene una protección
  anti-robots y suele responder "403 Forbidden". En ese caso lo avisa y sigue.
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

El archivo `.github/workflows/actualizar.yml` le dice a GitHub que, **cada día a las 6:17
(hora de Madrid en invierno)**, ejecute el script, guarde el `eventos.json` nuevo y
vuelva a publicar la web en GitHub Pages.

- **Ver si ha funcionado**: pestaña **Actions** del repositorio. Verde = bien, rojo = error.
- **Actualizar ahora mismo**: Actions → "Actualizar eventos y publicar web" → **Run workflow**.
- **Cambiar la hora**: edita la línea `cron` del archivo (va en hora UTC).
