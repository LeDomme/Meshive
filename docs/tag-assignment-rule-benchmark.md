# Tag-assignment rule re-evaluation benchmark

## Purpose

This benchmark measures the current canonical evaluator without changing its
semantics. It creates 4,000 models in two sources, one ready archive per model,
and configurable archive-entry density. It exercises global and source-scoped
`contains`, RE2 `regex`, and `path_relation` rules across model paths, archive
filenames, entry paths, and entry names.

Run from the repository root:

```text
uv run --project backend --extra dev python backend/benchmarks/tag_assignment_rules.py
```

The JSON result records wall time, SQL statements, Python tracemalloc peak,
canonical match rows, and assignment-rule ModelTag rows. The benchmark runs a
warm second evaluation, so writes caused by unchanged matches are visible.

## Measurement interpretation

The evaluator deliberately loads the selected model set and archive-entry
values into Python for each rule in order to retain current contains, casefold,
RE2, path-relation, and provenance semantics. Consequently, expected work is
approximately rules × selected models × selected archive entries. Source-scoped
rules reduce selected-model and entry work; global rules do not.

## Decision gate

Do not optimize production code from this PR. A follow-up is justified only if
the captured JSON shows a product-relevant wall-time or memory limit at the
deployment rule/entry density. Any such follow-up must preserve RE2 safety,
casefold matching, source scope, and TagAssignmentRuleMatch provenance. Likely
investigation targets are batching shared archive-value reads or persisted
pre-normalized target values; FTS and SQL regex are not assumed safe or
semantically equivalent.
