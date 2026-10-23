# GitHub mining mapped by package ecosystem

Mapping source: shard CSV package-overlap rows. All mappings include PyPI plus target ecosystems. For Maven-family rows, GitHub repo is recovered from evidence text when metadata fields are empty. Activity source: current worker CSV outputs.

## Summary by target ecosystem

| Target ecosystem | Mapped repos | Repos with mined activity | Issues | PRs | PR commits | Issue/commit links | Total rows |
|---|---:|---:|---:|---:|---:|---:|---:|
| npm | 1,993 | 246 | 10,895 | 31,528 | 67,241 | 12,395 | 122,059 |
| crates | 776 | 156 | 6,138 | 13,062 | 40,004 | 8,674 | 67,878 |
| maven | 11 | 2 | 114 | 127 | 244 | 53 | 538 |

## Summary by ecosystem combination

| Ecosystem combo | Mapped repos | Repos with mined activity | Issues | PRs | PR commits | Issue/commit links | Total rows |
|---|---:|---:|---:|---:|---:|---:|---:|
| npm+pypi | 1,887 | 227 | 10,249 | 29,325 | 59,739 | 11,225 | 110,538 |
| crates+pypi | 670 | 137 | 5,492 | 10,859 | 32,502 | 7,504 | 56,357 |
| crates+npm+pypi | 106 | 19 | 646 | 2,203 | 7,502 | 1,170 | 11,521 |
| maven+pypi | 11 | 2 | 114 | 127 | 244 | 53 | 538 |

## Top 30 mapped repos by PR/issue/commit activity

| Repo | Ecosystems | Workers | Issues | PRs | PR commits | Issue/commit links | Total |
|---|---|---|---:|---:|---:|---:|---:|
| getsentry/sentry-cli | npm+pypi | worker-02 | 1,457 | 1,788 | 4,148 | 1,913 | 9,306 |
| catboost/catboost | npm+pypi | worker-04 | 2,542 | 486 | 2,346 | 862 | 6,236 |
| dyne/zenroom | npm+pypi | worker-01 | 398 | 778 | 3,532 | 242 | 4,950 |
| evilmartians/lefthook | npm+pypi | worker-04 | 497 | 807 | 1,783 | 1,271 | 4,358 |
| nyx-space/anise | crates+pypi | worker-00 | 203 | 492 | 1,772 | 1,645 | 4,112 |
| metacall/core | crates+npm+pypi | worker-01 | 242 | 555 | 2,581 | 608 | 3,986 |
| dbsystel/cdk-sops-secrets | npm+pypi | worker-00 | 49 | 1,311 | 2,255 | 216 | 3,831 |
| arelle/ixbrl-viewer | npm+pypi | worker-04 | 126 | 949 | 2,351 | 251 | 3,677 |
| worldwidetelescope/pywwt | npm+pypi | worker-02;worker-02-assist-worker03 | 286 | 492 | 2,214 | 444 | 3,436 |
| clarencetw/cdk-lambda-layer-zip | npm+pypi | worker-01 | 0 | 1,695 | 1,700 | 0 | 3,395 |
| microsandbox/microsandbox | crates+npm+pypi | worker-01 | 202 | 654 | 2,052 | 373 | 3,281 |
| nibsbin/quillmark | crates+pypi | worker-00 | 9 | 670 | 2,478 | 4 | 3,161 |
| bentoml/openllm | npm+pypi | worker-01 | 280 | 899 | 1,950 | 14 | 3,143 |
| udondan/cdk-ec2-key-pair | npm+pypi | worker-04 | 36 | 1,415 | 1,585 | 105 | 3,141 |
| pcaversaccio/snekmate | npm+pypi | worker-01 | 73 | 296 | 1,560 | 1,180 | 3,109 |
| picovoice/picovoice | crates+pypi | worker-04 | 306 | 607 | 2,173 | 11 | 3,097 |
| pepperize/cdk-github | npm+pypi | worker-01 | 9 | 1,206 | 1,858 | 19 | 3,092 |
| holoviz/geoviews | npm+pypi | worker-00 | 361 | 474 | 1,647 | 485 | 2,967 |
| pulumi/pulumi-null | npm+pypi | worker-01 | 56 | 1,244 | 1,517 | 24 | 2,841 |
| pulumi/pulumi-mongodbatlas | npm+pypi | worker-01 | 180 | 868 | 1,201 | 469 | 2,718 |
| google/open-location-code | crates+pypi | worker-01 | 281 | 398 | 1,259 | 767 | 2,705 |
| zxing-cpp/zxing-cpp | crates+pypi | worker-02 | 576 | 422 | 1,400 | 302 | 2,700 |
| apache/hudi-rs | crates+pypi | worker-01 | 152 | 472 | 1,392 | 490 | 2,506 |
| qe-lab/dqcsim | crates+pypi | worker-04 | 59 | 640 | 1,146 | 507 | 2,352 |
| tamasfe/taplo | crates+pypi | worker-02 | 581 | 286 | 581 | 867 | 2,315 |
| benfred/py-spy | crates+pypi | worker-01 | 420 | 429 | 949 | 328 | 2,126 |
| pulumi/pulumi-kong | npm+pypi | worker-00 | 44 | 793 | 1,178 | 20 | 2,035 |
| pulumi/pulumi-opsgenie | npm+pypi | worker-01 | 72 | 763 | 953 | 130 | 1,918 |
| pulumi/pulumi-minio | npm+pypi | worker-00 | 67 | 756 | 956 | 90 | 1,869 |
| tailix/libkernaux | crates+pypi | worker-02 | 66 | 90 | 1,214 | 340 | 1,710 |

## Output files
- `artifacts/github-mining-summary/repo_ecosystem_activity.csv`
- `artifacts/github-mining-summary/repo_package_map.csv`
- `artifacts/github-mining-summary/ecosystem_target_summary.csv`
- `artifacts/github-mining-summary/ecosystem_combo_summary.csv`