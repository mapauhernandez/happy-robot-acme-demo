from __future__ import annotations

from typing import Iterable, Optional, Set

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Middleware enforcing a static API key via the ``x-api-key`` header."""

    def __init__(
        self,
        app,
        *,
        api_key: str,
        excluded_paths: Optional[Iterable[str]] = None,
    ) -> None:
        if not api_key:
            raise RuntimeError("APP_API_KEY environment variable is required for API key authentication.")

        super().__init__(app)
        self._api_key = api_key
        self._excluded_paths: Set[str] = set(excluded_paths or set())

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        path = request.url.path
        if self._is_excluded(path):
            return await call_next(request)

        provided_key = request.headers.get("x-api-key")
        if provided_key != self._api_key:
            return JSONResponse(status_code=403, content={"error": "Forbidden"})

        return await call_next(request)

    def _is_excluded(self, path: str) -> bool:
        if not self._excluded_paths:
            return False

        for excluded in self._excluded_paths:
            if path == excluded or path.startswith(f"{excluded}/"):
                return True
        return False
