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
| WS 단일 접속 lock | `ws:lock:{sessionId}` | String NX | 연결 중 |
| report generation lock | `report:gen:{interviewId}` | String NX | 5m |
| profile summary lock | `profile:gen:{userId}` | String NX | 10m |
| GitHub rate limit | `gh:rl:{githubUserId}` | String | reset까지 |

## 원칙

- 분석 결과, 질문/답변, evidence, report 원본은 Postgres.
- Redis가 비어도 Postgres에서 재구성할 수 있어야 한다.
- `analysis_repo_candidates` ranking 원본은 Postgres다. Redis page cache는 선택 사항이다.
- 면접 context snapshot은 빠른 Director 실행을 위한 작업 기억이다.

## 보류

- DEVON JWT는 HttpOnly cookie를 사용하므로 인증 session key를 새로 만들지 않는다.
- Sprint 1에는 heartbeat/timeout 기반 자동 abandoned 판정을 두지 않는다. `ws:lock:{sessionId}` 만료를 사용자 이탈로 해석하는 정책은 Sprint 2에서 검토한다.
