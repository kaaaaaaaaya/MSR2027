#!/usr/bin/env python3
"""RQ1: distribution of maintenance categories across ecosystem-facing sides.

Cross-tabulates the six-class maintenance-task category (Feature, Bug, Test
Cases, Refactoring, Documentation, Other; see classify_maintenance_categories.py)
with the ecosystem-side heuristic label (python_only, paired_only, both,
neither) for each artifact type and heuristic. This reproduces the paper table
"Distribution of Maintenance Activities by Maintenance Categories".

Input: the by-ecosystem/artifact/category tables written by
scripts/preliminary/ecosystem_side_labels.py. The collapse over ecosystems is
exact because label groups are disjoint within each
(ecosystem, artifact, category) cell.

Outputs:
  extension_by_artifact_category.csv/.md   long format, extension heuristic
  message_by_artifact_category.csv/.md     long format, message heuristic
  maintenance_category_by_heuristic.csv/.md  wide (paper-shaped) table

Usage (from the artifact root):
  python3 scripts/rq1/category_by_heuristic_tables.py \
      --labels-dir data/preliminary/ecosystem_side_labels --out-dir data/rq1
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path
from typing import Dict, List, Sequence

HEURISTICS = ["extension", "message"]
LABELS = ["python_only", "paired_only", "both", "neither"]
CATEGORIES = ["Bug", "Feature", "Documentation", "Test Cases", "Refactoring", "Other"]
ARTIFACTS = ["commit", "pull_request", "issue"]
FILE_ARTIFACTS = {"commit", "pull_request"}


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: Sequence[Dict[str, object]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def write_md(path: Path, rows: Sequence[Dict[str, object]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["| " + " | ".join(fields) + " |", "| " + " | ".join(["---"] * len(fields)) + " |"]
    for r in rows:
        lines.append("| " + " | ".join(str(r.get(f, "")) for f in fields) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def pct(n: int, d: int) -> str:
    return f"{100*n/d:.2f}" if d else "0.00"


def collapse(rows: List[Dict[str, str]], heuristic: str) -> List[Dict[str, object]]:
    counts: Counter = Counter()
    totals: Counter = Counter()
    for r in rows:
        key = (r["artifact_type"], r["category"])
        n = int(r["artifact_count"])
        counts[key + (r["label"],)] += n
        totals[key] += n
    out = []
    for art in ARTIFACTS:
        if heuristic == "extension" and art not in FILE_ARTIFACTS:
            continue
        for cat in CATEGORIES:
            key = (art, cat)
            if key not in totals:
                continue
            for lab in LABELS:
                n = counts[key + (lab,)]
                out.append({
                    "heuristic": heuristic, "artifact_type": art, "category": cat, "label": lab,
                    "eligible_artifacts": totals[key], "artifact_count": n, "percentage": pct(n, totals[key]),
                })
    return out


def widen(long_rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    cells: Dict[tuple, Dict[str, object]] = {}
    for r in long_rows:
        key = (r["heuristic"], r["artifact_type"], r["category"])
        cell = cells.setdefault(key, {
            "heuristic": r["heuristic"], "artifact_type": r["artifact_type"], "category": r["category"],
            "eligible": r["eligible_artifacts"],
        })
        cell[str(r["label"])] = r["artifact_count"]
        cell[f"{r['label']}_pct"] = r["percentage"]
    return list(cells.values())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels-dir", type=Path, default=Path("data/preliminary/ecosystem_side_labels"))
    ap.add_argument("--out-dir", type=Path, default=Path("data/rq1"))
    args = ap.parse_args()

    long_fields = ["heuristic", "artifact_type", "category", "label", "eligible_artifacts", "artifact_count", "percentage"]
    all_long: List[Dict[str, object]] = []
    for heuristic in HEURISTICS:
        src = args.labels_dir / f"{heuristic}_by_ecosystem_artifact_category.csv"
        long_rows = collapse(read_csv(src), heuristic)
        write_csv(args.out_dir / f"{heuristic}_by_artifact_category.csv", long_rows, long_fields)
        write_md(args.out_dir / f"{heuristic}_by_artifact_category.md", long_rows, long_fields)
        all_long.extend(long_rows)

    wide = widen(all_long)
    wide_fields = ["heuristic", "artifact_type", "category", "eligible"]
    for lab in LABELS:
        wide_fields += [lab, f"{lab}_pct"]
    write_csv(args.out_dir / "maintenance_category_by_heuristic.csv", wide, wide_fields)
    write_md(args.out_dir / "maintenance_category_by_heuristic.md", wide, wide_fields)
    print(f"Wrote RQ1 maintenance-category tables to {args.out_dir}")


if __name__ == "__main__":
    main()
