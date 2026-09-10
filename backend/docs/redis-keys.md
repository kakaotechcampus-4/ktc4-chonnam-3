# Redis 키 설계

상태: Sprint 1 FIX. Redis는 영구 원본이 아니다.

| 용도 | 키 | 타입 | TTL |
| --- | --- | --- | --- |
| OAuth state | `auth:oauth:{state}` | String | 10m |
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
- Redis가 비어도 Postgres에서 재구성할 수 있어야 한다.
- `analysis_repo_candidates` ranking 원본은 Postgres다. Redis page cache는 선택 사항이다.
- 면접 context snapshot은 빠른 Director 실행을 위한 작업 기억이다.

## 보류

- `ws:lock:{id}`의 id가 `interviewId`인지 `sessionId`인지는 `PENDING_FE`.
- DEVON JWT 전달 방식이 확정되기 전까지 인증 session key를 새로 만들지 않는다.
