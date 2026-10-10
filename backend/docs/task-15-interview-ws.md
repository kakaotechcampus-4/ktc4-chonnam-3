# task-15 — 면접 WebSocket

> 선행: task-13, task-14
> 근거: `spec/backend/features/interview.md`

## 목표

Sprint 1 텍스트 WS, turn loop, Redis context snapshot, evidence/conflict 흐름을 구현한다.

## 작업

- Sprint 1 client message는 `{type:"answer", turn, text:"..."}`.
- server message는 `answerReceived`, `thinking`, `evidenceCheck`, `question`, `interviewEnd`, `error`.
- `answerStart`, audio chunk, `answerEnd`, `transcript`, `questionEnd`, `stt_failed`, `tts_failed`, TTS audio는 Sprint 2.
- 첫 질문은 `hr_manager` 고정이며 question evidence 없이 허용한다.
- 2턴부터 Director가 답변 맥락과 남은 턴에 따라 persona를 선택한다. 첫 질문 이후의 persona 순서는 고정하지 않는다.
- 총 9턴 종료를 유지한다.
- [공통 0007](../../spec/shared/decisions/0007-fixed-persona-allocation.md)에 따라 정상 완료 배분은 `tech_lead` 6회·`domain_lead` 2회·`hr_manager` 1회다. 첫 HR이 유일한 HR이며 Controller는 확정·제시한 질문 수와 남은 할당으로 6/2/1 완주가 가능한 기술·도메인 후보만 허용한다.
- Tool 호출·질문 재생성·중복 요청은 질문 수를 늘리지 않고, 9번째 답변 처리 후 종료한다. 사용자 이탈·실패로 중단된 면접에는 정상 완료 배분을 강제하지 않는다.
- primary repo 1~2개 중심으로 꼬리질문 품질을 우선한다.
- T3에서 evidence가 부족하면 README/metadata/commit/notable_areas 주변 파일을 후속 조회한다.
- `answer_vs_code` conflict는 즉시 꼬리질문 후보로 쓴다.

## 완료 조건

- WS 텍스트 프로토콜, 첫 HR을 포함한 6/2/1 배분, 이후 HR·할당 초과 거절, 기술·도메인 순서 자율, 9번째 답변 후 종료와 10번째 질문 없음을 테스트한다.
- Tool 호출·질문 재생성·중복 요청의 질문 수 불변과 중단 예외를 테스트한다. 정책의 문서 승인을 구현 완료로 처리하지 않으며 실제 상태는 [AI 구현 기록](../../spec/ai/implementation.md)을 따른다.
- `turn` mismatch와 이미 답변된 turn의 중복 저장 차단을 테스트한다.
- Redis context snapshot 만료 시 Postgres 재구성이 가능하다.
- `evidence_conflicts(source='answer_vs_code')` 생성과 follow-up 후보화를 테스트한다.
