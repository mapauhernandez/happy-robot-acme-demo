from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, List, Optional

from dotenv import load_dotenv
from fastapi import Body, FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.services.fmcsa import (
    CarrierNotFoundError,
    CarrierRecord,
    FmcsaServiceError,
    fetch_carrier_by_mc,
)
from app.services.loads import (
    infer_equipment_preferences,
    recommend_loads_for_carrier,
    search_loads,
)
from app.utils.auth import APIKeyMiddleware

load_dotenv()

APP_API_KEY = os.getenv("APP_API_KEY")
FMCSA_WEBKEY = os.getenv("FMCSA_WEBKEY", "")

if not APP_API_KEY:
    raise RuntimeError("APP_API_KEY must be configured before starting the service.")

app = FastAPI(title="HappyRobot Carrier API", version="1.0.0")

app.add_middleware(
    APIKeyMiddleware,
    api_key=APP_API_KEY,
    excluded_paths={"/health", "/docs", "/openapi.json", "/redoc"},
)


class ErrorResponse(BaseModel):
    error: str


class HealthResponse(BaseModel):
    ok: bool = True


class CarrierVerificationResponse(BaseModel):
    mc: str
    dot_number: Optional[str]
    carrier_name: Optional[str]
    authority_status: Optional[str]
    eligible: bool

    @classmethod
    def from_record(cls, record: CarrierRecord) -> "CarrierVerificationResponse":
        return cls(
            mc=record.mc,
            dot_number=record.dot_number,
            carrier_name=record.carrier_name,
            authority_status=record.authority_status,
            eligible=record.eligible,
        )


class LoadItem(BaseModel):
    load_id: str
    origin: str
    destination: str
    pickup_datetime: str
    delivery_datetime: str
    equipment_type: str
    loadboard_rate: float
    weight: float
    commodity_type: str
    num_of_pieces: int
    miles: float
    dimensions: str
    notes: Optional[str] = None


class LoadsSearchResponse(BaseModel):
    items: List[LoadItem]


class LoadRecommendationGroup(BaseModel):
    equipment_type: str
    matched_origin_state: Optional[str] = Field(
        None, description="Two-letter state code when an origin match was applied"
    )
    items: List[LoadItem]


class LoadRecommendationsResponse(BaseModel):
    carrier: CarrierVerificationResponse
    recommendations: List[LoadRecommendationGroup]


class NegotiationRequest(BaseModel):
    listed_rate: float = Field(..., gt=0)
    counter_offer: float = Field(..., gt=0)


class NegotiationResponse(BaseModel):
    accepted: bool
    final_offer: float


class CallLogResponse(BaseModel):
    status: str


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else "Unexpected error"
    return JSONResponse(status_code=exc.status_code, content={"error": detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    messages = []
    for error in exc.errors():
        loc = ".".join(str(part) for part in error.get("loc", []))
        msg = error.get("msg", "invalid value")
        messages.append(f"{loc}: {msg}" if loc else msg)
    detail = "; ".join(messages) if messages else "Invalid request payload"
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"error": detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"error": "Internal server error"})


@app.get("/health", response_model=HealthResponse, include_in_schema=False)
async def health() -> HealthResponse:
    return HealthResponse()


@app.get(
    "/verify_fmcsa",
    response_model=CarrierVerificationResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
)
async def verify_fmcsa(mc: str = Query(..., description="Carrier MC (docket) number")) -> CarrierVerificationResponse:
    if not mc.isdigit():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MC number must be numeric.")

    try:
        record = await fetch_carrier_by_mc(mc, FMCSA_WEBKEY)
    except CarrierNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Carrier not found.")
    except FmcsaServiceError:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to reach FMCSA service.")

    return CarrierVerificationResponse.from_record(record)


@app.get(
    "/loads/search",
    response_model=LoadsSearchResponse,
    responses={400: {"model": ErrorResponse}},
)
async def search_loads_endpoint(
    *,
    equipment_type: str = Query(..., min_length=1, description="Equipment type to filter by"),
    origin: Optional[str] = Query(None, description="Optional origin substring filter"),
    pickup_after: Optional[datetime] = Query(None, description="Include loads picking up after this datetime"),
) -> LoadsSearchResponse:
    items = search_loads(
        equipment_type=equipment_type,
        origin=origin,
        pickup_after=pickup_after,
    )
    return LoadsSearchResponse(items=[LoadItem(**item) for item in items])


@app.get(
    "/loads/recommendations",
    response_model=LoadRecommendationsResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def recommend_loads_endpoint(
    mc: str = Query(..., description="Carrier MC (docket) number used for matching"),
) -> LoadRecommendationsResponse:
    if not mc.isdigit():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MC number must be numeric.")

    try:
        record = await fetch_carrier_by_mc(mc, FMCSA_WEBKEY)
    except CarrierNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Carrier not found.")
    except FmcsaServiceError:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to reach FMCSA service.")

    if not record.eligible:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Carrier is not eligible for load matching.",
        )

    equipment_preferences = infer_equipment_preferences(
        carrier_name=record.carrier_name,
        authority_status=record.authority_status,
    )
    recommendations = recommend_loads_for_carrier(
        equipment_preferences=equipment_preferences,
        origin_state=record.physical_state,
    )

    if not recommendations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No loads matched the carrier profile.",
        )

    groups = [
        LoadRecommendationGroup(
            equipment_type=group.equipment_type,
            matched_origin_state=group.matched_origin_state,
            items=[LoadItem(**item) for item in group.items],
        )
        for group in recommendations
    ]

    return LoadRecommendationsResponse(
        carrier=CarrierVerificationResponse.from_record(record),
        recommendations=groups,
    )


@app.post("/negotiate", response_model=NegotiationResponse)
async def negotiate_offer(request: NegotiationRequest) -> NegotiationResponse:
    listed = request.listed_rate
    counter = request.counter_offer
    floor = 0.9 * listed
    ceiling = 1.11 * listed

    if counter <= ceiling:
        final = max(floor, counter)
        return NegotiationResponse(accepted=True, final_offer=round(final, 2))

    final_counter = min(ceiling, (listed + counter) / 2)
    return NegotiationResponse(accepted=False, final_offer=round(final_counter, 2))


@app.post("/calls/log", response_model=CallLogResponse)
async def log_call(payload: Any = Body(...)) -> CallLogResponse:
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)
    log_path = os.path.join(data_dir, "calls.log.jsonl")

    with open(log_path, "a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, default=str))
        fp.write("\n")

    return CallLogResponse(status="saved")
