#!/usr/bin/env python3
"""RQ2: reclassify static coupling edges by phase (build/package time vs. runtime) and
assign one repository-level verdict by precedence.

Input:  <results_dir>/<owner>__<repo>/couplings.csv written by static_coupling_pipeline.py
Output: <results_dir>/<owner>__<repo>/couplings_runtime_reclassified.csv,
        <results_dir>/<owner>__<repo>/runtime_summary.json,
        <results_dir>/runtime_focused_summary.csv  (= data/rq2/static_coupling_summary.csv)
        <results_dir>/runtime_focused_report.md

Repository verdicts (precedence: external > packaged > build > none) and the
paper labels they correspond to:
  runtime-coupled-candidate                -> Potential External Runtime Coupling
  runtime-independent-if-packaged          -> Potential Runtime Loading
  build-coupled-runtime-likely-independent -> Build/Package-Time Coupling
  runtime-likely-independent               -> No Detected Runtime Coupling

Usage:
  python3 scripts/rq2/static_coupling_reclassify.py <results_dir> [<owner>__<repo> ...]
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

TEST_HINTS = ("test", "tests", "__test__", "spec.", ".test.", "fuzz")
DOC_HINTS = ("readme", "docs", "doc/", "templates", "template", "examples")
CONFIG_HINTS = ("package.json", "cargo.toml", "pyproject.toml", "setup.py", "setup.cfg")


def read_csv(path: Path):
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def path_has(path: str, hints):
    p = path.lower()
    return any(h in p for h in hints)


def classify_edge(edge):
    kind = edge.get("kind", "")
    file = edge.get("file", "")
    evidence = (edge.get("evidence") or "").lower()
    detail = (edge.get("detail") or "").lower()
    text = f"{evidence} {detail}"

    if path_has(file, TEST_HINTS):
        return "test-only", "test path"
    if path_has(file, DOC_HINTS) and kind == "subprocess_package_tool":
        return "docs/examples-only", "package-tool mention in docs/example/template"
    if file.lower().endswith(CONFIG_HINTS):
        if kind in {"manifest_python_rust_build", "manifest_python_rust_binding", "manifest_node_rust_binding", "manifest_node_native_tooling", "manifest_path_dependency"}:
            return "build/package", "manifest-level build/package dependency"
        if kind == "manifest_local_dependency":
            return "package-local", "local workspace/file dependency"

    if kind in {"manifest_python_rust_build", "manifest_python_rust_binding", "manifest_node_rust_binding", "manifest_node_native_tooling", "manifest_path_dependency"}:
        return "build/package", "manifest-level build/package dependency"

    if kind == "python_rust_binding":
        return "build/package", "Rust extension binding source; runtime may be self-contained in wheel"

    if kind == "napi_binding":
        return "build/package", "Node native binding source/tooling; runtime may be self-contained in npm package"

    if kind == "wasm_bridge":
        if ".wasm" in text or "wasi" in text or "wasm-runtime" in text:
            return "runtime-packaged-artifact", "runtime loads/mentions WASM/WASI artifact; independent if bundled"
        return "build/package", "WASM target-specific source/build configuration"

    if kind == "npm_to_native_binary":
        if "../" in text or "process.env" in text:
            return "runtime-conditional/external", "runtime native loading may use env or relative package path"
        return "runtime-packaged-artifact", "runtime loads native addon; independent if native package/artifact is bundled/installed"

    if kind == "subprocess_package_tool":
        if any(x in text for x in ["subprocess", "child_process", "command::new", "std::process", "spawn(", "exec("]):
            return "runtime-external-process", "runtime may spawn another ecosystem tool/process"
        return "docs/examples-only", "tool name appears as string/comment/template, not proven runtime"

    if kind == "manifest_local_dependency":
        return "package-local", "local workspace/file dependency"

    return "unknown", "needs manual inspection"


def repo_verdict(class_counts):
    external = class_counts["runtime-external-process"] + class_counts["runtime-conditional/external"]
    packaged = class_counts["runtime-packaged-artifact"]
    test_docs = class_counts["test-only"] + class_counts["docs/examples-only"]
    build = class_counts["build/package"] + class_counts["package-local"]
    if external:
        return "runtime-coupled-candidate", "runtime may require external sibling/process/env artifact"
    if packaged:
        return "runtime-independent-if-packaged", "runtime uses native/WASM artifacts, but these can be bundled in the package"
    if build:
        return "build-coupled-runtime-likely-independent", "coupling evidence is build/package-time, not runtime"
    if test_docs:
        return "runtime-likely-independent", "only test/docs/example coupling evidence found"
    return "runtime-likely-independent", "no runtime coupling evidence found"


def process_repo(result_dir: Path):
    rows = read_csv(result_dir / "couplings.csv")
    out_rows = []
    counts = Counter()
    for e in rows:
        phase, reason = classify_edge(e)
        counts[phase] += 1
        r = dict(e)
        r["runtime_phase"] = phase
        r["runtime_reason"] = reason
        out_rows.append(r)

    fields = ["runtime_phase", "runtime_reason", "kind", "source_ecosystem", "target_ecosystem", "file", "line", "detail", "evidence"]
    with (result_dir / "couplings_runtime_reclassified.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in out_rows:
            w.writerow({k: r.get(k, "") for k in fields})

    verdict, reason = repo_verdict(counts)
    summary = {}
    sp = result_dir / "summary.json"
    if sp.exists():
        summary = json.loads(sp.read_text())
    runtime_summary = {
        "repo": summary.get("repo", result_dir.name),
        "static_source_build_verdict": summary.get("verdict", "unknown"),
        "runtime_focused_verdict": verdict,
        "runtime_focused_reason": reason,
        "runtime_phase_counts": dict(counts),
    }
    (result_dir / "runtime_summary.json").write_text(json.dumps(runtime_summary, indent=2, ensure_ascii=False))
    return runtime_summary, out_rows


def main(out_root: str, *repo_names: str):
    root = Path(out_root)
    if not repo_names:
        repo_names = tuple(p.name for p in root.iterdir() if p.is_dir() and (p / "couplings.csv").exists())
    summaries = []
    for name in repo_names:
        s, _ = process_repo(root / name)
        summaries.append(s)

    with (root / "runtime_focused_summary.csv").open("w", newline="") as f:
        fields = ["repo", "static_source_build_verdict", "runtime_focused_verdict", "runtime_focused_reason", "runtime_phase_counts"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for s in summaries:
            s2 = dict(s); s2["runtime_phase_counts"] = json.dumps(s2["runtime_phase_counts"], ensure_ascii=False)
            w.writerow(s2)

    md = ["# RQ2 static coupling: runtime-focused reclassification", "", "This report reinterprets the Tree-sitter/static evidence for the narrower question: **does each ecosystem run independently?**", "", "Important: this is still static. `runtime-independent-if-packaged` means the package probably runs independently if its native/WASM artifacts are bundled or installed as normal package dependencies.", "", "| repo | previous static verdict | runtime-focused verdict | reason | phase counts |", "|---|---|---|---|---|"]
    for s in summaries:
        counts = ", ".join(f"{k}={v}" for k, v in sorted(s["runtime_phase_counts"].items())) or "none"
        md.append(f"| `{s['repo']}` | {s['static_source_build_verdict']} | **{s['runtime_focused_verdict']}** | {s['runtime_focused_reason']} | {counts} |")
    md += ["", "## Interpretation", "", "- `build-coupled-runtime-likely-independent`: source/build uses another ecosystem, but no runtime external dependency was found.", "- `runtime-independent-if-packaged`: runtime loads native/WASM artifacts, but they may be part of the package. Needs isolation-copy/package install test.", "- `runtime-coupled-candidate`: runtime may use external env/path/process; manual/isolation test required.", "- `test-only` and `docs/examples-only` are not counted as runtime non-independence."]
    (root / "runtime_focused_report.md").write_text("\n".join(md))
    print(json.dumps(summaries, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/rq2/static_coupling_reclassify.py <results_dir> [<owner>__<repo> ...]")
        sys.exit(2)
    main(*sys.argv[1:])
