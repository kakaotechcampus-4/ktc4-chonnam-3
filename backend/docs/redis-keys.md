# Redis 키 설계

상태: Sprint 1 FIX. Redis는 영구 원본이 아니다.

| 용도 | 키 | 타입 | TTL |
| --- | --- | --- | --- |
| OAuth state | `auth:oauth:{state}` | String | 10m |
| DEVON 로그인 세션 | `auth:sess:{sid}` | String | 14일(1,209,600초), sliding |
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
- 분석·면접 진행용 Redis 상태는 비어도 Postgres에서 재구성할 수 있어야 한다. 로그인 세션은 예외이며 유실·만료 시 재로그인한다.
- `analysis_repo_candidates` ranking 원본은 Postgres다. Redis page cache는 선택 사항이다.
- 면접 context snapshot은 빠른 Director 실행을 위한 작업 기억이다.
- [공통 0003 결정](../../spec/shared/decisions/0003-sprint1-session-auth.md)에 따라 API·WS 인증은 HttpOnly `devon_session` 쿠키의 `sid`로 로그인 세션을 확인한다. 쿠키는 `Path=/`, `SameSite=Lax`, 운영 환경 `Secure`를 사용한다.
- 로그아웃은 현재 `auth:sess:{sid}` 삭제와 쿠키 만료로 처리하며 이미 없는 세션에도 `204`를 반환한다. 로그인 세션은 SQL `auth_sessions` 테이블에 저장하지 않는다.
- 세션 생성·조회·14일 sliding 갱신·로그아웃은 구현·검증 대기이며, 이 표가 실제 Redis 연결 완료를 뜻하지 않는다.

## 보류

- DEVON JWT·refresh token은 Sprint 2로 넘기며 관련 저장 설계는 해당 구현 시 검토한다.
- Sprint 1에는 heartbeat/timeout 기반 자동 abandoned 판정을 두지 않는다. `ws:lock:{sessionId}` 만료를 사용자 이탈로 해석하는 정책은 Sprint 2에서 검토한다.
