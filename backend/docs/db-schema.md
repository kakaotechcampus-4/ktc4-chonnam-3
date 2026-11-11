# DB 스키마

상태: 현재 코드 기준([공통 0014](../../spec/shared/decisions/0014-current-state-docs.md)). 초기 migration은 수동 작성한다. autogenerate는 참고용이다.

## 규약

| 항목 | 결정 |
| --- | --- |
| PK | `UUID DEFAULT gen_random_uuid()`. `pgcrypto` 필요 |
| enum | PostgreSQL ENUM 금지. `VARCHAR + CHECK` |
| JSON | `JSONB` |
| 배열 | `TEXT[]`, `UUID[]` |
| migration | CHECK, UNIQUE, INDEX, extension을 수동 확인 |
| GitHub token | 일반 OAuth App long-lived token 전제. `BYTEA` 암호화 저장. FE 노출 금지 |
| pgvector | [0002 결정](../../spec/ai/decisions/0002-sprint1-vector-search.md): 미도입. migration에 extension이 없으며 도입 여부는 필요할 때 검토 |

## 테이블

| 그룹 | 테이블 |
| --- | --- |
| 계정 | `users`, `github_accounts` |
| GitHub | `repositories`, `repo_analyses`, `user_profile_summaries`, `profile_refresh_requests` |
| 공고 | `job_postings`, `jd_requirements` |
| 문서 | `user_documents`, `document_claims` |
| 분석 | `analysis_jobs`, `analysis_repo_candidates`, `analysis_repo_candidate_pages`, `repo_match_scores` |
| 면접 | `interview_sessions`, `session_repositories`, `interview_turns` |
| 근거 | `evidences`, `turn_evidences`, `evidence_conflicts`, `document_claim_comparisons`, `interview_external_sources`, `official_source_snapshots` |
| 리포트 | `interview_reports`, `report_scores`, `report_disagreements`, `report_generation_requests`, `report_revisions` |
| 지식 | `score_criteria`, `prompt_versions`, `domain_question_frames` |
| 지표 | `events`, `llm_call_records` |

만들지 않는 것:

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
- 음성 원본·전사 신뢰도 컬럼(`audio_uri`, `transcript_confidence` 등). 음성 답변은 전사한 텍스트만 저장한다

## 주요 결정

- 면접 준비 단계에서 선택한 문서의 Claim을 추출해 `document_claims`에 저장하고, 코드와 대조한 결과는 `document_claim_comparisons`에 저장한다.
- `user_documents`는 파일 바이너리 없이 metadata, extracted_text, extracted_github_urls, extract_status, truncation 여부만 저장한다.
- `evidence_conflicts`는 `answer_vs_code`만 사용한다. `claim_id UUID NULL`은 FK 없이 둔다.
- `report_persona_feedbacks`는 만들지 않는다. persona별 리포트 피드백은 `interview_reports.feedback_json`에 저장한다.
- `report_disagreements`는 페르소나별 피드백 이의 제기(`POST /interviews/{id}/feedback-disagreements`)를 저장한다. 이의 제기는 점수를 자동으로 바꾸지 않으며, 명시 재평가 결과는 `report_revisions`에 보존한다.
- `topic_taxonomy`, `interview_personas`, `probe_patterns`는 별도 테이블로 만들지 않고 CHECK 값, prompt, seed config로 흡수한다.
- `score_criteria`를 점수 기준으로 사용한다. 공개 점수는 0~100 number 6개와 단순 평균 `totalScore`로 계산한다. 항목별 세부 기준과 seed 문구는 평가 담당 자료 보강에 따라 수정 가능성을 열어둔다.
- `feedback_signals`, `eval_cases`, `eval_runs`는 DB에 만들지 않는다.
- `auth_sessions`는 만들지 않는다.
- DEVON 로그인 세션은 [공통 0003 결정](../../spec/shared/decisions/0003-sprint1-session-auth.md)에 따라 Redis `auth:sess:{sid}`에 둔다. 세션 유실·만료는 재로그인하며 Postgres에서 복구하지 않는다. 기존 계정 테이블·컬럼은 유지한다.
- `github_accounts`는 GitHub API 호출용 OAuth token만 암호화 저장한다. DEVON 로그인 세션이나 JWT를 이 테이블에 저장하지 않는다.
- DEVON JWT·refresh token은 사용하지 않는다. 도입하면 저장 설계를 별도로 검토한다.
- GitHub OAuth App은 long-lived access token 전제로 구현한다. expiring token, refresh token, GitHub App user token으로 바꾸면 별도 migration으로 추가한다.
- `analysis_jobs.status`는 `queued`, `running`, `succeeded`, `partial`, `failed`, `canceled`.
- FE `RunStatus`는 `running`, `completed`, `failed`; DB `partial`은 FE에 `failed`로 매핑한다.
- `repo_analyses` UNIQUE는 `(repository_id, analysis_level, head_sha, prompt_version)`. `model`은 UNIQUE에 넣지 않는다.
- `repo_analyses.batch_position SMALLINT NULL`을 둔다.
- `repositories.is_private`는 필드만 유지하고 private repo는 분석/선택 대상에서 제외한다.
- `interview_sessions.status`는 `preparing`, `preparing_failed`, `in_progress`, `completed`, `abandoned`.
- `interview_sessions.answer_mode`는 `text`, `voice`. 새 면접의 기본값은 `voice`이며, `text`는 음성 전환 이전에 만든 면접에 남아 있는 값이다.
- `interview_turns.topic_code`는 FK를 걸지 않는다.
- [0014 결정](../../spec/ai/decisions/0014-minimal-change-revision.md)에 따라 `interview_turns.analysis`와 `interview_turns.decision`은 별도 JSONB 컬럼이며, 기존 평면 구조를 사용하는 [분석과 판단의 저장](../../spec/ai/contracts.md#분석과-판단의-저장)을 따른다.
- 질문별 평가 기준의 기존 다섯 항목은 `interview_turns.question_contract` JSONB에 [Question Contract 저장 형식](../../spec/ai/contracts.md#question-contract-저장-형식)으로 보관한다. 별도 기준 테이블은 만들지 않는다.
- `user_profile_summaries`는 완료 면접에 사용된 repo 기준으로 갱신한다.

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

DEVON 로그인 세션은 기존 사용자 식별자를 연결한다. 로그인 쿠키에는 세션 식별자만 전달하고 GitHub access token은 넣지 않는다. GitHub token의 DB 암호화 저장과 세션 인증은 별개다.

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

- Wanted만 지원.
- `job_postings`는 normalized Wanted URL 기준 재사용을 유지하며, 재조회 내용이 바뀌면 새 공고·요구사항 ID로 저장해 이전 참조를 보존한다. [공고 재조회와 이전 자료 보존](../../spec/backend/features/analysis-run.md#공고-재조회와-이전-자료-보존)을 따른다.
- `fetched_at` 기준 TTL은 7일(`JD_REUSE_TTL_DAYS=7`).
- `jd_requirements.category`: `required`, `preferred`, `responsibility`.
  openapi.yaml 의 JdCategory 를 원본으로 한다. `unknown` 버킷은 두지 않으며,
  어느 항목에도 분류되지 않으면 행을 만들지 않는다. (팀 결정 2026-09-21, PR #41 코멘트 —
  이전에는 `requirement_type`/`unknown`으로 문서화돼 있었으나 `category`로 통일함, 이슈 #63)
- 주요 업무(`main_tasks`)는 `category=responsibility`로 저장하고 원문 출처(`source_field`)를 함께 보존한다. 변환·재조회 규칙은 [분석 Run의 Wanted 공고 수집·분류](../../spec/backend/features/analysis-run.md#wanted-공고-수집분류)를 따른다.
- `skill_tags`를 `tech_tags` 원천으로 사용한다.

## Report

리포트 점수는 반드시 공개한다. `report_scores.score`와 공개 `scores[].score`는 0~100 number이며, `totalScore`는 6개 항목의 단순 평균이다. 가중치와 nullable/status 기반 미계산 표현은 사용하지 않는다.

- persona별 피드백은 `interview_reports.feedback_json`에 저장한다.
- `report_scores`는 점수 항목별 score/reason/evidence turn 연결을 위해 유지한다.
- `report_disagreements`와 `report_revisions`는 이의 제기와 명시 재평가 이력을 보존한다. `report_generation_requests`는 생성 실행권과 실패 이력을 저장한다.
