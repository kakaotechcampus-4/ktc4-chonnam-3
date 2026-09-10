# task-15 — 면접 WebSocket

> 선행: task-13, task-14
> 근거: `spec/backend/features/interview.md`

## 목표

Sprint 1 텍스트 WS, turn loop, Redis context snapshot, evidence/conflict 흐름을 구현한다.

## 작업

- Sprint 1 client message는 `{type:"answer", text:"..."}`.
- server message는 `answerReceived`, `thinking`, `evidenceCheck`, `question`, `interviewEnd`, `error`.
- `answerStart`, audio chunk, `answerEnd`, `transcript`, `stt_failed`, `tts_failed`, TTS audio는 Sprint 2.
- 첫 질문은 `hr_manager` 고정이며 question evidence 없이 허용한다.
- 2턴부터 Director가 persona를 선택한다.
- 총 9턴 종료를 유지한다.
- `tech_lead` 목표 6턴, 최소 5턴.
- `domain_lead + hr_manager` 합산 최소 3턴.
- primary repo 1~2개 중심으로 꼬리질문 품질을 우선한다.
- T3에서 evidence가 부족하면 README/metadata/commit/notable_areas 주변 파일을 후속 조회한다.
- `answer_vs_code` conflict는 즉시 꼬리질문 후보로 쓴다.

## 완료 조건

- WS 텍스트 프로토콜과 9턴 흐름을 테스트한다.
- Redis context snapshot 만료 시 Postgres 재구성이 가능하다.
- `evidence_conflicts(source='answer_vs_code')` 생성과 follow-up 후보화를 테스트한다.
