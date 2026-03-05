from __future__ import annotations

import argparse
import json
from pathlib import Path


def pct(n: int, d: int) -> float:
    return round((n / d * 100.0), 2) if d else 0.0


def build_report(pred: dict) -> dict:
    overall = {
        "documents": 0,
        "sets": 0,
        "components": 0,
        "mfr_null": 0,
        "finish_null": 0,
        "catalog_null": 0,
        "suspicious_set_spans": 0,
    }

    per_doc = []
    for doc in pred.get("documents", []):
        sets = doc.get("hardware_sets", [])
        c_total = 0
        mfr_null = 0
        finish_null = 0
        catalog_null = 0
        suspicious = 0

        for s in sets:
            loc = s.get("location") or {}
            if (loc.get("page_end", 0) - loc.get("page_start", 0)) > 20:
                suspicious += 1
            for c in s.get("components", []):
                c_total += 1
                mfr_null += c.get("mfr") is None
                finish_null += c.get("finish") is None
                catalog_null += c.get("catalog_number") is None

        per_doc.append(
            {
                "doc_path": doc.get("doc_path"),
                "sets": len(sets),
                "components": c_total,
                "avg_components_per_set": round(c_total / len(sets), 2) if sets else 0.0,
                "mfr_null_pct": pct(mfr_null, c_total),
                "finish_null_pct": pct(finish_null, c_total),
                "catalog_null_pct": pct(catalog_null, c_total),
                "suspicious_set_spans": suspicious,
            }
        )

        overall["documents"] += 1
        overall["sets"] += len(sets)
        overall["components"] += c_total
        overall["mfr_null"] += mfr_null
        overall["finish_null"] += finish_null
        overall["catalog_null"] += catalog_null
        overall["suspicious_set_spans"] += suspicious

    report = {
        "overall": {
            "documents": overall["documents"],
            "sets": overall["sets"],
            "components": overall["components"],
            "mfr_null_pct": pct(overall["mfr_null"], overall["components"]),
            "finish_null_pct": pct(overall["finish_null"], overall["components"]),
            "catalog_null_pct": pct(overall["catalog_null"], overall["components"]),
            "suspicious_set_spans": overall["suspicious_set_spans"],
        },
        "per_document": per_doc,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build quality summary for extraction output")
    parser.add_argument("--pred", required=True, help="Path to prediction JSON")
    parser.add_argument("--out", required=True, help="Path to quality report JSON")
    args = parser.parse_args()

    pred = json.loads(Path(args.pred).read_text(encoding="utf-8"))
    report = build_report(pred)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report["overall"], indent=2))
    print(f"Wrote quality report: {out_path}")


if __name__ == "__main__":
    main()
