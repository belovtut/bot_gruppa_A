"""Map UI filter state to database search parameters (shared by handlers)."""
from __future__ import annotations

from database.models import FilterState, WorkArea


def work_area_labels(area_values: list[str]) -> list[str]:
    """Turn stored work-area codes into human-readable location substrings for SQL."""
    labels: list[str] = []
    for val in area_values:
        try:
            labels.append(WorkArea(val).label)
        except ValueError:
            labels.append(val)
    return labels


def filters_to_search_kwargs(filters: FilterState) -> dict:
    """Build kwargs for :meth:`database.Database.search_controllers`."""
    return {
        "specializations": filters.specializations or None,
        "min_rating": filters.min_rating,
        "experience_types": filters.experience_types or None,
        "location": filters.location,
        "areas": work_area_labels(filters.areas) if filters.areas else None,
        "languages": filters.languages or None,
        "available_date": filters.available_date,
    }
