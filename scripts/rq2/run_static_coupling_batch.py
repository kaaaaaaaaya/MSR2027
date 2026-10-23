#!/usr/bin/env python3
"""RQ2: batch runner for the static coupling analysis.

Clones each target repository (shallow), runs static_coupling_pipeline.py on it,
and finally runs static_coupling_reclassify.py over all analyzed repositories to
produce <results_dir>/runtime_focused_summary.csv (shipped in this artifact as
data/rq2/static_coupling_summary.csv) and <results_dir>/batch_failures.csv
(shipped as data/rq2/not_analyzed_repositories.csv).

Target selection:
  --all-mining-repos   all repo_slug values in data/population/repo_ecosystem_activity.csv
                       (the 2,674-repository population used in the paper)
  --all-classified     union of repo_slug values in the RQ1 and preliminary classified tables
  --input/--combo      repositories of one ecosystem_combo in a CSV with repo_slug/ecosystem_combo

Usage (from the artifact root; cloning 2,674 repositories takes a long time):
  python3 scripts/rq2/run_static_coupling_batch.py --all-mining-repos \
      --repos-dir work/repos --results-dir work/results \
      --clone-timeout 1800 --analyze-timeout 3600
"""
from __future__ import annotations

import argparse
import csv
import os
import shutil
import subprocess
import sys
from pathlib import Path

csv.field_size_limit(sys.maxsize)

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]  # artifact root
DEFAULT_INPUT = ROOT / "data/population/repo_ecosystem_activity.csv"


def safe_name(slug: str) -> str:
    return slug.replace("/", "__")


def run(cmd, *, timeout=None, env=None):
    print("$", " ".join(map(str, cmd)), flush=True)
    return subprocess.run(cmd, cwd=ROOT, timeout=timeout, env=env)


def load_repos(path: Path, combo: str):
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            if row.get("ecosystem_combo") == combo:
                yield row["repo_slug"]


def load_repo_slugs_from_csv(path: Path):
    repos = set()
    if not path.exists():
        return repos
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            slug = row.get("repo_slug")
            if slug:
                repos.add(slug)
    return repos


def load_all_classified_repos(data_root: Path):
    candidates = [
        data_root / "rq1/maintenance_classified.csv",
        data_root / "preliminary/python_related_topics/python_related_classified.csv",
    ]
    repos = set()
    for path in candidates:
        repos |= load_repo_slugs_from_csv(path)
    return sorted(repos)


def load_all_mining_repos(data_root: Path):
    repos = load_repo_slugs_from_csv(data_root / "population/repo_ecosystem_activity.csv")
    if not repos:
        repos = load_repo_slugs_from_csv(data_root / "population/repo_package_map.csv")
    return sorted(repos)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--combo", default="crates+npm+pypi")
    ap.add_argument("--data-root", type=Path, default=ROOT / "data", help="artifact data/ directory")
    ap.add_argument("--all-classified", action="store_true", help="Use all unique repo_slug values from the RQ1 and preliminary classified tables")
    ap.add_argument("--all-mining-repos", action="store_true", help="Use all unique repo_slug values from population/repo_ecosystem_activity.csv (paper population)")
    ap.add_argument("--repos-dir", type=Path, default=ROOT / "work/repos")
    ap.add_argument("--results-dir", type=Path, default=ROOT / "work/results")
    ap.add_argument("--clone-timeout", type=int, default=300)
    ap.add_argument("--analyze-timeout", type=int, default=300)
    ap.add_argument("--skip-clone", action="store_true")
    args = ap.parse_args()

    if args.all_mining_repos:
        repos = load_all_mining_repos(args.data_root)
    elif args.all_classified:
        repos = load_all_classified_repos(args.data_root)
    else:
        repos = list(load_repos(args.input, args.combo))
    args.repos_dir.mkdir(parents=True, exist_ok=True)
    args.results_dir.mkdir(parents=True, exist_ok=True)

    analyzed = []
    failures = []
    env = dict(**__import__("os").environ)
    vendor = ROOT / ".vendor"  # optional: pip install --target .vendor tree-sitter-language-pack
    if vendor.exists():
        env["PYTHONPATH"] = str(vendor) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

    for slug in repos:
        name = safe_name(slug)
        repo_dir = args.repos_dir / name
        out_dir = args.results_dir / name
        if not args.skip_clone and not (repo_dir / ".git").exists():
            if repo_dir.exists():
                shutil.rmtree(repo_dir, ignore_errors=True)
            try:
                rc = run(["git", "clone", "--depth", "1", f"https://github.com/{slug}.git", str(repo_dir)], timeout=args.clone_timeout).returncode
            except subprocess.TimeoutExpired:
                failures.append({"repo_slug": slug, "stage": "clone_timeout", "returncode": 124})
                shutil.rmtree(repo_dir, ignore_errors=True)
                continue
            if rc != 0:
                failures.append({"repo_slug": slug, "stage": "clone", "returncode": rc})
                continue
        if (out_dir / "summary.json").exists():
            analyzed.append(name)
            continue
        try:
            rc = run([sys.executable, str(SCRIPT_DIR / "static_coupling_pipeline.py"), str(repo_dir), str(out_dir)], timeout=args.analyze_timeout, env=env).returncode
        except subprocess.TimeoutExpired:
            failures.append({"repo_slug": slug, "stage": "analyze_timeout", "returncode": 124})
            continue
        if rc != 0:
            failures.append({"repo_slug": slug, "stage": "analyze", "returncode": rc})
            continue
        analyzed.append(name)

    if analyzed:
        rc = run([sys.executable, str(SCRIPT_DIR / "static_coupling_reclassify.py"), str(args.results_dir), *analyzed]).returncode
        if rc != 0:
            failures.append({"repo_slug": "ALL", "stage": "runtime_reclassify", "returncode": rc})

    with (args.results_dir / "batch_failures.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["repo_slug", "stage", "returncode"])
        w.writeheader(); w.writerows(failures)

    print(f"Analyzed {len(analyzed)}/{len(repos)} repos; failures={len(failures)}")
    if failures:
        print(f"See {args.results_dir / 'batch_failures.csv'}")


if __name__ == "__main__":
    main()
