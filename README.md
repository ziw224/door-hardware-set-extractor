# Fresco Coding Challenge

Hardware-set extraction from Division 08 spec PDFs.

## What is implemented

- Extracts hardware sets with location metadata (`page_start/page_end`, `line_range`).
- Handles multiple schedule formats:
  - `Heading #...` / `SET #...`
  - `Set: 1.0` / `Set: EX-3.0`
  - `Hardware Group No. 001`
- Parses components into:
  - `qty`, `description`, `catalog_number`, `mfr`, `finish`, `notes`
- Includes mfr/finish disambiguation using column context + code dictionaries.
- Adds per-field confidence scores in output (`component.field_confidence`).
- Adds spec/catalog shorthand resolution hook (`component.resolved_description`) using page-level code lookup.

## Setup

```bash
cd "/Users/zihanwang/Desktop/fresco-coding-challenge"
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Run

```bash
PYTHONPATH=. python -m src.pipeline --input "<pdf-or-folder>" --output "./out/result.json"
```

## Demo runs (3 different formats)

```bash
# Bridgeport (Heading # / SET #)
PYTHONPATH=. python -m src.pipeline \
  --input "./data/81-85 Bridgeport/08-70-00-Hardware-Schedule.pdf" \
  --output "./out/bridgeport_hw_schedule.json"

# Bridgeport Rev_0 (Heading # / SET #, alternate file)
PYTHONPATH=. python -m src.pipeline \
  --input "./data/81-85 Bridgeport/08-70-00-Hardware-Schedule_Rev_0.pdf" \
  --output "./out/bridgeport_hw_schedule_rev0.json"

# JC Ryan (Set: X.X / EX-X.X)
PYTHONPATH=. python -m src.pipeline \
  --input "./data/JC Ryan 2/087100 - Door Hardware-6.pdf" \
  --output "./out/jcryan_087100.json"

# HFH (Hardware Group No. XXX)
PYTHONPATH=. python -m src.pipeline \
  --input "./data/HFH DG - HOSPITAL/08 71 00 - DOOR HARDWARE.pdf" \
  --output "./out/hfh_087100.json"
```

## Evaluation workflow


1.Build prediction + gold draft for `08-70-00-Hardware-Schedule_Rev_0.pdf`:

```bash
PYTHONPATH=. python -m src.pipeline \
  --input "./data/81-85 Bridgeport/08-70-00-Hardware-Schedule_Rev_0.pdf" \
  --output "./out/bridgeport_hw_schedule_rev0.json"

PYTHONPATH=. python scripts/build_gold_from_pdf.py \
  --pdf "./data/81-85 Bridgeport/08-70-00-Hardware-Schedule_Rev_0.pdf" \
  --out "./eval/bridgeport_gold_from_pdf_draft_rev0.json" \
  --sample-size 20 \
  --seed 42
```

2. Annotate/correct one gold draft and save (example):

- `./eval/bridgeport_gold_from_pdf_annotated_v1.json`

3. Evaluate with matching pair:

```bash
python scripts/evaluate.py \
  --pred "./out/bridgeport_hw_schedule_rev0.json" \
  --gold "./eval/bridgeport_gold_from_pdf_annotated_v1.json" \
  --out "./eval/bridgeport_report_real_v1.json"
```

Current Bridgeport sampled result:

- `set_recall_on_sample`: `1.0`
- `catalog_number`: `0.9538` (124/130)
- `qty`: `1.0`
- `mfr`: `1.0`
- `finish`: `1.0`

## Feedback UI (JavaScript app)

Run local app:

```bash
node scripts/feedback_server.js
```

Open [http://localhost:4173](http://localhost:4173)

- Left panel: result files (`bridgeport_hw_schedule`, `bridgeport_hw_schedule_rev0`, `jcryan`, `hfh`)
- Click a file to preview sets/components
- Edit fields inline (`qty`, `description`, `catalog_number`, `mfr`, `finish`, `notes`, `resolved_description`)
- `Save Corrected JSON` writes to `./out/corrections/<file>.corrected.json`
- `Download JSON` exports the edited JSON directly

## Quality report

```bash
python scripts/quality_report.py \
  --pred "./out/bridgeport_hw_schedule_rev0.json" \
  --out "./eval/bridgeport_quality.json"
```

## GitHub Pages deployment

This repo includes a static deployable app in `docs/`.

1. Push current `master` to GitHub.
2. In GitHub repo settings: **Pages** -> **Build and deployment** -> **Source**: `Deploy from a branch`.
3. Branch: `master`, folder: `/docs`.
4. Save and wait ~1-2 minutes.

Then open:

- `https://ziw224.github.io/door-hardware-set-extractor/`

Notes:

- Static mode has no backend write API.
- `Save Corrected JSON` and `Download JSON` both download edited JSON locally.
- Files loaded by the page are in `docs/data/*.json`.
