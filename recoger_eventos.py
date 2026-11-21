"""
Recoge los próximos eventos del Estadio Riyadh Air Metropolitano (Madrid)
y los guarda en eventos.json, sin duplicados.

Fuentes:
  1. esmadrid.com (web oficial de turismo de Madrid): partidos y conciertos.
  2. atleticodemadrid.com (web oficial del club): se intenta, pero la web tiene
     una protección anti-robots (Cloudflare) que puede bloquear el acceso.
     Si pasa, el script lo avisa y sigue con lo demás.

Uso:
    python3 recoger_eventos.py
"""

import hashlib
import json
import re
import time
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuración (lo que más probablemente quieras cambiar algún día)
# ---------------------------------------------------------------------------

CARPETA = Path(__file__).parent
ARCHIVO_SALIDA = CARPETA / "eventos.json"
ARCHIVO_CALENDARIO = CARPETA / "eventos.ics"
ARCHIVO_CAMBIOS = CARPETA / "cambios.json"  # novedades para avisar.py (no se sube a GitHub)

ESMADRID = "https://www.esmadrid.com"
ESMADRID_BUSQUEDA = ESMADRID + "/agenda/busqueda?text=metropolitano&page={pagina}"
MAX_PAGINAS = 10  # límite de seguridad para no recorrer páginas sin fin

ATLETICO_CALENDARIO = "https://www.atleticodemadrid.com/calendario"

# Palabra que debe aparecer en el lugar del evento para aceptarlo
LUGAR_CLAVE = "metropolitano"

# Nos presentamos como un navegador normal; algunas webs rechazan lo demás
CABECERAS = {"User-Agent": "Mozilla/5.0 (compatible; eventos-metropolitano/1.0)"}

PAUSA_ENTRE_PETICIONES = 0.5  # segundos, para no saturar las webs


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def descargar(url):
    """Descarga una página y devuelve su HTML como texto."""
    respuesta = requests.get(url, headers=CABECERAS, timeout=30)
    respuesta.raise_for_status()  # si la web responde con error, lanza excepción
    time.sleep(PAUSA_ENTRE_PETICIONES)
    return respuesta.text


def normalizar(texto):
    """Pasa a minúsculas y quita tildes y signos, para comparar títulos."""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", texto.lower()).strip()


def eventos_jsonld(sopa):
    """
    Muchas webs incluyen 'datos estructurados' (formato JSON-LD de schema.org)
    pensados para buscadores. Esta función los busca y devuelve los que son
    eventos.
    """
    encontrados = []
    for bloque in sopa.find_all("script", type="application/ld+json"):
        try:
            datos = json.loads(bloque.string or "")
        except json.JSONDecodeError:
            continue
        elementos = datos if isinstance(datos, list) else datos.get("@graph", [datos])
        for el in elementos:
            if isinstance(el, dict) and "Event" in str(el.get("@type", "")):
                encontrados.append(el)
    return encontrados


def tipo_desde_texto(texto):
    """Decide si algo es 'partido', 'concierto' u 'otro' según palabras clave."""
    t = normalizar(texto)
    if any(p in t for p in ("futbol", "deporte", "laliga", "champions", "copa del rey")):
        return "partido"
    if any(p in t for p in ("musica", "concierto", "pop", "rock", "festival")):
        return "concierto"
    return "otro"


# ---------------------------------------------------------------------------
# Fuente 1: esmadrid.com
# ---------------------------------------------------------------------------

def enlaces_busqueda_esmadrid():
    """Recorre las páginas del buscador y devuelve los enlaces a cada evento."""
    enlaces = []
    for pagina in range(MAX_PAGINAS):
        sopa = BeautifulSoup(descargar(ESMADRID_BUSQUEDA.format(pagina=pagina)), "html.parser")
        nuevos = [
            ESMADRID + div["about"]
            for div in sopa.select("div.node-event[about]")
            if ESMADRID + div["about"] not in enlaces
        ]
        if not nuevos:
            break  # no hay más resultados
        enlaces.extend(nuevos)
    return enlaces


def leer_evento_esmadrid(url):
    """Abre la página de un evento de esmadrid y extrae sus datos."""
    sopa = BeautifulSoup(descargar(url), "html.parser")
    datos = eventos_jsonld(sopa)
    if not datos:
        return None
    ev = datos[0]

    lugar = (ev.get("location") or {}).get("name", "")
    if LUGAR_CLAVE not in normalizar(lugar):
        return None  # no es en el Metropolitano

    # Hora: está en el apartado "Horarios", p. ej. "21:00 h" o "Por confirmar"
    horarios = sopa.select_one(".group-wrapper-fecha-y-horas")
    hora = None
    if horarios:
        m = re.search(r"(\d{1,2}):(\d{2})", horarios.get_text(" "))
        if m:
            hora = f"{int(m.group(1)):02d}:{m.group(2)}"

    # Tipo: está en el apartado "Tipo", p. ej. "Deporte, Fútbol" o "Música, Pop-rock"
    categoria = sopa.select_one(".field-name-field-categoria")
    tipo = tipo_desde_texto(categoria.get_text() if categoria else ev.get("name", ""))

    inicio = (ev.get("startDate") or "")[:10]  # nos quedamos con AAAA-MM-DD
    fin = (ev.get("endDate") or "")[:10] or inicio
    if not inicio:
        return None

    return {
        "fecha": inicio,
        "fecha_fin": fin if fin != inicio else None,
        "hora": hora,  # None = hora por confirmar
        "tipo": tipo,
        "titulo": ev.get("name", "").strip(),
        "lugar": lugar,
        "url": url,
        "fuente": "esmadrid.com",
    }


def recoger_esmadrid():
    print("esmadrid.com: buscando eventos…")
    enlaces = enlaces_busqueda_esmadrid()
    print(f"  {len(enlaces)} resultados en el buscador; revisando cada uno…")
    eventos = []
    for url in enlaces:
        try:
            ev = leer_evento_esmadrid(url)
        except requests.RequestException as e:
            print(f"  Aviso: no se pudo leer {url} ({e})")
            continue
        if ev:
            eventos.append(ev)
    print(f"  {len(eventos)} eventos en el Metropolitano.")
    return eventos


# ---------------------------------------------------------------------------
# Fuente 2: atleticodemadrid.com
# ---------------------------------------------------------------------------

def recoger_atletico():
    """
    Intenta leer el calendario oficial del club usando sus datos estructurados.
    NOTA: esta parte no se ha podido probar porque la web bloquea el acceso
    automático. Si algún día funciona, habrá que revisar que los datos son
    correctos.
    """
    print("atleticodemadrid.com: intentando leer el calendario…")
    try:
        html = descargar(ATLETICO_CALENDARIO)
    except requests.RequestException as e:
        print(f"  Aviso: la web del Atlético no permite el acceso ({e}). Se omite.")
        return []

    eventos = []
    for ev in eventos_jsonld(BeautifulSoup(html, "html.parser")):
        lugar = (ev.get("location") or {}).get("name", "")
        inicio = ev.get("startDate") or ""
        if LUGAR_CLAVE not in normalizar(lugar) or len(inicio) < 10:
            continue
        m = re.search(r"T(\d{2}:\d{2})", inicio)
        hora = m.group(1) if m and m.group(1) != "00:00" else None
        eventos.append({
            "fecha": inicio[:10],
            "fecha_fin": None,
            "hora": hora,
            "tipo": "partido",
            "titulo": ev.get("name", "").strip(),
            "lugar": lugar,
            "url": ev.get("url") or ATLETICO_CALENDARIO,
            "fuente": "atleticodemadrid.com",
        })
    print(f"  {len(eventos)} partidos en el Metropolitano.")
    return eventos


# ---------------------------------------------------------------------------
# Unir, quitar duplicados y guardar
# ---------------------------------------------------------------------------

def clave(ev):
    """Dos eventos son el mismo si coinciden tipo, fecha y título normalizado.
    Para partidos basta con la fecha: no hay dos partidos el mismo día en el
    mismo estadio, aunque cada web escriba el título a su manera."""
    if ev["tipo"] == "partido":
        return ("partido", ev["fecha"])
    return (ev["tipo"], ev["fecha"], normalizar(ev["titulo"]))


def combinar(listas):
    """Junta varias listas de eventos; si uno se repite, completa los huecos
    (p. ej. la hora) con los datos del otro."""
    resultado = {}
    for lista in listas:
        for ev in lista:
            k = clave(ev)
            if k not in resultado:
                resultado[k] = ev
            else:
                existente = resultado[k]
                for campo, valor in ev.items():
                    if existente.get(campo) is None and valor is not None:
                        existente[campo] = valor
    return list(resultado.values())


def detectar_cambios(recientes, anteriores, hoy):
    """Compara lo recogido hoy con lo guardado antes y devuelve las novedades:
    eventos nuevos y horas que se han confirmado o cambiado."""
    if not anteriores:
        return []  # primera ejecución: no hay con qué comparar
    previos = {clave(e): e for e in anteriores}
    cambios = []
    for ev in recientes:
        if (ev.get("fecha_fin") or ev["fecha"]) < hoy:
            continue
        viejo = previos.get(clave(ev))
        if viejo is None:
            cambios.append({"motivo": "nuevo", "evento": ev})
        elif ev.get("hora") and ev["hora"] != viejo.get("hora"):
            cambios.append({"motivo": "hora", "evento": ev, "hora_anterior": viejo.get("hora")})
    return cambios


# ---------------------------------------------------------------------------
# Calendario (.ics): el formato estándar que entienden Google, Apple y Outlook
# ---------------------------------------------------------------------------

DURACION_HORAS = {"partido": 2, "concierto": 3, "otro": 2}  # duración aproximada

ZONA_MADRID = """BEGIN:VTIMEZONE
TZID:Europe/Madrid
BEGIN:DAYLIGHT
TZOFFSETFROM:+0100
TZOFFSETTO:+0200
TZNAME:CEST
DTSTART:19700329T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:+0200
TZOFFSETTO:+0100
TZNAME:CET
DTSTART:19701025T030000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
END:STANDARD
END:VTIMEZONE""".splitlines()


def _escapar(texto):
    return (texto.replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\n", "\\n"))


def _plegar(linea):
    """El formato .ics pide líneas de 75 bytes como máximo; las largas se parten."""
    datos = linea.encode("utf-8")
    trozos = []
    while len(datos) > 74:
        corte = 74
        while (datos[corte] & 0xC0) == 0x80:  # no partir una letra con tilde por la mitad
            corte -= 1
        trozos.append(datos[:corte])
        datos = datos[corte:]
    trozos.append(datos)
    return "\r\n ".join(t.decode("utf-8") for t in trozos)


def generar_ics(eventos, hoy):
    sello = hoy.replace("-", "") + "T000000Z"
    lineas = [
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "PRODID:-//eventos-metropolitano//ES", "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:Riyadh Air Metropolitano", "X-WR-TIMEZONE:Europe/Madrid",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H",
        *ZONA_MADRID,
    ]
    for ev in eventos:
        inicio = date.fromisoformat(ev["fecha"])
        uid = hashlib.md5("|".join(clave(ev)).encode()).hexdigest()
        lineas += ["BEGIN:VEVENT", f"UID:{uid}@eventos-metropolitano", f"DTSTAMP:{sello}"]
        if ev.get("hora") and not ev.get("fecha_fin"):
            h, m = map(int, ev["hora"].split(":"))
            comienzo = datetime(inicio.year, inicio.month, inicio.day, h, m)
            final = comienzo + timedelta(hours=DURACION_HORAS.get(ev["tipo"], 2))
            lineas += [f"DTSTART;TZID=Europe/Madrid:{comienzo:%Y%m%dT%H%M%S}",
                       f"DTEND;TZID=Europe/Madrid:{final:%Y%m%dT%H%M%S}"]
        else:
            # Sin hora (o varios días): evento de día completo
            fin = date.fromisoformat(ev.get("fecha_fin") or ev["fecha"]) + timedelta(days=1)
            lineas += [f"DTSTART;VALUE=DATE:{inicio:%Y%m%d}", f"DTEND;VALUE=DATE:{fin:%Y%m%d}"]
        nota = f"Hora: {ev['hora']} h" if ev.get("hora") else "Hora por confirmar"
        lineas += [
            f"SUMMARY:{_escapar(ev['titulo'])}",
            f"LOCATION:{_escapar(ev.get('lugar') or 'Estadio Riyadh Air Metropolitano')}",
            f"DESCRIPTION:{_escapar(nota + chr(10) + ev['url'])}",
            f"URL:{ev['url']}",
            f"CATEGORIES:{ev['tipo'].capitalize()}",
            "END:VEVENT",
        ]
    lineas.append("END:VCALENDAR")
    return "\r\n".join(_plegar(l) for l in lineas) + "\r\n"


def main():
    hoy = date.today().isoformat()

    # Eventos guardados de ejecuciones anteriores (por si una web falla hoy)
    anteriores = []
    if ARCHIVO_SALIDA.exists():
        anteriores = json.loads(ARCHIVO_SALIDA.read_text(encoding="utf-8")).get("eventos", [])

    recientes = combinar([recoger_atletico(), recoger_esmadrid()])
    cambios = detectar_cambios(recientes, anteriores, hoy)

    # Los datos nuevos van primero para que tengan prioridad sobre los viejos
    eventos = combinar([recientes, anteriores])

    # Solo eventos que no han terminado
    eventos = [e for e in eventos if (e.get("fecha_fin") or e["fecha"]) >= hoy]
    eventos.sort(key=lambda e: (e["fecha"], e["hora"] or "99:99"))

    salida = {"actualizado": hoy, "eventos": eventos}
    ARCHIVO_SALIDA.write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
    ARCHIVO_CALENDARIO.write_bytes(generar_ics(eventos, hoy).encode("utf-8"))
    ARCHIVO_CAMBIOS.write_text(json.dumps(cambios, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nGuardados {len(eventos)} eventos en {ARCHIVO_SALIDA.name} y {ARCHIVO_CALENDARIO.name}")
    print(f"Novedades desde la última vez: {len(cambios)}")


if __name__ == "__main__":
    main()
