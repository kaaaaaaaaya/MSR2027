#!/usr/bin/env python3
"""Preliminary study: rule-based maintenance topics among Python-related artifacts.

Step 1 - select Python-related artifacts from the classified maintenance records.
An artifact is Python-related when either
  * the extension heuristic indicates Python (changed files include Python files;
    commits and pull requests only), or
  * the message heuristic indicates Python (artifact text matches PY_RE).
An artifact matching both signals is counted once (22,764 records in the paper).

Step 2 - assign one of seven maintenance topics with a deterministic,
single-label rule set applied in priority order over artifact text plus
file-path evidence. The first matching rule group is the primary topic;
records matching no rule fall into "Other Python Maintenance". The complete
rule list is the RULES table below (this is the rule list referenced in the
paper). This seven-topic schema is distinct from the six-class maintenance-task
taxonomy used for RQ1 (scripts/rq1/classify_maintenance_categories.py).

Outputs:
  python_related_classified.csv      one row per Python-related artifact
  topic_distribution.csv/.md         paper Table "Rule-based maintenance topics
                                     among Python-related artifacts"
  topic_distribution_by_repo.csv     repository-level topic counts

Usage (from the artifact root):
  python3 scripts/preliminary/python_related_topics.py \
      --input data/rq1/maintenance_classified.csv \
      --out-dir data/preliminary/python_related_topics
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

csv.field_size_limit(sys.maxsize)

FILE_ARTIFACTS = {"commit", "pull_request"}

PY_RE = re.compile(r"(?i)(\bpython(?:2|3)?\b|\bpytest\b|\bpip\b|\bpyo3\b|\bpybind(?:11)?\b|(?<![A-Za-z0-9_./-])[A-Za-z0-9_./-]+\.py(?![A-Za-z0-9_./-])|\bsetup\.py\b|\bpyproject\.toml\b|\brequirements\.txt\b|\btox\.ini\b)")

TOPICS = [
    "Dependency/Packaging",
    "API Evolution",
    "Runtime/Error Handling",
    "Compatibility",
    "Documentation/Configuration",
    "Testing/CI",
    "Other Python Maintenance",
]

# Priority-ordered rule set. The first topic with any matching pattern wins.
RULES: List[Tuple[str, List[re.Pattern[str]]]] = [
    ("Dependency/Packaging", [
        re.compile(p, re.I) for p in [
            r"\bdependenc(?:y|ies)\b", r"\bpackage\b", r"\bpackaging\b", r"\bpip\b", r"\bpoetry\b",
            r"\bsetuptools\b", r"\bwheel\b", r"\bbuild\b", r"\brelease\b", r"\bversion\b", r"\bbump\b",
            r"\brequirements\.txt\b", r"\bsetup\.py\b", r"\bpyproject\.toml\b", r"\bsetup\.cfg\b",
            r"\bmanifest\.in\b", r"\bconda\b", r"\bvirtualenv\b", r"\bvenv\b",
        ]
    ]),
    ("API Evolution", [
        re.compile(p, re.I) for p in [
            r"\bapi\b", r"\binterface\b", r"\bendpoint\b", r"\bargument\b", r"\bparameter\b", r"\boption\b",
            r"\bfunction\b", r"\bmethod\b", r"\bclass\b", r"\bsignature\b", r"\brename\b", r"\bdeprecat",
            r"\bremove\b", r"\badd\b", r"\bsupport\b", r"\bexpose\b", r"\bpublic\b",
        ]
    ]),
    ("Runtime/Error Handling", [
        re.compile(p, re.I) for p in [
            r"\berror\b", r"\bexception\b", r"\btraceback\b", r"\bcrash\b", r"\bfail(?:ure|ed|ing)?\b",
            r"\bbug\b", r"\bfix\b", r"\bhang\b", r"\btimeout\b", r"\bruntime\b", r"\bimporterror\b",
            r"\btypeerror\b", r"\bvalueerror\b", r"\bkeyerror\b", r"\battributeerror\b", r"\bwarning\b",
        ]
    ]),
    ("Compatibility", [
        re.compile(p, re.I) for p in [
            r"\bcompat(?:ibility|ible)?\b", r"\bpython\s*2\b", r"\bpython\s*3\b", r"\bpy2\b", r"\bpy3\b",
            r"\bpy\d+(?:\.\d+)?\b", r"\b3\.\d+\b", r"\b2\.7\b", r"\bplatform\b", r"\bwindows\b",
            r"\blinux\b", r"\bmacos\b", r"\bosx\b", r"\bdeprecated\b", r"\bmigration\b", r"\bport\b",
        ]
    ]),
    ("Documentation/Configuration", [
        re.compile(p, re.I) for p in [
            r"\bdoc(?:s|umentation)?\b", r"\breadme\b", r"\bexample\b", r"\btutorial\b", r"\bguide\b",
            r"\bconfig(?:uration)?\b", r"\bsettings?\b", r"\byaml\b", r"\byml\b", r"\bjson\b", r"\bini\b",
            r"\btoml\b", r"\b\.md\b", r"\b\.rst\b", r"\b\.yaml\b", r"\b\.yml\b", r"\b\.json\b",
        ]
    ]),
    ("Testing/CI", [
        re.compile(p, re.I) for p in [
            r"\btest(?:s|ing)?\b", r"\bpytest\b", r"\bunittest\b", r"\bci\b", r"\bcontinuous integration\b",
            r"\bgithub actions\b", r"\bworkflow\b", r"\btox\b", r"\bcoverage\b", r"\bflake8\b", r"\blint\b",
        ]
    ]),
]


def read_rows(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if "pypi" in " ".join([r.get("ecosystem_combo", ""), r.get("target_ecosystems", ""), r.get("pypi_names", "")]).lower()]


def artifact_text(row: Dict[str, str]) -> str:
    """Message/body text only; used for the message-based Python signal."""
    return "\n".join([row.get("message", ""), row.get("description", "")])


def classification_text(row: Dict[str, str]) -> str:
    """Text plus file names; used only to assign the topic after selection."""
    return "\n".join([row.get("message", ""), row.get("description", ""), row.get("file_names", ""), row.get("inferred_file_names", "")])


def ext_python(row: Dict[str, str]) -> bool:
    return row.get("artifact_type") in FILE_ARTIFACTS and "Python" in [x for x in row.get("all_languages", "").split(";") if x]


def msg_python(row: Dict[str, str]) -> bool:
    return bool(PY_RE.search(artifact_text(row)))


def signal_source(row: Dict[str, str]) -> str:
    e, m = ext_python(row), msg_python(row)
    if e and m:
        return "both_extension_and_message"
    if e:
        return "extension_only"
    if m:
        return "message_only"
    return "not_python_related"


def classify_topics(row: Dict[str, str]) -> Tuple[str, List[str], str]:
    t = classification_text(row)
    matches: List[str] = []
    evidence: List[str] = []
    for topic, pats in RULES:
        for pat in pats:
            if pat.search(t):
                matches.append(topic)
                evidence.append(f"{topic}:{pat.pattern}")
                break
    if not matches:
        matches = ["Other Python Maintenance"]
    return matches[0], matches, "; ".join(evidence)


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


def summarize(rows: List[Dict[str, object]], group_cols: Sequence[str]) -> List[Dict[str, object]]:
    counts: Counter = Counter()
    totals: Counter = Counter()
    repos = defaultdict(set)
    for r in rows:
        base = tuple(str(r.get(c, "")) for c in group_cols)
        topic = str(r["primary_topic"])
        counts[base + (topic,)] += 1
        totals[base] += 1
        repos[base + (topic,)].add(str(r.get("repo_slug", "")))
    out = []
    for base in sorted(totals):
        for topic in TOPICS:
            n = counts[base + (topic,)]
            if n == 0 and group_cols:
                continue
            rec = dict(zip(group_cols, base))
            rec.update({
                "primary_topic": topic,
                "total_python_related": totals[base],
                "artifact_count": n,
                "percentage": pct(n, totals[base]),
                "repo_count": len([x for x in repos[base + (topic,)] if x]),
            })
            out.append(rec)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path, default=Path("data/rq1/maintenance_classified.csv"))
    ap.add_argument("--out-dir", type=Path, default=Path("data/preliminary/python_related_topics"))
    args = ap.parse_args()

    selected: List[Dict[str, object]] = []
    for r in read_rows(args.input):
        src = signal_source(r)
        if src == "not_python_related":
            continue
        primary, labels, evidence = classify_topics(r)
        out = dict(r)
        out.update({
            "python_signal_source": src,
            "primary_topic": primary,
            "all_matched_topics": ";".join(labels),
            "matched_rules": evidence,
        })
        selected.append(out)

    detail_fields = [
        "ecosystem_combo", "repo_slug", "artifact_type", "category", "python_signal_source",
        "primary_topic", "all_matched_topics", "message", "description", "file_names", "inferred_file_names",
        "commit_sha", "pr_number", "issue_number", "source_file",
    ]
    write_csv(args.out_dir / "python_related_classified.csv", selected, detail_fields)

    overall = summarize(selected, [])
    fields = ["primary_topic", "total_python_related", "artifact_count", "percentage", "repo_count"]
    write_csv(args.out_dir / "topic_distribution.csv", overall, fields)
    write_md(args.out_dir / "topic_distribution.md", overall, fields)

    by_repo = summarize(selected, ["ecosystem_combo", "repo_slug"])
    write_csv(args.out_dir / "topic_distribution_by_repo.csv", by_repo, ["ecosystem_combo", "repo_slug"] + fields)

    print(f"Python-related artifacts: {len(selected)}; wrote tables to {args.out_dir}")


if __name__ == "__main__":
    main()
