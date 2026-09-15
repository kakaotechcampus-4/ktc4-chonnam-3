# Redis 키 설계

상태: Sprint 1 FIX. Redis는 영구 원본이 아니다.

현재 인증 구현에서 사용하는 Redis 키는 OAuth state뿐이다. 나머지 도메인 키는 후속 구현 기준이며 현재 worker·분석 기능의 동작을 의미하지 않는다.

| 용도 | 키 | 타입 | TTL |
| --- | --- | --- | --- |
| OAuth state | `auth:oauth:{state}` | Hash (`binding` SHA-256, PKCE `verifier`) | 10m |
| run 중복 lock | `run:lock:{userId}:analysis:{fingerprint}` | String NX | 30m |
| run 진행 mirror | `run:{runId}:steps` | Hash | 2h |
| run 이벤트 channel | `run:{runId}:events` | Pub/Sub | 없음 |
| candidate page lock | `cand:lock:{runId}:{page}` | String NX | 10m |
| 면접 context snapshot | `iv:ctx:{interviewId}` | JSON/Hash | 2h |
| WS 단일 접속 lock | `ws:lock:{id}` | String NX | 60s heartbeat |
| report generation lock | `report:gen:{interviewId}` | String NX | 5m |
| profile summary lock | `profile:gen:{userId}` | String NX | 10m |
| GitHub rate limit | `gh:rl:{githubUserId}` | String | reset까지 |

## 원칙

- 분석 결과, 질문/답변, evidence, report 원본은 Postgres.
- 분석·면접 cache와 mirror는 Redis가 비어도 Postgres 원본에서 재구성할 수 있어야 한다.
- OAuth state는 browser-bound single-use 값으로 Redis에서만 보관하고 유실 시 로그인 절차를 다시 시작한다. Redis 장애 시 OAuth 시작은 503, callback은 안전한 실패 redirect로 처리한다.
- DEVON Refresh는 PostgreSQL `users.refresh_generation`과 `auth_sessions`만 사용한다. 기존 로그인 갱신·로그아웃에서 Redis 조회·이중 기록·fallback을 하지 않는다.
- 2026-09-15 전환 전 `auth:refresh:user:{userId}`, `auth:refresh:session:{sid}` 키는 더 이상 읽거나 쓰지 않는다. DB로 복사하지 않고 TTL로 자연 만료시키며 전환 전 로그인은 다음 Refresh 때 재로그인한다. 다른 Redis 데이터와 함께 일괄 삭제하지 않는다.
- `analysis_repo_candidates` ranking 원본은 Postgres다. Redis page cache는 선택 사항이다.
- 면접 context snapshot은 빠른 Director 실행을 위한 작업 기억이다.

## 보류

- `ws:lock:{id}`의 id가 `interviewId`인지 `sessionId`인지는 `PENDING_FE`.
