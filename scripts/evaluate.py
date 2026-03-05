from __future__ import annotations

import argparse
import json
from pathlib import Path


SCORABLE_FIELDS = ["qty", "catalog_number", "mfr", "finish"]


def norm(v):
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s.upper() if s else None
    return str(v).strip().upper()


def index_predictions(pred: dict) -> dict:
    idx = {}
    for doc in pred.get("documents", []):
        doc_path = doc.get("doc_path")
        for s in doc.get("hardware_sets", []):
            key = (doc_path, str(s.get("set_number")))
            idx[key] = s
    return idx


def evaluate(pred: dict, gold: dict) -> dict:
    pred_idx = index_predictions(pred)

    total_sets = 0
    matched_sets = 0

    field_total = {f: 0 for f in SCORABLE_FIELDS}
    field_correct = {f: 0 for f in SCORABLE_FIELDS}

    for sample in gold.get("samples", []):
        total_sets += 1
        key = (sample.get("doc_path"), str(sample.get("set_number")))
        pred_set = pred_idx.get(key)
        if pred_set is None:
            continue

        matched_sets += 1
        pred_components = pred_set.get("components", [])
        gold_components = sample.get("gold_components", [])

        n = min(len(pred_components), len(gold_components))
        for i in range(n):
            pc = pred_components[i]
            gc = gold_components[i]
            for f in SCORABLE_FIELDS:
                gv = norm(gc.get(f))
                if gv is None:
                    continue
                field_total[f] += 1
                if norm(pc.get(f)) == gv:
                    field_correct[f] += 1

    set_recall = matched_sets / total_sets if total_sets else 0.0
    field_acc = {
        f: (field_correct[f] / field_total[f] if field_total[f] else 0.0)
        for f in SCORABLE_FIELDS
    }

    return {
        "set_recall_on_sample": round(set_recall, 4),
        "sampled_sets": total_sets,
        "matched_sets": matched_sets,
        "field_accuracy": {k: round(v, 4) for k, v in field_acc.items()},
        "field_counts": {
            f: {"correct": field_correct[f], "total": field_total[f]} for f in SCORABLE_FIELDS
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate predictions against a small gold sample")
    parser.add_argument("--pred", required=True, help="Path to prediction JSON")
    parser.add_argument("--gold", required=True, help="Path to annotated template JSON")
    parser.add_argument("--out", required=False, help="Optional output JSON report path")
    args = parser.parse_args()

    pred = json.loads(Path(args.pred).read_text(encoding="utf-8"))
    gold = json.loads(Path(args.gold).read_text(encoding="utf-8"))

    report = evaluate(pred, gold)
    print(json.dumps(report, indent=2))

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote report: {out_path}")


if __name__ == "__main__":
    main()
