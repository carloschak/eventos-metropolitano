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

import json
import re
import time
import unicodedata
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuración (lo que más probablemente quieras cambiar algún día)
# ---------------------------------------------------------------------------

CARPETA = Path(__file__).parent
ARCHIVO_SALIDA = CARPETA / "eventos.json"

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


def main():
    hoy = date.today().isoformat()

    # Eventos guardados de ejecuciones anteriores (por si una web falla hoy)
    anteriores = []
    if ARCHIVO_SALIDA.exists():
        anteriores = json.loads(ARCHIVO_SALIDA.read_text(encoding="utf-8")).get("eventos", [])

    # Los datos nuevos van primero para que tengan prioridad sobre los viejos
    eventos = combinar([recoger_atletico(), recoger_esmadrid(), anteriores])

    # Solo eventos que no han terminado
    eventos = [e for e in eventos if (e.get("fecha_fin") or e["fecha"]) >= hoy]
    eventos.sort(key=lambda e: (e["fecha"], e["hora"] or "99:99"))

    salida = {"actualizado": hoy, "eventos": eventos}
    ARCHIVO_SALIDA.write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nGuardados {len(eventos)} eventos en {ARCHIVO_SALIDA.name}")


if __name__ == "__main__":
    main()
