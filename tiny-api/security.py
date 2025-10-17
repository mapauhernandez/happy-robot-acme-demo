"""Security helpers for API key validation."""
from __future__ import annotations

import os
from typing import Optional

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

API_KEY_HEADER_NAME = "X-API-Key"
DEFAULT_API_KEY = "local-dev-api-key"
api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)


def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    """Ensure the caller supplied the expected API key."""
    expected_key = os.getenv("DEMO_API_KEY", DEFAULT_API_KEY)
    if not api_key or api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return api_key
