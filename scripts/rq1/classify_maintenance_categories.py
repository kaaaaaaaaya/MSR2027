#!/usr/bin/env python3
"""RQ1: maintenance-task classification of mined GitHub artifacts.

Classifies commit messages, issue title/body, and pull-request title/body into
the six maintenance-task categories of Wattanakriengkrai et al. (FSE 2022):
  Feature, Bug, Test Cases, Refactoring, Documentation, Other
using the keyword rule set in CATEGORIES below (this is the full keyword listing
referenced in the paper). Rule precedence: a changed/mentioned Markdown file
-> Documentation; JSON-only file changes -> Other; otherwise the first category
in KEYWORD_ORDER with a keyword match; no match -> Other.

The script also derives the changed-file language/file-type context used by the
extension heuristic (language_combo, all_languages, file_type_combo,
all_file_types) from file extensions and file names.

Input: the raw GitHub-mining worker CSVs (workers/*/{issues,pull_requests,pr_commits}.csv)
collected with the GitHub REST API. These raw files are not part of this
artifact; the script's classified output is shipped as
data/rq1/maintenance_classified.csv (128,570 records). issue_commit_links.csv is
excluded because it is a derived link table, not an independent artifact source.

Usage:
  python3 scripts/rq1/classify_maintenance_categories.py --help
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

CATEGORIES: Dict[str, List[str]] = {
    "Feature": [
        "integrate", "add", "feat", "update", "upgrade", "support",
        "dependency", "feature", "improve", "version", "automate",
        "compatibility", "bundle", "improvement", "bump",
    ],
    "Bug": [
        "avoid", "fix", "resolve", "close", "bug", "solve", "solution",
        "issue", "fixing",
    ],
    "Test Cases": [
        "test case", "test", "unit test", "CI", "continuous integration",
    ],
    "Refactoring": [
        "remove", "unnecessary", "refactor", "performance", "optimise",
    ],
    "Documentation": ["documentation", "doc"],
}

# Precedence when keyword matches overlap. Documentation / JSON-only file rules
# are handled before keyword rules.
KEYWORD_ORDER = ["Bug", "Test Cases", "Refactoring", "Feature", "Documentation"]

SUMMARY_INPUTS = [
    ("commit", "github-mining-summary/all_pr_commits_list.csv"),
    ("issue", "github-mining-summary/all_issues_list.csv"),
    ("pull_request", "github-mining-summary/all_pull_requests_list.csv"),
]

RQ1_WORKER_FILE_KINDS = {
    "pr_commits.csv": "commit",
    "issues.csv": "issue",
    "pull_requests.csv": "pull_request",
}

LINK_WORKER_FILE_KINDS = {
    "issue_commit_links.csv": "issue_commit_link",
}

TEXT_COLUMNS = {
    # GitHub commit objects have `commit.message`; they do NOT have a native
    # `description` field. commit_title/commit_description in older outputs are
    # derived splits, so RQ1 uses only the raw API-backed commit_message.
    "commit": ["commit_message"],
    # For issues and PRs, `description` in our CSV is GitHub API `body`.
    "issue": ["title", "description", "issue_title", "issue_description"],
    "pull_request": ["title", "description", "pr_title", "pr_description"],
    "issue_commit_link": [
        "issue_title", "issue_description", "pr_title", "pr_description",
        "commit_message", "commit_title", "commit_description",
    ],
}

ID_COLUMNS = [
    "worker", "repo_slug", "issue_number", "pr_number", "commit_sha", "html_url",
    "commit_html_url",
]

FILE_COLUMNS = ["file_extensions", "file_names"]

LANGUAGE_BY_EXT = {
    "py": "Python",
    "js": "JavaScript", "jsx": "JavaScript", "mjs": "JavaScript", "cjs": "JavaScript",
    "ts": "TypeScript", "tsx": "TypeScript",
    "java": "Java", "kt": "Kotlin", "kts": "Kotlin", "scala": "Scala", "groovy": "Groovy",
    "rs": "Rust",
    "c": "C", "h": "C/C++", "cc": "C++", "cpp": "C++", "cxx": "C++", "hpp": "C++",
    "cs": "C#", "go": "Go", "rb": "Ruby", "php": "PHP", "swift": "Swift",
    "sh": "Shell", "bash": "Shell", "zsh": "Shell", "fish": "Shell",
    "r": "R", "lua": "Lua", "dart": "Dart", "ex": "Elixir", "exs": "Elixir",
    "erl": "Erlang", "hrl": "Erlang", "clj": "Clojure", "cljs": "Clojure",
}

FILE_TYPE_BY_EXT = {
    # Documentation
    "md": "Documentation", "markdown": "Documentation", "rst": "Documentation", "txt": "Documentation",
    # Config / metadata
    "json": "Config/Metadata", "yaml": "Config/Metadata", "yml": "Config/Metadata",
    "toml": "Config/Metadata", "ini": "Config/Metadata", "cfg": "Config/Metadata",
    "lock": "Lockfile", "xml": "Config/Metadata", "properties": "Config/Metadata",
    # Build / dependency manifests
    "gradle": "Build/Dependency", "pom": "Build/Dependency", "sbt": "Build/Dependency",
    # CI
    "github": "CI", "gitlab-ci": "CI",
    # Tests are detected partly from path names too.
    # Code extensions default to Source Code via LANGUAGE_BY_EXT.
}

SPECIAL_FILE_TYPES = {
    "dockerfile": "Config/Metadata",
    "makefile": "Build/Dependency",
    "package.json": "Build/Dependency",
    "package-lock.json": "Lockfile",
    "yarn.lock": "Lockfile",
    "pnpm-lock.yaml": "Lockfile",
    "cargo.toml": "Build/Dependency",
    "cargo.lock": "Lockfile",
    "pyproject.toml": "Build/Dependency",
    "setup.py": "Build/Dependency",
    "requirements.txt": "Build/Dependency",
    "pom.xml": "Build/Dependency",
    "build.gradle": "Build/Dependency",
    "gradle.properties": "Build/Dependency",
    "tsconfig.json": "Config/Metadata",
}

FILENAME_RE = re.compile(
    r"(?<![A-Za-z0-9_/@.-])"
    r"(?:[A-Za-z0-9_.-]+/)*"
    r"[A-Za-z0-9_.-]+\."
    r"(?:py|js|jsx|mjs|cjs|ts|tsx|java|kt|kts|scala|groovy|rs|c|h|cc|cpp|cxx|hpp|"
    r"cs|go|rb|php|swift|sh|bash|zsh|fish|r|lua|dart|ex|exs|erl|hrl|clj|cljs|"
    r"md|markdown|rst|txt|json|yaml|yml|toml|ini|cfg|lock|xml|properties|gradle|sbt)"
    r"(?![A-Za-z0-9_/@.-])",
    re.I,
)


def compile_keyword_patterns() -> Dict[str, List[Tuple[str, re.Pattern[str]]]]:
    patterns: Dict[str, List[Tuple[str, re.Pattern[str]]]] = {}
    for category, keywords in CATEGORIES.items():
        patterns[category] = []
        for keyword in keywords:
            k = keyword.lower()
            # Exact token/phrase match. This avoids matching doc in docker.
            pat = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(k) + r"(?![A-Za-z0-9_])", re.I)
            patterns[category].append((keyword, pat))
    return patterns


PATTERNS = compile_keyword_patterns()
csv.field_size_limit(sys.maxsize)


def split_listish(value: str) -> List[str]:
    if not value:
        return []
    # Handles values such as "py,md", ".py .md", "['py', 'md']".
    cleaned = value.strip().strip("[]")
    parts = re.split(r"[,;|\s]+", cleaned)
    return [p.strip().strip("'\"") for p in parts if p.strip().strip("'\"")]


def load_repo_ecosystem_map(path: Path) -> Dict[str, Dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        return {
            row["repo_slug"]: row
            for row in csv.DictReader(f)
            if row.get("repo_slug")
        }


def get_file_names(row: Dict[str, str]) -> List[str]:
    names = split_listish(row.get("file_names", ""))
    names.extend(split_listish(row.get("inferred_file_names", "")))
    return list(dict.fromkeys([n for n in names if n]))


def extract_filenames_from_text(text: str) -> List[str]:
    """Extract explicit filenames mentioned in issue/PR/commit text."""
    found = FILENAME_RE.findall(text or "")
    lower_text = (text or "").lower()
    for special in SPECIAL_FILE_TYPES:
        if re.search(r"(?<![A-Za-z0-9_.-])" + re.escape(special) + r"(?![A-Za-z0-9_.-])", lower_text, re.I):
            found.append(special)
    return list(dict.fromkeys(found))


def get_extensions(row: Dict[str, str]) -> List[str]:
    exts: List[str] = []

    for item in split_listish(row.get("file_extensions", "")):
        item = item.lower().lstrip(".")
        if item:
            exts.append(item)

    for name in get_file_names(row):
        suffix = Path(name).suffix.lower().lstrip(".")
        if suffix:
            exts.append(suffix)

    # Keep order, remove duplicates.
    return list(dict.fromkeys(exts))


def is_json_only(exts: List[str]) -> bool:
    return bool(exts) and set(exts) == {"json"}


def has_markdown(exts: List[str], row: Dict[str, str]) -> bool:
    if "md" in exts or "markdown" in exts:
        return True
    names = ";".join(get_file_names(row))
    return bool(re.search(r"\.md(?:$|[,;|\s\]\)])", names, re.I))


def keyword_matches(text: str, category: str) -> List[str]:
    return [kw for kw, pat in PATTERNS[category] if pat.search(text)]


def classify_language_and_file_type(row: Dict[str, str]) -> Tuple[str, str, str, str]:
    exts = get_extensions(row)
    file_names_list = get_file_names(row)
    file_names = ";".join(file_names_list).lower()

    languages = []
    file_types = []
    for ext in exts:
        if ext in LANGUAGE_BY_EXT:
            languages.append(LANGUAGE_BY_EXT[ext])
            file_types.append("Source Code")
        if ext in FILE_TYPE_BY_EXT:
            file_types.append(FILE_TYPE_BY_EXT[ext])

    for name in file_names_list:
        base = Path(name).name.lower()
        if base in SPECIAL_FILE_TYPES:
            file_types.append(SPECIAL_FILE_TYPES[base])

    if re.search(r"(^|[/_.-])(test|tests|spec|specs)(__|[/_.-]|$)", file_names):
        file_types.append("Test")
    if ".github/workflows" in file_names or "gitlab-ci" in file_names or "circleci" in file_names:
        file_types.append("CI")

    languages = sorted(dict.fromkeys(languages))
    file_types = sorted(dict.fromkeys(file_types))

    if not exts and not file_names_list:
        return "No file context", "No file context", "No file context", "No file context"

    language_labels = languages if languages else ["Non-code/Unknown"]
    file_type_labels = file_types if file_types else ["Other/Unknown"]
    language_combo = "+".join(language_labels)
    file_type_combo = "+".join(file_type_labels)
    all_languages = ";".join(language_labels)
    all_file_types = ";".join(file_type_labels)
    return language_combo, all_languages, file_type_combo, all_file_types


def classify(text: str, row: Dict[str, str]) -> Tuple[str, str, str]:
    """Return category, rule, matched keywords."""
    exts = get_extensions(row)

    if has_markdown(exts, row):
        return "Documentation", "markdown_file", ".md"

    if is_json_only(exts):
        return "Other", "json_only_file", ".json"

    for category in KEYWORD_ORDER:
        matches = keyword_matches(text, category)
        if matches:
            return category, "keyword", ";".join(matches)

    return "Other", "fallback", ""


def iter_rows(
    kind: str,
    path: Path,
    repo_ecosystem_map: Optional[Dict[str, Dict[str, str]]] = None,
) -> Iterable[Dict[str, str]]:
    repo_ecosystem_map = repo_ecosystem_map or {}
    worker_from_path = path.parent.name if path.parent.name.startswith("worker-") else ""
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if worker_from_path and not row.get("worker"):
                row["worker"] = worker_from_path
            texts = [row.get(c, "") for c in TEXT_COLUMNS.get(kind, []) if row.get(c)]
            text = "\n".join(texts).strip()
            if not row.get("file_names"):
                row["inferred_file_names"] = ";".join(extract_filenames_from_text(text))
            category, rule, matched = classify(text.lower(), row)

            eco = repo_ecosystem_map.get(row.get("repo_slug", ""), {})
            language_combo, all_languages, file_type_combo, all_file_types = classify_language_and_file_type(row)

            out = {c: row.get(c, "") for c in ID_COLUMNS}
            out.update({
                "artifact_type": kind,
                "source_file": str(path),
                "ecosystem_combo": eco.get("ecosystem_combo", "Unknown"),
                "target_ecosystems": eco.get("target_ecosystems", "Unknown"),
                "pypi_names": eco.get("pypi_names", ""),
                "other_names": eco.get("other_names", ""),
                "language_combo": language_combo,
                "all_languages": all_languages,
                "file_type_combo": file_type_combo,
                "all_file_types": all_file_types,
                "message": first_present(row, ["commit_message", "title", "issue_title", "pr_title"]),
                "description": "" if kind == "commit" else first_present(row, ["description", "issue_description", "pr_description"]),
                "file_extensions": row.get("file_extensions", ""),
                "file_names": row.get("file_names", ""),
                "inferred_file_names": row.get("inferred_file_names", ""),
                "category": category,
                "matched_rule": rule,
                "matched_keywords": matched,
            })
            yield out


def first_present(row: Dict[str, str], columns: List[str]) -> str:
    for col in columns:
        value = row.get(col, "")
        if value:
            return value
    return ""


def write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "ecosystem_combo", "target_ecosystems", "artifact_type", "category",
        "language_combo", "file_type_combo", "matched_rule", "matched_keywords",
        "repo_slug", "issue_number", "pr_number", "commit_sha", "worker",
        "pypi_names", "other_names", "message", "description",
        "all_languages", "all_file_types", "file_extensions", "file_names",
        "inferred_file_names", "html_url", "commit_html_url", "source_file",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, rows: List[Dict[str, str]]) -> None:
    group_cols = [
        "ecosystem_combo", "target_ecosystems", "artifact_type", "category",
        "language_combo", "file_type_combo",
    ]
    counts: Dict[Tuple[str, ...], int] = {}
    repo_sets: Dict[Tuple[str, ...], set] = {}
    for row in rows:
        key = tuple(row.get(c, "") for c in group_cols)
        counts[key] = counts.get(key, 0) + 1
        repo_sets.setdefault(key, set()).add(row.get("repo_slug", ""))

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=group_cols + ["repo_count", "artifact_count"])
        writer.writeheader()
        for key, count in sorted(counts.items()):
            row = dict(zip(group_cols, key))
            row["repo_count"] = len([r for r in repo_sets[key] if r])
            row["artifact_count"] = count
            writer.writerow(row)


def write_multilabel_summary(path: Path, rows: List[Dict[str, str]]) -> None:
    group_cols = ["ecosystem_combo", "target_ecosystems", "artifact_type", "category"]
    counts: Dict[Tuple[str, ...], int] = {}
    repo_sets: Dict[Tuple[str, ...], set] = {}

    for row in rows:
        for dimension, source_col in [("language", "all_languages"), ("file_type", "all_file_types")]:
            labels = [x for x in row.get(source_col, "").split(";") if x]
            for label in labels:
                key = tuple(row.get(c, "") for c in group_cols) + (dimension, label)
                counts[key] = counts.get(key, 0) + 1
                repo_sets.setdefault(key, set()).add(row.get("repo_slug", ""))

    fieldnames = group_cols + ["dimension", "label", "repo_count", "artifact_count"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for key, count in sorted(counts.items()):
            out = dict(zip(fieldnames[:-2], key))
            out["repo_count"] = len([r for r in repo_sets[key] if r])
            out["artifact_count"] = count
            writer.writerow(out)


def parse_input(value: str) -> Tuple[str, Path]:
    """Parse KIND=PATH; if KIND is omitted, infer from filename."""
    if "=" in value:
        kind, path = value.split("=", 1)
        return kind.strip(), Path(path)

    path = Path(value)
    name = path.name.lower()
    if name == "issue_commit_links.csv":
        kind = "issue_commit_link"
    elif name == "pr_commits.csv" or "commit" in name:
        kind = "commit"
    elif name == "issues.csv" or "issue" in name:
        kind = "issue"
    elif name == "pull_requests.csv" or "pull" in name or "pr" in name:
        kind = "pull_request"
    else:
        kind = "record"
    return kind, path


def discover_default_inputs(
    workers_dir: Path = Path("workers"),
    include_issue_commit_links: bool = False,
) -> List[Tuple[str, Path]]:
    """Prefer full worker CSVs because they include message/description columns."""
    file_kinds = dict(RQ1_WORKER_FILE_KINDS)
    if include_issue_commit_links:
        file_kinds.update(LINK_WORKER_FILE_KINDS)

    inputs: List[Tuple[str, Path]] = []
    if workers_dir.exists():
        for csv_path in sorted(workers_dir.glob("worker-*/*.csv")):
            kind = file_kinds.get(csv_path.name)
            if kind:
                inputs.append((kind, csv_path))
    if inputs:
        return inputs

    inputs = [(kind, Path(path)) for kind, path in SUMMARY_INPUTS]
    if include_issue_commit_links:
        inputs.append(("issue_commit_link", Path("github-mining-summary/all_issue_commit_links_list.csv")))
    return inputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify RQ1 GitHub messages/descriptions.")
    parser.add_argument(
        "--input", action="append", default=[], metavar="KIND=CSV",
        help="Input CSV. KIND examples: commit, issue, pull_request. Can be repeated.",
    )
    parser.add_argument("--output", default="github-mining-summary/rq1_classified.csv")
    parser.add_argument("--summary", default="github-mining-summary/rq1_category_summary.csv")
    parser.add_argument("--multilabel-summary", default="github-mining-summary/rq1_multilabel_summary.csv")
    parser.add_argument(
        "--repo-ecosystem-map", default="github-mining-summary/repo_ecosystem_activity.csv",
        help="CSV containing repo_slug, ecosystem_combo, target_ecosystems, etc.",
    )
    parser.add_argument(
        "--include-issue-commit-links", action="store_true",
        help="Also classify issue_commit_links.csv. Off by default for RQ1.",
    )
    args = parser.parse_args()

    inputs = [parse_input(x) for x in args.input] if args.input else discover_default_inputs(
        include_issue_commit_links=args.include_issue_commit_links
    )

    repo_ecosystem_map = load_repo_ecosystem_map(Path(args.repo_ecosystem_map))

    rows: List[Dict[str, str]] = []
    for kind, path in inputs:
        if not path.exists():
            print(f"[WARN] missing input: {path}")
            continue
        rows.extend(iter_rows(kind, path, repo_ecosystem_map))

    write_csv(Path(args.output), rows)
    write_summary(Path(args.summary), rows)
    write_multilabel_summary(Path(args.multilabel_summary), rows)
    print(f"Wrote {len(rows)} classified rows: {args.output}")
    print(f"Wrote combination summary: {args.summary}")
    print(f"Wrote multi-label summary: {args.multilabel_summary}")


if __name__ == "__main__":
    main()
