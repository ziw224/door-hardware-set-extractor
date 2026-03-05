from __future__ import annotations

import argparse
import contextlib
import io
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from src.schemas.models import Component, DocumentResult, ExtractionResult, HardwareSet, Location
from src.confidence_review import enrich_components
from src.mfr_finish import (
    extract_reference_codes,
    is_finish_code,
    is_mfr_code,
    maybe_catalog_token,
    normalize_mfr_finish,
    normalize_token,
    tokenize_text,
)
from src.set_boundaries import close_active_set

SET_HEADER_RE = re.compile(
    r"^\s*(?:HARDWARE\s+|HW\s+)?SET(?:\s+NO\.?)?\s*#?\s*([0-9]+[A-Z]?)\b",
    re.IGNORECASE,
)
HEADING_HEADER_RE = re.compile(r"^\s*Heading\s*#\s*([0-9]+[A-Z]?)\s*$", re.IGNORECASE)
SET_COLON_HEADER_RE = re.compile(r"^\s*Set\s*:\s*([A-Z]{0,4}-?\d+(?:\.\d+)?[A-Z]?)\s*$", re.IGNORECASE)
HARDWARE_GROUP_HEADER_RE = re.compile(r"^\s*Hardware\s+Group\s+No\.?\s*([0-9]{1,4}[A-Z]?)\s*$", re.IGNORECASE)
DESCRIPTION_LINE_RE = re.compile(r"^\s*Description\s*:\s*(.+)$", re.IGNORECASE)
ITEM_LINE_RE = re.compile(r"^\s*Item\s*#\s*\d+\s*(.+)$", re.IGNORECASE)
NOT_USED_RE = re.compile(r"\b(?:NOT\s+USED|N/?A|NA)\b", re.IGNORECASE)
QTY_PREFIX_RE = re.compile(r"^\s*(\d+)\s+(.+)$")
COMPONENT_HINT_RE = re.compile(
    r"^(?:Hinge|Pivot|Panic|Gasketing|Threshold|Door|Lock|Latch|Exit|Surface|Stop|Sweep|Astragal|Flush|Dust|Coordinator|Closer|Electric|Automatic|Wave|Silencers|Passage|Privacy|Classroom|Storeroom|Office|Push|Pull|Hanging\s+Device|Hardware\s+provided)",
    re.IGNORECASE,
)
GROUP_QTY_LINE_RE = re.compile(r"^\s*(\d+)\s+(EA|SET)\b\s*(.+)$", re.IGNORECASE)
COMPONENT_SPLIT_RE = re.compile(r"\s{2,}|\t+")
DIMENSION_LINE_RE = re.compile(
    r"^(?:\s*\d{2,4}\s*x\s*\d{2,4}\s*x\s*\d{1,3}\b|\s*x\s*\d{2,4}\s*x\s*\d{1,3}\b)",
    re.IGNORECASE,
)
NOISE_RE = re.compile(
    r"^(?:SECTION\s+\d{2}[- ]\d{2}[- ]\d{2}|PAGE\s+\d+(?:\s+OF\s+\d+)?|END OF SECTION|PART\s+\d+|SUBMITTAL DATE:|HARDWARE SCHEDULE)$",
    re.IGNORECASE,
)
CODE_LOOKUP_LINE_RE = re.compile(r"^\s*([A-Z0-9]{1,6})\s*[-:]\s+(.+)$")
HARDWARE_FILENAME_RE = re.compile(r"(?:08[-_ ]?70|087100|door[-_ ]?hardware|hardware[-_ ]?schedule|\bhdw\b)", re.IGNORECASE)
HARDWARE_TEXT_HINT_RE = re.compile(r"(?:hardware\s+schedule|heading\s*#\d+|^\s*set\s*#?\d+)", re.IGNORECASE | re.MULTILINE)


def configure_pdf_logging() -> None:
    logging.getLogger("pypdf").setLevel(logging.ERROR)

def find_pdfs(input_path: Path) -> list[Path]:
    if input_path.is_file() and input_path.suffix.lower() == ".pdf":
        return [input_path]
    if input_path.is_dir():
        return sorted(input_path.rglob("*.pdf"))
    return []






def normalize_doc_path_for_output(pdf_path: Path) -> str:
    parts = pdf_path.parts
    if "data" in parts:
        idx = parts.index("data")
        return str(Path(*parts[idx:]))
    return str(pdf_path)










def likely_hardware_doc(pdf_path: Path, sample_text: str) -> bool:
    if HARDWARE_FILENAME_RE.search(pdf_path.name):
        return True
    return bool(HARDWARE_TEXT_HINT_RE.search(sample_text))




def extract_code_lookup(sample_lines: list[str]) -> dict[str, str]:
    code_lookup: dict[str, str] = {}
    for raw in sample_lines:
        line = raw.strip()
        if not line:
            continue
        match = CODE_LOOKUP_LINE_RE.match(line)
        if not match:
            continue
        code = normalize_token(match.group(1))
        desc = match.group(2).strip()
        if len(code) <= 1:
            continue
        if code in {"SECTION", "PART", "PAGE", "ITEM", "SET"}:
            continue
        if len(desc) < 3:
            continue
        if code not in code_lookup:
            code_lookup[code] = desc
    return code_lookup


def parse_component_line(line: str) -> Component | None:
    raw = line.strip()
    if not raw or NOISE_RE.search(raw):
        return None

    qty: str | None = None
    content = raw
    qty_match = QTY_PREFIX_RE.match(raw)
    if qty_match:
        qty = qty_match.group(1)
        content = qty_match.group(2).strip()

    if DIMENSION_LINE_RE.match(content) or content.lower().startswith("x "):
        return None

    notes: str | None = None
    note_idx = content.upper().find("NOTE:")
    if note_idx >= 0:
        notes = content[note_idx + len("NOTE:") :].strip() or None
        content = content[:note_idx].strip()

    parts = [p.strip() for p in COMPONENT_SPLIT_RE.split(content) if p.strip()]
    if len(parts) >= 4:
        description = " ".join(parts[:-3]).strip() or None
        return Component(
            qty=qty,
            description=description,
            catalog_number=parts[-3],
            mfr=parts[-2],
            finish=parts[-1],
            notes=notes,
        )

    if len(parts) == 3:
        return Component(
            qty=qty,
            description=parts[0],
            catalog_number=parts[1],
            mfr=parts[2],
            finish=None,
            notes=notes,
        )

    return Component(qty=qty, description=content or None, notes=notes)












def parse_group_component_line(line: str, mfr_codes: set[str], finish_codes: set[str]) -> Component | None:
    match = GROUP_QTY_LINE_RE.match(line)
    if not match:
        return None

    qty = match.group(1)
    body = match.group(3).strip()
    tokens = tokenize_text(body)
    if not tokens:
        return Component(qty=qty, description=body or None)

    mfr: str | None = None
    finish: str | None = None
    end = len(tokens)

    last_tok = normalize_token(tokens[end - 1])
    if is_mfr_code(last_tok, mfr_codes):
        mfr = last_tok
        end -= 1

    if end > 0:
        prev_tok = normalize_token(tokens[end - 1])
        if is_finish_code(prev_tok, finish_codes):
            finish = prev_tok
            end -= 1

    catalog: str | None = None
    catalog_idx: int | None = None
    for i in range(end - 1, -1, -1):
        tok = normalize_token(tokens[i])
        if maybe_catalog_token(tok, mfr_codes, finish_codes):
            catalog = tok
            catalog_idx = i
            break

    desc_tokens = tokens[:end]
    if catalog_idx is not None and 0 <= catalog_idx < len(desc_tokens):
        desc_tokens = [t for idx, t in enumerate(desc_tokens) if idx != catalog_idx]

    description = " ".join(desc_tokens).strip() or body
    return Component(qty=qty, description=description, catalog_number=catalog, mfr=mfr, finish=finish)
















def parse_pdf(pdf_path: Path) -> DocumentResult:
    from pypdf import PdfReader

    with contextlib.redirect_stderr(io.StringIO()):
        reader = PdfReader(str(pdf_path), strict=False)

        sample_texts: list[str] = []
        sample_lines: list[str] = []
        sample_pages = min(8, len(reader.pages))
        for idx in range(sample_pages):
            txt = reader.pages[idx].extract_text() or ""
            sample_texts.append(txt)
            sample_lines.extend(txt.splitlines())

        if not likely_hardware_doc(pdf_path, "\n".join(sample_texts)):
            return DocumentResult(doc_path=normalize_doc_path_for_output(pdf_path), hardware_sets=[])

        mfr_codes, finish_codes = extract_reference_codes(sample_lines)

        detected_sets: list[HardwareSet] = []
        page_code_lookup: dict[int, dict[str, str]] = {}
        active_set_idx: int | None = None
        active_set_start_line = 1
        active_mode: str | None = None
        last_seen_page: int | None = None
        last_seen_line: int | None = None

        for page_idx, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            lines = [ln.strip() for ln in text.splitlines()]
            page_code_lookup[page_idx] = extract_code_lookup(lines)

            for line_idx, line in enumerate(lines, start=1):
                if not line or NOISE_RE.search(line):
                    continue

                heading_match = HEADING_HEADER_RE.match(line)
                set_match = SET_HEADER_RE.match(line)
                set_colon_match = SET_COLON_HEADER_RE.match(line)
                hardware_group_match = HARDWARE_GROUP_HEADER_RE.match(line)
                header_match = heading_match or set_match or set_colon_match or hardware_group_match

                if header_match:
                    close_active_set(detected_sets, active_set_idx, active_set_start_line, last_seen_page, last_seen_line)

                    raw_set_number = header_match.group(1).upper().strip()
                    if set_colon_match:
                        set_number = raw_set_number
                    elif hardware_group_match:
                        set_number = raw_set_number.lstrip("0") or "0"
                    else:
                        set_number = raw_set_number.lstrip("0") or "0"
                    status = "not_used" if NOT_USED_RE.search(line) else "active"
                    description = None
                    if set_match:
                        description = line[set_match.end() :].strip(" :-\t") or None

                    detected_sets.append(
                        HardwareSet(
                            set_number=set_number,
                            description=description,
                            status=status,
                            location=Location(
                                page_start=page_idx,
                                page_end=page_idx,
                                bbox=None,
                                line_range=[line_idx, line_idx],
                            ),
                            components=[],
                        )
                    )
                    active_set_idx = len(detected_sets) - 1
                    active_set_start_line = line_idx
                    if heading_match:
                        active_mode = "heading"
                    elif set_colon_match:
                        active_mode = "set_colon"
                    elif hardware_group_match:
                        active_mode = "group"
                    else:
                        active_mode = "set"
                    last_seen_page = page_idx
                    last_seen_line = line_idx
                    continue

                if active_set_idx is None:
                    continue
                if detected_sets[active_set_idx].status == "not_used":
                    continue

                if active_mode == "heading":
                    item_match = ITEM_LINE_RE.match(line)
                    if item_match:
                        if not detected_sets[active_set_idx].description:
                            detected_sets[active_set_idx].description = item_match.group(1).strip() or None
                        last_seen_page = page_idx
                        last_seen_line = line_idx
                        continue

                    if not QTY_PREFIX_RE.match(line):
                        if line.startswith("@") and detected_sets[active_set_idx].components:
                            prev_notes = detected_sets[active_set_idx].components[-1].notes
                            addon = line.lstrip("@ ").strip()
                            if addon:
                                detected_sets[active_set_idx].components[-1].notes = (
                                    f"{prev_notes}; {addon}" if prev_notes else addon
                                )
                                last_seen_page = page_idx
                                last_seen_line = line_idx
                        continue

                if active_mode == "set_colon":
                    desc_match = DESCRIPTION_LINE_RE.match(line)
                    if desc_match:
                        desc = desc_match.group(1).strip()
                        existing = detected_sets[active_set_idx].description
                        detected_sets[active_set_idx].description = desc if not existing else f"{existing} {desc}"
                        last_seen_page = page_idx
                        last_seen_line = line_idx
                        continue

                    if line.lower().startswith("notes:") or line.lower().startswith("operation:") or line.startswith("*"):
                        continue

                    if not QTY_PREFIX_RE.match(line) and not COMPONENT_HINT_RE.match(line):
                        if detected_sets[active_set_idx].description and not line.lower().startswith("set:"):
                            # Some descriptions wrap to the next line in this format.
                            if len(line.split()) > 2 and not line.lower().startswith("description:"):
                                detected_sets[active_set_idx].description = (
                                    f"{detected_sets[active_set_idx].description} {line}".strip()
                                )
                        continue

                if active_mode == "group":
                    if line.lower().startswith("notes:") or line.lower().startswith("operation:") or line.startswith("*"):
                        continue
                    group_component = parse_group_component_line(line, mfr_codes, finish_codes)
                    if group_component is not None:
                        detected_sets[active_set_idx].components.append(group_component)
                        last_seen_page = page_idx
                        last_seen_line = line_idx
                    continue

                component = parse_component_line(line)
                if component is not None:
                    detected_sets[active_set_idx].components.append(component)
                    last_seen_page = page_idx
                    last_seen_line = line_idx

        close_active_set(detected_sets, active_set_idx, active_set_start_line, last_seen_page, last_seen_line)

        for hardware_set in detected_sets:
            if hardware_set.status == "active" and hardware_set.components:
                normalize_mfr_finish(hardware_set.components, mfr_codes, finish_codes)

                lookup: dict[str, str] = {}
                start = hardware_set.location.page_start
                end = hardware_set.location.page_end
                for pg in range(start, end + 1):
                    lookup.update(page_code_lookup.get(pg, {}))

                enrich_components(hardware_set.components, mfr_codes, finish_codes, lookup)

    return DocumentResult(doc_path=normalize_doc_path_for_output(pdf_path), hardware_sets=detected_sets)


def run(input_path: Path, output_path: Path) -> None:
    configure_pdf_logging()
    pdfs = find_pdfs(input_path)
    if not pdfs:
        raise SystemExit(f"No PDF files found at: {input_path}")

    documents: list[DocumentResult] = []
    failed_files: list[tuple[str, str]] = []

    for pdf_path in pdfs:
        try:
            documents.append(parse_pdf(pdf_path))
        except Exception as exc:
            failed_files.append((str(pdf_path), str(exc)))

    result = ExtractionResult(
        generated_at=datetime.now(timezone.utc).isoformat(),
        documents=documents,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(result.model_dump(), f, ensure_ascii=False, indent=2)

    print(f"Processed documents: {len(documents)}")
    if failed_files:
        print(f"Skipped documents due to parse errors: {len(failed_files)}")
        for path, reason in failed_files[:10]:
            print(f"- {path}: {reason}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract hardware sets from PDFs")
    parser.add_argument("--input", required=True, help="Input PDF file or folder path")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    args = parser.parse_args()

    run(Path(args.input), Path(args.output))


if __name__ == "__main__":
    main()
