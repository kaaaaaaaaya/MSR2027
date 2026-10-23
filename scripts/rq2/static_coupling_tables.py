#!/usr/bin/env python3
"""RQ2: static coupling distribution tables.

Aggregates the repository-level static-coupling verdicts produced by
static_coupling_reclassify.py (data/rq2/static_coupling_summary.csv) together
with the repositories that could not be cloned (data/rq2/not_analyzed_repositories.csv)
over the common population (data/population/repo_ecosystem_activity.csv).

Verdict names used by the pipeline map onto the paper's classification labels:

  runtime-likely-independent               -> No Detected Runtime Coupling
  build-coupled-runtime-likely-independent -> Build/Package-Time Coupling
  runtime-independent-if-packaged          -> Potential Runtime Loading
  runtime-coupled-candidate                -> Potential External Runtime Coupling
  (not in summary; clone failed)           -> Not Analyzed

Outputs:
  static_coupling_summary_labeled.csv   summary with an added paper_classification column
  static_coupling_distribution.csv/.md  paper table "Static Coupling Distribution"
  static_coupling_by_ecosystem.csv/.md  paper table "Static Coupling by Ecosystem"

Usage (from the artifact root):
  python3 scripts/rq2/static_coupling_tables.py
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Sequence

VERDICT_TO_PAPER = {
    "runtime-likely-independent": "No Detected Runtime Coupling",
    "build-coupled-runtime-likely-independent": "Build/Package-Time Coupling",
    "runtime-independent-if-packaged": "Potential Runtime Loading",
    "runtime-coupled-candidate": "Potential External Runtime Coupling",
    "not_analyzed": "Not Analyzed",
}
ORDER = [
    "runtime-likely-independent",
    "build-coupled-runtime-likely-independent",
    "runtime-independent-if-packaged",
    "runtime-coupled-candidate",
    "not_analyzed",
]
COLUMN = {
    "runtime-likely-independent": "no_detected_runtime_coupling",
    "build-coupled-runtime-likely-independent": "build_package_time_coupling",
    "runtime-independent-if-packaged": "potential_runtime_loading",
    "runtime-coupled-candidate": "potential_external_runtime_coupling",
    "not_analyzed": "not_analyzed",
}


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--population", type=Path, default=Path("data/population/repo_ecosystem_activity.csv"))
    ap.add_argument("--summary", type=Path, default=Path("data/rq2/static_coupling_summary.csv"))
    ap.add_argument("--not-analyzed", type=Path, default=Path("data/rq2/not_analyzed_repositories.csv"))
    ap.add_argument("--out-dir", type=Path, default=Path("data/rq2"))
    args = ap.parse_args()

    population = read_csv(args.population)
    eco_of = {r["repo_slug"]: r["ecosystem_combo"] for r in population}
    summary = read_csv(args.summary)
    verdict_of = {r["repo"].replace("__", "/"): r["runtime_focused_verdict"] for r in summary}
    not_analyzed = {r["repo_slug"] for r in read_csv(args.not_analyzed)}

    unknown = {v for v in verdict_of.values() if v not in VERDICT_TO_PAPER}
    if unknown:
        raise SystemExit(f"Unknown verdict values: {sorted(unknown)}")
    missing = [s for s in eco_of if s not in verdict_of and s not in not_analyzed]
    if missing:
        raise SystemExit(f"{len(missing)} population repositories have neither a verdict nor a clone failure, e.g. {missing[:5]}")

    labeled = []
    for r in summary:
        rr = dict(r)
        rr["repo_slug"] = r["repo"].replace("__", "/")
        rr["ecosystem_combo"] = eco_of.get(rr["repo_slug"], "")
        rr["paper_classification"] = VERDICT_TO_PAPER[r["runtime_focused_verdict"]]
        labeled.append(rr)
    write_csv(args.out_dir / "static_coupling_summary_labeled.csv", labeled,
              ["repo_slug", "ecosystem_combo", "paper_classification", "runtime_focused_verdict",
               "runtime_focused_reason", "static_source_build_verdict", "runtime_phase_counts"])

    overall: Counter = Counter()
    by_eco: Dict[str, Counter] = defaultdict(Counter)
    for slug, eco in eco_of.items():
        v = verdict_of.get(slug, "not_analyzed")
        overall[v] += 1
        by_eco[eco][v] += 1
    n_pop = len(eco_of)
    n_analyzed = n_pop - overall["not_analyzed"]

    dist = []
    for v in ORDER:
        n = overall[v]
        dist.append({
            "classification": VERDICT_TO_PAPER[v], "pipeline_verdict": v, "count": n,
            "pct_of_all_mapped_repos": pct(n, n_pop),
            "pct_of_analyzed_repos": pct(n, n_analyzed) if v != "not_analyzed" else "",
        })
    dist_fields = ["classification", "pipeline_verdict", "count", "pct_of_all_mapped_repos", "pct_of_analyzed_repos"]
    write_csv(args.out_dir / "static_coupling_distribution.csv", dist, dist_fields)
    write_md(args.out_dir / "static_coupling_distribution.md", dist, dist_fields)

    eco_rows = []
    for eco in sorted(by_eco):
        rec = {"ecosystem_combo": eco, "population": sum(by_eco[eco].values())}
        for v in ORDER:
            rec[COLUMN[v]] = by_eco[eco][v]
        eco_rows.append(rec)
    eco_fields = ["ecosystem_combo", "population"] + [COLUMN[v] for v in ORDER]
    write_csv(args.out_dir / "static_coupling_by_ecosystem.csv", eco_rows, eco_fields)
    write_md(args.out_dir / "static_coupling_by_ecosystem.md", eco_rows, eco_fields)

    print(f"Population {n_pop}; analyzed {n_analyzed}; not analyzed {overall['not_analyzed']}")
    for d in dist:
        print(f"  {d['classification']}: {d['count']} ({d['pct_of_all_mapped_repos']}% of all; {d['pct_of_analyzed_repos']}% of analyzed)")


if __name__ == "__main__":
    main()
