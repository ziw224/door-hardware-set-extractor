from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Location(BaseModel):
    page_start: int
    page_end: int
    bbox: list[float] | None = None
    line_range: list[int] | None = None


class Component(BaseModel):
    qty: str | None = None
    description: str | None = None
    catalog_number: str | None = None
    mfr: str | None = None
    finish: str | None = None
    notes: str | None = None
    resolved_description: str | None = None
    field_confidence: dict[str, float] | None = None


class HardwareSet(BaseModel):
    set_number: str
    description: str | None = None
    location: Location
    status: Literal["active", "not_used"] = "active"
    components: list[Component] = Field(default_factory=list)


class DocumentResult(BaseModel):
    doc_path: str
    hardware_sets: list[HardwareSet] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    generated_at: str
    documents: list[DocumentResult] = Field(default_factory=list)
