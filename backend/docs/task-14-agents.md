# task-14 — Director · LLM Task

> 선행: task-03
> 근거: `spec/backend/features/interview.md`

## 목표

단일 Director와 작업별 LLM task 계약을 구현한다.

## 작업

- Agent는 Director 하나만 둔다.
- Evidence Retriever는 Director tool로 구현한다.
- LLM task는 repo_shallow, repo_deep, jd_extract, answer_analysis, report, profile_summary로 나눈다.
- `doc_claims`, 문서-코드 conflict 확장은 Sprint 2.
- 모든 LLM 작업은 Sprint 1에서 `5.5 Luna` 모델을 사용한다.
- prompt version은 작업별로 저장한다.
- JSON parsing 실패는 1회 재시도 후 실패 처리한다.
- raw output, model, prompt_version, input/output tokens, latency_ms를 가능한 범위에서 저장한다.

## 완료 조건

- Director는 DB session 없이 계약 객체만 받는다.
- LLM mock으로 성공, timeout, parse failure가 테스트된다.
