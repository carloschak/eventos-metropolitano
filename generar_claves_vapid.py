"""
Genera un par de claves VAPID para los avisos push. Solo hace falta ejecutarlo UNA vez.

    pip install -r requirements.txt
    python3 generar_claves_vapid.py

Muestra dos valores:
  - la clave PÚBLICA  -> variable de GitHub  VAPID_PUBLIC_KEY  (no es secreta, va en la web)
  - la clave PRIVADA  -> secret de GitHub    VAPID_PRIVATE_KEY (¡secreta! no la subas a git)

No guarda nada en disco. Si pierdes la privada, genera otras nuevas: los suscriptores
tendrán que volver a pulsar "Activar avisos".
"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64url(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode()


clave = ec.generate_private_key(ec.SECP256R1())
privada = clave.private_numbers().private_value.to_bytes(32, "big")
publica = clave.public_key().public_bytes(serialization.Encoding.X962,
                                          serialization.PublicFormat.UncompressedPoint)

print("VAPID_PUBLIC_KEY  (variable, pública):\n  " + b64url(publica) + "\n")
print("VAPID_PRIVATE_KEY (secret, privada):\n  " + b64url(privada) + "\n")
print("Cópialas en GitHub → Settings → Secrets and variables → Actions (mira el README).")
