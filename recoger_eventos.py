"""
Recoge los próximos eventos del Estadio Riyadh Air Metropolitano (Madrid)
y los guarda en eventos.json, sin duplicados.

Fuente: esmadrid.com (web oficial de turismo de Madrid), que incluye los
partidos del Atlético en casa y los conciertos del estadio.

Uso:
    python3 recoger_eventos.py
"""

import hashlib
import json
import re
import sys
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

# Palabra que debe aparecer en el lugar del evento para aceptarlo
LUGAR_CLAVE = "metropolitano"

# Nos presentamos como un navegador normal; algunas webs rechazan lo demás
CABECERAS = {"User-Agent": "Mozilla/5.0 (compatible; eventos-metropolitano/1.0)"}

PAUSA_ENTRE_PETICIONES = 0.5  # segundos, para no saturar las webs


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def descargar(url, intentos=3):
    """Descarga una página y devuelve su HTML como texto.
    Si la conexión falla o la web da un error temporal, lo reintenta."""
    for intento in range(1, intentos + 1):
        try:
            respuesta = requests.get(url, headers=CABECERAS, timeout=30)
            if respuesta.status_code < 500 or intento == intentos:
                respuesta.raise_for_status()  # si la web responde con error, lanza excepción
                time.sleep(PAUSA_ENTRE_PETICIONES)
                return respuesta.text
        except (requests.ConnectionError, requests.Timeout):
            if intento == intentos:
                raise
        time.sleep(5 * intento)  # espera 5 s, luego 10 s… antes de reintentar


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
    try:
        enlaces = enlaces_busqueda_esmadrid()
    except requests.RequestException as e:
        print(f"  Aviso: no se pudo usar el buscador de esmadrid ({e}).")
        return []
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
# Unir, quitar duplicados y guardar
# ---------------------------------------------------------------------------

def clave(ev):
    """Dos eventos son el mismo si coinciden tipo, fecha y título normalizado.
    Para partidos basta con la fecha: no hay dos partidos el mismo día en el
    mismo estadio, aunque el título cambie ligeramente de un día a otro."""
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


# ---------------------------------------------------------------------------
# Afluencia estimada y franja en la que la zona está complicada
# (pensado para los vecinos: cuándo es mejor no mover el coche)
# ---------------------------------------------------------------------------

# No hay datos reales de asistencia: es una estimación con reglas sencillas.
# Nivel 1 = afluencia normal de partido, 2 = mucha gente, 3 = lleno total.
NIVELES = {1: "Afluencia normal", 2: "Mucha gente", 3: "Lleno total"}

# Rivales que llenan el estadio (o casi). Se buscan en el título sin tildes.
RIVALES_LLENO = ["real madrid", "barcelona", "barca"]
RIVALES_MUCHA_GENTE = ["athletic", "sevilla", "betis", "valencia", "real sociedad", "villarreal"]

# Rondas de eliminatoria (Champions, Europa League, Copa...)
RONDAS_GRANDES = ["final", "semifinal", "semifinales", "cuartos"]
RONDAS_ELIMINATORIA = ["octavos", "dieciseisavos", "playoff", "play off", "eliminatoria"]

# Horas antes y después de la hora de inicio en las que la zona está complicada
# (llegada de público, cortes, aparcamiento lleno y salida). Se puede ajustar.
ANTES_HORAS = {"partido": 2.5, "concierto": 4, "otro": 2}
DESPUES_HORAS = {"partido": 2.75, "concierto": 4, "otro": 2.5}
ANTES_EXTRA_LLENO = 0.5  # si se espera lleno total, la gente llega antes


def _contiene(texto, palabras):
    return any(re.search(r"\b" + re.escape(p) + r"\b", texto) for p in palabras)


def estimar_afluencia(ev):
    """Devuelve (nivel, motivo) a partir del tipo de evento y su título."""
    t = normalizar(ev["titulo"])
    if ev["tipo"] == "concierto":
        return 3, "Concierto: estadio lleno y colas desde la tarde"
    if _contiene(t, RIVALES_LLENO):
        return 3, "Partido grande contra un rival de máxima rivalidad"
    if _contiene(t, RONDAS_ELIMINATORIA):  # va antes que "final" por "octavos de final"
        return 2, "Eliminatoria europea o de Copa"
    if _contiene(t, RONDAS_GRANDES):
        return 3, "Final" if re.search(r"(?<!de )\bfinal\b", t) and "semifinal" not in t else "Eliminatoria en ronda decisiva"
    if "champions" in t:
        return 2, "Partido de Champions League"
    if _contiene(t, RIVALES_MUCHA_GENTE):
        return 2, "Rival con mucha afición"
    if "copa" in t:
        return 1, "Copa en ronda temprana"
    if ev["tipo"] == "partido":
        return 1, "Partido de liga habitual"
    return 1, "Evento"


def _sumar_horas(hora, horas):
    h, m = map(int, hora.split(":"))
    total = (h * 60 + m + round(horas * 60)) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def zona_complicada(ev, nivel):
    """Franja aproximada en la que la zona está complicada, o None si no hay hora."""
    if not ev.get("hora"):
        return None
    antes = ANTES_HORAS.get(ev["tipo"], 2) + (ANTES_EXTRA_LLENO if nivel == 3 and ev["tipo"] == "partido" else 0)
    despues = DESPUES_HORAS.get(ev["tipo"], 2.5)
    return {"desde": _sumar_horas(ev["hora"], -antes), "hasta": _sumar_horas(ev["hora"], despues)}


def completar_estimaciones(ev):
    """Añade (o recalcula) los campos 'afluencia' y 'zona_complicada' del evento."""
    nivel, motivo = estimar_afluencia(ev)
    ev["afluencia"] = {"nivel": nivel, "texto": NIVELES[nivel], "motivo": motivo}
    ev["zona_complicada"] = zona_complicada(ev, nivel)
    return ev


def resumen_vecinos(ev):
    """Texto corto con la afluencia y la franja, para el calendario y los avisos."""
    if "afluencia" not in ev:
        completar_estimaciones(ev)
    texto = f"Afluencia estimada: {ev['afluencia']['texto']} ({ev['afluencia']['motivo']})."
    z = ev.get("zona_complicada")
    if z:
        texto += f" Zona complicada aprox. de {z['desde']} a {z['hasta']}."
    else:
        texto += " Franja complicada: cuando se confirme la hora."
    return texto


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


def _alarma(titulo, texto, minutos):
    """Aviso del calendario. 'minutos' es respecto al inicio del evento:
    negativo = antes, positivo = después (sirve para los de día completo)."""
    signo = "-" if minutos < 0 else ""
    return ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_escapar(texto + ': ' + titulo)}",
            f"TRIGGER:{signo}PT{abs(minutos)}M", "END:VALARM"]


def alarmas(ev, con_hora):
    """Dos avisos: 24 horas antes y 3 horas antes si hay hora;
    si es de día completo, a las 10:00 del día anterior y del mismo día."""
    if con_hora:
        dia_antes = -24 * 60                      # 24 horas antes
        mismo_dia = -180
    else:                                         # empieza a las 00:00
        dia_antes = -14 * 60                      # 10:00 del día anterior
        mismo_dia = 10 * 60                       # 10:00 del mismo día
    return (_alarma(ev["titulo"], "Mañana en el Metropolitano", dia_antes)
            + _alarma(ev["titulo"], "Hoy en el Metropolitano", mismo_dia))


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
        con_hora = bool(ev.get("hora") and not ev.get("fecha_fin"))
        if con_hora:
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
        nota += "\n" + resumen_vecinos(ev)
        lineas += [
            f"SUMMARY:{_escapar(ev['titulo'])}",
            f"LOCATION:{_escapar(ev.get('lugar') or 'Estadio Riyadh Air Metropolitano')}",
            f"DESCRIPTION:{_escapar(nota)}",
            f"CATEGORIES:{ev['tipo'].capitalize()}",
            *alarmas(ev, con_hora),
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

    recientes = combinar([recoger_esmadrid()])
    if not recientes:
        # esmadrid no ha respondido: no tocamos los archivos y avisamos con un error
        print("\nERROR: no se ha podido recoger ningún evento. Se conservan los datos anteriores.")
        sys.exit(1)
    cambios = detectar_cambios(recientes, anteriores, hoy)

    # Los datos nuevos van primero para que tengan prioridad sobre los viejos
    eventos = combinar([recientes, anteriores])

    # Solo eventos que no han terminado
    eventos = [e for e in eventos if (e.get("fecha_fin") or e["fecha"]) >= hoy]
    eventos.sort(key=lambda e: (e["fecha"], e["hora"] or "99:99"))

    # Afluencia estimada y franja complicada (se recalculan siempre, por si cambian las reglas)
    for ev in eventos + [c["evento"] for c in cambios]:
        completar_estimaciones(ev)

    salida = {"actualizado": hoy, "eventos": eventos}
    ARCHIVO_SALIDA.write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
    ARCHIVO_CALENDARIO.write_bytes(generar_ics(eventos, hoy).encode("utf-8"))
    ARCHIVO_CAMBIOS.write_text(json.dumps(cambios, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nGuardados {len(eventos)} eventos en {ARCHIVO_SALIDA.name} y {ARCHIVO_CALENDARIO.name}")
    print(f"Novedades desde la última vez: {len(cambios)}")


if __name__ == "__main__":
    main()
