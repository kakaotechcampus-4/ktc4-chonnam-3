# task-14 — Director · LLM Task

> 선행: task-03
> 근거: `spec/backend/features/interview.md`

## 목표

단일 Director와 작업별 LLM task 계약을 구현한다.

코드 배치는 [승인된 AI 패키지 설계](../../spec/ai/designs/2026-09-12-ai-package-structure.md)를 따른다. AI 원본은 `ai/src/devon_ai/agents/director/`, `ai/src/devon_ai/llm_tasks/`, `ai/src/devon_ai/contracts.py`에 둔다. 기존 backend AI 모듈은 연결 계층이며 prompt DB 로드·구체 provider·실제 Evidence 조회는 BE가 맡는다. 패키지 골격·import 검사는 준비되어도 아래 기능과 입출력 계약의 구현 완료는 아니다.

## 작업

- Agent는 Director 하나만 둔다.
- Evidence Retriever는 Director tool로 구현한다.
- AI 패키지의 LLM task 위치는 repo_shallow, repo_deep, answer_analysis, report다. 기존 jd_extract와 profile_summary의 BE 경계는 유지하며 [0006 정책](../../spec/ai/decisions/0006-task-llm-usage-policy.md)에 따라 Sprint 1 Wanted 규칙 변환·프로필 확정 집계는 LLM을 호출하지 않는다. 일곱 prompt version 목록은 유지한다.
- `doc_claims`, 문서-코드 conflict 확장은 Sprint 2.
- 모든 LLM 작업은 Sprint 1에서 `5.5 Luna` 모델을 사용한다.
- prompt version은 작업별로 저장한다.
- JSON parsing 실패는 1회 재시도 후 실패 처리한다.
- raw output, model, prompt_version, input/output tokens, latency_ms를 가능한 범위에서 저장한다.

## 완료 조건

- Director는 DB session 없이 계약 객체만 받는다.
- LLM mock으로 성공, timeout, parse failure가 테스트된다.
