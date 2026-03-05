from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


KEY_FIELDS = ["qty", "catalog_number", "mfr", "finish"]


def load_prediction(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def sample_sets(pred: dict, sample_size: int, seed: int) -> list[dict]:
    all_sets: list[tuple[str, dict]] = []
    for doc in pred.get("documents", []):
        doc_path = doc.get("doc_path", "")
        for hw_set in doc.get("hardware_sets", []):
            if hw_set.get("components"):
                all_sets.append((doc_path, hw_set))

    if not all_sets:
        return []

    random.seed(seed)
    k = min(sample_size, len(all_sets))
    chosen = random.sample(all_sets, k)

    template_sets = []
    for doc_path, hw_set in chosen:
        comps = hw_set.get("components", [])
        trimmed = comps[: min(8, len(comps))]
        template_sets.append(
            {
                "doc_path": doc_path,
                "set_number": hw_set.get("set_number"),
                "description": hw_set.get("description"),
                "location": hw_set.get("location"),
                "gold_components": [
                    {
                        "qty": c.get("qty"),
                        "description": c.get("description"),
                        "catalog_number": c.get("catalog_number"),
                        "mfr": c.get("mfr"),
                        "finish": c.get("finish"),
                        "notes": c.get("notes"),
                    }
                    for c in trimmed
                ],
                "annotation_notes": "Edit only incorrect values. Keep null if truly missing.",
            }
        )

    return template_sets


def build_template(pred: dict, sample_size: int, seed: int) -> dict:
    sets = sample_sets(pred, sample_size=sample_size, seed=seed)
    return {
        "meta": {
            "instructions": [
                "Review each sampled set.",
                "Only correct wrong fields in gold_components.",
                "Use null for truly missing values.",
                "Focus on qty, catalog_number, mfr, finish.",
            ],
            "scored_fields": KEY_FIELDS,
            "sample_size": len(sets),
        },
        "samples": sets,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a small annotation template from prediction output")
    parser.add_argument("--pred", required=True, help="Path to prediction JSON (e.g., out/result.json)")
    parser.add_argument("--out", required=True, help="Path to output annotation template JSON")
    parser.add_argument("--sample-size", type=int, default=20, help="Number of sets to sample")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    pred_path = Path(args.pred)
    out_path = Path(args.out)

    pred = load_prediction(pred_path)
    template = build_template(pred, sample_size=args.sample_size, seed=args.seed)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(template, f, ensure_ascii=False, indent=2)

    print(f"Wrote annotation template: {out_path}")
    print(f"Sampled sets: {template['meta']['sample_size']}")


if __name__ == "__main__":
    main()
