# Source provenance

This repository is a sanitized source snapshot of an existing device-testing codebase, including later working-tree extensions. Importing the snapshot does not establish that all modules were written by the uploader.

The source repository recorded the following baseline commits. Their identifiers and recorded authors are preserved here because the original Git database also contains local environments and device test artifacts and is not included in this snapshot.

| Commit | Date | Recorded author | Original message |
|---|---|---|---|
| `e6ba021b7624e4afecda8130ed8007567caac187` | 2026-03-23 | yangxingya | 新增了python环境 |
| `3e3162d62ce8f38dea7f7804291d69b1faf835b6` | 2026-03-23 | yangxingya | 初始化，第一版 |
| `1811514a41568ef1f4a78b81de37ed344872e5d5` | 2026-03-23 | yangxingya | Add README.md |

The snapshot also contains working-tree changes for Pydantic intent validation, LangGraph lifecycle and SQLite checkpoints, plan review, bounded failure diagnosis, HTTP/browser interfaces, and regression tests. Those changes were not part of the baseline commits above. Personal contribution statements should refer to the work actually completed by each contributor.

Publication preparation adds ignore rules and an example configuration, normalizes the dependency entry point, replaces example connection addresses with loopback, and excludes device-specific adapters, original device knowledge, runtime records, personal interview notes, and the original Git database.

No license has been added during this preparation.
