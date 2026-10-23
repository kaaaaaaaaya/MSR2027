# Different Sides of the Same Repository: Maintenance and Coupling in PyPI Cross-Ecosystem Packages — Replication Package

This artifact contains the data tables and analysis scripts for the paper
*Different Sides of the Same Repository: Maintenance and Coupling in PyPI Cross-Ecosystem Packages*.

The study examines 2,674 GitHub repositories with packages on PyPI and at least one of npm, Crates.io, or Maven (including repositories mapped to both npm and Crates.io). It characterizes maintenance artifacts (issues, pull requests, PR-linked commits) and static evidence of coupling between the ecosystem-facing sides of each repository.

The paper is organized as a **Preliminary Study** (dataset construction, ecosystem-side heuristic labels, and a rule-based topic analysis of Python-related artifacts) followed by two research questions:

- **RQ1** — *How is maintenance work distributed across the ecosystem-facing sides of PyPI cross-ecosystem repositories?*
  Six-class maintenance-task categories (Feature, Bug, Test Cases, Refactoring, Documentation, Other) cross-tabulated with the ecosystem-side heuristic labels, per artifact type.
- **RQ2** — *What evidence of coupling exists between the ecosystem-facing sides of PyPI cross-ecosystem repositories?*
  Tree-sitter/manifest static analysis distinguishing build/package-time coupling from potential runtime coupling.

> **GitHub copy of the artifact.** To stay under GitHub's file-size limits, the two large tables are stored gzip-compressed here.
> Decompress them once before running the scripts (the Zenodo archive ships them uncompressed, and `MANIFEST_SHA256.txt` lists the uncompressed files):
>
> ```bash
> gunzip -k data/rq1/maintenance_classified.csv.gz
> gunzip -k data/preliminary/python_related_topics/python_related_classified.csv.gz
> ```

The artifact is organized around the common population of 2,674 repositories; every repository-level table keeps all 2,674 rows (zero counts where no artifact was observed).

## Contents

```text
data/
  population/          Repository population (N = 2,674), package mapping, mined GitHub activity counts,
                       and the dataset summary by ecosystem pairing (paper Table "Summary Dataset")
  preliminary/
    ecosystem_side_labels/   Ecosystem-side heuristic labels (Python-only / Paired-ecosystem-only / Both / Neither)
                             for the extension and message heuristics (paper Table "Ecosystem-side heuristic labels
                             by ecosystem pairing")
    python_related_topics/   Python-related artifacts (22,764) with rule-based seven-topic labels
                             (paper Table "Rule-based maintenance topics among Python-related artifacts")
  rq1/                 Classified maintenance artifacts (128,570) and the maintenance-category x heuristic-label
                       tables (paper Table "Distribution of Maintenance Activities by Maintenance Categories")
  rq2/                 Static-coupling verdicts for the 2,250 analyzed repositories, the 424 repositories that could
                       not be cloned, and the distribution tables (paper Tables "Static Coupling Distribution" and
                       "Static Coupling by Ecosystem")
  repo_availability/   git ls-remote reachability validation for all 2,674 repositories
  all_population/      Repository-level tables joining the preliminary, RQ1, and RQ2 outputs
scripts/
  preliminary/         dataset summary, ecosystem-side labels, Python-related topic rules
  rq1/                 six-class maintenance-task classifier (keyword rules) and RQ1 table generation
  rq2/                 Tree-sitter static-coupling pipeline, batch runner, verdict reclassification,
                       repository-availability validation, and RQ2 table generation
  all_population/      repository-level join over the common population
```

The artifact intentionally does **not** include cloned GitHub repositories, raw GitHub REST API worker outputs, virtual environments, logs, cache directories, draft paper files, or internal review notes.

## Main tables

| File | Description | Rows |
|---|---|---:|
| `data/population/repo_ecosystem_activity.csv` | Common repository population and mined GitHub activity counts | 2,674 |
| `data/population/dataset_summary_by_ecosystem.csv` | Paper Table "Summary Dataset" | 5 |
| `data/preliminary/ecosystem_side_labels/{extension,message}_by_ecosystem.csv` | Paper Table "Ecosystem-side heuristic labels by ecosystem pairing" | 16 each |
| `data/preliminary/ecosystem_side_labels/{extension,message}_overall.csv` | Overall label shares (70.33% / 79.23% *Neither*, reported in the abstract and conclusion) | 4 each |
| `data/preliminary/python_related_topics/python_related_classified.csv` | Python-related artifacts with primary topic and all matched topics | 22,764 |
| `data/preliminary/python_related_topics/topic_distribution.csv` | Paper Table "Rule-based maintenance topics among Python-related artifacts" | 7 |
| `data/rq1/maintenance_classified.csv` | Artifact-level maintenance classification (79,988 PR-linked commits, 34,250 pull requests, 14,332 issues; 304 repositories) | 128,570 |
| `data/rq1/maintenance_category_by_heuristic.csv` | Paper Table "Distribution of Maintenance Activities by Maintenance Categories" (wide form; long forms in `{extension,message}_by_artifact_category.csv`) | 30 |
| `data/rq2/static_coupling_summary.csv` | Repository-level static-coupling verdicts for analyzed repositories (pipeline output) | 2,250 |
| `data/rq2/static_coupling_summary_labeled.csv` | Same verdicts with ecosystem pairing and the paper's classification label | 2,250 |
| `data/rq2/not_analyzed_repositories.csv` | Repositories not analyzed because `git clone` failed (not found/private) | 424 |
| `data/rq2/static_coupling_distribution.csv` | Paper Table "Static Coupling Distribution" | 5 |
| `data/rq2/static_coupling_by_ecosystem.csv` | Paper Table "Static Coupling by Ecosystem" | 4 |
| `data/repo_availability/repo_availability.csv` | `git ls-remote` reachability for all repositories | 2,674 |
| `data/all_population/all_population_combined.csv` | One row per population repository joining all sources | 2,674 |

## Key counts

```text
Repository population:                                   2,674
Repositories reachable by git ls-remote / analyzed (RQ2): 2,250
Repositories not found/private (Not Analyzed):             424
RQ1 classified maintenance artifacts:                  128,570
  PR-linked commits / pull requests / issues:   79,988 / 34,250 / 14,332
Repositories with >= 1 classified artifact:                304
Preliminary Python-related artifacts (seven-topic rules): 22,764  (244 repositories)
```

Ecosystem-side labels (*Neither* = no configured Python or paired-ecosystem heuristic match):

```text
Extension heuristic (commits + pull requests, 114,238): Python-only 8.84%, Paired-only 17.12%, Both 3.72%, Neither 70.33%
Message heuristic   (commits + PRs + issues, 128,570):   Python-only 6.75%, Paired-only 11.80%, Both 2.22%, Neither 79.23%
```

RQ2 static-coupling classification (2,250 analyzed repositories):

```text
No Detected Runtime Coupling:          1,102  (48.98% of analyzed)
Build/Package-Time Coupling:             917  (40.76%)
Potential Runtime Loading:                98  ( 4.36%)
Potential External Runtime Coupling:     133  ( 5.91%)
Not Analyzed (clone failed):             424
```

## Label and column conventions

- Ecosystem-side labels: `python_only`, `paired_only` (paired-ecosystem-only), `both`, `neither`.
  Paired-ecosystem languages are JavaScript/TypeScript for npm, Rust for Crates.io, Java for Maven.
  The **extension** heuristic uses changed-file paths (`all_languages` column; commits and pull requests only).
  The **message** heuristic uses artifact text (`message` + `description`; commits, issues, pull requests). The keyword/filename patterns are the `PY_RE`, `JS_RE`, `RUST_RE`, `JAVA_RE` regular expressions in `scripts/preliminary/ecosystem_side_labels.py`.
- RQ1 categories (`category` column): Feature, Bug, Test Cases, Refactoring, Documentation, Other. The complete keyword list and rule precedence are in `scripts/rq1/classify_maintenance_categories.py` (`CATEGORIES`, `KEYWORD_ORDER`).
- Preliminary seven topics (`primary_topic` column): Dependency/Packaging, API Evolution, Runtime/Error Handling, Compatibility, Documentation/Configuration, Testing/CI, Other Python Maintenance. The complete priority-ordered rule list is `RULES` in `scripts/preliminary/python_related_topics.py`. `all_matched_topics` lists every matching topic; `primary_topic` is the first match.
- RQ2 verdicts: the pipeline's `runtime_focused_verdict` values map onto the paper's labels as follows.

  | `runtime_focused_verdict` | Paper classification |
  |---|---|
  | `runtime-likely-independent` | No Detected Runtime Coupling |
  | `build-coupled-runtime-likely-independent` | Build/Package-Time Coupling |
  | `runtime-independent-if-packaged` | Potential Runtime Loading |
  | `runtime-coupled-candidate` | Potential External Runtime Coupling |
  | (absent; listed in `not_analyzed_repositories.csv`) | Not Analyzed |

  Precedence when a repository contains several kinds of edges: potential external runtime coupling > potential runtime loading > build/package-time coupling > no detected runtime coupling.

## Reproducing the tables

All commands run from the artifact root with Python 3.10+ and only the standard library (no third-party packages are needed for the table scripts).

```bash
# Preliminary study
python3 scripts/preliminary/dataset_summary.py                     # Table "Summary Dataset"
python3 scripts/preliminary/ecosystem_side_labels.py               # Table "Ecosystem-side heuristic labels ..." (~3 min)
python3 scripts/preliminary/python_related_topics.py               # Table "Rule-based maintenance topics ..." (~3 min)

# RQ1
python3 scripts/rq1/category_by_heuristic_tables.py                # Table "Distribution of Maintenance Activities by Maintenance Categories"

# RQ2
python3 scripts/rq2/static_coupling_tables.py                      # Tables "Static Coupling Distribution" / "... by Ecosystem"

# Repository-level join over the common population
python3 scripts/all_population/build_all_population_tables.py
```

Each script accepts `--out-dir` (and `--input` where applicable), so regenerated tables can be written next to the shipped ones for comparison, e.g. `--out-dir data/rq1_reproduced`.

## Re-running the RQ2 static analysis

Re-running the static coupling analysis requires cloning the GitHub repositories and installing Tree-sitter language support (`pip install -r requirements.txt`). The batch runner clones each repository shallowly, runs `static_coupling_pipeline.py`, and reclassifies the detected coupling edges:

```bash
python3 scripts/rq2/run_static_coupling_batch.py --all-mining-repos \
  --repos-dir work/repos --results-dir work/results \
  --clone-timeout 1800 --analyze-timeout 3600
# -> work/results/runtime_focused_summary.csv  (shipped as data/rq2/static_coupling_summary.csv)
# -> work/results/batch_failures.csv           (shipped as data/rq2/not_analyzed_repositories.csv)
```

To reclassify existing per-repository results only:

```bash
python3 scripts/rq2/static_coupling_reclassify.py work/results
```

Repository reachability (`git ls-remote --heads`, 2,674 network calls):

```bash
python3 scripts/rq2/validate_repo_availability.py --data-root data --rq2-results work/results --out-dir data/repo_availability
```

Because repositories change over time (deletions, renames, new commits), re-running the clone/analysis step may yield counts that differ from the shipped tables; the shipped `static_coupling_summary.csv` is the snapshot used in the paper.

## Notes on interpretation

- Ecosystem-side labels are heuristic evidence. An artifact in the *Neither* group is not necessarily unrelated to either ecosystem-facing side; it matched none of the configured heuristics.
- RQ1 categories and the preliminary seven topics are deterministic rule-based labels, not validated ground truth.
- RQ2 verdicts are based on static evidence (manifests and source files). The absence of detected runtime-coupling evidence does not prove runtime independence of the distributed package; the two "Potential" groups require further validation.
- `Not Analyzed` repositories were unreachable (`git ls-remote` / `git clone` failed) during validation and are excluded from the analyzed-repository denominator.

## Citation

If you use this artifact, please cite the accompanying paper and this archived dataset (see `CITATION.cff`).
