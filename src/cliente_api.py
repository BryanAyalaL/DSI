"""Consulta de un ID al sistema externo, con reintentos.

Frontera de reintentos (ver README):
- 200                      -> encontrado (final)
- 404                      -> no_existe (final, caso de negocio). No se reintenta:
                              mañana dará lo mismo.
- 429, 5xx (configurables) -> se reintenta con espera creciente.
- Timeout / error de red   -> se reintenta con espera creciente.
- Otros códigos (400, 403) -> error técnico SIN reintento: repetir no lo arregla,
                              hay que revisar configuración. Queda pendiente para
                              la próxima ejecución.

Esta función nunca lanza excepciones por fallas de la API o de la red:
siempre devuelve un Resultado, para que un ID no detenga el proceso.
"""

import logging
import time
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)


@dataclass
class Resultado:
    """Lo que se guarda por cada ID (mismos campos que estados.guardar_resultado)."""
    estado: str                       # encontrado / no_existe / error_tecnico
    intentos: int
    http_status: int | None = None    # None si no hubo respuesta (timeout, red)
    mensaje_error: str | None = None
    user_id: int | None = None
    titulo: str | None = None


class ClienteAPI:
    def __init__(
        self,
        url_base: str,
        timeout_segundos: float,
        max_reintentos: int,
        espera_base_segundos: float,
        codigos_reintentables: list[int],
        transporte: httpx.BaseTransport | None = None,  # solo para pruebas
        dormir=time.sleep,                              # solo para pruebas
    ):
        self.url_base = url_base.rstrip("/")
        self.timeout = timeout_segundos
        self.max_reintentos = max_reintentos
        self.espera_base = espera_base_segundos
        self.reintentables = set(codigos_reintentables)
        self._dormir = dormir
        self._http = httpx.Client(timeout=timeout_segundos, transport=transporte)

    def cerrar(self) -> None:
        self._http.close()

    def consultar(self, id_cuenta: int) -> Resultado:
        url = f"{self.url_base}/{id_cuenta}"
        total_intentos = self.max_reintentos + 1  # 1 normal + N reintentos

        for intento in range(1, total_intentos + 1):
            status = None
            try:
                resp = self._http.get(url)
            except httpx.TimeoutException:
                error, reintentable = f"Timeout tras {self.timeout} s", True
            except httpx.TransportError as e:  # conexión rechazada, DNS, red caída...
                error, reintentable = f"Error de red: {type(e).__name__}: {e}", True
            else:
                status = resp.status_code
                if status == 200:
                    return self._leer_encontrado(resp, intento, url)
                if status == 404:
                    log.info("ID %s no existe (404) - %s", id_cuenta, url)
                    return Resultado("no_existe", intento, 404)
                error = f"HTTP {status} {resp.reason_phrase}"
                reintentable = status in self.reintentables

            if not reintentable or intento == total_intentos:
                log.error("ID %s error técnico tras %s intento(s): %s - %s",
                          id_cuenta, intento, error, url)
                return Resultado("error_tecnico", intento, status, error)

            # Espera creciente: base, base*2, base*4...
            espera = self.espera_base * 2 ** (intento - 1)
            log.warning("ID %s intento %s/%s falló (%s). Reintento en %s s - %s",
                        id_cuenta, intento, total_intentos, error, espera, url)
            self._dormir(espera)

    @staticmethod
    def _leer_encontrado(resp: httpx.Response, intento: int, url: str) -> Resultado:
        # Un 200 con cuerpo que no es el post esperado no se da por bueno:
        # se registra como error técnico (pendiente), no como encontrado.
        try:
            datos = resp.json()
        except ValueError:
            datos = None
        if not isinstance(datos, dict) or "id" not in datos:
            error = "HTTP 200 con respuesta inesperada (no es un post válido)"
            log.error("%s - %s", error, url)
            return Resultado("error_tecnico", intento, 200, error)
        return Resultado("encontrado", intento, 200,
                         user_id=datos.get("userId"), titulo=datos.get("title"))
