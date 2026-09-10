# task-03 — 도메인 지식 시드

> 선행: task-02
> 근거: `spec/backend/features/interview.md`

## 목표

prompt version, domain question frame, score criteria 초기 데이터를 넣는다.

## 작업

- domain category seed: `finance`, `game`, `travel`, `shopping`, `medical`, `mobility`, `etc`.
- domain별 question frame 3개씩 seed한다.
- frame 축은 개인정보/민감정보, 장애/신뢰성/운영, 사용자 경험/서비스 사용 맥락이다.
- Sprint 1 LLM model은 모든 prompt version에서 `5.5 Luna`.
- prompt version은 작업별로 둔다: `repo_shallow_v1`, `repo_deep_v1`, `jd_extract_v1`, `answer_analysis_v1`, `director_v1`, `report_v1`, `profile_summary_v1`.
- score criteria는 Sprint 1에 사용하되 점수 공식/세부 기준은 `PENDING_TEAM`이라 seed 수정 가능성을 열어둔다.
- persona, topic taxonomy, probe pattern은 별도 테이블/seed로 만들지 않는다.
- 질문 frame과 score criteria는 코드에 하드코딩하지 않는다.

## 완료 조건

- seed 재실행이 idempotent하다.
- domain frame은 팀 검수 후 데이터만 바꿔도 반영된다.
