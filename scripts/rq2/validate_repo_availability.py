#!/usr/bin/env python3
"""RQ2 support: validate GitHub repository reachability for the common population.

Separates true zero-count cases from data-availability cases where the GitHub
repository is no longer reachable. It does not clone repositories; it uses
`git ls-remote --heads` as a lightweight reachability check. Repositories that
are not reachable are the "Not Analyzed" group of the RQ2 static coupling
analysis (424 repositories in the paper).

Outputs (data/repo_availability/):
  repo_availability.csv
  repo_availability_summary.json
  repo_availability_summary.md

Usage (from the artifact root; performs 2,674 network calls):
  python3 scripts/rq2/validate_repo_availability.py --data-root data \
      --rq2-results work/results --out-dir data/repo_availability
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Iterable, List, Set

csv.field_size_limit(sys.maxsize)


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def repo_set_from_csv(path: Path) -> Set[str]:
    return {r.get("repo_slug", "") for r in read_csv(path) if r.get("repo_slug")}


def safe_name(slug: str) -> str:
    return slug.replace("/", "__")


def classify_git_result(returncode: int | str, stderr: str) -> str:
    if returncode == "timeout":
        return "timeout"
    text = (stderr or "").lower()
    if returncode == 0:
        return "available"
    if "repository not found" in text or "not found" in text:
        return "not_found_or_private"
    if "could not resolve host" in text or "failed to connect" in text or "network is unreachable" in text:
        return "network_error"
    if "authentication failed" in text or "permission denied" in text or "access denied" in text:
        return "auth_or_permission"
    return "other_error"


def check_repo(slug: str, timeout: int) -> Dict[str, str]:
    url = f"https://github.com/{slug}.git"
    cmd = ["git", "ls-remote", "--heads", url]
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
        status = classify_git_result(p.returncode, p.stderr)
        return {
            "repo_slug": slug,
            "git_url": url,
            "availability_status": status,
            "returncode": str(p.returncode),
            "stderr_excerpt": (p.stderr or "").strip().replace("\n", " ")[:500],
        }
    except subprocess.TimeoutExpired as e:
        stderr = (e.stderr or "") if isinstance(e.stderr, str) else ""
        return {
            "repo_slug": slug,
            "git_url": url,
            "availability_status": "timeout",
            "returncode": "timeout",
            "stderr_excerpt": stderr.strip().replace("\n", " ")[:500],
        }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", type=Path, default=Path("data"), help="artifact data/ directory")
    ap.add_argument("--rq2-results", type=Path, default=Path("work/results"), help="per-repository results from run_static_coupling_batch.py")
    ap.add_argument("--out-dir", type=Path, default=Path("data/repo_availability"))
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    pop_rows = read_csv(args.data_root / "population/repo_ecosystem_activity.csv")
    if not pop_rows:
        raise SystemExit(f"No population rows found: {args.data_root / 'population/repo_ecosystem_activity.csv'}")

    rq1_repos = repo_set_from_csv(args.data_root / "rq1/maintenance_classified.csv")
    python_related_repos = repo_set_from_csv(args.data_root / "preliminary/python_related_topics/python_related_classified.csv")

    rq2_repos = set()
    if args.rq2_results.exists():
        rq2_repos = {p.name.replace("__", "/") for p in args.rq2_results.iterdir() if p.is_dir() and (p / "summary.json").exists()}
    else:
        summary_csv = args.data_root / "rq2/static_coupling_summary.csv"
        rq2_repos = {r.get("repo", "").replace("__", "/") for r in read_csv(summary_csv)}

    slugs = [r["repo_slug"] for r in pop_rows]
    meta = {r["repo_slug"]: r for r in pop_rows}

    checks: Dict[str, Dict[str, str]] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(check_repo, slug, args.timeout): slug for slug in slugs}
        done = 0
        for fut in as_completed(futs):
            row = fut.result()
            checks[row["repo_slug"]] = row
            done += 1
            if done % 100 == 0:
                print(f"checked {done}/{len(slugs)}", flush=True)

    out_rows = []
    for slug in slugs:
        m = meta[slug]
        c = checks[slug]
        total_activity = int(m.get("total_activity_rows") or 0)
        rq1 = slug in rq1_repos
        pyrel = slug in python_related_repos
        rq2 = slug in rq2_repos
        out_rows.append({
            "repo_slug": slug,
            "ecosystem_combo": m.get("ecosystem_combo", ""),
            "mapped_total_activity_rows": str(total_activity),
            "mapped_issues": m.get("issues", "0"),
            "mapped_pull_requests": m.get("pull_requests", "0"),
            "mapped_pr_commits": m.get("pr_commits", "0"),
            "mapped_issue_commit_links": m.get("issue_commit_links", "0"),
            "has_mined_activity": str(total_activity > 0),
            "has_rq1_classified_records": str(rq1),
            "has_python_related_records": str(pyrel),
            "has_rq2_static_summary": str(rq2),
            **c,
        })

    fields = [
        "repo_slug", "ecosystem_combo",
        "mapped_total_activity_rows", "mapped_issues", "mapped_pull_requests", "mapped_pr_commits", "mapped_issue_commit_links",
        "has_mined_activity", "has_rq1_classified_records", "has_python_related_records", "has_rq2_static_summary",
        "git_url", "availability_status", "returncode", "stderr_excerpt",
    ]
    out_csv = args.out_dir / "repo_availability.csv"
    with out_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(out_rows)

    by_status = Counter(r["availability_status"] for r in out_rows)
    summary = {
        "population_repositories": len(out_rows),
        "availability_status_counts": dict(by_status),
        "available_repositories": by_status.get("available", 0),
        "unavailable_or_problem_repositories": len(out_rows) - by_status.get("available", 0),
        "available_with_zero_mined_activity": sum(1 for r in out_rows if r["availability_status"] == "available" and r["has_mined_activity"] == "False"),
        "available_with_mined_activity": sum(1 for r in out_rows if r["availability_status"] == "available" and r["has_mined_activity"] == "True"),
        "unavailable_with_zero_mined_activity": sum(1 for r in out_rows if r["availability_status"] != "available" and r["has_mined_activity"] == "False"),
        "unavailable_with_mined_activity": sum(1 for r in out_rows if r["availability_status"] != "available" and r["has_mined_activity"] == "True"),
        "available_with_zero_rq1_classified_records": sum(1 for r in out_rows if r["availability_status"] == "available" and r["has_rq1_classified_records"] == "False"),
        "available_with_zero_python_related_records": sum(1 for r in out_rows if r["availability_status"] == "available" and r["has_python_related_records"] == "False"),
        "available_without_rq2_static_summary": sum(1 for r in out_rows if r["availability_status"] == "available" and r["has_rq2_static_summary"] == "False"),
        "unavailable_without_rq2_static_summary": sum(1 for r in out_rows if r["availability_status"] != "available" and r["has_rq2_static_summary"] == "False"),
    }
    (args.out_dir / "repo_availability_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    md = [
        "# Repository availability validation",
        "",
        f"Population repositories: **{summary['population_repositories']}**",
        "",
        "## Git availability status",
        "",
        "| Status | Repositories |",
        "|---|---:|",
    ]
    for k, v in sorted(by_status.items()):
        md.append(f"| {k} | {v} |")
    md += [
        "",
        "## Cross-checks",
        "",
        f"- Available repositories with mined GitHub activity rows > 0: {summary['available_with_mined_activity']}",
        f"- Available repositories with zero mined GitHub activity rows: {summary['available_with_zero_mined_activity']}",
        f"- Unavailable/problem repositories with zero mined GitHub activity rows: {summary['unavailable_with_zero_mined_activity']}",
        f"- Unavailable/problem repositories with mined GitHub activity rows > 0: {summary['unavailable_with_mined_activity']}",
        f"- Available repositories with zero RQ1-classified records: {summary['available_with_zero_rq1_classified_records']}",
        f"- Available repositories with zero preliminary Python-related records: {summary['available_with_zero_python_related_records']}",
        f"- Available repositories without RQ2 static-coupling summary: {summary['available_without_rq2_static_summary']}",
        f"- Unavailable/problem repositories without RQ2 static-coupling summary: {summary['unavailable_without_rq2_static_summary']}",
    ]
    (args.out_dir / "repo_availability_summary.md").write_text("\n".join(md))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
