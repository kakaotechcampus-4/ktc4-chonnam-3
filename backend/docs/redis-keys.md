# Redis 키 설계표

> Redis 를 "캐시니까 넣었다" 로 두지 않는다. 아래 각 항목은 api-spec 의 특정 응답이 요구한다.

| 용도 | 키 | 타입 | TTL | 이게 없으면 안 되는 응답 |
|---|---|---|---|---|
| 로그인 세션 | `auth:sess:{sid}` | Hash | 14d 슬라이딩 | HttpOnly 쿠키 인증 전체 |
| OAuth state | `auth:oauth:{state}` | String | 10m | OAuth CSRF 방어 |
| run 중복 락 | `run:lock:{userId}:{jobType}` | String NX | 30m | `409 run_in_progress` (DB 인덱스와 이중 방어) |
| run 진행 스냅샷 | `run:{runId}:steps` | Hash | 2h | SSE 재연결 시 초기 상태 |
| run 이벤트 채널 | `run:{runId}:events` | Pub/Sub | — | SSE 다중 워커 fan-out |
| 실시간 세션 | `rt:{sessionId}` | Hash | 2h | `sessionId` → `interviewId` 해석 |
| WS 단일 접속 락 | `ws:lock:{sessionId}` | String NX | 60s 하트비트 | `409 already_connected` |
| 동시 면접 제한 | `iv:active:{userId}` | Set | — | `409 session_limit_exceeded` |
| 리포트 생성중 | `report:gen:{interviewId}` | String | 5m | `202 {"status":"generating","retryAfter":3}` |
| GitHub rate limit | `gh:rl:{githubUserId}` | String | reset 까지 | `rate_limited` 사전 차단 |
| 레포 분석 캐시 | `cache:repo_analysis:{repoId}:{level}:{headSha}:{promptVersion}` | String(JSON) | 24h | 비용 — `repo_analyses` UNIQUE 와 같은 키 |

## 확정본 반영으로 바뀐 키 2개

### `run:lock` — `jobType` 을 키에 넣는다

`job_type` 이 3종(`initial_sync` / `interview_prep` / `deep_analysis`)으로 확정됐고,
DB 부분 유니크도 `(user_id, job_type) WHERE status IN ('queued','running')` 이다.

M1 `initial_sync` 는 **GitHub 연동 직후 백그라운드로 도는 작업**이라 사용자가 바로 공고를
입력하면 M2 `interview_prep` 과 겹친다. 사용자 단일 락으로 두면 정상 흐름이 `run_in_progress`
로 막힌다.

### `cache:repo_analysis` — `level` 과 `headSha` 를 키에 넣는다

`repo_analyses` UNIQUE 가 `(repository_id, analysis_level, head_sha, prompt_version)` 이다.
기존 키(`{repoId}:{promptVersion}`)로는 **shallow 와 deep 이 서로를 덮고**, push 가 와서
`head_sha` 가 바뀌어도 캐시가 히트해 재분석이 안 된다.

`head_sha` 를 키에 넣는 것이 곧 캐시 무효화 전략이다 — 레포에 push 가 오면 새 sha → 자동 재분석.

> ⚠ 모델 A/B(Opus↔Sonnet 비교)를 1차에 할 거면 UNIQUE 와 이 키에 `model` 을 추가해야 한다.
> 추가하면 모델을 바꿀 때 캐시가 전부 무효화된다. **A/B 계획이 없으면 넣지 않는다** (미결).

## 원칙 — 진실은 Postgres, Redis 는 미러

⚠ Redis 가 비어도 서비스는 계속 동작해야 한다.

| Redis 만 갖는 것 (유실 시 결과) | 반드시 Postgres 에도 있는 것 |
|---|---|
| `auth:sess` → 재로그인 | `analysis_jobs.steps` / `.status` (원본) |
| `auth:oauth` → OAuth 재시작 | `interview_sessions` / `interview_turns` |
| `ws:lock` → 중복 접속이 일시 허용 | `interview_reports` |
| `rt:{sessionId}` → `GET /interviews/{id}` 가 새 sessionId 재발급 | |

`run:{runId}:steps` 는 미러다. SSE 재연결 시 Redis 가 비어 있으면 Postgres 에서 읽어 채운다.

> `auth_sessions` 테이블은 만들지 않는다 (BE 리드 판단). 여러 기기 동시 로그인 관리는
> 이 서비스 범위에서 트레이드오프라고 보고 제외했다 — 세션은 Redis 만 갖는다.
