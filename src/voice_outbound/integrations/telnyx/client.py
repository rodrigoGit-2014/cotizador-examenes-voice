"""Cliente HTTP de Telnyx: auth, timeouts, reintentos con backoff y errores tipados."""

import time
from typing import Any

import httpx

from voice_outbound.logging import get_logger

log = get_logger(__name__)

_REINTENTABLES = {429, 500, 502, 503, 504}


class TelnyxError(RuntimeError):
    def __init__(self, status_code: int, detalle: str):
        super().__init__(f"Telnyx {status_code}: {detalle}")
        self.status_code = status_code
        self.detalle = detalle


class TelnyxNotFound(TelnyxError):
    pass


def _detalle(respuesta: httpx.Response) -> str:
    try:
        cuerpo = respuesta.json()
    except ValueError:
        return respuesta.text[:300]
    errores = cuerpo.get("errors") if isinstance(cuerpo, dict) else None
    if errores:
        return "; ".join(e.get("detail") or e.get("title") or str(e) for e in errores)
    return str(cuerpo)[:300]


class TelnyxClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.telnyx.com/v2",
        timeout: float = 30.0,
        max_reintentos: int = 3,
        backoff_seg: float = 1.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self._http = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            timeout=timeout,
            transport=transport,
        )
        self._max_reintentos = max_reintentos
        self._backoff = backoff_seg

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, json: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        return self._request("POST", path, json=json, **kwargs)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        # Un POST con 5xx no se reintenta: podría duplicar una llamada ya iniciada.
        idempotente = method == "GET"
        for intento in range(self._max_reintentos + 1):
            ultimo = intento == self._max_reintentos
            try:
                respuesta = self._http.request(method, path, **kwargs)
            except httpx.TransportError as e:
                if ultimo or not (idempotente or isinstance(e, httpx.ConnectError)):
                    raise TelnyxError(0, f"error de red: {e}") from e
                self._esperar(intento, method, path, str(e))
                continue

            if respuesta.status_code < 400:
                return respuesta.json() if respuesta.content else None
            reintentar = respuesta.status_code == 429 or (
                idempotente and respuesta.status_code in _REINTENTABLES
            )
            if reintentar and not ultimo:
                self._esperar(intento, method, path, f"HTTP {respuesta.status_code}")
                continue
            clase = TelnyxNotFound if respuesta.status_code == 404 else TelnyxError
            raise clase(respuesta.status_code, _detalle(respuesta))
        raise AssertionError("inalcanzable")

    def _esperar(self, intento: int, method: str, path: str, motivo: str) -> None:
        espera = self._backoff * 2**intento
        log.warning("reintentando", extra={"ctx": {"op": f"{method} {path}", "motivo": motivo,
                                                    "espera_seg": espera}})
        time.sleep(espera)

    def close(self) -> None:
        self._http.close()
