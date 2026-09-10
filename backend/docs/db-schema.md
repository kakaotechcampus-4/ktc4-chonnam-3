# DB 스키마

상태: Sprint 1 FIX. 초기 migration은 수동 작성한다. autogenerate는 참고용이다.

## 규약

| 항목 | 결정 |
| --- | --- |
| PK | `UUID DEFAULT gen_random_uuid()`. `pgcrypto` 필요 |
| enum | PostgreSQL ENUM 금지. `VARCHAR + CHECK` |
| JSON | `JSONB` |
| 배열 | `TEXT[]`, `UUID[]` |
| migration | CHECK, UNIQUE, INDEX, extension을 수동 확인 |
| GitHub token | 일반 OAuth App long-lived token 전제. `BYTEA` 암호화 저장. FE 노출 금지 |
| pgvector | `PENDING_AI` |

## Sprint 1 테이블

| 그룹 | 테이블 |
| --- | --- |
| 계정 | `users`, `github_accounts` |
| GitHub | `repositories`, `repo_analyses`, `user_profile_summaries` |
| 공고 | `job_postings`, `jd_requirements` |
| 문서 | `user_documents`, `document_claims` |
| 분석 | `analysis_jobs`, `analysis_repo_candidates`, `analysis_repo_candidate_pages`, `repo_match_scores` |
| 면접 | `interview_sessions`, `session_repositories`, `interview_turns` |
| 근거 | `evidences`, `turn_evidences`, `evidence_conflicts` |
| 리포트 | `interview_reports`, `report_scores`, `report_disagreements` |
| 지식 | `score_criteria`, `prompt_versions`, `domain_question_frames` |
| 지표 | `events` |

Sprint 1에 만들지 않는 것:

- `tool_calls`
- `auth_sessions`
- `topic_taxonomy`
- `interview_personas`
- `probe_patterns`
- `report_persona_feedbacks`
- `feedback_signals`
- `eval_cases`
- `eval_runs`
- `answer_analyses`
- `director_decisions`
- 음성/STT/TTS 관련 컬럼(`audio_uri`, `transcript_confidence` 등)

## 주요 결정

- `document_claims`는 Sprint 1 migration에 만들되 row 생성/claim 추출은 하지 않는다. Sprint 2에서 자소서/포트폴리오 claim 추출을 함께 구현하며 사용한다.
- `user_documents`는 파일 바이너리 없이 metadata, extracted_text, extracted_github_urls, extract_status, truncation 여부만 저장한다.
- `evidence_conflicts`는 Sprint 1에 만들되 `answer_vs_code`만 사용한다. `claim_id UUID NULL`은 FK 없이 둔다. Sprint 2에서 `document_claims` FK를 추가한다.
- `report_persona_feedbacks`는 만들지 않는다. persona별 리포트 피드백은 `interview_reports.feedback_json`에 저장한다.
- `report_disagreements`는 Sprint 1 migration에 만들되 API/row 생성은 Sprint 2로 넘긴다.
- `topic_taxonomy`, `interview_personas`, `probe_patterns`는 별도 테이블로 만들지 않는다. Sprint 1에서는 CHECK 값, prompt, seed config로 흡수한다.
- `score_criteria`는 Sprint 1에 사용한다. 다만 점수 공식/세부 기준은 `PENDING_TEAM`이며 seed 수정 가능성을 열어둔다.
- `feedback_signals`, `eval_cases`, `eval_runs`는 Sprint 2로 미루고 Sprint 1 DB에서는 제외한다.
- `auth_sessions`는 Sprint 1과 Sprint 2 모두 만들지 않는다.
- `github_accounts`는 GitHub API 호출용 OAuth token만 저장한다. DEVON 자체 JWT는 이 테이블에 저장하지 않는다.
- GitHub OAuth App은 long-lived access token 전제로 구현한다. expiring token, refresh token, GitHub App user token으로 바꾸면 별도 migration으로 추가한다.
- `analysis_jobs.status`는 `queued`, `running`, `succeeded`, `partial`, `failed`, `canceled`.
- FE `RunStatus`는 `running`, `completed`, `failed`; DB `partial`은 FE에 `failed`로 매핑한다.
- `repo_analyses` UNIQUE는 `(repository_id, analysis_level, head_sha, prompt_version)`. `model`은 UNIQUE에 넣지 않는다.
- `repo_analyses.batch_position SMALLINT NULL`을 Sprint 1부터 둔다.
- `repositories.is_private`는 필드만 유지하고 private repo는 분석/선택 대상에서 제외한다.
- `interview_sessions.status`는 `preparing`, `preparing_failed`, `in_progress`, `completed`, `abandoned`.
- `interview_sessions.answer_mode`는 Sprint 1에서 `text` 고정.
- `interview_turns.topic_code`는 Sprint 1에 FK를 걸지 않는다.
- `user_profile_summaries`는 Sprint 1에 만들고 완료 면접에 사용된 repo 기준으로 갱신한다.

## GitHub Accounts Token Fields

`github_accounts` 토큰 관련 필드 판정:

| 필드 | 판정 | 이유 |
| --- | --- | --- |
| `access_token_encrypted` | KEEP, NOT NULL | BE가 GitHub API를 대행 호출하기 위한 필수 토큰. 평문 저장/응답/log 노출 금지 |
| `token_status` | KEEP | `valid`, `revoked` 등 GitHub API 호출 가능 상태를 빠르게 판단 |
| `token_scope` | KEEP, NULL 허용 | 실제 부여된 scope 기록과 권한 문제 디버깅에 사용 |
| `token_type` | DROP | 일반 OAuth App 응답에서 사실상 `bearer` 고정이라 컬럼 실익이 낮음 |
| `token_expires_at` | DROP | long-lived OAuth App access token 전제에서는 만료 시각이 없음 |
| `refresh_token_encrypted` | DROP | refresh token을 받지 않는 전제라 저장하지 않음 |
| `refresh_token_expires_at` | DROP | refresh token을 저장하지 않으므로 불필요 |

DEVON 자체 JWT 생성은 `users.id`와 필요 시 `github_accounts.id` 같은 식별자만 사용한다. GitHub access token은 JWT payload에 넣지 않고, JWT 발급/검증을 위해 `github_accounts`의 token 필드를 읽지 않는다.

## Candidate Tables

`analysis_repo_candidates`

- `id`
- `analysis_job_id`
- `repository_id`
- `base_rank`
- `batch_no`
- `batch_rank`
- `selection_reason`
- `ranking_score`
- `ranking_signals JSONB`
- `filter_status`
- `filter_reason`
- `created_at`

제약:

- `UNIQUE (analysis_job_id, repository_id)`
- `UNIQUE (analysis_job_id, base_rank)`
- `INDEX (analysis_job_id, batch_no, batch_rank)`

`analysis_repo_candidate_pages`

- `id`
- `analysis_job_id`
- `page_no`
- `status`
- `requested_at`
- `completed_at`
- `error_code`
- `created_at`

제약:

- `UNIQUE (analysis_job_id, page_no)`
- `CHECK status IN ('pending','running','succeeded','failed')`

## Wanted 공고

- Sprint 1은 Wanted만 지원.
- `job_postings`는 normalized Wanted URL 기준 재사용.
- `fetched_at` 기준 TTL은 24시간.
- `jd_requirements.requirement_type`: `required`, `preferred`, `unknown`.
- `skill_tags`를 `tech_tags` 원천으로 사용한다.

## Report

리포트 점수 스케일과 산정 근거는 `PENDING_TEAM`. 테이블은 API shape를 만들 수 있는 최소 구조로 둔다. 점수 공식은 문서에서 임의 확정하지 않는다.

- persona별 피드백은 `interview_reports.feedback_json`에 저장한다.
- `report_scores`는 점수 항목별 score/reason/evidence turn 연결을 위해 유지한다.
- `report_disagreements`는 Sprint 1에 테이블만 만들고 API/행 생성은 Sprint 2에서 구현한다.
