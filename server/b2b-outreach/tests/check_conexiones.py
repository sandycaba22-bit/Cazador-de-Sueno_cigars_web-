"""Comprueba .env, Google, Telegram y Claude sin imprimir secretos."""
from __future__ import annotations

import io
import json
import os
import sys
import urllib.request
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from telegram_bot import load_local_env  # noqa: E402

load_local_env()


def report(nombre: str, ok: bool, detalle: str = "") -> bool:
    extra = f" | {detalle}" if detalle else ""
    print(f"{'OK' if ok else 'FAIL'} {nombre}{extra}")
    return ok


def main() -> int:
    fallos = 0
    print("=== ENV (solo presencia) ===")
    for key in ("GOOGLE_PLACES_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        hay = bool((os.getenv(key) or "").strip())
        fallos += not report(".env " + key, hay, "presente" if hay else "faltante")
    claude = (os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY") or "").strip()
    fallos += not report(".env Claude (ANTHROPIC/CLAUDE)", bool(claude), "presente" if claude else "faltante")

    print("=== Google Places ===")
    from b2b.places import _normalizar_place, _post_search, motivo_descarte_google

    for consulta, pais in (
        ("cigar shop in Miami, Florida", "Florida"),
        ("cigar shop in San Juan, Puerto Rico", "Puerto Rico"),
        ("cigar shop in Kingston, Jamaica", "Jamaica"),
    ):
        try:
            raws = _post_search(consulta, "en")
            buenos = []
            for raw in raws:
                lead = _normalizar_place(raw, pais)
                if not motivo_descarte_google(raw, lead):
                    buenos.append(lead.get("nombre") or "")
            muestra = ", ".join(buenos[:3]) if buenos else "ninguno tras filtro"
            fallos += not report(
                "Google " + pais,
                bool(buenos),
                f"{len(buenos)} reales / {len(raws)} crudos; {muestra}",
            )
        except Exception as exc:
            fallos += not report("Google " + pais, False, type(exc).__name__)

    print("=== Telegram ===")
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=15) as resp:
            me = json.loads(resp.read().decode("utf-8"))
        fallos += not report("Telegram getMe", bool(me.get("ok")), "bot valido" if me.get("ok") else "no ok")
    except Exception as exc:
        fallos += not report("Telegram getMe", False, type(exc).__name__)

    from b2b import telegram_control as tc

    def texto_comando(cmd: str) -> list[str]:
        cuerpo = {"ok": True, "result": [{"update_id": 1, "message": {"chat": {"id": chat}, "text": cmd}}]}
        with patch.object(tc.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(cuerpo).encode())):
            return tc.procesar_comandos_chat(token, chat)

    try:
        textos = []
        for cmd in ("/pendientes", "/stats", "/estado FL"):
            acks = texto_comando(cmd)
            textos.append(cmd + " => " + ((acks[0][:80] + "...") if acks and len(acks[0]) > 80 else (acks[0] if acks else "sin texto")))
        fallos += not report("Telegram comandos", True, " | ".join(textos))
    except Exception as exc:
        fallos += not report("Telegram comandos", False, type(exc).__name__)

    try:
        def enviar(texto: str) -> bool:
            payload = json.dumps({"chat_id": chat, "text": texto[:3500]}).encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                return bool(json.loads(resp.read().decode("utf-8")).get("ok"))

        fallos += not report(
            "Telegram mensaje prueba",
            enviar("Prueba local Cazador de Sueno: bot B2B conectado. No es un mensaje a un cliente."),
        )
        for cmd in ("/pendientes", "/stats", "/estado FL"):
            acks = texto_comando(cmd)
            if acks:
                enviar(acks[0])
        fallos += not report("Telegram envio comandos", True)
    except Exception as exc:
        fallos += not report("Telegram mensaje prueba", False, type(exc).__name__)

    print("=== Claude ===")
    if not claude:
        fallos += not report("Claude API", False, "sin llave en .env")
    else:
        try:
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=json.dumps(
                    {
                        "model": "claude-haiku-4-5-20251001",
                        "max_tokens": 80,
                        "messages": [
                            {
                                "role": "user",
                                "content": "Draft one short B2B greeting. Lead: Miami Cigar Emporium, shop, Miami, en.",
                            }
                        ],
                    }
                ).encode(),
                headers={
                    "content-type": "application/json",
                    "x-api-key": claude,
                    "anthropic-version": "2023-06-01",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            texto = "".join(
                block.get("text") or "" for block in (data.get("content") or []) if block.get("type") == "text"
            )
            fallos += not report("Claude API", bool(texto.strip()), f"{len(texto)} chars")
        except Exception as exc:
            fallos += not report("Claude API", False, type(exc).__name__)

    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
