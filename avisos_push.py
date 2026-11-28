"""
Avisos push en el móvil (Web Push con claves VAPID).

avisar.py decide QUÉ eventos avisar (los de mañana) y llama a
enviar(). Este archivo solo se ocupa de CÓMO enviarlos:
  1. pide la lista de suscriptores al servidor de suscripciones (Cloudflare Worker, carpeta worker/),
  2. envía a cada uno una notificación por evento,
  3. borra del servidor las suscripciones que ya no existen (el servicio de push responde 404 o 410).

Variables de entorno (en GitHub: Secrets y Variables de Actions):
  PUSH_API            dirección del Worker, p. ej. https://eventos-metropolitano-avisos.tu-cuenta.workers.dev
  PUSH_ADMIN_TOKEN    secreto compartido con el Worker (el mismo que su ADMIN_TOKEN)
  VAPID_PRIVATE_KEY   clave privada VAPID (secreta; se crea con generar_claves_vapid.py)
  VAPID_SUBJECT       opcional: contacto para los servicios de push (mailto:… o https://dominio);
                      por defecto, el dominio de la web (https://eventosmadridmetropolitano.es)
"""

import json
import os
import re
from urllib.parse import urlsplit

import requests

TIEMPO_ESPERA = 30  # segundos


def configuracion():
    """Devuelve la configuración o None si falta algo (entonces no se envía nada)."""
    api = (os.environ.get("PUSH_API") or "").strip().rstrip("/")
    token = (os.environ.get("PUSH_ADMIN_TOKEN") or "").strip()
    clave = (os.environ.get("VAPID_PRIVATE_KEY") or "").strip()
    if not (api and token and clave):
        return None
    return {"api": api, "token": token, "clave": clave}


def titulo_corto(titulo):
    """Quita lo que va entre paréntesis al final, para que quepa en la notificación:
    'Atlético de Madrid - Viking FK (UEFA Champions League. Jornada 5)' -> 'Atlético de Madrid - Viking FK'"""
    return re.sub(r"\s*\([^()]*\)\s*$", "", titulo).strip() or titulo


def mensaje_manana(ev, web):
    """El aviso del día antes: 'Mañana hay [evento] en el Metropolitano a las [hora]'."""
    nombre = titulo_corto(ev["titulo"])
    cuando = f"a las {ev['hora']}" if ev.get("hora") else "(hora por confirmar)"
    return {
        "title": "Mañana en el Metropolitano",
        "body": f"Mañana hay {nombre} en el Metropolitano {cuando}",
        "url": web.rstrip("/") + "/#eventos",
        "tag": f"manana-{ev['fecha']}-{nombre}"[:64],
    }


def mensaje_prueba(web):
    return {
        "title": "Metropolitano",
        "body": "✅ Mensaje de prueba: los avisos en el móvil funcionan.",
        "url": web.rstrip("/") + "/",
        "tag": "prueba",
    }


def _cabeceras(cfg):
    return {"Authorization": f"Bearer {cfg['token']}"}


def listar_suscripciones(cfg, sesion):
    r = sesion.get(cfg["api"] + "/suscripciones", headers=_cabeceras(cfg), timeout=TIEMPO_ESPERA)
    r.raise_for_status()
    return r.json()["suscripciones"]


def borrar_suscripciones(cfg, sesion, endpoints):
    r = sesion.post(cfg["api"] + "/borrar", headers=_cabeceras(cfg), json={"endpoints": endpoints},
                    timeout=TIEMPO_ESPERA)
    r.raise_for_status()


def enviar(eventos_manana, web, prueba=False, sesion=None):
    """Envía los avisos push. Devuelve un resumen; lanza un error si algún envío falla
    por un motivo distinto de 'la suscripción ya no existe'."""
    cfg = configuracion()
    if not cfg:
        print("Push: no configurado, se omite.")
        return None
    mensajes = [mensaje_manana(e, web) for e in eventos_manana]
    if prueba:
        mensajes.insert(0, mensaje_prueba(web))
    if not mensajes:
        print("Push: no hay eventos mañana.")
        return None

    # Solo se importa aquí: así los demás canales funcionan aunque falte la librería
    from pywebpush import WebPushException, webpush

    sesion = sesion or requests.Session()
    suscripciones = listar_suscripciones(cfg, sesion)
    print(f"Push: {len(mensajes)} aviso(s) para {len(suscripciones)} suscriptor(es).")
    # Contacto para los servicios de push: un mailto: o el origen de la web (sin ruta)
    asunto = (os.environ.get("VAPID_SUBJECT") or "").strip() or "https://" + urlsplit(web).netloc

    enviados, caducadas, errores = 0, [], []
    for sub in suscripciones:
        for msg in mensajes:
            try:
                webpush(
                    subscription_info=sub,
                    data=json.dumps(msg, ensure_ascii=False),
                    vapid_private_key=cfg["clave"],
                    vapid_claims={"sub": asunto},
                    ttl=24 * 3600,                 # si el móvil está apagado, el aviso espera hasta 1 día
                    headers={"Urgency": "normal"},
                    timeout=TIEMPO_ESPERA,
                    requests_session=sesion,
                )
                enviados += 1
            except WebPushException as e:
                estado = e.response.status_code if e.response is not None else None
                if estado in (404, 410):          # el usuario se dio de baja o borró la app
                    caducadas.append(sub["endpoint"])
                    break                          # no tiene sentido mandarle el resto
                cuerpo = (e.response.text[:200] if e.response is not None else str(e))
                errores.append(f"{_servicio(sub)} {estado}: {cuerpo}")
            except requests.RequestException as e:  # corte de conexión con ese servicio
                errores.append(f"{_servicio(sub)}: {e}")

    if caducadas:
        borrar_suscripciones(cfg, sesion, caducadas)
    print(f"Push: {enviados} enviado(s), {len(caducadas)} suscripción(es) caducada(s) borrada(s), "
          f"{len(errores)} error(es).")
    if errores:
        raise RuntimeError("algunos avisos push fallaron:\n  " + "\n  ".join(errores))
    return {"enviados": enviados, "borradas": len(caducadas)}


def _servicio(sub):
    """Para los mensajes de error: solo el servicio (fcm.googleapis.com, web.push.apple.com…),
    nunca la dirección completa del suscriptor."""
    return sub["endpoint"].split("/")[2] if sub.get("endpoint", "").count("/") >= 2 else "?"
