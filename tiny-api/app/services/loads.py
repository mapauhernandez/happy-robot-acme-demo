from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

BASE_DIR = Path(__file__).resolve().parent.parent
LOADS_FILE = BASE_DIR / "data" / "loads.json"
STATE_PATTERN = re.compile(r"\b([A-Z]{2})\b")


def _load_data() -> List[Dict[str, Any]]:
    with LOADS_FILE.open("r", encoding="utf-8") as fp:
        return json.load(fp)


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
    pickup_raw = load.get("pickup_datetime")
    if not isinstance(pickup_raw, str):
        return None
    try:
        pickup_dt = datetime.fromisoformat(pickup_raw)
    except ValueError:
        return None
    if pickup_dt.tzinfo is None:
        pickup_dt = pickup_dt.replace(tzinfo=timezone.utc)
    pickup_dt = pickup_dt.astimezone(timezone.utc)
    return pickup_dt.date()


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

    Selection criteria are applied in the following order:

    1. Restrict loads to the current equipment type being evaluated.
    2. Prioritise loads that pick up today *and* originate in the carrier's
       state (when available), then fall back to other combinations in the
       following order: today-only, state-only, finally any remaining loads
       for that equipment type.
    3. Sort the candidate list by `loadboard_rate` in descending order and
       take up to ``limit_per_equipment`` unique loads across equipment
       groups.

    The function returns each equipment grouping alongside the loads that
    satisfied these filters so callers can explain why a recommendation was
    chosen.
    """
    loads = _load_data()
    normalized_state = _normalize_state(origin_state)
    seen_ids: Set[str] = set()
    recommendations: List[LoadRecommendation] = []
    today = datetime.now(timezone.utc).date()

    for equipment in equipment_preferences:
        equipment_lower = equipment.lower()
        equipment_loads = [
            load for load in loads if str(load.get("equipment_type", "")).lower() == equipment_lower
        ]
        if not equipment_loads:
            continue

        near_today: List[Dict[str, Any]] = []
        today_only: List[Dict[str, Any]] = []
        near_only: List[Dict[str, Any]] = []
        remainder: List[Dict[str, Any]] = []

        for load in equipment_loads:
            pickup_date = _pickup_date(load)
            origin_state_value = _origin_state_from_location(str(load.get("origin", "")))
            is_today = pickup_date == today if pickup_date else False
            is_near = bool(normalized_state and origin_state_value == normalized_state)

            if is_today and is_near:
                near_today.append(load)
            elif is_today:
                today_only.append(load)
            elif is_near:
                near_only.append(load)
            else:
                remainder.append(load)

        prioritized_groups = [near_today, today_only, near_only, remainder]
        prioritized: List[Dict[str, Any]] = []
        matched_state_for_group: Optional[str] = None

        for group in prioritized_groups:
            if group:
                group.sort(key=lambda item: item.get("loadboard_rate", 0), reverse=True)
                prioritized = group
                if group is near_today or group is near_only:
                    matched_state_for_group = normalized_state
                break

        if not prioritized:
            continue

        selected: List[Dict[str, Any]] = []
        for load in prioritized:
            load_id = str(load.get("load_id"))
            if load_id in seen_ids:
                continue
            selected.append(load)
            seen_ids.add(load_id)
            if len(selected) >= limit_per_equipment:
                break

        if selected:
            matched_state = matched_state_for_group
            recommendations.append(
                LoadRecommendation(
                    equipment_type=equipment,
                    matched_origin_state=matched_state,
                    items=selected,
                )
            )

    return recommendations


def search_loads(
    *,
    equipment_type: str,
    origin: Optional[str] = None,
    pickup_after: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    loads = _load_data()
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
