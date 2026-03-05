from __future__ import annotations

import json
import re
from pathlib import Path

IN_PATH = Path('/Users/zihanwang/Desktop/fresco-coding-challenge/eval/bridgeport_gold_from_pdf_draft.json')
OUT_PATH = Path('/Users/zihanwang/Desktop/fresco-coding-challenge/eval/bridgeport_gold_from_pdf_annotated_v1.json')

LOCKSET_RE = re.compile(r'\b(?:LOCKSET|LATCHSET)\s+([A-Z]{1,3}\d{2,4}[A-Z]?)\b', re.IGNORECASE)
EXIT_MODEL_RE = re.compile(r'\b(510L-(?:BE|NL)|F-25-R|712L-BE|24-R-C|24-R)\b', re.IGNORECASE)
GEN_MODEL_RE = re.compile(r'\b([A-Z]{1,5}\d{2,5}(?:-[A-Z0-9]{1,6})?)\b')


def normalize_model(s: str | None) -> str | None:
    if not s:
        return None
    return s.upper()


def pick_catalog_from_description(desc: str) -> str | None:
    # 1) Lockset/latchset explicit code
    m = LOCKSET_RE.search(desc)
    if m:
        return normalize_model(m.group(1))

    # 2) Exit device common models
    m = EXIT_MODEL_RE.search(desc)
    if m:
        return normalize_model(m.group(1))

    # 3) For gasketing lines with W-22AL where cat got parsed as 2/2134
    if 'W-22AL' in desc.upper():
        return 'W-22AL'

    # 4) For kick plate lines with obvious 8400 code
    if 'KICK PLATE' in desc.upper() and '8400' in desc:
        return '8400'

    # 5) For 63F-626E wall stop keep full code
    if '63F-626E' in desc.upper():
        return '63F-626E'

    # 6) generic fallback
    m = GEN_MODEL_RE.search(desc.upper())
    if m:
        return m.group(1)
    return None


def should_replace_catalog(cat: str | None) -> bool:
    if cat is None:
        return True
    c = cat.strip().upper()
    if c in {'626/626', '626/622', '626/630', '2/2134', '-626E'}:
        return True
    return False


def main() -> None:
    data = json.loads(IN_PATH.read_text(encoding='utf-8'))
    changes = []

    for s in data.get('samples', []):
        set_no = s.get('set_number')
        for i, c in enumerate(s.get('gold_components', []), start=1):
            before_cat = c.get('catalog_number')
            desc = c.get('description') or ''

            if should_replace_catalog(before_cat):
                new_cat = pick_catalog_from_description(desc)
                if new_cat and new_cat != before_cat:
                    c['catalog_number'] = new_cat
                    changes.append((set_no, i, 'catalog_number', before_cat, new_cat))

            # fill obvious manufacturers on lines that contain known brand terms
            before_mfr = c.get('mfr')
            up = desc.upper()
            new_mfr = None
            if 'HORTON' in up:
                new_mfr = 'HORTON'
            elif 'SALTO' in up:
                new_mfr = 'SALTO'
            elif 'IVES' in up:
                new_mfr = 'IVE'

            if new_mfr and before_mfr != new_mfr:
                c['mfr'] = new_mfr
                changes.append((set_no, i, 'mfr', before_mfr, new_mfr))

    data.setdefault('meta', {})['annotated_by'] = 'codex_v1_heuristic_manual_draft'
    data['meta']['change_count'] = len(changes)

    OUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f'Wrote: {OUT_PATH}')
    print(f'Changes: {len(changes)}')
    for row in changes[:120]:
        print(row)


if __name__ == '__main__':
    main()
