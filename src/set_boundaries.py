from __future__ import annotations

from src.schemas.models import HardwareSet


def close_active_set(
    detected_sets: list[HardwareSet],
    active_set_idx: int | None,
    active_set_start_line: int,
    last_seen_page: int | None,
    last_seen_line: int | None,
) -> None:
    if active_set_idx is None:
        return
    target = detected_sets[active_set_idx]
    end_page = last_seen_page or target.location.page_start
    end_line = last_seen_line or active_set_start_line
    target.location.page_end = end_page
    target.location.line_range = [active_set_start_line, max(end_line, active_set_start_line)]


__all__ = ["close_active_set"]
