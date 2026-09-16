# task-02 — DB 모델 · 초기 마이그레이션

> 선행: task-01
> 근거: `backend/docs/db-schema.md`

## 목표

Sprint 1 DB 모델을 단계적으로 만든다. 현재 인증 범위의 `0001`은 `users`, `github_accounts`이며 `0002`에서 user Refresh generation과 `auth_sessions`를 추가한다. 나머지 도메인 테이블은 후속 migration에서 구현한다.

## 작업

- 초기 migration은 수동 작성한다. autogenerate는 참고용으로만 사용한다.
- `pgcrypto` extension을 추가한다.
- PostgreSQL ENUM 대신 `VARCHAR + CHECK`를 쓴다.
- `tool_calls`, 음성 컬럼은 만들지 않는다.
- 적용된 `0001`을 다시 쓰지 않는다. `0002`에서 기존 계정을 보존하고 `users.refresh_generation`을 무작위 UUID로 채운 뒤 `auth_sessions`와 FK/INDEX를 추가한다.
- `auth_sessions`에는 raw JWT가 아닌 현재 `refresh_jti`, generation, 만료 시각만 인증 관리 정보로 저장한다. 정확한 필드와 전환 시 재로그인 정책은 DB 문서와 인증 결정 0002를 따른다.
- `topic_taxonomy`, `interview_personas`, `probe_patterns`, `report_persona_feedbacks`, `feedback_signals`, `eval_cases`, `eval_runs`, `answer_analyses`, `director_decisions`는 만들지 않는다.
- `user_documents`, `document_claims`, `analysis_repo_candidates`, `analysis_repo_candidate_pages`, `evidence_conflicts`, `user_profile_summaries`, `report_disagreements`를 Sprint 1에 포함한다.
- `document_claims`는 Sprint 1에 테이블만 만들고 row 생성/claim 추출은 하지 않는다.
- `report_disagreements`는 Sprint 1에 테이블만 만들고 API/row 생성은 Sprint 2로 넘긴다.
- `evidence_conflicts.claim_id`는 FK 없이 nullable UUID로 둔다.
- `repo_analyses.batch_position`을 추가하고 UNIQUE에는 `model`을 넣지 않는다.
- `interview_sessions.status`에 `preparing_failed`를 포함한다.

## 완료 조건

- migration upgrade가 새 DB에서 성공한다.
- CHECK/UNIQUE/INDEX가 문서와 일치한다.
- downgrade 가능 범위를 명시한다.
