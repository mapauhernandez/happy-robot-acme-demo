from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
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
    loads = _load_data()
    normalized_state = _normalize_state(origin_state)
    seen_ids: Set[str] = set()
    recommendations: List[LoadRecommendation] = []

    for equipment in equipment_preferences:
        equipment_lower = equipment.lower()
        equipment_loads = [
            load for load in loads if str(load.get("equipment_type", "")).lower() == equipment_lower
        ]
        if not equipment_loads:
            continue

        state_matches = []
        if normalized_state:
            for load in equipment_loads:
                origin_state_value = _origin_state_from_location(str(load.get("origin", "")))
                if origin_state_value and origin_state_value == normalized_state:
                    state_matches.append(load)

        prioritized = state_matches if state_matches else equipment_loads
        prioritized.sort(key=lambda item: item.get("loadboard_rate", 0), reverse=True)

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
            matched_state = normalized_state if state_matches else None
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
