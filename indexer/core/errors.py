"""Indexer-specific exceptions.

Each exception exists because the main loop needs to react differently:
retry, skip, stop, or switch flows.
"""


class IndexerError(Exception):
    """Base of all indexer exceptions."""

    #: If True, the ingester retries the operation with backoff.
    retriable: bool = False


# --- Configuration and startup --------------------------------------------


class ConfigError(IndexerError):
    """Invalid or incomplete configuration. Fatal: do not start."""


# --- RPC ------------------------------------------------------------------


class RPCError(IndexerError):
    """Transient error talking to the JSON-RPC provider."""

    retriable = True


class RPCFatalError(IndexerError):
    """RPC error that won't be fixed by retrying (e.g. invalid address)."""

    retriable = False


# --- Decoding -------------------------------------------------------------


class DecodingError(IndexerError):
    """A log could not be decoded with the known ABI.

    Non-fatal by default: the ingester quarantines the log and continues,
    so a single weird event doesn't block the backfill.
    """

    retriable = False


# --- Reorgs (flow control, not error) -------------------------------------


class ReorgDetected(IndexerError):
    """A chain reorganization was detected.

    Not a failure: it's a signal the ingester uses to switch to the rollback
    flow and re-process the affected range.
    """

    def __init__(self, from_block: int, to_block: int, reason: str = "") -> None:
        self.from_block = from_block
        self.to_block = to_block
        self.reason = reason
        super().__init__(f"Reorg between blocks {from_block} and {to_block}: {reason}")


# --- Checkpoints and persistence ------------------------------------------


class CheckpointError(IndexerError):
    """Could not read or write an adapter's checkpoint."""


# --- Adapters -------------------------------------------------------------


class AdapterError(IndexerError):
    """Error in a niche adapter."""


class AdapterConfigError(AdapterError):
    """Invalid adapter configuration (address, ABI, range)."""


class HandlerError(AdapterError):
    """An event handler failed to transform an event into domain rows.

    Fatal by default: if a handler cannot write its domain, the checkpoint
    must NOT advance, or the event will be lost.
    """
