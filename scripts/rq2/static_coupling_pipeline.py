#!/usr/bin/env python3
"""RQ2: Tree-sitter based static analysis of cross-ecosystem coupling for one repository.

Parses manifests (Cargo.toml, package.json, pyproject.toml, setup.py, setup.cfg)
and supported source files (Rust, Python, JavaScript, TypeScript/TSX) with
Tree-sitter, and extracts cross-ecosystem coupling edges (pyo3/maturin, napi,
.node native loading, WASM/WASI references, local path dependencies,
package-tool invocations). Writes summary.json, files.csv, manifests.csv,
couplings.csv and report.md for the repository.

Usage:
  python3 scripts/rq2/static_coupling_pipeline.py <cloned_repo_dir> <results_dir/<owner>__<repo>>

Requires: tree-sitter-language-pack (see requirements.txt).
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import tomllib
from collections import Counter, defaultdict
from pathlib import Path

from tree_sitter_language_pack import get_parser

EXT_LANG = {
    ".rs": "rust", ".py": "python", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "tsx", ".mjs": "javascript", ".cjs": "javascript",
}
LANG_ECO = {"rust": "crates", "python": "pypi", "javascript": "npm", "typescript": "npm", "tsx": "npm"}
MANIFESTS = {"Cargo.toml": "crates", "package.json": "npm", "pyproject.toml": "pypi", "setup.py": "pypi", "setup.cfg": "pypi"}
IGNORE_DIRS = {".git", "target", "node_modules", ".venv", "dist", "build", "__pycache__", ".next"}
MAX_SOURCE_BYTES = 2_000_000

COUPLING_PATTERNS = [
    ("npm_to_native_binary", re.compile(r"require\([^)]*(?:\.node|native|wasi|wasm)|import\([^)]*(?:\.node|native|wasi|wasm)", re.I), "npm", "crates"),
    ("napi_binding", re.compile(r"\b(?:napi|napi_derive|napi-rs|node-addon|\.node)\b", re.I), None, None),
    ("python_rust_binding", re.compile(r"\b(?:pyo3|maturin|setuptools-rust|cdylib|python_extension)\b", re.I), None, None),
    ("wasm_bridge", re.compile(r"\b(?:wasm-bindgen|wasm32|webassembly|\.wasm|wasi)\b", re.I), None, None),
    ("subprocess_package_tool", re.compile(r"\b(?:cargo|npm|pnpm|yarn|pip|maturin)\b"), None, None),
]

DECL_TYPES = {
    "function_item", "function_declaration", "function_definition", "method_definition", "method_declaration",
    "class_definition", "class_declaration", "struct_item", "enum_item", "trait_item", "interface_declaration",
    "impl_item", "mod_item", "const_item", "static_item", "type_alias_declaration",
}
IMPORT_TYPES = {"use_declaration", "extern_crate_declaration", "import_statement", "import_from_statement", "import_declaration"}
CALL_TYPES = {"call_expression", "macro_invocation", "await_expression"}


def rel(root: Path, p: Path) -> str:
    return p.relative_to(root).as_posix()


def walk_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for fn in filenames:
            p = Path(dirpath) / fn
            if not p.is_file():
                continue
            try:
                if p.stat().st_size > MAX_SOURCE_BYTES:
                    continue
            except OSError:
                continue
            if p.suffix in EXT_LANG or fn in MANIFESTS:
                yield p


def ancestors(p: Path, root: Path):
    cur = p if p.is_dir() else p.parent
    while True:
        yield cur
        if cur == root:
            break
        cur = cur.parent


def detect_manifest_roots(root: Path):
    roots = []
    for p in walk_files(root):
        if p.name in MANIFESTS:
            roots.append({"path": p, "dir": p.parent, "ecosystem": MANIFESTS[p.name]})
    return roots


def ecosystems_for_file(root: Path, p: Path, manifests) -> set[str]:
    ecos = set()
    lang = EXT_LANG.get(p.suffix)
    if lang in LANG_ECO:
        ecos.add(LANG_ECO[lang])

    # Add only co-located/nearest package-root ecosystems. This prevents a monorepo
    # root Cargo.toml/pyproject.toml from making every nested npm file look mixed.
    containing = []
    for m in manifests:
        try:
            p.relative_to(m["dir"])
        except ValueError:
            continue
        containing.append(m)
    if containing:
        max_depth = max(len(m["dir"].relative_to(root).parts) for m in containing)
        for m in containing:
            if len(m["dir"].relative_to(root).parts) == max_depth:
                ecos.add(m["ecosystem"])
    return ecos or {"unknown"}


def call_or_attr(obj, name):
    v = getattr(obj, name)
    return v() if callable(v) else v


def node_kind(node) -> str:
    return call_or_attr(node, "kind") if hasattr(node, "kind") else call_or_attr(node, "type")


def node_children(node):
    if hasattr(node, "children"):
        ch = getattr(node, "children")
        return ch() if callable(ch) else ch
    return [node.child(i) for i in range(call_or_attr(node, "child_count"))]


def node_line(node) -> int:
    if hasattr(node, "start_point"):
        return call_or_attr(node, "start_point")[0] + 1
    return call_or_attr(node, "start_position").row + 1


def node_text(src: str, node, max_len=160) -> str:
    s = src[call_or_attr(node, "start_byte"):call_or_attr(node, "end_byte")].strip()
    return re.sub(r"\s+", " ", s)[:max_len]


def child_identifier(src: str, node) -> str:
    for ch in node_children(node):
        if node_kind(ch) in {"identifier", "type_identifier", "scoped_identifier", "property_identifier"}:
            return node_text(src, ch, 100)
    return node_text(src, node, 100)


def parse_source(path: Path, lang: str):
    parser = get_parser(lang)
    text = path.read_text(errors="replace")
    tree = parser.parse(text)
    root_node = tree.root_node() if callable(getattr(tree, "root_node", None)) else tree.root_node
    out = {"decls": [], "imports": [], "calls": [], "errors": 0, "nodes": 0}
    stack = [root_node]
    while stack:
        n = stack.pop()
        kind = node_kind(n)
        out["nodes"] += 1
        if call_or_attr(n, "has_error") or kind == "ERROR" or (hasattr(n, "is_error") and call_or_attr(n, "is_error")):
            out["errors"] += 1
        if kind in DECL_TYPES:
            out["decls"].append({"type": kind, "name": child_identifier(text, n), "line": node_line(n)})
        elif kind in IMPORT_TYPES:
            out["imports"].append({"type": kind, "text": node_text(text, n), "line": node_line(n)})
        elif kind in CALL_TYPES:
            out["calls"].append({"type": kind, "text": node_text(text, n, 120), "line": node_line(n)})
        stack.extend(node_children(n))
    # Regex fallback for require()/dynamic imports and Rust use items if grammar names differ.
    for i, line in enumerate(text.splitlines(), 1):
        if re.search(r"\b(require\(|import\(|from\s+['\"]|use\s+)", line):
            if len(out["imports"]) < 500:
                out["imports"].append({"type": "regex_import", "text": line.strip()[:160], "line": i})
    return out, text


def manifest_edges(root: Path, path: Path):
    edges = []
    try:
        if path.name == "Cargo.toml":
            data = tomllib.loads(path.read_text(errors="replace"))
            for sec in ["dependencies", "dev-dependencies", "build-dependencies"]:
                for name, spec in (data.get(sec) or {}).items():
                    if isinstance(spec, dict) and "path" in spec:
                        edges.append(("manifest_path_dependency", "crates", "crates", name, spec["path"]))
                    if name.lower() in {"pyo3", "maturin"}:
                        edges.append(("manifest_python_rust_binding", "pypi", "crates", name, sec))
                    if "napi" in name.lower():
                        edges.append(("manifest_node_rust_binding", "npm", "crates", name, sec))
        elif path.name == "package.json":
            data = json.loads(path.read_text(errors="replace"))
            for sec in ["dependencies", "devDependencies", "peerDependencies", "optionalDependencies"]:
                for name, spec in (data.get(sec) or {}).items():
                    if isinstance(spec, str) and (spec.startswith("file:") or spec.startswith("workspace:")):
                        edges.append(("manifest_local_dependency", "npm", "unknown", name, spec))
                    if "napi" in name.lower() or "wasm" in name.lower():
                        edges.append(("manifest_node_native_tooling", "npm", "crates", name, sec))
        elif path.name == "pyproject.toml":
            data = tomllib.loads(path.read_text(errors="replace"))
            flat = json.dumps(data).lower()
            if "maturin" in flat or "pyo3" in flat:
                edges.append(("manifest_python_rust_build", "pypi", "crates", "pyproject", "maturin/pyo3"))
    except Exception as e:
        edges.append(("manifest_parse_error", "unknown", "unknown", path.name, str(e)[:80]))
    return edges


def main(repo: str, outdir: str):
    root, out = Path(repo).resolve(), Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    manifests = detect_manifest_roots(root)
    files, couplings, manifest_rows = [], [], []
    eco_counts = Counter()

    for m in manifests:
        manifest_rows.append({"manifest": rel(root, m["path"]), "ecosystem": m["ecosystem"]})
        for kind, src, dst, detail, evidence in manifest_edges(root, m["path"]):
            couplings.append({"kind": kind, "source_ecosystem": src, "target_ecosystem": dst, "file": rel(root, m["path"]), "line": "", "detail": detail, "evidence": evidence})

    for p in walk_files(root):
        if p.name in MANIFESTS:
            continue
        lang = EXT_LANG.get(p.suffix)
        if not lang:
            continue
        ecos = ecosystems_for_file(root, p, manifests)
        try:
            parsed, text = parse_source(p, lang)
        except Exception:
            # File-level robustness: broken symlinks, disappearing files, parser
            # issues, or encoding/IO errors should not make the whole repo fail.
            try:
                text = p.read_text(errors="replace")
            except Exception:
                text = ""
            parsed = {"decls": [], "imports": [], "calls": [], "errors": 1, "nodes": 0}
        for e in ecos:
            eco_counts[e] += 1
        files.append({
            "file": rel(root, p), "language": lang, "ecosystems": "+".join(sorted(ecos)),
            "decl_count": len(parsed["decls"]), "import_count": len(parsed["imports"]),
            "call_count": len(parsed["calls"]), "parse_error_nodes": parsed["errors"], "ast_nodes": parsed["nodes"],
        })
        for label, rx, src_hint, dst_hint in COUPLING_PATTERNS:
            for mt in rx.finditer(text):
                line = text.count("\n", 0, mt.start()) + 1
                source = src_hint or (sorted(ecos)[0] if len(ecos) == 1 else "+".join(sorted(ecos)))
                target = dst_hint or ("crates" if any(x in mt.group(0).lower() for x in ["pyo3", "maturin", "napi", "wasm", "cargo"]) else "unknown")
                if target not in ecos or source != target:
                    couplings.append({"kind": label, "source_ecosystem": source, "target_ecosystem": target, "file": rel(root, p), "line": line, "detail": mt.group(0), "evidence": text.splitlines()[line-1].strip()[:200]})

    # Deduplicate noisy edges.
    seen, dedup = set(), []
    for c in couplings:
        key = tuple(c.items())
        if key not in seen:
            seen.add(key); dedup.append(c)
    couplings = dedup

    def write_csv(name, rows, fields):
        with (out / name).open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)

    write_csv("files.csv", files, ["file", "language", "ecosystems", "decl_count", "import_count", "call_count", "parse_error_nodes", "ast_nodes"])
    write_csv("manifests.csv", manifest_rows, ["manifest", "ecosystem"])
    write_csv("couplings.csv", couplings, ["kind", "source_ecosystem", "target_ecosystem", "file", "line", "detail", "evidence"])

    cross = [c for c in couplings if c["source_ecosystem"] != c["target_ecosystem"]]
    # Bounded pilot metric: 1.0 means no observed cross-ecosystem edge; values near 0
    # mean cross-ecosystem evidence is dense relative to analyzed units.
    score = (len(files) + len(manifest_rows)) / max(1, len(files) + len(manifest_rows) + len(cross))
    verdict = "independent" if len(cross) == 0 else ("weakly coupled" if score >= 0.8 else "coupled")
    summary = {
        "repo": root.name, "files_analyzed": len(files), "manifests": len(manifest_rows),
        "ecosystem_file_counts": dict(eco_counts), "coupling_edges": len(couplings),
        "cross_ecosystem_edges": len(cross), "independence_score_simple": round(score, 3), "verdict": verdict,
        "top_coupling_kinds": Counter(c["kind"] for c in cross).most_common(),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    md = [f"# Static coupling summary: {root.name}", "", f"Verdict: **{verdict}**", f"Simple independence score: **{summary['independence_score_simple']}**", "", "## Counts", "", json.dumps(summary, indent=2, ensure_ascii=False), "", "## Cross-ecosystem evidence (first 20)", ""]
    for c in cross[:20]:
        md.append(f"- `{c['kind']}` {c['source_ecosystem']} -> {c['target_ecosystem']} in `{c['file']}:{c['line']}`: {c['evidence']}")
    (out / "report.md").write_text("\n".join(md))
    print(json.dumps(summary, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__); sys.exit(2)
    main(sys.argv[1], sys.argv[2])
