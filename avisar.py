"""
Envía avisos por email y/o WhatsApp cuando:
  - aparece un evento nuevo,
  - se confirma o cambia la hora de un evento,
  - hay un evento mañana (recordatorio del día antes),
  - hay un evento hoy (recordatorio del mismo día).

Se ejecuta después de recoger_eventos.py (que deja las novedades en cambios.json).

Las "llaves" se leen de variables de entorno, que en GitHub son los "Secrets".
Cada canal solo se usa si tiene sus llaves puestas:

  Email (Gmail u otro):  EMAIL_USUARIO, EMAIL_CLAVE, EMAIL_DESTINO (opcional),
                         EMAIL_SMTP (opcional, por defecto smtp.gmail.com)
  WhatsApp (CallMeBot):  WHATSAPP_TELEFONO, WHATSAPP_APIKEY
  Canal de Telegram:     TELEGRAM_TOKEN (la llave del bot), TELEGRAM_CANAL (p. ej. @micanal)

Uso:
    python3 avisar.py            # avisa solo si hay algo que contar
    python3 avisar.py --prueba   # envía un mensaje de prueba
"""

import json
import os
import smtplib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

CARPETA = Path(__file__).parent
WEB = os.environ.get("WEB_URL", "https://carloschak.github.io/eventos-metropolitano/")

DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def leer_json(nombre, por_defecto):
    ruta = CARPETA / nombre
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else por_defecto


def describir(ev):
    """Convierte un evento en una línea de texto, p. ej.
    'mié 25 nov · 21:00 · Atlético de Madrid - Viking FK (...)'"""
    f = date.fromisoformat(ev["fecha"])
    cuando = f"{DIAS[f.weekday()]} {f.day} {MESES[f.month - 1]}"
    if ev.get("fecha_fin"):
        ff = date.fromisoformat(ev["fecha_fin"])
        cuando += f" – {ff.day} {MESES[ff.month - 1]}"
    hora = ev["hora"] if ev.get("hora") else "hora por confirmar"
    return f"• {cuando} · {hora} · {ev['titulo']}"


def redactar(prueba=False):
    """Prepara el texto del aviso. Devuelve None si no hay nada que contar."""
    eventos = leer_json("eventos.json", {"eventos": []})["eventos"]
    cambios = leer_json("cambios.json", [])
    hoy = datetime.now(ZoneInfo("Europe/Madrid")).date()
    manana = (hoy + timedelta(days=1)).isoformat()
    hoy = hoy.isoformat()

    partes = []
    if prueba:
        partes.append("✅ Mensaje de prueba: los avisos funcionan.\n\nPróximos eventos:\n"
                      + "\n".join(describir(e) for e in eventos[:3]))

    de_hoy = [e for e in eventos if e["fecha"] == hoy]
    if de_hoy:
        partes.append("🏟️ Hoy en el Metropolitano:\n" + "\n".join(describir(e) for e in de_hoy))

    de_manana = [e for e in eventos if e["fecha"] == manana]
    if de_manana:
        partes.append("📅 Mañana en el Metropolitano:\n" + "\n".join(describir(e) for e in de_manana))

    nuevos = [c["evento"] for c in cambios if c["motivo"] == "nuevo"]
    if nuevos:
        partes.append("🆕 Nuevos eventos:\n" + "\n".join(describir(e) for e in nuevos))

    horas = [c["evento"] for c in cambios if c["motivo"] == "hora"]
    if horas:
        partes.append("🕘 Hora confirmada o cambiada:\n" + "\n".join(describir(e) for e in horas))

    if not partes:
        return None
    return "Riyadh Air Metropolitano\n\n" + "\n\n".join(partes) + f"\n\nMás info: {WEB}"


def enviar_email(texto):
    usuario = os.environ.get("EMAIL_USUARIO")
    clave = os.environ.get("EMAIL_CLAVE")
    if not (usuario and clave):
        print("Email: no configurado, se omite.")
        return
    msg = EmailMessage()
    msg["Subject"] = "Novedades en el Metropolitano"
    msg["From"] = usuario
    msg["To"] = os.environ.get("EMAIL_DESTINO") or usuario
    msg.set_content(texto)
    with smtplib.SMTP_SSL(os.environ.get("EMAIL_SMTP") or "smtp.gmail.com", 465, timeout=30) as s:
        s.login(usuario, clave)
        s.send_message(msg)
    print("Email: enviado.")


def enviar_whatsapp(texto):
    telefono = os.environ.get("WHATSAPP_TELEFONO")
    apikey = os.environ.get("WHATSAPP_APIKEY")
    if not (telefono and apikey):
        print("WhatsApp: no configurado, se omite.")
        return
    url = "https://api.callmebot.com/whatsapp.php?" + urllib.parse.urlencode(
        {"phone": telefono, "text": texto, "apikey": apikey})
    with urllib.request.urlopen(url, timeout=30) as r:
        respuesta = r.read().decode("utf-8", "replace")
    if r.status != 200 or "error" in respuesta.lower():
        raise RuntimeError(f"CallMeBot respondió: {respuesta[:300]}")
    print("WhatsApp: enviado.")


def enviar_telegram(texto):
    token = (os.environ.get("TELEGRAM_TOKEN") or "").strip()  # por si se copió con espacios
    canal = (os.environ.get("TELEGRAM_CANAL") or "").strip()
    if not (token and canal):
        print("Telegram: no configurado, se omite.")
        return
    if not canal.startswith(("@", "-")):
        canal = "@" + canal  # por si se escribe el nombre sin la @
    datos = json.dumps({
        "chat_id": canal,
        "text": texto,
        "link_preview_options": {"is_disabled": True},  # sin vista previa del enlace
    }).encode("utf-8")
    peticion = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=datos, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(peticion, timeout=30) as r:
            respuesta = json.loads(r.read())
    except urllib.error.HTTPError as e:
        # Telegram explica el motivo del error en la respuesta (p. ej. "chat not found")
        respuesta = json.loads(e.read() or b"{}")
    if not respuesta.get("ok"):
        raise RuntimeError(f"Telegram respondió: {respuesta.get('description', respuesta)}")
    print("Telegram: publicado en el canal.")


def con_reintentos(enviar, texto, intentos=3):
    """Si la conexión se corta (fallo de red), espera y lo vuelve a intentar.
    Si el servicio responde con un error de verdad (p. ej. token incorrecto),
    no reintenta: el error se muestra directamente."""
    for intento in range(1, intentos + 1):
        try:
            return enviar(texto)
        except OSError as e:  # cortes de conexión, tiempo agotado, etc.
            if intento == intentos:
                raise
            print(f"  Fallo de conexión ({e}); reintento {intento + 1} de {intentos} en {10 * intento} s…")
            time.sleep(10 * intento)


def main():
    texto = redactar(prueba="--prueba" in sys.argv)
    if texto is None:
        print("Nada nuevo que avisar hoy.")
        return
    print("Mensaje:\n" + texto + "\n")

    errores = []
    for enviar in (enviar_email, enviar_whatsapp, enviar_telegram):
        try:
            con_reintentos(enviar, texto)
        except Exception as e:  # un canal que falla no impide probar el otro
            errores.append(f"{enviar.__name__}: {e}")
    if errores:
        print("Errores:\n" + "\n".join(errores))
        sys.exit(1)  # así la ejecución sale en rojo en GitHub y te enteras


if __name__ == "__main__":
    main()
