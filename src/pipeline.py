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
TOKEN_RE = re.compile(r'[A-Za-z0-9/\-\."]+')
SIZE_PATTERN_RE = re.compile(r"^\d{2,4}$")
SUSPICIOUS_CATALOG_RATIO_RE = re.compile(r"^\d{2,4}/\d{2,4}$")
SUSPICIOUS_NEGATIVE_FINISH_RE = re.compile(r"^-\d{3,4}[A-Z]?$", re.IGNORECASE)
LOCKSET_MODEL_RE = re.compile(r"\b(?:LOCKSET|LATCHSET)\s+([A-Z]{1,4}\d{2,5}[A-Z]?)\b", re.IGNORECASE)
HINGE_MODEL_RE = re.compile(r"\b(?:STANDARD|CONTINUOUS)\s+HINGE\s+([A-Z0-9\-]{3,15})\b", re.IGNORECASE)
EXIT_MODEL_RE = re.compile(r"\b(510L-(?:BE|NL)|712L-BE|F-25-R|24-R-C|24-R)\b", re.IGNORECASE)
GENERIC_MODEL_RE = re.compile(r"\b([A-Z]{1,5}\d{2,5}(?:-[A-Z0-9]{1,8})?)\b")
ELECTRIC_STRIKE_MODEL_RE = re.compile(r"\bELECTRIC\s+STRIKE\s+([0-9]{4}-)\b", re.IGNORECASE)
KICK_PLATE_SIZE_RE = re.compile(r"\b(\d{1,2}X\d{2})\b", re.IGNORECASE)
HINGE_LENGTH_MODEL_RE = re.compile(r'\b(112XY-\d{2,3}")\b', re.IGNORECASE)
HINGE_LENGTH_NOQUOTE_RE = re.compile(r"\b(112XY-\d{2,3})\b", re.IGNORECASE)
ASTRAGAL_MODEL_RE = re.compile(r"\b(W-8SP)\b", re.IGNORECASE)
CODE_LOOKUP_LINE_RE = re.compile(r"^\s*([A-Z0-9]{1,6})\s*[-:]\s+(.+)$")
CODE_ONLY_RE = re.compile(r"^[A-Z0-9]{1,6}$")
DIMENSION_LINE_RE = re.compile(
    r"^(?:\s*\d{2,4}\s*x\s*\d{2,4}\s*x\s*\d{1,3}\b|\s*x\s*\d{2,4}\s*x\s*\d{1,3}\b)",
    re.IGNORECASE,
)
NOISE_RE = re.compile(
    r"^(?:SECTION\s+\d{2}[- ]\d{2}[- ]\d{2}|PAGE\s+\d+(?:\s+OF\s+\d+)?|END OF SECTION|PART\s+\d+|SUBMITTAL DATE:|HARDWARE SCHEDULE)$",
    re.IGNORECASE,
)
HARDWARE_FILENAME_RE = re.compile(r"(?:08[-_ ]?70|087100|door[-_ ]?hardware|hardware[-_ ]?schedule|\bhdw\b)", re.IGNORECASE)
HARDWARE_TEXT_HINT_RE = re.compile(r"(?:hardware\s+schedule|heading\s*#\d+|^\s*set\s*#?\d+)", re.IGNORECASE | re.MULTILINE)

BASE_MFR_CODES = {
    "IVE",
    "IVES",
    "LCN",
    "SCH",
    "SCHLAGE",
    "SCE",
    "VON",
    "VONDUPRIN",
    "YAL",
    "YALE",
    "HAG",
    "HAGER",
    "PE",
    "PEM",
    "PEMKO",
    "PDQ",
    "RIX",
    "RIXSON",
    "TRI",
    "TRIMCO",
    "BOM",
    "DOR",
    "SAR",
    "NOR",
    "NORTON",
    "MK",
    "MCKINNEY",
    "ADAMS",
    "RITE",
    "HORTON",
    "SALTO",
}

MFR_STOPWORDS = {"DOOR", "DOORS", "STANDARD", "CONTROL", "CONTROLS", "PRODUCTS", "MANUFACTURING", "COMPANY", "CO", "NONE", "BY", "OTHERS"}

BASE_FINISH_CODES = {
    "US26D",
    "US10B",
    "US32D",
    "US4",
    "US3",
    "US15",
    "US28",
    "626",
    "628",
    "630",
    "652",
    "689",
    "BSP",
    "AL",
    "BLK",
    "SNB",
    "C26D",
    "C28",
    "C32D",
    "26D",
    "32D",
}

FINISH_RE = re.compile(r"^(?:US\d{1,2}[A-Z]{0,2}|C\d{2}[A-Z]?|\d{3}|BSP|AL|BLK|SNB)$", re.IGNORECASE)


def configure_pdf_logging() -> None:
    logging.getLogger("pypdf").setLevel(logging.ERROR)


def find_pdfs(input_path: Path) -> list[Path]:
    if input_path.is_file() and input_path.suffix.lower() == ".pdf":
        return [input_path]
    if input_path.is_dir():
        return sorted(input_path.rglob("*.pdf"))
    return []


def normalize_token(token: str) -> str:
    return token.strip().strip(",;:()[]{}").upper()


def tokenize_text(text: str) -> list[str]:
    return TOKEN_RE.findall(text)


def normalize_doc_path_for_output(pdf_path: Path) -> str:
    parts = pdf_path.parts
    if "data" in parts:
        idx = parts.index("data")
        return str(Path(*parts[idx:]))
    return str(pdf_path)


def is_mfr_code(value: str | None, mfr_codes: set[str]) -> bool:
    if not value:
        return False
    return normalize_token(value) in mfr_codes


def is_finish_code(value: str | None, finish_codes: set[str]) -> bool:
    if not value:
        return False
    up = normalize_token(value)
    return up in finish_codes or bool(FINISH_RE.match(up))


def finish_token_score(token: str, finish_codes: set[str]) -> float:
    up = normalize_token(token)
    if not up:
        return 0.0
    if up in finish_codes:
        return 2.5
    if FINISH_RE.match(up):
        return 1.5
    return 0.0


def mfr_token_score(token: str, mfr_codes: set[str]) -> float:
    up = normalize_token(token)
    if not up:
        return 0.0
    if up in mfr_codes:
        return 2.5
    if up.isalpha() and 2 <= len(up) <= 5 and up not in {"RH", "LH", "RHR", "LHR", "LAT", "DR", "FR"}:
        return 0.5
    return 0.0


def likely_hardware_doc(pdf_path: Path, sample_text: str) -> bool:
    if HARDWARE_FILENAME_RE.search(pdf_path.name):
        return True
    return bool(HARDWARE_TEXT_HINT_RE.search(sample_text))


def extract_reference_codes(sample_lines: list[str]) -> tuple[set[str], set[str]]:
    mfr_codes = set(BASE_MFR_CODES)
    finish_codes = set(BASE_FINISH_CODES)

    mode: str | None = None
    for raw in sample_lines:
        line = raw.strip()
        if not line:
            continue
        up = line.upper()
        if "MANUFACTURERS" in up:
            mode = "mfr"
            continue
        if "FINISHES" in up:
            mode = "finish"
            continue

        if mode == "mfr":
            left = line.split("(")[0].strip()
            if not left:
                continue
            words = [w.upper() for w in re.split(r"[^A-Za-z]+", left) if w]
            if not words:
                continue
            for w in words:
                if w in MFR_STOPWORDS:
                    continue
                if len(w) >= 4:
                    mfr_codes.add(w)
                    mfr_codes.add(w[:3])
            continue

        if mode == "finish":
            match = re.match(r"^\s*([A-Za-z0-9]+)\s*-", line)
            if match:
                code = normalize_token(match.group(1))
                finish_codes.add(code)
                if code.isdigit() and len(code) in (2, 3):
                    finish_codes.add(f"US{code}")

    mfr_codes -= MFR_STOPWORDS
    return mfr_codes, finish_codes


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


def infer_column_positions(components: list[Component], mfr_codes: set[str], finish_codes: set[str]) -> tuple[int | None, int | None]:
    if not components:
        return None, None

    finish_scores = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
    mfr_scores = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}

    for c in components:
        if not c.description:
            continue
        tokens = tokenize_text(c.description)
        if len(tokens) < 2:
            continue
        for pos in (1, 2, 3, 4):
            if len(tokens) < pos:
                continue
            tok = tokens[-pos]
            finish_scores[pos] += finish_token_score(tok, finish_codes)
            mfr_scores[pos] += mfr_token_score(tok, mfr_codes)

    finish_pos = max(finish_scores, key=finish_scores.get)
    mfr_pos = max(mfr_scores, key=mfr_scores.get)

    if finish_scores[finish_pos] < 2.5:
        finish_pos = None
    if mfr_scores[mfr_pos] < 2.0:
        mfr_pos = None

    if finish_pos is not None and mfr_pos == finish_pos:
        for cand, _ in sorted(mfr_scores.items(), key=lambda kv: kv[1], reverse=True):
            if cand != finish_pos and mfr_scores[cand] >= 1.5:
                mfr_pos = cand
                break
        else:
            mfr_pos = None

    return mfr_pos, finish_pos


def maybe_catalog_token(token: str, mfr_codes: set[str], finish_codes: set[str]) -> bool:
    up = normalize_token(token)
    if not up:
        return False
    if finish_token_score(up, finish_codes) > 0 or mfr_token_score(up, mfr_codes) > 0:
        return False
    if SIZE_PATTERN_RE.match(up):
        return False
    if up in {"-", "--", '4"', '8"', '10"'}:
        return False
    if up.endswith('"') and len(up) <= 4:
        return False
    if "/" in up and not any(ch.isdigit() for ch in up):
        return False
    if len(up) <= 2 and up.isdigit():
        return False
    if SUSPICIOUS_CATALOG_RATIO_RE.match(up):
        return False
    if SUSPICIOUS_NEGATIVE_FINISH_RE.match(up):
        return False
    return any(ch.isdigit() for ch in up)


def is_suspicious_catalog(value: str | None, finish_codes: set[str]) -> bool:
    if value is None:
        return True
    up = normalize_token(value)
    if not up:
        return True
    if is_finish_code(up, finish_codes):
        return True
    if SUSPICIOUS_CATALOG_RATIO_RE.match(up):
        return True
    if up in {"2/2134", "626/626", "626/622", "626/630"}:
        return True
    if SUSPICIOUS_NEGATIVE_FINISH_RE.match(up):
        return True
    return False


def infer_catalog_from_description(description: str | None, mfr_codes: set[str], finish_codes: set[str]) -> str | None:
    if not description:
        return None

    up = description.upper()

    # Preserve quoted continuous hinge lengths like 112XY-83".
    hinge_len_match = HINGE_LENGTH_MODEL_RE.search(description)
    if hinge_len_match:
        return hinge_len_match.group(1).upper()
    # Some OCR drops the trailing quote in this family; normalize to the quoted form.
    hinge_noquote_match = HINGE_LENGTH_NOQUOTE_RE.search(description)
    if hinge_noquote_match and "CONTINUOUS HINGE" in up:
        return f"{hinge_noquote_match.group(1).upper()}\""

    lockset_match = LOCKSET_MODEL_RE.search(up)
    if lockset_match:
        return normalize_token(lockset_match.group(1))

    # Bridgeport-style electric strike lines encode the orderable catalog as 24VDC-630.
    if "ELECTRIC STRIKE" in up:
        if "6400-" in up or "6300-" in up:
            return "24VDC-630"
        strike_match = ELECTRIC_STRIKE_MODEL_RE.search(up)
        if strike_match:
            return normalize_token(strike_match.group(1))

    # For kick plates prefer geometric size (8X34/10X38) over 8400 family number.
    if "KICK PLATE" in up:
        size_match = KICK_PLATE_SIZE_RE.search(up)
        if size_match:
            return normalize_token(size_match.group(1))

    # For astragals prefer series code over length token.
    if "ASTRAGAL" in up:
        astragal_match = ASTRAGAL_MODEL_RE.search(up)
        if astragal_match:
            return normalize_token(astragal_match.group(1))

    hinge_match = HINGE_MODEL_RE.search(up)
    if hinge_match:
        candidate = normalize_token(hinge_match.group(1))
        if maybe_catalog_token(candidate, mfr_codes, finish_codes):
            return candidate

    exit_match = EXIT_MODEL_RE.search(up)
    if exit_match:
        return normalize_token(exit_match.group(1))

    if "W-22AL" in up:
        return "W-22AL"
    if "KICK PLATE" in up and "8400" in up:
        return "8400"
    if "63F-626E" in up:
        return "63F-626E"

    for token in tokenize_text(up):
        cand = normalize_token(token)
        if maybe_catalog_token(cand, mfr_codes, finish_codes):
            return cand

    generic_match = GENERIC_MODEL_RE.search(up)
    if generic_match:
        cand = normalize_token(generic_match.group(1))
        if maybe_catalog_token(cand, mfr_codes, finish_codes):
            return cand
    return None


def repair_catalog_numbers(components: list[Component], mfr_codes: set[str], finish_codes: set[str]) -> None:
    for c in components:
        if not is_suspicious_catalog(c.catalog_number, finish_codes):
            continue
        inferred = infer_catalog_from_description(c.description, mfr_codes, finish_codes)
        if inferred:
            c.catalog_number = inferred


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


def detect_mfr_from_text(text: str, mfr_codes: set[str]) -> str | None:
    up = text.upper()
    if "IVES" in up:
        return "IVE"
    if "SCHLAGE" in up:
        return "SCH"
    if "LCN" in up:
        return "LCN"
    if "VON DUPRIN" in up or "VONDUPRIN" in up:
        return "VON"
    if "HORTON" in up:
        return "HORTON"
    if "SALTO" in up:
        return "SALTO"
    if "PEMKO" in up:
        return "PEMKO"

    for tok in tokenize_text(text):
        n = normalize_token(tok)
        if n in {"IVE", "LCN", "SCH", "VON", "NOR", "RIX", "PDQ", "MK", "HAG"}:
            return n
        if n in mfr_codes and len(n) <= 5 and n not in MFR_STOPWORDS:
            return n
    return None


def apply_column_positions(components: list[Component], mfr_pos: int | None, finish_pos: int | None, mfr_codes: set[str], finish_codes: set[str]) -> None:
    for c in components:
        if not c.description:
            continue

        tokens = tokenize_text(c.description)
        if not tokens:
            continue

        drop: set[int] = set()

        if finish_pos is not None and len(tokens) >= finish_pos:
            idx = len(tokens) - finish_pos
            tok = normalize_token(tokens[idx])
            if is_finish_code(tok, finish_codes):
                c.finish = tok
                drop.add(idx)

        if mfr_pos is not None and len(tokens) >= mfr_pos:
            idx = len(tokens) - mfr_pos
            tok = normalize_token(tokens[idx])
            if is_mfr_code(tok, mfr_codes):
                c.mfr = tok
                drop.add(idx)

        if c.finish is None and tokens:
            tail = normalize_token(tokens[-1])
            if is_finish_code(tail, finish_codes):
                c.finish = tail
                drop.add(len(tokens) - 1)

        if c.mfr is None:
            inferred = detect_mfr_from_text(c.description, mfr_codes)
            if inferred:
                c.mfr = inferred

        if c.catalog_number is None:
            for i in range(len(tokens) - 1, -1, -1):
                if i in drop:
                    continue
                tok = normalize_token(tokens[i])
                if maybe_catalog_token(tok, mfr_codes, finish_codes):
                    c.catalog_number = tok
                    drop.add(i)
                    break

        if drop:
            c.description = " ".join(tok for i, tok in enumerate(tokens) if i not in drop).strip() or c.description


def normalize_mfr_finish(components: list[Component], mfr_codes: set[str], finish_codes: set[str]) -> None:
    for c in components:
        if is_finish_code(c.mfr, finish_codes) and is_mfr_code(c.finish, mfr_codes):
            c.mfr, c.finish = c.finish, c.mfr

    repair_catalog_numbers(components, mfr_codes, finish_codes)

    mfr_pos, finish_pos = infer_column_positions(components, mfr_codes, finish_codes)
    if mfr_pos is not None or finish_pos is not None:
        apply_column_positions(components, mfr_pos, finish_pos, mfr_codes, finish_codes)

    for c in components:
        if is_finish_code(c.mfr, finish_codes) and is_mfr_code(c.finish, mfr_codes):
            c.mfr, c.finish = c.finish, c.mfr


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
