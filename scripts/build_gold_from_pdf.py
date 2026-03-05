from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from src.pipeline import parse_pdf

KEY_FIELDS = ["qty", "catalog_number", "mfr", "finish"]


def sample_sets_from_pdf(pdf_path: Path, sample_size: int, seed: int) -> list[dict]:
    doc = parse_pdf(pdf_path)
    candidates = [s for s in doc.hardware_sets if s.status == "active" and s.components]
    if not candidates:
        return []

    random.seed(seed)
    chosen = random.sample(candidates, min(sample_size, len(candidates)))

    samples: list[dict] = []
    for s in chosen:
        comps = s.components[: min(8, len(s.components))]
        samples.append(
            {
                "doc_path": doc.doc_path,
                "set_number": s.set_number,
                "description": s.description,
                "location": s.location.model_dump(),
                "gold_components": [c.model_dump() for c in comps],
                "annotation_notes": "Review values against PDF. Edit only wrong fields; keep null if truly missing.",
            }
        )
    return samples


def main() -> None:
    parser = argparse.ArgumentParser(description="Build gold sample draft directly from a PDF")
    parser.add_argument("--pdf", required=True, help="Path to source hardware schedule PDF")
    parser.add_argument("--out", required=True, help="Output JSON path")
    parser.add_argument("--sample-size", type=int, default=20, help="Number of sets to sample")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    out_path = Path(args.out)

    samples = sample_sets_from_pdf(pdf_path, sample_size=args.sample_size, seed=args.seed)

    payload = {
        "meta": {
            "instructions": [
                "This draft is generated directly from PDF parsing, not copied from a prediction JSON.",
                "Review each sampled set with the original PDF and correct mistakes.",
                "Focus on qty, catalog_number, mfr, finish.",
            ],
            "source_pdf": str(pdf_path),
            "scored_fields": KEY_FIELDS,
            "sample_size": len(samples),
        },
        "samples": samples,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Wrote PDF-based gold draft: {out_path}")
    print(f"Sampled sets: {len(samples)}")


if __name__ == "__main__":
    main()
