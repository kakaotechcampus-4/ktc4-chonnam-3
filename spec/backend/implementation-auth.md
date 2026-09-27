# OAuth·세션 인증 구현·검증 기록

관련 PR: [#57](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/57).
기능 기준은 [서버 세션 결정](../shared/decisions/0003-sprint1-session-auth.md),
[BE task 06](../../backend/docs/task-06-auth.md), [FE 인증 명세](../frontend/features/auth.md)를 따른다.

## 현재 게시 범위와 선행 조건

PR 기준은 `develop`이며 이력 정리 기준은 `7e54047`이다. 기존 #57의 최종 구현 `0bd0ccd`는
[`backup/pr57-before-cleanup-20260928`](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/tree/backup/pr57-before-cleanup-20260928)에 보존한다.
정리한 게시본은 #57의 신규 변경만 포함하며 **선행 구현과 후속 보완이 필요한 Draft**다.
`develop`에 이미 병합된 DB 모델·초기 migration은 다시 변경하지 않는다.

| 구분 | 게시·보존 범위 |
| --- | --- |
| OAuth·세션 | state 일회 소비·브라우저 바인딩·PKCE, GitHub 장기 토큰 암호화, 기존 사용자·계정 보호, Redis 세션과 쿠키의 14일 sliding 갱신, 멱등 로그아웃 |
| 인증 소비 | REST·SSE·WS 공통 인증, `/me`·홈·프로필·면접 이력 조회, 계정 상태 오류와 내부 장애 구분 |
| 초기 수집 연결 | 계정 commit 후 job ID enqueue, dataclass 직렬화·DB 저장, 무효 토큰·재연동 경합·큐 복구, ARQ worker와 해당 회귀 테스트 유지 |
| FE와 프록시 | 공통 401 처리·캐시 정리·재로그인, 알려진 callback 오류 안내·재연동 재시도, MSW, Vite/Caddy 공개 callback 전달과 민감값 로그 제외 |
| 선행 수집 | [#45](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/45)의 DTO·GitHub client·목록/상세 수집·후보 선택과 선행 테스트는 이번 diff에서 제외 |
| 선행 파일의 보완 | `base.py`·`client.py`의 아래 보안 보완과 선행 테스트 수정은 원본을 보존하고 후속 변경으로 분리 |

이력 정리는 공개 API 계약·OAuth 설정값을 바꾸지 않는다. #57의 callback 오류 안내와
FE 리뷰 반영, 공통 오류 처리·세션·초기 수집 회귀 테스트는 그대로 유지한다.
의존성을 숨기기 위한 대체 client나 임시 인증 구현은 추가하지 않는다.

## 분리한 보완과 병합 전 필수 조건

#45 검토 기준은 `e3cc0c7`이다. **#45만 병합해도 기존 #57의 수집 안전성이 모두 복원되지는 않는다.**
다음 후속 변경을 적용하고 초기 수집 연결·보안 회귀를 함께 검증해야 한다.

| 보존 파일 | 후속 적용할 내용 |
| --- | --- |
| [`integrations/github/base.py`](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/backup/pr57-before-cleanup-20260928/backend/app/integrations/github/base.py) | 저장소 ID·private·필드 타입을 엄격히 확인하는 목록 데이터 검증 |
| [`integrations/github/client.py`](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/backup/pr57-before-cleanup-20260928/backend/app/integrations/github/client.py) | HTTPS `api.github.com:443/user/repos` 페이지 URL 제한, redirect·순환 차단, private 제외·중복 제거, 잘못된 JSON·목록 거부, 헤더 없는 429 처리 |
| [`test_github_client.py`](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/backup/pr57-before-cleanup-20260928/backend/tests/integrations/test_github_client.py)·[`test_github_pagination.py`](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/backup/pr57-before-cleanup-20260928/backend/tests/integrations/test_github_pagination.py) | 위 client·페이지네이션 보완의 회귀 검증 |

위 네 파일은 #45 `e3cc0c7`과 보존한 원본의 차이로 복원할 수 있다. 보존 원본을 통째로
덮어쓰지 않고 현재 선행 코드에 보완을 적용한다. 특히 `repo_select.py`는 후속 패치 대상이
아니며 #45의 최신 포트폴리오·후보 선택 정책을 유지한다.

게시본의 `backend/tests/integrations/test_github_auth_integration.py`는 필수 통합 계약을
계속 검사한다. #45만 결합했을 때 보완 부재로 실패하는 테스트를 삭제·skip해 완료로 만들지 않는다.
병합 전에는 최신 `develop`·#45·위 보완을 결합해 BE 정적 검사·전체 테스트와 FE 인증 통합을
다시 실행해야 한다. 선행 코드 결합 환경의 성공을 게시본 단독 성공으로 보고하지 않는다.

## 현재 게시본의 실행 결과

아래 결과는 기존 통합본의 수치를 재사용하지 않고 각 대상에서 새로 확인한다.
GitHub HTTP는 대체하고 DB 기능은 격리 PostgreSQL, 세션·큐 기능은 전용 Redis를 사용한다.

| 대상 | 검증 | 결과 |
| --- | --- | --- |
| 게시본 단독 | BE Ruff check·format | 통과; 188파일 포맷 확인 |
| 게시본 단독 | mypy·전체 pytest | 타입 오류 2개(1파일, 115파일 검사), 테스트 수집 오류 1개로 중단. GitHub base/client 선행 구현 부재 |
| 게시본 + #45 | BE 전체 pytest | 481통과·20실패·skip 0. 비공개 제외·응답 검증·페이지 URL/순환 차단·429 등 분리한 보완의 필요성을 확인 |
| 게시본 + #45 | BE Ruff·format·mypy | 통과; 195파일 포맷·116파일 타입 검사 |
| 게시본 + #45 + 보존 보완 | BE 정적 검사·전체 pytest·AI 전체 pytest | BE 501통과·AI 167통과·skip 0. Ruff·195파일 포맷·116파일 타입 검사 통과 |
| 게시본 FE | lint·build·MSW 인증 화면·Vite 프록시 | 통과; MSW 34개·프록시 4개 통과, skip 0 |
| 선행·보완 결합 환경 | Vite·API·PostgreSQL·Redis·브라우저 인증 통합 | 1개 시나리오 연속 2회 통과; 로그인·세션 유지·재연동·로그아웃·재로그인 검증 |
| 게시본 | 공통 계약·diff 검사 | 2스키마·부분 OpenAPI·fixture 7개 및 공백 검사 통과 |
| 실제 GitHub 계정·운영 HTTPS 배포 | 이번 이력 정리 이후 재검증 | 미실행 |

실행 명령과 격리 환경은 [로컬 OAuth 안내](../../backend/docs/local-oauth.md#검증),
[FE 안내](../../frontend/README.md)를 따른다. 공통 계약 스크립트는 부분 형식 검사이며,
MSW와 GitHub HTTP 대체 브라우저 검증은 실제 GitHub 계정 동의·운영 배포의 성공을 뜻하지 않는다.

게시본과 검증본은 같은 신규 실행 코드·테스트를 사용하고, 별도 검증본에서만 선행 수집 및
보존 패치를 적용했다. PostgreSQL 15 전용 DB·Redis 전용 인스턴스를 사용했다.
검증 명령은 BE/AI의 `python -m pytest -q`, BE의 `python -m ruff check .`,
`python -m ruff format --check .`, `python -m mypy app`와 FE의 `npm run lint`,
`npm run build`, `npm test`, `npm run test:proxy`다. DB 테스트에는 전용
`TEST_DATABASE_URL`·`TEST_POSTGRES_URL`·`TEST_REDIS_URL`을 모두 지정했다.

순환 차단이 없는 선행 수집기를 검사할 때 mock 요청이 무한 반복되지 않도록 두 회귀 테스트에
요청 상한 assertion을 넣었다. 요구하는 URL 차단·오류 결과는 그대로 유지한다.
단독과 결합 환경에서 import 정렬이 달라지지 않도록 Ruff의 `app` 패키지 분류를 명시했다.
브라우저 검증에서 마지막 URL 전환과 문서 교체 사이의 HTML 조회 경합을 두 번 재현했다.
로그인 화면 준비와 전체 HTML의 토큰 비노출 assertion을 유한 재시도로 확인하도록 테스트만
보완한 뒤 동일 시나리오를 두 번 통과했다. 앱 실행 동작이나 보안 assertion 범위는 바꾸지 않았다.

열린 PR 14개를 대조했으며 직접 파일 중복은 #79의 인증/문서 설정·앱·Ruff 네 파일,
#44의 의존성·lock 두 파일, #64의 오류 안내 한 파일이다. 통합 시 양쪽 설정·router·의존성과
오류 계약을 보존해야 한다. `migrations/env.py`는 테스트가 명시한 Alembic URL을 보존하는
보완만 포함하며 DB 모델이나 초기 migration 버전 파일을 다시 게시하지 않는다.

## 원본 구현의 과거 검증 — 현재 게시본 결과 아님

다음은 이력 정리 전 문서에 남은 기록이다. 원본 코드와 함께 보존하며 위 표의 현재 결과와
구분한다. 당시 포함했던 선행 수집과 보안 보완이 지금 게시본에 모두 있는 것은 아니다.

- 2026-09-23: BE pytest 128개, FE MSW 9개, GitHub HTTP 대체 브라우저 통합 1개 통과.
  BE Ruff·format·mypy(116개), FE lint·TypeScript·build, lock·부분 계약·diff 검사를 통과했다.
  state·PKCE·동시 로그인·슬라이딩 세션·로그아웃·초기 수집 복구·비밀값 로그 제외를 검증했다.
- 당시 실제 계정 검증: GitHub 토큰 만료 옵션을 OFF로 바꾼 뒤 사용자가 로그인과 홈 진입을
  확인했다. 토큰 암호화 저장, 인증/비인증 조회, Redis 세션과 쿠키, ARQ의 공개 저장소 29개·
  비공개 0개 저장을 별도 로컬 DB에서 확인했다. 운영 배포 검증은 수행하지 않았다.
- 당시 새 격리 DB의 migration upgrade·비교·downgrade·재upgrade와 Caddy validate·
  Compose config를 확인했다. 기존 운영 DB나 ignored PostgreSQL 55432 이력을 변경한 것이 아니다.
- 2026-09-28 원본 통합 기록: develop `7e54047` + #45 `a327f64`를 포함한 #57 `0bd0ccd`에서
  BE 501개, AI 167개, FE 34개, 브라우저 통합 1개, Vite 프록시 4개 통과를 기록했다.
  정적 검사·Caddy 전달/로그·migration·부분 계약과 별도 복사본의 #64 면접 테스트 32개도
  확인했다. 이 수치의 대상은 정리 후 게시본이나 최신 #45 `e3cc0c7` 결합 환경이 아니다.

## 남은 범위

- #45와 보존한 네 파일의 보완 통합·재검증 전까지 초기 수집 포함 전체 인증 실행 완료로
  판단하지 않는다. 실제 GitHub 계정과 운영 HTTPS 배포는 별도 환경에서 확인한다.
- 홈의 재연동 링크와 callback 고정 안내는 유지한다. 홈·분석 실패 화면 공용 재연동 배너는
  후속 작업이다. 내부 Redis·세션·DB·enqueue 실패는 기존 `500` JSON 오류로 남는다.
- 프로세스 강제 종료 뒤 남은 `running` job의 운영 복구, #68 분석 run 연결, AI 분석·면접·
  리포트 생성은 이번 인증 구현 범위에 포함하지 않는다.
- #64의 `current_user → User`, `get_db`, `app.state.redis: ArqRedis` 연결 계약을 유지한다.
  면접 router 연결·fixture 공용화는 해당 작업에서 진행한다. 면접 준비 재시도가 직접 `api`를
  호출한 뒤 상태 재조회도 네트워크 오류로 실패하는 경로의 전역 인증 처리는 후속 보완 대상이다.
