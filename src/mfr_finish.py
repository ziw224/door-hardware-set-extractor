from __future__ import annotations

import re

from src.schemas.models import Component

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


def normalize_token(token: str) -> str:
    return token.strip().strip(",;:()[]{}").upper()


def tokenize_text(text: str) -> list[str]:
    return TOKEN_RE.findall(text)


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

    hinge_len_match = HINGE_LENGTH_MODEL_RE.search(description)
    if hinge_len_match:
        return hinge_len_match.group(1).upper()
    hinge_noquote_match = HINGE_LENGTH_NOQUOTE_RE.search(description)
    if hinge_noquote_match and "CONTINUOUS HINGE" in up:
        return f"{hinge_noquote_match.group(1).upper()}\""

    lockset_match = LOCKSET_MODEL_RE.search(up)
    if lockset_match:
        return normalize_token(lockset_match.group(1))

    if "ELECTRIC STRIKE" in up:
        if "6400-" in up or "6300-" in up:
            return "24VDC-630"
        strike_match = ELECTRIC_STRIKE_MODEL_RE.search(up)
        if strike_match:
            return normalize_token(strike_match.group(1))

    if "KICK PLATE" in up:
        size_match = KICK_PLATE_SIZE_RE.search(up)
        if size_match:
            return normalize_token(size_match.group(1))

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


__all__ = [
    "BASE_MFR_CODES",
    "MFR_STOPWORDS",
    "BASE_FINISH_CODES",
    "FINISH_RE",
    "normalize_token",
    "tokenize_text",
    "is_mfr_code",
    "is_finish_code",
    "finish_token_score",
    "mfr_token_score",
    "extract_reference_codes",
    "infer_column_positions",
    "maybe_catalog_token",
    "is_suspicious_catalog",
    "infer_catalog_from_description",
    "repair_catalog_numbers",
    "detect_mfr_from_text",
    "apply_column_positions",
    "normalize_mfr_finish",
]
