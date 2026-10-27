"""Logging estructurado: `clave=valor` en una línea, un logger por módulo."""

import logging
import sys


class _KeyValueFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = getattr(record, "ctx", None)
        if not extras:
            return base
        return base + " " + " ".join(f"{k}={v!r}" for k, v in extras.items())


def configurar(nivel: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_KeyValueFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    raiz = logging.getLogger("voice_outbound")
    raiz.handlers[:] = [handler]
    raiz.setLevel(nivel)
    raiz.propagate = False


def get_logger(nombre: str) -> logging.Logger:
    return logging.getLogger(nombre)
