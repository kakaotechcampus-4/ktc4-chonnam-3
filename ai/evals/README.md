# AI evaluation workspace

This directory reserves the evaluation workspace described in
[`spec/ai/verification.md`](../../spec/ai/verification.md) and
[ADR 0007](../../spec/ai/decisions/0007-evaluation-design-policy.md). The local synthetic
fixture and comparison method follows
[ADR 0009](../../spec/ai/decisions/0009-ai-evaluation-method.md).

- `inputs/` is reserved for information that a model may receive.
- `expectations/` is reserved for expected or forbidden outcomes and review notes. Its
  contents must not enter model prompts or retrieval inputs.

Future local synthetic cases use paired JSON files in these directories. Each pair has the
same `case_id` and `version`; a loader must reject mismatches, duplicates, and orphans. The
input side keeps its execution payload distinct from case, split, and source-group control
metadata. Only that execution payload may reach the model. Expectations, review information,
and control metadata must not enter prompts, retrieval queries, or tool inputs.

No JSON cases, loaders, real datasets, operating schemas, examples, answers, or evaluation
harnesses are included yet. This local contract does not define a database or public API
schema. These directories are not part of the runtime package or its built distributions.

Future cases derived from the same source must remain in one source group. Development and
holdout sets must use different source groups. Once a holdout case informs implementation or
policy changes, it becomes regression material and must retain its usage history; renaming or
copying it does not make it unused holdout evidence.

Do not commit real user material or undisclosed holdout answers here. Store temporary evaluation
output in the ignored `ai/report/` path.
