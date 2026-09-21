# AI evaluation workspace

This directory reserves the evaluation workspace described in
[`spec/ai/verification.md`](../../spec/ai/verification.md) and
[ADR 0007](../../spec/ai/decisions/0007-evaluation-design-policy.md). The local synthetic
fixture and comparison method follows
[ADR 0009](../../spec/ai/decisions/0009-ai-evaluation-method.md).

- `inputs/` is reserved for information that a model may receive.
- `expectations/` is reserved for expected or forbidden outcomes and review notes. Its
  contents must not enter model prompts or retrieval inputs.

Local synthetic cases use paired JSON files in these directories. Each pair has the
same `case_id` and `version`; a loader must reject mismatches, duplicates, and orphans. The
input side keeps its execution payload distinct from case, split, and source-group control
metadata. Only that execution payload may reach the model. Expectations, review information,
and control metadata must not enter prompts, retrieval queries, or tool inputs.

`inputs/director/` and `expectations/director/` now contain four synthetic proposal pairs:
first HR question, bounded retrieval, an `etc` domain question, and Controller-confirmed
completion. All belong to one development source group. The sample candidates and review
notes are draft controls, not independently reviewed answers or model-quality evidence.

Run from `ai/`:

```text
uv run --locked python scripts/review_director_contract.py
uv run --locked pytest tests/agents/director/test_director_contract_proposal.py
```

The standalone checker pairs JSON by `case_id` and positive integer `version`, rejects empty,
duplicate, mismatched/orphan pairs and source groups crossing splits, and validates the
candidate's proposed structure and supplied Controller constraints. Input metadata is kept
outside `payload`. `candidate`, `expected_stage`, and `review_notes` stay on the expectation
side. The checker consumes those candidates as test controls; it does not call a model or
send expectations to a model. `valid` means only these mechanical checks passed. Malformed
raw JSON and negative mutations are covered by the Python tests.

Only the proposed Director fixture format is supported. This is not a generic evaluation
loader, a production schema, a natural-language grader or a real-model evaluation harness.
The format and manual review cases are documented in the
[Director proposal](../../spec/ai/designs/2026-09-21-director-contract-and-flow.md).
These directories and the script are excluded from runtime distributions. No real user
datasets, operating schemas, or independent review/quality results are included.

Future cases derived from the same source must remain in one source group. Development and
holdout sets must use different source groups. Once a holdout case informs implementation or
policy changes, it becomes regression material and must retain its usage history; renaming or
copying it does not make it unused holdout evidence.

Do not commit real user material or undisclosed holdout answers here. Store temporary evaluation
output in the ignored `ai/report/` path.
