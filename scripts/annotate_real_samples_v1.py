from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path('/Users/zihanwang/Desktop/fresco-coding-challenge')

BAD_MFR = {
    'PER', 'WITH', 'PANIC', 'SYSTEMS', 'MANUFACTURER', 'SECURE', 'FIRE', 'LOCK', 'SET', 'INT', 'CON',
    'POWER', 'CLOSER', 'REQUIRED', 'RELATED', 'COR', 'ASSEMBLY', 'SAFETY', 'REG', 'HARDWARE'
}

MFR_MAP = {
    'ROCKWOOD': 'ROCKWOOD',
    'PEMKO': 'PEMKO',
    'SARGENT': 'SARGENT',
    'MCKINNEY': 'MCKINNEY',
    'NORTON': 'NORTON',
    'LCN': 'LCN',
    'IVES': 'IVE',
    'IVE': 'IVE',
    'VON': 'VON',
    'SCHLAGE': 'SCH',
    'SCH': 'SCH',
    'SECURITRON': 'SECURITRON',
    'BES': 'BES',
}


def norm(v: str | None) -> str | None:
    if v is None:
        return None
    s = v.strip().upper()
    return s or None


def fix_component(c: dict) -> int:
    changed = 0
    desc = (c.get('description') or '').upper()

    # 1) remove obviously bogus manufacturer tokens
    mfr = norm(c.get('mfr'))
    if mfr in BAD_MFR:
        c['mfr'] = None
        changed += 1
        mfr = None

    # 2) infer manufacturer from description when explicit brand appears
    if mfr is None:
        for k, v in MFR_MAP.items():
            if k in desc:
                c['mfr'] = v
                changed += 1
                mfr = v
                break

    cat = norm(c.get('catalog_number'))

    # 3) clean obvious catalog mis-assignments
    if cat == '4.5' and '5BB1HW' in desc:
        c['catalog_number'] = '5BB1HW'
        changed += 1
        cat = '5BB1HW'

    if cat == '15D':
        if '9K30N' in desc:
            c['catalog_number'] = '9K30N'
            changed += 1
            cat = '9K30N'
        elif '9K37D' in desc:
            c['catalog_number'] = '9K37D'
            changed += 1
            cat = '9K37D'

    if cat in {'2845/', '7500/'}:
        c['catalog_number'] = cat.rstrip('/')
        changed += 1
        cat = c['catalog_number']

    if cat is None and 'DUST PROOF STRIKE 570' in desc:
        c['catalog_number'] = '570'
        changed += 1
        cat = '570'

    if cat is None and 'EL-CEPT' in desc:
        c['catalog_number'] = 'EL-CEPT'
        changed += 1
        cat = 'EL-CEPT'

    if cat is None and 'STOREROOM/ CLOSET LOCK 8204' in desc:
        c['catalog_number'] = '8204'
        changed += 1
        cat = '8204'
    if cat is None and 'STOREROOM LOCK 8204' in desc:
        c['catalog_number'] = '8204'
        changed += 1
        cat = '8204'
    if cat is None and 'CLASSROOM LOCK 8237' in desc:
        c['catalog_number'] = '8237'
        changed += 1
        cat = '8237'
    if cat is None and 'PASSAGE SET 8215' in desc:
        c['catalog_number'] = '8215'
        changed += 1
        cat = '8215'

    # 4) clear mfr on obvious non-components / headers
    if 'DOOR HARDWARE  08 71 00 - ' in desc or desc.startswith('HARDWARE PROVIDED BY SECTION'):
        if c.get('mfr') is not None:
            c['mfr'] = None
            changed += 1

    # 5) finish cleanup: numeric lock/bolt code mistakenly put in finish
    fin = norm(c.get('finish'))
    if fin in {'555', '570'} and (cat is None or cat in {'', 'NULL'}):
        c['catalog_number'] = fin
        c['finish'] = None
        changed += 1

    return changed


def annotate(in_path: Path, out_path: Path) -> tuple[int, int]:
    data = json.loads(in_path.read_text(encoding='utf-8'))
    changes = 0
    comps = 0

    for s in data.get('samples', []):
        for c in s.get('gold_components', []):
            comps += 1
            changes += fix_component(c)

    data.setdefault('meta', {})['annotated_by'] = 'codex_real_v1_rules'
    data['meta']['change_count'] = changes
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return changes, comps


def main() -> None:
    jobs = [
        ('eval/jcryan_gold_from_pdf_draft.json', 'eval/jcryan_gold_from_pdf_annotated_v1.json'),
        ('eval/hfh_gold_from_pdf_draft.json', 'eval/hfh_gold_from_pdf_annotated_v1.json'),
    ]

    for src, dst in jobs:
        ch, cp = annotate(ROOT / src, ROOT / dst)
        print(f'{src} -> {dst} | components={cp} changes={ch}')


if __name__ == '__main__':
    main()
