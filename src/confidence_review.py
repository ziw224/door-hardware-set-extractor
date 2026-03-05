from __future__ import annotations

import re

from src.mfr_finish import is_finish_code, is_mfr_code, is_suspicious_catalog, normalize_token
from src.schemas.models import Component

CODE_ONLY_RE = re.compile(r"^[A-Z0-9]{1,6}$")


def resolve_component_code(component: Component, code_lookup: dict[str, str]) -> None:
    if not code_lookup:
        return

    if component.catalog_number:
        code = normalize_token(component.catalog_number)
        if code in code_lookup:
            component.resolved_description = code_lookup[code]
            return

    if component.description:
        desc = component.description.strip()
        if CODE_ONLY_RE.match(desc):
            code = normalize_token(desc)
            if code in code_lookup:
                component.resolved_description = code_lookup[code]


def component_confidence(component: Component, mfr_codes: set[str], finish_codes: set[str]) -> dict[str, float]:
    qty_conf = 0.95 if (component.qty and component.qty.isdigit()) else (0.25 if component.qty else 0.1)

    if component.catalog_number is None:
        cat_conf = 0.15
    elif is_suspicious_catalog(component.catalog_number, finish_codes):
        cat_conf = 0.4
    else:
        cat_conf = 0.85
    if component.resolved_description:
        cat_conf = min(0.98, cat_conf + 0.08)

    if component.mfr is None:
        mfr_conf = 0.2
    elif is_mfr_code(component.mfr, mfr_codes):
        mfr_conf = 0.9
    else:
        mfr_conf = 0.55

    if component.finish is None:
        finish_conf = 0.2
    elif is_finish_code(component.finish, finish_codes):
        finish_conf = 0.9
    else:
        finish_conf = 0.5

    desc_conf = 0.8 if component.description else 0.2
    notes_conf = 0.7 if component.notes else 0.2

    return {
        "qty": round(qty_conf, 3),
        "description": round(desc_conf, 3),
        "catalog_number": round(cat_conf, 3),
        "mfr": round(mfr_conf, 3),
        "finish": round(finish_conf, 3),
        "notes": round(notes_conf, 3),
    }


def enrich_components(components: list[Component], mfr_codes: set[str], finish_codes: set[str], code_lookup: dict[str, str]) -> None:
    for component in components:
        resolve_component_code(component, code_lookup)
        component.field_confidence = component_confidence(component, mfr_codes, finish_codes)


__all__ = ["resolve_component_code", "component_confidence", "enrich_components"]
