"""FastAPI application wiring for the HappyRobot carrier demo API."""
from __future__ import annotations

import logging

from fastapi import FastAPI

from database import initialize_database
from routers.dashboard import router as dashboard_router
from routers.loads import router as loads_router
from routers.negotiations import router as negotiations_router


def _get_logger() -> logging.Logger:
    """Return a logger that mirrors uvicorn's console output."""

    base_logger = logging.getLogger("uvicorn.error")
    if not base_logger.handlers:
        base_logger = logging.getLogger()
    child = base_logger.getChild("app")
    child.setLevel(logging.INFO)
    return child


logger = _get_logger()

app = FastAPI(title="HappyRobot Carrier Demo API")


@app.on_event("startup")
def _ensure_database() -> None:
    """Initialize the SQLite database before serving requests."""

    logger.info("Starting application startup")
    initialize_database()
    logger.info("Database initialized and application startup complete")


app.include_router(loads_router)
app.include_router(negotiations_router)
app.include_router(dashboard_router)
