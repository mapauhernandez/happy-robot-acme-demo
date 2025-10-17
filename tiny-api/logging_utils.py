"""Shared logging helpers that fall back to stdout when uvicorn logging is missing."""
from __future__ import annotations

import logging


def get_uvicorn_logger(name: str) -> logging.Logger:
    """Return a logger that mirrors uvicorn's console output.

    When uvicorn configures logging it attaches handlers to the ``uvicorn.error``
    logger. In test environments or when the FastAPI app is imported without the
    server running yet there may be no handlers registered, which would normally
    swallow our diagnostics. To make sure developers always see the negotiation
    debug statements we install a basic stream handler the first time the logger
    is requested.
    """

    base_logger = logging.getLogger("uvicorn.error")
    if not base_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
        )
        base_logger.addHandler(handler)
        base_logger.setLevel(logging.INFO)

    child = base_logger.getChild(name)
    child.setLevel(logging.INFO)
    child.propagate = True
    return child
