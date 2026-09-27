# task-03 — 도메인 지식 시드

> 선행: task-02
> 근거: `spec/backend/features/interview.md`

## 목표

prompt version, domain question frame, score criteria 초기 데이터를 넣는다.

## 작업

- domain category seed: `finance`, `game`, `travel`, `shopping`, `medical`, `mobility`, `etc`.
- domain별 question frame 3개씩 seed한다.
- frame 축은 개인정보/민감정보, 장애/신뢰성/운영, 사용자 경험/서비스 사용 맥락이다.
- Sprint 1의 실제 LLM 호출 모델은 [0011 결정](../../spec/ai/decisions/0011-sprint1-model-selection.md)의 OpenAI `gpt-5.6-luna`다. 기본 모델은 BE 설정의 `LLM_DEFAULT_MODEL`에서 읽어 seed에 반영하고 실제 호출에 사용한 모델·version을 기록한다. 일곱 prompt version 이름은 유지한다. Wanted 규칙 변환·프로필 언어·유형 집계는 LLM을 호출하지 않으며, 개인 역할 요약은 [0019 결정](../../spec/ai/decisions/0019-sprint1-profile-role-summary-restoration.md)을 따른다.
- prompt version은 작업별로 둔다: `repo_shallow_v1`, `repo_deep_v1`, `jd_extract_v1`, `answer_analysis_v1`, `director_v1`, `report_v1`, `profile_summary_v1`.
- score criteria는 Sprint 1에 사용한다. 공개 점수는 0~100 score 6개와 단순 평균 `totalScore`이며, 항목별 세부 기준 seed 문구는 평가 담당 자료 보강에 따라 수정 가능성을 열어둔다.
- persona, topic taxonomy, probe pattern은 별도 테이블/seed로 만들지 않는다.
- 질문 frame과 score criteria는 코드에 하드코딩하지 않는다.

## 완료 조건

- seed 재실행이 idempotent하다.
- domain frame은 팀 검수 후 데이터만 바꿔도 반영된다.
