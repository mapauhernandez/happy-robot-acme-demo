from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
LOADS_FILE = BASE_DIR / "data" / "loads.json"


def _load_data() -> List[Dict[str, Any]]:
    with LOADS_FILE.open("r", encoding="utf-8") as fp:
        return json.load(fp)


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
