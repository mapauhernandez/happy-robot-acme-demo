"""Pydantic models describing carrier loads and negotiation records."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class CarrierRequest(BaseModel):
    """Incoming request describing the carrier's location and equipment."""

    origin: str = Field(..., description="Carrier origin in 'City, ST' format")
    equipment_type: str = Field(..., description="Requested equipment type")


class LoadResponse(BaseModel):
    """Response payload describing a single load."""

    load_id: str
    origin: str
    destination: str
    pickup_datetime: str
    delivery_datetime: str
    equipment_type: str
    loadboard_rate: float
    notes: Optional[str] = None
    weight: int
    commodity_type: str
    num_of_pieces: int
    miles: int
    dimensions: str


class NegotiationRequest(BaseModel):
    """Incoming request representing a load negotiation outcome."""

    load_accepted: bool = Field(..., description="Whether the carrier accepted the load")
    posted_price: float = Field(..., description="Initial posted price", ge=0)
    final_price: float = Field(..., description="Final negotiated price", ge=0)
    total_negotiations: int = Field(
        ..., description="Number of negotiation rounds", ge=0
    )
    call_sentiment: str = Field(..., description="Sentiment label for the call")
    commodity: str = Field(..., description="Commodity discussed on the call")

    @field_validator("load_accepted", mode="before")
    @classmethod
    def _parse_bool(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "y"}:
                return True
            if lowered in {"false", "0", "no", "n"}:
                return False
        raise ValueError("load_accepted must be 'true' or 'false'")

    @field_validator("posted_price", "final_price", mode="before")
    @classmethod
    def _parse_price(cls, value: object) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            return float(value.replace(",", "").strip())
        raise ValueError("Price fields must be numeric")

    @field_validator("total_negotiations", mode="before")
    @classmethod
    def _parse_negotiation_count(cls, value: object) -> int:
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            return int(value.strip())
        raise ValueError("total_negotiations must be an integer")

    @field_validator("call_sentiment", "commodity")
    @classmethod
    def _normalize_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value cannot be empty")
        return normalized


class NegotiationRecord(NegotiationRequest):
    """Stored negotiation record."""

    id: int
    created_at: datetime
