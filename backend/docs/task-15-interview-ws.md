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
- `tech_lead`는 목표 6턴·최소 5턴, `domain_lead + hr_manager`는 합산 최소 3턴이다. 첫 HR 질문도 포함하며, 두 역할의 개별 배분은 고정하지 않는다. Controller는 남은 턴으로 최소 조건을 충족할 수 있는 후보를 제한한다.
- primary repo 1~2개 중심으로 꼬리질문 품질을 우선한다.
- T3에서 evidence가 부족하면 README/metadata/commit/notable_areas 주변 파일을 후속 조회한다.
- `answer_vs_code` conflict는 즉시 꼬리질문 후보로 쓴다.

## 완료 조건

- WS 텍스트 프로토콜, 첫 `hr_manager` 질문, 기술 목표 6턴·최소 5턴, 도메인·HR 합산 최소 3턴, HR 재선택과 9턴 종료를 테스트한다.
- `turn` mismatch와 이미 답변된 turn의 중복 저장 차단을 테스트한다.
- Redis context snapshot 만료 시 Postgres 재구성이 가능하다.
- `evidence_conflicts(source='answer_vs_code')` 생성과 follow-up 후보화를 테스트한다.

## 진행 상태

- 턴 저장·조회 뼈대: `turn_service.py`의 `save_question`(질문 + `question_basis` 연결)·`save_answer`(turn mismatch·중복 제출 차단), `queries.py`의 `list_turns`와 PostgreSQL 테스트 완료. 선행 task-13 준비·task-14 Director 대신 `tests/features/interview/factories.py`의 목데이터와 인자 고정값으로 검증했다.
- 분석·판단 저장(`analysis`, `decision`, `context_state`): `analysis`·`decision` JSON 형태를 정하는 PR #49·#50 머지 후 진행.
- `save_question`의 `jd_requirement_ids`·`claim_ids` 인자: Director 출력 계약(PR #49·#50) 확정 후 추가.
- WS 핸들러, persona 배분·첫 `hr_manager` 강제, Redis context snapshot, `evidence_conflicts`: 미착수.
