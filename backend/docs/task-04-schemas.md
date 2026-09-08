# task-04 — 스키마 · 계약 테스트

> 선행: task-02
> 설계 근거: [layer-rules.md](layer-rules.md) · [db-schema.md](db-schema.md)

## 목표

`CamelModel` 과 `features/*/schemas.py` 를 api-spec 과 맞추고 `tests/contract/` 를 함께 작성한다.

## 확정본 반영 (설계 초기안 대비 변경)

FE 합의로 **BE 내부명을 그대로 쓴다** — 경계 매핑 레이어를 두지 않는다. FE `types/api.ts` 가 수정된다.

| FE 현재 | 확정 |
|---|---|
| `AgentRole = tech_lead \| senior_developer \| manager` | `tech_lead` / `hr_manager` / `domain_lead` |
| `StepKey` 4개 | 7개 — `doc_extract` / `repo_select` / `repo_detail` / `jd_fetch` / `jd_extract` / `repo_analyze` / `match_score` |
| `jd_unreachable` / `jd_parse_failed` / `github_token_expired` | `jd_fetch_failed` / `jd_extraction_failed` / `token_invalid` |

⚠ 미결 — `analysis_jobs.status=partial` 을 `RunStatus` 에 어떻게 싣나. [error-reasons.md](error-reasons.md) 미결 절.

## 작업

- [ ] TODO

## 완료 조건

- [ ] TODO

## 커밋 메시지

```
TODO
```
