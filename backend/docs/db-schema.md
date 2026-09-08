# DB 스키마 — 마이그레이션 반영본

이 문서는 **실제 마이그레이션(`migrations/versions/`)에 들어간 스키마**를 기록한다.
컬럼 단위 확정본(필드·타입·API 출처)은 팀 스키마 문서가 원본이고, 여기에는 **코드가 지켜야 하는
결정과 1차/2차 경계**를 남긴다.

- 작성 시점: task-02
- 갱신 규칙: 마이그레이션을 추가할 때 같은 PR 에서 이 문서를 함께 고친다.
- ⚠ `becontext.md` 1장(충돌 9건)·§9.1 은 이 문서보다 낡았다. 아래 "becontext 대비 변경" 참조.

## 규약

| 항목 | 결정 |
|---|---|
| 드라이버 | `asyncpg` + SQLAlchemy 2.0 async |
| PK | `UUID DEFAULT gen_random_uuid()` (`pgcrypto` 필요). `events` 만 `BIGSERIAL` |
| API 의 id | UUID 문자열 그대로. 프리픽스를 붙이지 않는다 |
| 배열 | `TEXT[]` / `UUID[]` |
| 마이그레이션 | Alembic. 자동생성 결과를 그대로 커밋하지 않는다 (부분 유니크·`TEXT[]`·JSONB 기본값을 놓친다) |
| 토큰 | `BYTEA` + AES-GCM (`core/crypto.py`). 평문 저장 금지 |

## 1차 테이블

| 그룹 | 테이블 | 모델 모듈 |
|---|---|---|
| 계정 | `users`, `github_accounts` | `db/models/user.py` |
| 레포 | `repositories`, `repo_analyses`, `user_profile_summaries` | `db/models/github.py` |
| 공고 | `job_postings`, `jd_requirements` | `db/models/posting.py` |
| 문서 | `user_documents`, `document_claims` | `db/models/document.py` |
| 분석 | `analysis_jobs`, `repo_match_scores` | `db/models/analysis.py` |
| 면접 | `interview_sessions`, `session_repositories`, `interview_turns` | `db/models/interview.py` |
| 근거 | `evidences`, `turn_evidences`, `evidence_conflicts`(빈 테이블) | `db/models/evidence.py` |
| 리포트 | `interview_reports`, `report_scores`, `report_persona_feedbacks`, `report_disagreements` | `db/models/report.py` |
| 지식 | `topic_taxonomy`, `interview_personas`, `probe_patterns`, `score_criteria`, `prompt_versions` | `db/models/knowledge.py` |
| 지표 | `events`, `feedback_signals`, `eval_cases`, `eval_runs` | `db/models/metric.py` |

**만들지 않는 것** — `auth_sessions`. 여러 기기 동시 로그인 관리는 이 서비스 범위에서
트레이드오프라고 판단해 제외했다(BE 리드). 세션은 Redis 만 갖는다.
`users` 에 `login_id` / `password_hash` 를 만들지 않는다 (로그인 자체가 GitHub OAuth).

**`tool_calls`** 는 1차에 없다. Tool 계약 확정 후 2차.

## becontext.md 대비 변경 (확정본 반영)

| 항목 | becontext | 확정 |
|---|---|---|
| `document_claims` | §9.1 "1단계 제외" | **1차 포함.** 끝난 면접의 "어느 주장이 다뤄졌나" 는 소급 복원이 불가능하다. 1차 컬럼 5개(`claim_text`/`claim_type`/`tech_tags`/`paragraph_no`/`confidence`), `topic_code`·`repository_hint` 는 2차 |
| `analysis_jobs` | 1 run = 4 steps | **`job_type` 3종** (`initial_sync`/`interview_prep`/`deep_analysis`), `interview_prep` 은 **7 steps** |
| `analysis_jobs.status` | 4값 | **6값** — `queued`/`running`/`succeeded`/`partial`/`failed`/`canceled` |
| `interview_sessions.answer_mode` | §1.6 `voice` | **`text` 고정** + `CHECK (answer_mode='text')`. 2차에 완화 (FE 합의) |
| `interview_turns` | `transcript_confidence`, `audio_uri` 선반영 | **컬럼 자체를 만들지 않는다** — 스프린트2 |
| `interview_turns.topic_code` | FK `topic_taxonomy` | **1차 FK 없음.** `topic_taxonomy` 확정 후 2차에 FK 추가 |
| persona 값 | 3인(값 미정) | `tech_lead` / `hr_manager` / `domain_lead` |
| `github_accounts` | 토큰 3컬럼 | + `token_status`(`valid`/`expired`/`revoked`), `refresh_token_expires_at`, `token_type` |
| `users` | — | + `status`(`active`/`suspended`/`withdrawn`), `last_login_at` |
| `repositories` | 단일 수집 | **L0-a / L0-b 2단계.** `fetch_level`(`list`/`detail`) 이 "`readme_text` 가 NULL 인 게 미조회인지 README 없음인지" 를 구분하는 유일한 수단 |
| `repo_analyses` | 단일 | **`analysis_level`**(`shallow`/`deep`) + `head_sha` 가 캐시 무효화 키 |
| `job_postings` | URL 크롤링 | + `site_adapter`, `content_form`, `industry`, `parse_error_code`, 재사용 TTL 7일 |

## 주요 제약 · 인덱스

```sql
-- 레포 분석 캐시 (★ head_sha 가 캐시 무효화 키)
UNIQUE (repository_id, analysis_level, head_sha, prompt_version)   -- repo_analyses
INDEX  (repository_id, analysis_level, analyzed_at DESC)
CHECK  (analysis_level IN ('shallow','deep'))
CHECK  (analysis_level = 'deep' OR architecture_summary IS NULL)

-- 작업 중복 실행 방지 (Redis run:lock 과 이중 방어)
CREATE UNIQUE INDEX ON analysis_jobs (user_id, job_type)
  WHERE status IN ('queued','running');
CHECK (job_type IN ('initial_sync','interview_prep','deep_analysis'))
CHECK (status   IN ('queued','running','succeeded','partial','failed','canceled'))
INDEX (user_id, created_at DESC)

-- 공고
UNIQUE (user_id, source_url)                                      -- job_postings
CHECK  (content_form IN ('text','image','mixed'))
CHECK  (parse_status IN ('pending','success','partial','failed'))
INDEX  (job_posting_id, display_order)                            -- jd_requirements
CHECK  (category IN ('required','preferred','responsibility'))

-- 문서
CHECK (kind           IN ('cover_letter','portfolio'))             -- user_documents
CHECK (extract_status IN ('pending','success','failed','unsupported'))
CHECK (claim_type     IN ('tech_decision','contribution','achievement','motivation'))
       -- CHECK 에는 4개를 남기고 1차 추출은 앞의 2개만

-- 추천 · 확정
UNIQUE (analysis_job_id, repository_id)                            -- repo_match_scores
INDEX  (analysis_job_id, rank)
UNIQUE (session_id, repository_id)                                 -- session_repositories

-- 면접
CHECK  (status IN ('preparing','in_progress','completed','abandoned'))  -- paused 없음
CHECK  (answer_mode = 'text')                                      -- 2차에 완화
INDEX  (user_id, created_at DESC)
INDEX  (status)                                                    -- North Star 집계
UNIQUE (session_id, turn_no)                                       -- interview_turns
CHECK  (persona IN ('tech_lead','hr_manager','domain_lead'))
CHECK  (status  IN ('asked','answered','skipped','timeout'))

-- 근거
INDEX  (session_id), (session_id, repository_id)                   -- evidences
PRIMARY KEY (turn_id, evidence_id, usage)                          -- turn_evidences

-- 지표
INDEX (event_name, occurred_at DESC)                               -- events
```

## 코드가 지켜야 하는 것

- **`evidences.git_ref` NOT NULL** — `session_repositories.snapshot_head_sha` 에서 복사한다.
  없으면 재조회가 불가능하고, 면접 중 사용자가 push 하면 근거와 질문이 어긋난다.
- **`evidences.tool_name` NULL 구분** — NULL = L2 사전분석 부산물, 값 있음 = 면접 중 Tool 호출.
  이 구분이 없으면 "Tool 호출 0건 = 꼬리질문이 근거 없이 생성됨" 을 감지할 수 없다.
- **`turn_evidences.usage` 가 PK 에 포함** — 같은 evidence 가 질문 근거(`question_basis`)이면서
  채점 근거(`evaluation_basis`)일 수 있다.
- **`is_ai_recommended` ≤ 5** — `is_selected` 상한과 같아야 채택률이 의미를 갖는다.
- **`user_profile_summaries.based_repo_ids` 정렬 저장** — 재생성 판정 키.
- **`interview_turns.depth`** — 1=주제 시작, 2+=꼬리질문, 새 주제면 1로 리셋.
  평균 depth 1.2 면 꼬리질문이 거의 없다는 뜻이고 그건 이 서비스의 실패다.
- **`evidence_conflicts` 는 1차에 행을 만들지 않는다.** 테이블만 미리 만드는 이유는 FK 가
  `document_claims` · `evidences` 양쪽을 참조해서, 나중에 추가하면 그 시점의 정합성을 다시
  봐야 하기 때문이다.

## 미결

- **`repo_analyses` UNIQUE 에 `model` 포함 여부** — 모델 A/B(Opus↔Sonnet)를 1차에 할 거면
  필요하다. 넣으면 캐시 조회에 `AND model = ?` 가 붙고 모델 교체 시 캐시가 전부 무효화된다.
  A/B 계획이 없으면 넣지 않는다.
- **`batch_position SMALLINT`** (P2) — 배치 내 순번. 없으면 배치 뒤쪽 레포의 품질이 떨어지는지
  (lost in the middle) 측정할 수 없다. 같은 배치의 row 는 `analyzed_at` 이 전부 같아서
  순서를 복원할 방법이 없다. 배치 크기를 20 고정으로 갈 거면 불필요.
- **리포트 4테이블** — 컬럼 확정본이 아직 없다. `becontext.md` §1.8 · §1.9 기준으로 두고 있다.
- **`interview_sessions.job_posting_id` NOT NULL ↔ `unsupported_site`** — 아래 참조.

### `job_posting_id` NOT NULL 과 "공고 없이 진행" 이 충돌한다 ⚠

`unsupported_site` 화면 문구는 *"지원하지 않는 사이트예요 → 공고 없이 진행 유도"* 인데
`interview_sessions.job_posting_id` 는 NOT NULL 이다. 둘이 동시에 성립하지 않는다.

`parse_status='failed'` 인 껍데기 `job_postings` 행을 만들어 붙이면 NOT NULL 은 지켜지지만,
`jd_requirements` 0건인 세션에서 `company_job_fit` 채점을 어떻게 할지가 남는다.
