from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from typing import Dict, Iterable, List, Optional

from app.services.loads import (
    load_board_snapshot,
    origin_state_for_load,
    pickup_date_for_load,
)


def _format_currency(value: Optional[float]) -> str:
    if value is None:
        return "--"
    return f"${value:,.0f}"


def _format_percentage(part: int, whole: int) -> str:
    if whole <= 0:
        return "0%"
    return f"{(part / whole) * 100:.1f}%"


def _top_entries(counter: Counter[str], limit: int = 5) -> Iterable[tuple[str, int]]:
    return counter.most_common(limit)


def _collect_snapshot(reference_date: Optional[date] = None) -> Dict[str, object]:
    loads = load_board_snapshot(reference_date=reference_date)
    today = reference_date or datetime.now(timezone.utc).date()

    by_equipment: Counter[str] = Counter()
    by_origin_state: Counter[str] = Counter()
    departures: Dict[date, List[Dict[str, object]]] = defaultdict(list)
    top_rates: List[Dict[str, object]] = []

    for load in loads:
        equipment = str(load.get("equipment_type") or "Unknown")
        by_equipment[equipment] += 1

        origin_state = origin_state_for_load(load)
        if origin_state:
            by_origin_state[origin_state] += 1

        pickup = pickup_date_for_load(load)
        if pickup:
            departures[pickup].append(load)

        rate = load.get("loadboard_rate")
        try:
            rate_value = float(rate)
        except (TypeError, ValueError):
            rate_value = 0.0
        load_copy = dict(load)
        load_copy["_rate_value"] = rate_value
        top_rates.append(load_copy)

    top_rates.sort(key=lambda item: item.get("_rate_value", 0), reverse=True)

    upcoming: List[tuple[date, List[Dict[str, object]]]] = []
    for pickup_date, items in departures.items():
        if pickup_date >= today:
            upcoming.append((pickup_date, sorted(items, key=lambda item: item.get("loadboard_rate", 0), reverse=True)))
    upcoming.sort(key=lambda entry: entry[0])

    return {
        "loads": loads,
        "by_equipment": by_equipment,
        "by_origin_state": by_origin_state,
        "upcoming": upcoming,
        "top_rates": top_rates[:5],
        "reference_date": today,
    }


def render_dashboard(reference_date: Optional[date] = None) -> str:
    snapshot = _collect_snapshot(reference_date)
    loads: List[Dict[str, object]] = snapshot["loads"]  # type: ignore[assignment]
    total_loads = len(loads)

    lines: List[str] = []
    lines.append("HappyRobot Load Board Dashboard")
    lines.append("=" * len(lines[0]))
    lines.append(f"Reference date: {snapshot['reference_date']:%Y-%m-%d}")
    lines.append(f"Total loads available: {total_loads}")

    if total_loads:
        lines.append("")
        lines.append("Equipment mix:")
        for equipment, count in _top_entries(snapshot["by_equipment"], limit=len(snapshot["by_equipment"])):
            lines.append(
                f"  - {equipment}: {count} ({_format_percentage(count, total_loads)})"
            )

        if snapshot["by_origin_state"]:
            lines.append("")
            lines.append("Top origin states:")
            for state, count in _top_entries(snapshot["by_origin_state"]):
                lines.append(
                    f"  - {state}: {count} loads ({_format_percentage(count, total_loads)})"
                )

        if snapshot["upcoming"]:
            lines.append("")
            lines.append("Upcoming departures:")
            for pickup_date, items in snapshot["upcoming"]:
                lines.append(
                    f"  {pickup_date:%a %Y-%m-%d}: {len(items)} load{'s' if len(items) != 1 else ''}"
                )
                preview = items[:3]
                for load in preview:
                    rate_display = _format_currency(load.get("loadboard_rate"))
                    lines.append(
                        "    • "
                        f"{load.get('load_id', 'N/A')} | "
                        f"{load.get('origin', 'Unknown')} → {load.get('destination', 'Unknown')} | "
                        f"{load.get('equipment_type', 'Unknown')} | {rate_display}"
                    )
                if len(items) > len(preview):
                    lines.append(
                        f"      … {len(items) - len(preview)} more load(s) on this date"
                    )

        if snapshot["top_rates"]:
            lines.append("")
            lines.append("Highest paying loads:")
            for load in snapshot["top_rates"]:
                lines.append(
                    "  - "
                    f"{load.get('load_id', 'N/A')} ({load.get('equipment_type', 'Unknown')}) "
                    f"{_format_currency(load.get('loadboard_rate'))} from {load.get('origin', 'Unknown')} "
                    f"to {load.get('destination', 'Unknown')}"
                )

    else:
        lines.append("")
        lines.append("No loads are currently available.")

    return "\n".join(lines)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Display a CLI snapshot of the HappyRobot load board."
    )
    parser.add_argument(
        "--reference-date",
        type=str,
        help="Optional reference date (YYYY-MM-DD) used to normalise recurring loads.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    reference_date: Optional[date] = None
    if args.reference_date:
        try:
            reference_date = datetime.strptime(args.reference_date, "%Y-%m-%d").date()
        except ValueError as exc:
            raise SystemExit(f"Invalid --reference-date value: {args.reference_date}") from exc

    output = render_dashboard(reference_date)
    print(output)


if __name__ == "__main__":
    main()
