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
| 면접 실시간 세션 | `rt:{sessionId}` | String(JSON: interviewId, userId) | 2h |
| WS 단일 접속 lock | `ws:lock:{sessionId}` | String NX, 소유자 nonce | 30초, 연결 중 10초마다 갱신 |
| 수락된 답변 실행 표식 | `ws:work:{sessionId}` | String NX, 소유자 nonce | `ceil(6 × LLM_TIMEOUT_SECONDS + DIRECTOR_EVIDENCE_TIMEOUT_SECONDS + 120)`초 |
| WS 연결 교체 알림 | `ws:replace:{sessionId}` | Pub/Sub, 닫을 소유자 nonce | 없음 |
| report generation lock | `report:gen:{interviewId}` | String NX | 5m |
| profile summary lock | `profile:gen:{userId}` | String NX | 10m |
| GitHub rate limit | `gh:rl:{githubUserId}` | String | reset까지 |

## 원칙

- 분석 결과, 질문/답변, evidence, report 원본은 Postgres.
- 분석·면접 진행용 Redis 상태는 비어도 Postgres에서 재구성할 수 있어야 한다. 로그인 세션은 예외이며 유실·만료 시 재로그인한다.
- `analysis_repo_candidates` ranking 원본은 Postgres다. Redis page cache는 선택 사항이다.
- 면접 context snapshot은 빠른 Director 실행을 위한 작업 기억이다.
- WS 교체 알림은 기존 소켓을 닫도록 요청한다. 실제 종료 뒤 nonce가 같은 lock만 해제하며 새 연결은 NX 획득 후 수락한다. 죽은 소유자의 lock을 강제로 덮지 않고 TTL 만료까지 최대 30초 기다린다.
- `ws:work`는 소켓 교체 중 이미 수락한 T3→Tool→T4를 재실행하지 않고 DB 결과를 기다리기 위한 표식이다. 일반 작업 lease·reaper나 프로세스 강제 종료 복구를 대신하지 않는다. 준비 상태 원본은 DB이며 WS는 이를 약 1초 간격으로 읽는다.
- [공통 0003 결정](../../spec/shared/decisions/0003-sprint1-session-auth.md)에 따라 API·WS 인증은 HttpOnly `devon_session` 쿠키의 `sid`로 로그인 세션을 확인한다. 쿠키는 `Path=/`, `SameSite=Lax`, 운영 환경 `Secure`를 사용한다.
- 로그아웃은 현재 `auth:sess:{sid}` 삭제와 쿠키 만료로 처리하며 이미 없는 세션에도 `204`를 반환한다. 로그인 세션은 SQL `auth_sessions` 테이블에 저장하지 않는다.
- 세션 생성·조회·14일 sliding 갱신·로그아웃은 구현·검증 대기이며, 이 표가 실제 Redis 연결 완료를 뜻하지 않는다.

## 보류

- DEVON JWT·refresh token은 Sprint 2로 넘기며 관련 저장 설계는 해당 구현 시 검토한다.
- Sprint 1에는 heartbeat/timeout 기반 자동 abandoned 판정을 두지 않는다. `ws:lock:{sessionId}` 만료를 사용자 이탈로 해석하는 정책은 Sprint 2에서 검토한다.
