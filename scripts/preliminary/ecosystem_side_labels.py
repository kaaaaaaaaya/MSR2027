#!/usr/bin/env python3
"""Preliminary study: ecosystem-side heuristic labels for maintenance artifacts.

Assigns each maintenance artifact (commit, pull request, issue) one of four
ecosystem-side labels, separately for two heuristics:

  * extension heuristic  - changed-file paths (commits and pull requests only)
  * message heuristic    - artifact text (commits, issues, pull requests)

Labels:
  python_only       the artifact matches Python-specific heuristics only
  paired_only       the artifact matches paired-ecosystem heuristics only
  both              the artifact matches Python and at least one paired ecosystem
  neither           the artifact matches none of the configured heuristics

Paired-ecosystem language sets:
  npm+pypi         -> JavaScript, TypeScript
  crates+pypi      -> Rust
  maven+pypi       -> Java
  crates+npm+pypi  -> Rust, JavaScript, TypeScript

Produces (per heuristic) the overall table, the by-ecosystem table reported in
the paper (Table "Ecosystem-side heuristic labels by ecosystem pairing"), the
by-ecosystem/artifact/category table consumed by scripts/rq1, and a by-repository
table.

Usage (from the artifact root):
  python3 scripts/preliminary/ecosystem_side_labels.py \
      --input data/rq1/maintenance_classified.csv \
      --out-dir data/preliminary/ecosystem_side_labels
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Sequence, Set

csv.field_size_limit(sys.maxsize)

FILE_ARTIFACTS = {"commit", "pull_request"}
HEURISTICS = ["extension", "message"]
LABELS = ["python_only", "paired_only", "both", "neither"]

COUNTERPART_LANGS = {
    "npm+pypi": {"JavaScript", "TypeScript"},
    "crates+pypi": {"Rust"},
    "maven+pypi": {"Java"},
    "crates+npm+pypi": {"Rust", "JavaScript", "TypeScript"},
}

# Message-heuristic keyword/filename patterns (see paper footnote).
PY_RE = re.compile(r"(?i)(\bpython(?:2|3)?\b|\bpytest\b|\bpip\b|\bpyo3\b|\bpybind(?:11)?\b|(?<![A-Za-z0-9_./-])[A-Za-z0-9_./-]+\.py(?![A-Za-z0-9_./-])|\bsetup\.py\b|\bpyproject\.toml\b|\brequirements\.txt\b|\btox\.ini\b)")
JS_RE = re.compile(r"(?i)(\bjavascript\b|\btypescript\b|\bnode\.js\b|\bnodejs\b|\bnpm\b|\byarn\b|\bpnpm\b|\bpackage\.json\b|\bpackage-lock\.json\b|\byarn\.lock\b|\bpnpm-lock\.yaml\b|(?<![A-Za-z0-9_./-])[A-Za-z0-9_./-]+\.(js|jsx|ts|tsx)(?![A-Za-z0-9_./-]))")
RUST_RE = re.compile(r"(?i)(\brust\b|\bcargo\b|\bcrates?\b|\bcrate\b|\bcargo\.toml\b|\bcargo\.lock\b|(?<![A-Za-z0-9_./-])[A-Za-z0-9_./-]+\.rs(?![A-Za-z0-9_./-]))")
JAVA_RE = re.compile(r"(?i)(\bjava\b|\bmaven\b|\bgradle\b|\bpom\.xml\b|\bbuild\.gradle\b|(?<![A-Za-z0-9_./-])[A-Za-z0-9_./-]+\.java(?![A-Za-z0-9_./-]))")


def read_rows(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if "pypi" in " ".join([r.get("ecosystem_combo", ""), r.get("target_ecosystems", ""), r.get("pypi_names", "")]).lower()]


def file_langs(row: Dict[str, str]) -> Set[str]:
    return {x for x in row.get("all_languages", "").split(";") if x}


def text(row: Dict[str, str]) -> str:
    return "\n".join([row.get("message", ""), row.get("description", "")])


def msg_python(row: Dict[str, str]) -> bool:
    return bool(PY_RE.search(text(row)))


def msg_counterpart(row: Dict[str, str]) -> bool:
    eco = row.get("ecosystem_combo", "")
    t = text(row)
    found = False
    if "npm" in eco:
        found = found or bool(JS_RE.search(t))
    if "crates" in eco:
        found = found or bool(RUST_RE.search(t))
    if "maven" in eco:
        found = found or bool(JAVA_RE.search(t))
    return found


def label(py: bool, cp: bool) -> str:
    if py and cp:
        return "both"
    if py:
        return "python_only"
    if cp:
        return "paired_only"
    return "neither"


def extension_label(row: Dict[str, str]) -> str:
    langs = file_langs(row)
    return label("Python" in langs, bool(langs & COUNTERPART_LANGS.get(row.get("ecosystem_combo", ""), set())))


def message_label(row: Dict[str, str]) -> str:
    return label(msg_python(row), msg_counterpart(row))


def pct(n: int, d: int) -> str:
    return f"{100*n/d:.2f}" if d else "0.00"


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


def group_table(rows: List[Dict[str, str]], heuristic: str, group_cols: Sequence[str]) -> List[Dict[str, object]]:
    counts: Counter = Counter()
    totals: Counter = Counter()
    repos = defaultdict(set)
    for r in rows:
        if heuristic == "extension":
            if r.get("artifact_type") not in FILE_ARTIFACTS:
                continue
            lab = extension_label(r)
        else:
            lab = message_label(r)
        key = tuple(r.get(c, "") for c in group_cols)
        counts[key + (lab,)] += 1
        totals[key] += 1
        repos[key + (lab,)].add(r.get("repo_slug", ""))
    out = []
    for key in sorted(totals):
        for lab in LABELS:
            n = counts[key + (lab,)]
            rec = dict(zip(group_cols, key))
            rec.update({
                "heuristic": heuristic,
                "label": lab,
                "eligible_artifacts": totals[key],
                "artifact_count": n,
                "percentage": pct(n, totals[key]),
                "repo_count": len([x for x in repos[key + (lab,)] if x]),
            })
            out.append(rec)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path, default=Path("data/rq1/maintenance_classified.csv"))
    ap.add_argument("--out-dir", type=Path, default=Path("data/preliminary/ecosystem_side_labels"))
    args = ap.parse_args()

    rows = read_rows(args.input)
    specs = {
        "overall": [],
        "by_ecosystem": ["ecosystem_combo"],
        "by_ecosystem_artifact_category": ["ecosystem_combo", "artifact_type", "category"],
        "by_repo": ["ecosystem_combo", "repo_slug"],
    }
    for name, cols in specs.items():
        for heuristic in HEURISTICS:
            tab = group_table(rows, heuristic, cols)
            fields = list(cols) + ["heuristic", "label", "eligible_artifacts", "artifact_count", "percentage", "repo_count"]
            write_csv(args.out_dir / f"{heuristic}_{name}.csv", tab, fields)
            if name != "by_repo":
                write_md(args.out_dir / f"{heuristic}_{name}.md", tab, fields)
    print(f"Read {len(rows)} artifacts; wrote ecosystem-side label tables to {args.out_dir}")


if __name__ == "__main__":
    main()
