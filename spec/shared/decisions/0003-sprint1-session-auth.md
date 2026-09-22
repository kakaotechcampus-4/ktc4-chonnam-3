# 0003 Sprint 1 세션 인증 유지와 JWT의 Sprint 2 이관

- 상태: Accepted — 인증 방식과 적용 범위 확정, 실제 구현·통합 검증은 대기
- 날짜: 2026-09-22
- 결정자·검토자: 현재 사용자
- 결정 근거: 사용자가 Sprint 1은 세션으로 기존 구조를 유지하고 JWT는 Sprint 2로 옮기자고 제안한 뒤, 영향 설명에 “그래 그렇게 정하자.”라고 승인함.
- 관련 PR: #40 설정과 #41 DB 구조를 대조함. 이번 결정으로 원격 PR을 수정하거나 병합하지 않음.

## 맥락과 이유

현행 명세는 JWT와 갱신 토큰을 요구하지만 로컬 BE 인증 모듈은 대부분 설명만 있는 상태다. 기존 `.env.example`과 `session_store.py`에는 `devon_session`, Redis, 14일 세션 기준이 남아 있다. FE 요청도 이미 `credentials: 'include'`를 사용한다. 이 기반을 사용하면 JWT 발급·갱신·회전·재사용 감지와 별도 갱신 토큰 저장 구조를 Sprint 1에 추가하지 않아도 된다.

이는 완성된 인증 기능을 그대로 쓸 수 있다는 뜻은 아니다. 기존 구성과 화면 흐름을 유지하면서 세션 저장·검증을 구현하는 방향으로 확정한다.

## Sprint 1 결정

| 항목 | 기준 |
| --- | --- |
| 로그인 상태 | 기존 Redis의 `auth:sess:{sid}`에 사용자 식별자를 저장한다. 쿠키에는 추측하기 어려운 불투명 세션 ID만 둔다. |
| 쿠키 | `devon_session`, HttpOnly, `Path=/`, `SameSite=Lax`. 운영은 Secure, 로컬 HTTP 개발은 기존 `COOKIE_SECURE=false`를 유지한다. |
| 유효기간 | 기존 `SESSION_TTL_SECONDS=1209600`(14일)과 sliding 방식을 유지한다. 유효한 인증 요청에서 연장하며 Redis TTL과 브라우저 쿠키 만료가 어긋나지 않도록 구현·검증한다. 별도 `/auth/refresh`는 사용하지 않는다. |
| 인증 범위 | REST 요청, SSE 연결, WS handshake에서 같은 쿠키와 서버 세션을 확인한다. WS query/body/subprotocol에 인증 토큰을 추가하지 않는다. |
| 만료·유실 | 쿠키가 없거나 유효한 Redis 세션을 찾지 못하면 기존 `401 unauthenticated`를 사용한다. FE는 사용자 캐시를 비우고 로그인으로 이동한다. 브라우저 이동용 인증 경로는 기존 로그인 redirect를 유지한다. |
| Redis 장애 | 세션 조회 장애를 유효한 로그인이나 정상적인 세션 만료로 간주하지 않는다. 서버 오류로 처리하며, 오류 매핑은 기존 공통 오류 계약 안에서 구현·검증한다. |
| 로그아웃 | 현재 Redis 로그인 세션을 삭제하고 같은 이름·경로의 쿠키를 만료시킨다. 이미 만료·삭제된 경우에도 기존 `204` 멱등 동작을 유지한다. GitHub 연동 토큰은 삭제하지 않는다. |
| GitHub 토큰 | 기존대로 `github_accounts.access_token_encrypted`에 암호화 저장한다. 로그인 쿠키나 세션 값에 GitHub 토큰을 복사하지 않는다. |

로그인 세션 ID와 면접의 WS `sessionId`는 서로 다른 값이다. REST `interviewId`, 면접 `sessionId`, 분석 `runId`와 면접 복구·종료 정책은 유지한다. 이번 결정은 이미 열린 SSE/WS를 만료 시각에 강제 종료하는 새 정책을 추가하지 않는다. 재연결 시에는 다시 인증한다.

## 저장 구조와 유지 범위

- 기존 Redis를 사용하며 PostgreSQL의 `users`, `github_accounts`와 면접·분석 테이블은 이 결정 때문에 변경하지 않는다. Sprint 1에 SQL `auth_sessions`나 갱신 토큰 테이블을 추가하지 않는다.
- 로그인 세션은 “Redis가 비면 Postgres에서 재구성”하는 대상이 아니다. 만료·유실 시 다시 로그인한다. 사용자·면접 등 업무 기록은 기존 Postgres에 남으며, 면접 Context snapshot의 DB 복구 원칙도 유지한다.
- 로그인·연동·로그아웃 화면 흐름과 인증 외 요청·응답 형식은 유지한다. 인증 쿠키 기준과 `/auth/refresh`의 Sprint 1 제외는 명세에 반영한다.

## Sprint 2로 이관

JWT, access/refresh token, `/auth/refresh`, 갱신 토큰 회전·재사용 감지 및 그 저장·검증은 Sprint 2 착수 시 설계·구현한다. 과거 JWT 명세는 참고 이력이며 세부 만료시간·저장 위치·전환 절차가 이번에 승인된 것은 아니다. 이 공통 인증 후속 작업은 기존 AI Sprint 2의 7개 항목과 별개로 관리한다.

## 구현·검증 인계

- BE: [task-06](../../../backend/docs/task-06-auth.md)에서 OAuth 성공 시 새 세션 발급, REST/SSE/WS 인증, 만료 연장, 로그아웃과 장애 처리를 연결한다. OAuth state 검증과 사용자 상태·소유권 검사는 유지한다.
- FE: [task-07](../../../frontend/docs/task-07-auth.md)에서 조회·변경 요청의 `unauthenticated` 처리와 캐시 정리를 맞춘다. 현재 남아 있는 `api.refresh()`, MSW `/auth/refresh`, 관련 smoke 확인을 Sprint 1 흐름에서 제거·정리하고 세션 동작을 검증한다. 이번 문서 결정만으로 해당 코드가 수정됐다고 보지 않는다.
- 검증: 로그인 후 보호 API·SSE·WS, 로그인 세션과 면접 ID의 분리, 만료·유실 후 재로그인, Redis 장애와 만료 구분, 로그아웃 후 접근 차단·반복 로그아웃, 쿠키/Redis 만료 연장을 확인한다.
- #40의 세션 설정은 재사용하되 함께 남아 있는 JWT 설정은 구현 반영 시 정리한다. #41의 사용자·GitHub 테이블에 세션 저장용 migration을 추가하지 않는다.

## 대체 관계

[AI 0010](../../ai/decisions/0010-sprint1-interface-runtime-decisions.md)의 HttpOnly `accessToken` 인증 부분과 기존 FE·BE JWT 안내만 대체한다. 0010의 WS 식별자·메시지·복구 등 나머지 결정과 기존 로컬 정책은 유지한다. 과거 결정 원문과 변경 이력은 보존한다.
