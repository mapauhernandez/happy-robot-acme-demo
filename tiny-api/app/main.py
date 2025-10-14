from __future__ import annotations

import html
import json
import os
from collections import Counter
from datetime import datetime
from typing import Any, List, Optional

from dotenv import load_dotenv
from fastapi import Body, FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, ValidationError

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


class NegotiationLogRequest(BaseModel):
    negotiation_rounds: int = Field(..., ge=0, description="Total back-and-forth counter offers")
    final_price: float = Field(..., gt=0, description="Final negotiated rate in USD")
    commodity_type: str = Field(..., min_length=1)
    load_booked: bool = Field(..., description="Flag indicating whether the load was booked")
    equipment_type: str = Field(..., min_length=1)


class NegotiationLogEntry(NegotiationLogRequest):
    timestamp: str = Field(..., description="UTC timestamp when the entry was recorded")


class NegotiationLogResponse(BaseModel):
    status: str
    entry: NegotiationLogEntry


DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CALL_LOG_PATH = os.path.join(DATA_DIR, "calls.log.jsonl")
NEGOTIATION_LOG_PATH = os.path.join(DATA_DIR, "negotiations.log.jsonl")


def _append_json_line(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, default=str))
        fp.write("\n")


def _load_negotiation_entries() -> List[NegotiationLogEntry]:
    if not os.path.exists(NEGOTIATION_LOG_PATH):
        return []

    entries: List[NegotiationLogEntry] = []
    with open(NEGOTIATION_LOG_PATH, "r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                raw_entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            try:
                entries.append(NegotiationLogEntry(**raw_entry))
            except ValidationError:
                continue

    return entries


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


@app.post("/negotiations/log", response_model=NegotiationLogResponse)
async def log_negotiation(request: NegotiationLogRequest) -> NegotiationLogResponse:
    request_payload = request.model_dump() if hasattr(request, "model_dump") else request.dict()
    entry = NegotiationLogEntry(
        timestamp=f"{datetime.utcnow().replace(microsecond=0).isoformat()}Z",
        **request_payload,
    )

    entry_payload = entry.model_dump() if hasattr(entry, "model_dump") else entry.dict()
    _append_json_line(NEGOTIATION_LOG_PATH, entry_payload)

    return NegotiationLogResponse(status="saved", entry=entry)


@app.get("/negotiations/dashboard", response_class=HTMLResponse)
async def negotiations_dashboard() -> HTMLResponse:
    entries = _load_negotiation_entries()
    title = "Negotiation Performance Dashboard"

    if not entries:
        empty_html = f"""
        <html>
          <head>
            <title>{html.escape(title)}</title>
            <style>
              body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 2rem; }}
              .card {{ padding: 1.5rem; border-radius: 8px; background: #f5f5f5; max-width: 420px; }}
            </style>
          </head>
          <body>
            <div class="card">
              <h1>{html.escape(title)}</h1>
              <p>No negotiations have been logged yet. Submit entries with the <code>/negotiations/log</code> endpoint to populate the dashboard.</p>
            </div>
          </body>
        </html>
        """
        return HTMLResponse(content=empty_html)

    total_entries = len(entries)
    booked_count = sum(1 for entry in entries if entry.load_booked)
    average_price = sum(entry.final_price for entry in entries) / total_entries
    average_rounds = sum(entry.negotiation_rounds for entry in entries) / total_entries

    equipment_counts = Counter(entry.equipment_type for entry in entries)
    commodity_counts = Counter(entry.commodity_type for entry in entries)

    def _format_counter(counter: Counter[str]) -> str:
        top_three = counter.most_common(3)
        if not top_three:
            return "—"
        return ", ".join(
            f"{html.escape(name)} ({count})" for name, count in top_three
        )

    table_rows = "".join(
        "<tr>"
        f"<td>{html.escape(entry.timestamp)}</td>"
        f"<td>{html.escape(entry.commodity_type)}</td>"
        f"<td>{html.escape(entry.equipment_type)}</td>"
        f"<td>{entry.negotiation_rounds}</td>"
        f"<td>${entry.final_price:,.2f}</td>"
        f"<td>{'Yes' if entry.load_booked else 'No'}</td>"
        "</tr>"
        for entry in entries
    )

    booked_ratio = (booked_count / total_entries) * 100 if total_entries else 0

    html_content = f"""
    <html>
      <head>
        <title>{html.escape(title)}</title>
        <style>
          :root {{ color-scheme: light dark; }}
          body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 2rem; line-height: 1.5; }}
          h1 {{ margin-bottom: 1.5rem; }}
          .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
          .metric {{ border-radius: 10px; padding: 1.25rem; background: rgba(59, 130, 246, 0.08); backdrop-filter: blur(6px); }}
          .metric h2 {{ font-size: 0.95rem; text-transform: uppercase; letter-spacing: 0.08em; margin: 0 0 0.35rem 0; color: #2563eb; }}
          .metric p {{ font-size: 1.5rem; margin: 0; font-weight: 600; }}
          table {{ border-collapse: collapse; width: 100%; }}
          th, td {{ text-align: left; padding: 0.75rem; border-bottom: 1px solid rgba(148, 163, 184, 0.4); }}
          th {{ font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.08em; color: #475569; }}
          tr:hover td {{ background: rgba(59, 130, 246, 0.08); }}
          code {{ background: rgba(100, 116, 139, 0.15); padding: 0.1rem 0.3rem; border-radius: 4px; }}
        </style>
      </head>
      <body>
        <h1>{html.escape(title)}</h1>
        <section class="metrics">
          <div class="metric">
            <h2>Total entries</h2>
            <p>{total_entries}</p>
          </div>
          <div class="metric">
            <h2>Loads booked</h2>
            <p>{booked_count} <small>({booked_ratio:.1f}% win rate)</small></p>
          </div>
          <div class="metric">
            <h2>Avg. final price</h2>
            <p>${average_price:,.2f}</p>
          </div>
          <div class="metric">
            <h2>Avg. negotiation rounds</h2>
            <p>{average_rounds:.1f}</p>
          </div>
          <div class="metric">
            <h2>Top equipment</h2>
            <p>{_format_counter(equipment_counts)}</p>
          </div>
          <div class="metric">
            <h2>Top commodities</h2>
            <p>{_format_counter(commodity_counts)}</p>
          </div>
        </section>
        <section>
          <h2>Recent negotiations</h2>
          <table>
            <thead>
              <tr>
                <th>Logged at (UTC)</th>
                <th>Commodity</th>
                <th>Equipment</th>
                <th>Rounds</th>
                <th>Final price</th>
                <th>Booked?</th>
              </tr>
            </thead>
            <tbody>
              {table_rows}
            </tbody>
          </table>
        </section>
      </body>
    </html>
    """

    return HTMLResponse(content=html_content)


@app.post("/calls/log", response_model=CallLogResponse)
async def log_call(payload: Any = Body(...)) -> CallLogResponse:
    _append_json_line(CALL_LOG_PATH, payload)
    return CallLogResponse(status="saved")
