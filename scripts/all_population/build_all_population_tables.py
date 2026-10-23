#!/usr/bin/env python3
"""Build repository-level tables over the common population.

Population: all repo_slug values in data/population/repo_ecosystem_activity.csv
(2,674 mapped repositories). Repositories with no classified artifacts are kept
with zero counts, so every output has one row per population repository.

Inputs (artifact layout):
  data/population/repo_ecosystem_activity.csv
  data/rq1/maintenance_classified.csv                         RQ1 six-class categories
  data/preliminary/python_related_topics/python_related_classified.csv
                                                              preliminary seven-topic labels
  data/rq2/static_coupling_summary.csv                        RQ2 static-coupling verdicts

Outputs (data/all_population/):
  rq1_repo_level.csv                       per-repo maintenance-category counts
  preliminary_python_related_repo_level.csv per-repo Python-related topic counts
  all_population_combined.csv              one row per repo joining all sources
  all_population_summary.json/.md          coverage counts

Usage (from the artifact root):
  python3 scripts/all_population/build_all_population_tables.py --out-dir data/all_population
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)

RQ1_CATS = ["Bug", "Feature", "Documentation", "Test Cases", "Refactoring", "Other"]
TOPICS = [
    "Dependency/Packaging", "API Evolution", "Runtime/Error Handling", "Compatibility",
    "Documentation/Configuration", "Testing/CI", "Other Python Maintenance",
]
VERDICT_TO_PAPER = {
    "runtime-likely-independent": "No Detected Runtime Coupling",
    "build-coupled-runtime-likely-independent": "Build/Package-Time Coupling",
    "runtime-independent-if-packaged": "Potential Runtime Loading",
    "runtime-coupled-candidate": "Potential External Runtime Coupling",
    "not_analyzed": "Not Analyzed",
}


def read_csv(path: Path):
    if not path.exists():
        raise SystemExit(f"Missing input: {path}")
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def col(name: str) -> str:
    return name.replace("/", "_").replace(" ", "_")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--population", type=Path, default=Path("data/population/repo_ecosystem_activity.csv"))
    ap.add_argument("--rq1", type=Path, default=Path("data/rq1/maintenance_classified.csv"))
    ap.add_argument("--python-related", type=Path, default=Path("data/preliminary/python_related_topics/python_related_classified.csv"))
    ap.add_argument("--rq2-summary", type=Path, default=Path("data/rq2/static_coupling_summary.csv"))
    ap.add_argument("--out-dir", type=Path, default=Path("data/all_population"))
    args = ap.parse_args()

    pop_rows = read_csv(args.population)
    pop = [r["repo_slug"] for r in pop_rows]
    pop_meta = {r["repo_slug"]: r for r in pop_rows}

    rq1_counts = defaultdict(Counter)
    for r in read_csv(args.rq1):
        repo = r.get("repo_slug", "")
        if repo in pop_meta:
            rq1_counts[repo][r.get("category") or "Other"] += 1
            rq1_counts[repo]["__total__"] += 1

    topic_counts = defaultdict(Counter)
    for r in read_csv(args.python_related):
        repo = r.get("repo_slug", "")
        if repo in pop_meta:
            topic_counts[repo][r.get("primary_topic") or "Other Python Maintenance"] += 1
            topic_counts[repo]["__total__"] += 1

    rq2 = {r["repo"].replace("__", "/"): r for r in read_csv(args.rq2_summary)}

    rq1_out, topic_out, combined = [], [], []
    for repo in pop:
        meta = pop_meta[repo]
        eco = meta.get("ecosystem_combo", "")
        activity = {
            "mapped_total_activity_rows": meta.get("total_activity_rows", "0"),
            "mapped_issues": meta.get("issues", "0"),
            "mapped_pull_requests": meta.get("pull_requests", "0"),
            "mapped_pr_commits": meta.get("pr_commits", "0"),
            "mapped_issue_commit_links": meta.get("issue_commit_links", "0"),
        }

        r1 = {"repo_slug": repo, "ecosystem_combo": eco, **activity, "rq1_total_artifacts": rq1_counts[repo]["__total__"]}
        for c in RQ1_CATS:
            r1[f"rq1_{col(c)}"] = rq1_counts[repo][c]
        r1["rq1_no_observed_artifact"] = int(r1["rq1_total_artifacts"] == 0)
        rq1_out.append(r1)

        r2 = {"repo_slug": repo, "ecosystem_combo": eco, **activity, "python_related_total_artifacts": topic_counts[repo]["__total__"]}
        for k in TOPICS:
            r2[f"topic_{col(k)}"] = topic_counts[repo][k]
        r2["no_observed_python_related_artifact"] = int(r2["python_related_total_artifacts"] == 0)
        topic_out.append(r2)

        s = rq2.get(repo, {})
        verdict = s.get("runtime_focused_verdict", "not_analyzed")
        combined.append({
            "repo_slug": repo, "ecosystem_combo": eco, **activity,
            "rq1_total_artifacts": r1["rq1_total_artifacts"],
            "python_related_total_artifacts": r2["python_related_total_artifacts"],
            "rq2_static_source_build_verdict": s.get("static_source_build_verdict", "not_analyzed"),
            "rq2_verdict": verdict,
            "rq2_paper_classification": VERDICT_TO_PAPER.get(verdict, verdict),
            "rq2_reason": s.get("runtime_focused_reason", ""),
        })

    write_csv(args.out_dir / "rq1_repo_level.csv", rq1_out, list(rq1_out[0].keys()))
    write_csv(args.out_dir / "preliminary_python_related_repo_level.csv", topic_out, list(topic_out[0].keys()))
    write_csv(args.out_dir / "all_population_combined.csv", combined, list(combined[0].keys()))

    summary = {
        "population_repositories": len(pop),
        "repos_with_mined_activity_rows": sum(1 for r in combined if int(r["mapped_total_activity_rows"] or 0) > 0),
        "repos_with_zero_mined_activity_rows": sum(1 for r in combined if int(r["mapped_total_activity_rows"] or 0) == 0),
        "rq1_repos_with_classified_artifacts": sum(1 for r in rq1_out if r["rq1_total_artifacts"] > 0),
        "rq1_repos_with_zero_classified_artifacts": sum(1 for r in rq1_out if r["rq1_total_artifacts"] == 0),
        "preliminary_repos_with_python_related_artifacts": sum(1 for r in topic_out if r["python_related_total_artifacts"] > 0),
        "preliminary_repos_with_zero_python_related_artifacts": sum(1 for r in topic_out if r["python_related_total_artifacts"] == 0),
        "rq2_repos_analyzed": sum(1 for r in combined if r["rq2_verdict"] != "not_analyzed"),
        "rq2_repos_not_analyzed": sum(1 for r in combined if r["rq2_verdict"] == "not_analyzed"),
        "repos_with_mined_activity_but_zero_rq1_artifacts": sum(1 for r in combined if int(r["mapped_total_activity_rows"] or 0) > 0 and r["rq1_total_artifacts"] == 0),
        "repos_with_rq1_artifacts_but_zero_python_related_artifacts": sum(1 for r in combined if r["rq1_total_artifacts"] > 0 and r["python_related_total_artifacts"] == 0),
        "rq2_verdict_counts": dict(sorted(Counter(r["rq2_verdict"] for r in combined).items())),
        "rq2_paper_classification_counts": dict(sorted(Counter(r["rq2_paper_classification"] for r in combined).items())),
    }
    (args.out_dir / "all_population_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")

    md = [
        "# All-population repository-level tables", "",
        f"Population repositories: **{summary['population_repositories']}**", "",
        "## Data availability within the same population", "",
        "| Data source | repos meeting criterion | remaining repos |", "|---|---:|---:|",
        f"| Mined GitHub activity rows > 0 | {summary['repos_with_mined_activity_rows']} | {summary['repos_with_zero_mined_activity_rows']} |",
        f"| RQ1 classified maintenance artifacts > 0 | {summary['rq1_repos_with_classified_artifacts']} | {summary['rq1_repos_with_zero_classified_artifacts']} |",
        f"| Preliminary Python-related artifacts > 0 | {summary['preliminary_repos_with_python_related_artifacts']} | {summary['preliminary_repos_with_zero_python_related_artifacts']} |",
        f"| RQ2 static-coupling verdict available | {summary['rq2_repos_analyzed']} | {summary['rq2_repos_not_analyzed']} |",
        "", "## Zero-count diagnostics", "",
        f"- Repositories with zero mined GitHub activity rows: {summary['repos_with_zero_mined_activity_rows']}",
        f"- Repositories with mined activity rows but zero RQ1 classified artifacts: {summary['repos_with_mined_activity_but_zero_rq1_artifacts']}",
        f"- Repositories with RQ1 artifacts but zero Python-related artifacts: {summary['repos_with_rq1_artifacts_but_zero_python_related_artifacts']}",
        "", "## RQ2 static-coupling classification counts", "",
    ]
    for k, v in summary["rq2_paper_classification_counts"].items():
        md.append(f"- {k}: {v}")
    (args.out_dir / "all_population_summary.md").write_text("\n".join(md) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
