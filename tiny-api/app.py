"""FastAPI application wiring for the HappyRobot carrier demo API."""
from __future__ import annotations

import logging

from fastapi import FastAPI

from database import initialize_database
from routers.dashboard import router as dashboard_router
from routers.loads import router as loads_router
from routers.negotiations import router as negotiations_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="HappyRobot Carrier Demo API")


@app.on_event("startup")
def _ensure_database() -> None:
    """Initialize the SQLite database before serving requests."""

    initialize_database()


app.include_router(loads_router)
app.include_router(negotiations_router)
app.include_router(dashboard_router)
