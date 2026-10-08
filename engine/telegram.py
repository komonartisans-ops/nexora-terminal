#!/usr/bin/env python3
"""NEXORA · envío a Telegram. El token y el chat vienen SOLO del entorno (GitHub Secrets):
TELEGRAM_TOKEN y TELEGRAM_CHAT_ID. Nunca se escriben en logs, JSON ni CSV."""
from __future__ import annotations

import html
import json
import os
import urllib.error
import urllib.request


def configurado() -> bool:
    return bool(os.environ.get("TELEGRAM_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def enviar(texto_html: str) -> tuple[bool, str | None]:
    """Envía un mensaje (HTML de Telegram: solo <b>, <i>, <a>). Devuelve (ok, error sin secretos)."""
    token, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False, "TELEGRAM_TOKEN o TELEGRAM_CHAT_ID sin configurar en el entorno"
    body = json.dumps({"chat_id": chat, "text": texto_html[:4000], "parse_mode": "HTML", "disable_web_page_preview": True}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            j = json.loads(r.read().decode())
        return bool(j.get("ok")), None if j.get("ok") else f"Telegram respondió ok=false: {str(j.get('description'))[:120]}"
    except urllib.error.HTTPError as e:  # el cuerpo trae la descripción del error (sin el token)
        try:
            d = json.loads(e.read().decode()).get("description")
        except Exception:  # noqa: BLE001
            d = ""
        return False, f"HTTP {e.code} {str(d)[:120]}"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}"  # sin str(e): la URL contiene el token


def esc(s) -> str:
    return html.escape(str(s), quote=False)
