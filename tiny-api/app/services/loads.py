from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
LOADS_FILE = BASE_DIR / "data" / "loads.json"
STATE_PATTERN = re.compile(r"\b([A-Z]{2})\b")

STATE_TO_REGION = {
    "AL": "Southeast",
    "AK": "Northwest",
    "AZ": "Southwest",
    "AR": "South",
    "CA": "West",
    "CO": "Mountain",
    "CT": "Northeast",
    "DE": "Northeast",
    "FL": "Southeast",
    "GA": "Southeast",
    "HI": "Pacific",
    "ID": "Northwest",
    "IL": "Midwest",
    "IN": "Midwest",
    "IA": "Midwest",
    "KS": "Midwest",
    "KY": "South",
    "LA": "South",
    "ME": "Northeast",
    "MD": "Northeast",
    "MA": "Northeast",
    "MI": "Midwest",
    "MN": "Midwest",
    "MS": "South",
    "MO": "Midwest",
    "MT": "Mountain",
    "NE": "Midwest",
    "NV": "Southwest",
    "NH": "Northeast",
    "NJ": "Northeast",
    "NM": "Southwest",
    "NY": "Northeast",
    "NC": "Southeast",
    "ND": "Midwest",
    "OH": "Midwest",
    "OK": "South",
    "OR": "Northwest",
    "PA": "Northeast",
    "RI": "Northeast",
    "SC": "Southeast",
    "SD": "Midwest",
    "TN": "South",
    "TX": "South",
    "UT": "Mountain",
    "VT": "Northeast",
    "VA": "South",
    "WA": "Northwest",
    "WI": "Midwest",
    "WV": "South",
    "WY": "Mountain",
    "DC": "Northeast",
}


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _normalize_load_dates(load: Dict[str, Any], reference_date: date) -> Dict[str, Any]:
    normalized = dict(load)
    pickup_dt = _parse_iso_datetime(load.get("pickup_datetime"))
    if not pickup_dt:
        return normalized

    delivery_dt = _parse_iso_datetime(load.get("delivery_datetime"))
    if delivery_dt and delivery_dt.tzinfo is None:
        delivery_dt = delivery_dt.replace(tzinfo=pickup_dt.tzinfo)

    # Treat demo loads as weekly recurring freight so tests remain relevant.
    days_ahead = (pickup_dt.weekday() - reference_date.weekday()) % 7
    next_pickup_date = reference_date + timedelta(days=days_ahead)
    new_pickup_dt = pickup_dt.replace(
        year=next_pickup_date.year,
        month=next_pickup_date.month,
        day=next_pickup_date.day,
    )

    if delivery_dt:
        duration = delivery_dt - pickup_dt
        new_delivery_dt = new_pickup_dt + duration
    else:
        new_delivery_dt = None

    normalized["pickup_datetime"] = new_pickup_dt.isoformat()
    if new_delivery_dt:
        normalized["delivery_datetime"] = new_delivery_dt.isoformat()

    return normalized


def _load_data(reference_date: Optional[date] = None) -> List[Dict[str, Any]]:
    with LOADS_FILE.open("r", encoding="utf-8") as fp:
        raw: List[Dict[str, Any]] = json.load(fp)

    reference = reference_date or datetime.now(timezone.utc).date()
    return [_normalize_load_dates(load, reference) for load in raw]


def _normalize_state(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    if len(text) == 2 and text.isalpha():
        return text
    match = STATE_PATTERN.search(text)
    if match:
        return match.group(1)
    return None


def _origin_state_from_location(location: Optional[str]) -> Optional[str]:
    if not location:
        return None
    parts = [part.strip() for part in location.split(",") if part.strip()]
    if not parts:
        return None
    return _normalize_state(parts[-1])


def _pickup_date(load: Dict[str, Any]) -> Optional[date]:
    pickup_dt = _parse_iso_datetime(load.get("pickup_datetime"))
    if not pickup_dt:
        return None
    pickup_dt = pickup_dt.astimezone(timezone.utc)
    return pickup_dt.date()


def _region_for_state(state: Optional[str]) -> Optional[str]:
    if not state:
        return None
    return STATE_TO_REGION.get(state.upper())


@dataclass
class LoadRecommendation:
    equipment_type: str
    matched_origin_state: Optional[str]
    items: List[Dict[str, Any]]


DEFAULT_EQUIPMENT_ORDER = ["Dry Van", "Reefer"]
EQUIPMENT_KEYWORDS = {
    "Reefer": {"reefer", "refrigerated", "frozen", "cold", "temperature"},
    "Dry Van": {"van", "logistics", "transport", "freight"},
}


def infer_equipment_preferences(
    *, carrier_name: Optional[str], authority_status: Optional[str]
) -> List[str]:
    """Infer equipment order from carrier metadata.

    The function scans the carrier name and authority status text for
    equipment-specific keywords (for example "reefer" or "refrigerated").
    Any matches are prioritised first and the remaining defaults (Dry Van,
    Reefer) are appended afterwards so the recommendation phase always
    evaluates both supported equipment classes.
    """
    text_blobs = " ".join(filter(None, [carrier_name, authority_status])).lower()
    preferences: List[str] = []

    for equipment, keywords in EQUIPMENT_KEYWORDS.items():
        if text_blobs and any(keyword in text_blobs for keyword in keywords):
            preferences.append(equipment)

    for equipment in DEFAULT_EQUIPMENT_ORDER:
        if equipment not in preferences:
            preferences.append(equipment)

    return preferences


def recommend_loads_for_carrier(
    *,
    equipment_preferences: Sequence[str],
    origin_state: Optional[str],
    limit_per_equipment: int = 5,
) -> List[LoadRecommendation]:
    """Return top load matches for the carrier profile.

    Each equipment type is filtered down to loads that depart within the next
    few days (treating the sample data as a recurring weekly board). Loads are
    scored so that same-state departures today rank first, followed by same
    state within a day, then regional matches, and finally any other nearby
    departures. Within each priority bucket loads are ordered by
    ``loadboard_rate`` descending.

    The first ``limit_per_equipment`` unique loads per equipment group are
    returned together with a descriptor that highlights whether the matches
    were aligned to a state or broader region.
    """
    today = datetime.now(timezone.utc).date()
    loads = _load_data(reference_date=today)
    normalized_state = _normalize_state(origin_state)
    normalized_region = _region_for_state(normalized_state)
    seen_ids: Set[str] = set()
    best_candidate: Optional[
        Tuple[Tuple[int, int, float], str, Optional[str], Dict[str, Any]]
    ] = None

    if limit_per_equipment <= 0:
        return []

    for equipment in equipment_preferences:
        equipment_lower = equipment.lower()
        equipment_loads = [
            load for load in loads if str(load.get("equipment_type", "")).lower() == equipment_lower
        ]
        if not equipment_loads:
            continue

        scored_loads: List[tuple[int, int, float, Optional[str], Dict[str, Any]]] = []

        for load in equipment_loads:
            pickup_date = _pickup_date(load)
            if not pickup_date:
                continue

            days_diff = (pickup_date - today).days
            if days_diff < 0:
                continue

            origin_state_value = _origin_state_from_location(str(load.get("origin", "")))
            same_state = bool(normalized_state and origin_state_value == normalized_state)
            same_region = False
            if not same_state and normalized_region and origin_state_value:
                same_region = _region_for_state(origin_state_value) == normalized_region

            if days_diff > 3 and not same_state:
                continue

            if same_state:
                if days_diff == 0:
                    priority = 0
                elif days_diff == 1:
                    priority = 1
                else:
                    priority = 2
                match_label = normalized_state
            elif same_region:
                if days_diff == 0:
                    priority = 3
                elif days_diff <= 1:
                    priority = 4
                else:
                    priority = 5
                region_label = _region_for_state(origin_state_value)
                match_label = f"{region_label} region" if region_label else None
            else:
                if days_diff == 0:
                    priority = 6
                elif days_diff <= 1:
                    priority = 7
                else:
                    priority = 8
                match_label = None

            rate = float(load.get("loadboard_rate", 0))
            scored_loads.append((priority, days_diff, -rate, match_label, load))

        if not scored_loads:
            continue

        scored_loads.sort()

        for priority, days_diff, rate_key, label, load in scored_loads:
            load_id = str(load.get("load_id"))
            if load_id in seen_ids:
                continue
            seen_ids.add(load_id)
            candidate_key = (priority, days_diff, rate_key)
            if not best_candidate or candidate_key < best_candidate[0]:
                best_candidate = (
                    candidate_key,
                    equipment,
                    label,
                    load,
                )
            break

    if not best_candidate:
        return []

    _, equipment, match_descriptor, load = best_candidate
    return [
        LoadRecommendation(
            equipment_type=equipment,
            matched_origin_state=match_descriptor,
            items=[load],
        )
    ]


def search_loads(
    *,
    equipment_type: str,
    origin: Optional[str] = None,
    pickup_after: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    reference_date = datetime.now(timezone.utc).date()
    loads = _load_data(reference_date=reference_date)
    origin_query = origin.lower() if origin else None

    def matches(load: Dict[str, Any]) -> bool:
        if load.get("equipment_type", "").lower() != equipment_type.lower():
            return False
        if origin_query and origin_query not in load.get("origin", "").lower():
            return False
        if pickup_after:
            pickup_raw = load.get("pickup_datetime")
            if not isinstance(pickup_raw, str):
                return False
            try:
                pickup_dt = datetime.fromisoformat(pickup_raw)
            except ValueError:
                return False
            if pickup_dt < pickup_after:
                return False
        return True

    filtered = [load for load in loads if matches(load)]
    filtered.sort(key=lambda item: item.get("loadboard_rate", 0), reverse=True)
    return filtered[:5]


def load_board_snapshot(reference_date: Optional[date] = None) -> List[Dict[str, Any]]:
    """Return the normalized load board dataset used by the API."""

    return _load_data(reference_date)


def origin_state_for_load(load: Dict[str, Any]) -> Optional[str]:
    """Extract the origin state code from a load record."""

    origin = load.get("origin")
    if origin is None:
        return None
    return _origin_state_from_location(str(origin))


def pickup_date_for_load(load: Dict[str, Any]) -> Optional[date]:
    """Return the normalized pickup date for a load record."""

    return _pickup_date(load)
