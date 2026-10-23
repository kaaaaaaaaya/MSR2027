#!/usr/bin/env python3
"""Preliminary study: dataset summary by ecosystem pairing.

Aggregates the repository population (data/population/repo_ecosystem_activity.csv)
into the paper table "Summary Dataset": number of GitHub repositories, issues,
pull requests, PR-linked commits, and issue--commit links per PyPI
cross-ecosystem pairing, plus the total row.

Usage (from the artifact root):
  python3 scripts/preliminary/dataset_summary.py
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

ORDER = ["npm+pypi", "crates+pypi", "crates+npm+pypi", "maven+pypi"]
LABEL = {
    "npm+pypi": "npm (JavaScript/TypeScript)",
    "crates+pypi": "Crates.io (Rust)",
    "crates+npm+pypi": "npm + Crates.io (JavaScript/TypeScript/Rust)",
    "maven+pypi": "Maven (Java)",
}
METRICS = ["issues", "pull_requests", "pr_commits", "issue_commit_links"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--population", type=Path, default=Path("data/population/repo_ecosystem_activity.csv"))
    ap.add_argument("--out", type=Path, default=Path("data/population/dataset_summary_by_ecosystem.csv"))
    args = ap.parse_args()

    repos: Counter = Counter()
    sums = defaultdict(Counter)
    with args.population.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            eco = r["ecosystem_combo"]
            repos[eco] += 1
            for m in METRICS:
                sums[eco][m] += int(r.get(m) or 0)

    rows = []
    for eco in ORDER + sorted(set(repos) - set(ORDER)):
        if eco not in repos:
            continue
        rows.append({"ecosystem_combo": eco, "paper_label": LABEL.get(eco, eco), "github_repos": repos[eco], **{m: sums[eco][m] for m in METRICS}})
    rows.append({"ecosystem_combo": "total", "paper_label": "Total", "github_repos": sum(repos.values()), **{m: sum(s[m] for s in sums.values()) for m in METRICS}})

    fields = ["ecosystem_combo", "paper_label", "github_repos"] + METRICS
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    md = ["| " + " | ".join(fields) + " |", "| " + " | ".join(["---"] * len(fields)) + " |"]
    md += ["| " + " | ".join(str(r[c]) for c in fields) + " |" for r in rows]
    args.out.with_suffix(".md").write_text("\n".join(md) + "\n", encoding="utf-8")
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
