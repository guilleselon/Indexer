"""Excepciones propias del indexador.

Cada excepción existe porque el bucle principal necesita reaccionar distinto:
reintentar, saltar, detener o cambiar de flujo.
"""


class IndexerError(Exception):
    """Base de todas las excepciones del indexador."""

    #: Si es True, el ingester reintenta la operación con backoff.
    retriable: bool = False


# --- Configuración y arranque ---------------------------------------------


class ConfigError(IndexerError):
    """Configuración inválida o incompleta. Fatal: no arrancar."""


# --- RPC ------------------------------------------------------------------


class RPCError(IndexerError):
    """Error transitorio hablando con el proveedor JSON-RPC."""

    retriable = True


class RPCFatalError(IndexerError):
    """Error del RPC que no se arregla reintentando (p.ej. dirección inválida)."""

    retriable = False


# --- Decodificación -------------------------------------------------------


class DecodingError(IndexerError):
    """Un log no se pudo decodificar con la ABI conocida.

    Por defecto NO es fatal: el ingester registra el log en cuarentena
    y continúa, para no bloquear el backfill por un solo evento raro.
    """

    retriable = False


# --- Reorgs (control de flujo, no error) ----------------------------------


class ReorgDetected(IndexerError):
    """Se detectó una reorganización de cadena.

    No es un fallo: es una señal que el ingester usa para cambiar al flujo
    de rollback y re-procesar el rango afectado.
    """

    def __init__(self, from_block: int, to_block: int, reason: str = "") -> None:
        self.from_block = from_block
        self.to_block = to_block
        self.reason = reason
        super().__init__(f"Reorg entre bloques {from_block} y {to_block}: {reason}")


# --- Checkpoints y persistencia -------------------------------------------


class CheckpointError(IndexerError):
    """No se pudo leer o escribir el checkpoint de un adapter."""


# --- Adapters -------------------------------------------------------------


class AdapterError(IndexerError):
    """Error en un adapter de nicho."""


class AdapterConfigError(AdapterError):
    """Configuración del adapter inválida (dirección, ABI, rango)."""


class HandlerError(AdapterError):
    """Un handler de evento falló al transformar un evento en filas de dominio.

    Por defecto es fatal: si un handler no puede escribir su dominio,
    el checkpoint NO debe avanzar, o el evento se perderá.
    """
