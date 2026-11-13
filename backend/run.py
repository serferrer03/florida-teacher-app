"""Arranque de la app: HTTPS (red local) + HTTP, en un solo proceso.

  python run.py            -> https://IP:8443 y http://IP:8000
Variables: PORT (8000), HTTPS_PORT (8443, 0 = sin HTTPS),
           HTTP_LAN (true; false = HTTP solo para este PC, la tablet usa HTTPS).
"""
from __future__ import annotations

import asyncio
import os

import uvicorn

from app.config import get_settings
from app.tls import ensure_certs, lan_ip


def _bool(v: str | None, default: bool) -> bool:
    return default if not v else v.strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


async def main() -> None:
    settings = get_settings()
    from app.main import app  # tras cargar .env

    http_port = int(os.environ.get("PORT") or 8000)
    https_port = int(os.environ.get("HTTPS_PORT") or 8443)
    http_host = "0.0.0.0" if _bool(os.environ.get("HTTP_LAN"), True) else "127.0.0.1"
    ip = lan_ip()
    servers = [uvicorn.Server(uvicorn.Config(app, host=http_host, port=http_port, log_level="info"))]
    if https_port:
        crt, key, _ = ensure_certs(settings.data_dir, ip)
        servers.append(uvicorn.Server(uvicorn.Config(
            app, host="0.0.0.0", port=https_port, ssl_certfile=str(crt), ssl_keyfile=str(key),
            log_level="info", lifespan="off")))

    lines = [f"  En el PC:          http://localhost:{http_port}"]
    if https_port:
        lines.append(f"  En la tablet:      https://{ip}:{https_port}   (recomendado, ver «Conexión segura»)")
    if http_host == "0.0.0.0":
        lines.append(f"  Tablet sin HTTPS:  http://{ip}:{http_port}")
    print("\n" + "=" * 66 + "\n" + "\n".join(lines)
          + f"\n  Código de acceso para la tablet: {settings.access_token}\n" + "=" * 66 + "\n", flush=True)
    await asyncio.gather(*(s.serve() for s in servers))


if __name__ == "__main__":
    asyncio.run(main())
