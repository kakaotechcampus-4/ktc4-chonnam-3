# BE 구현·검증 기록

구현 범위와 실제 실행 결과를 기록한다. 기능 요구사항은 각 features 문서와 task 문서를 따른다.

## 2026-10-08 — PR #79 리뷰 반영

기준은 #79 `9cd8189`와 develop `4a3187e`다. 원본 브랜치·커밋을 보존하고 별도 게시용 브랜치에서
최신 develop으로 재배치했다. 충돌한 이 문서의 #85·Task 9 기록은 모두 보존했다. #44는 이미 병합됐고,
FE 업로드 오류명도 #96에서 정정됐다. 아래 이전 날짜의 Draft·실패 기록은 당시 상태로 남긴다.

### 변경 범위

- `posting_service.py`: 공고 원문의 NUL을 수집 단계에서 검증해 `jd_fetch_failed`로 기록한다.
  원문 스냅샷·TEXT·태그 배열·요구사항 및 추출 실패 기록에 오염된 문자열을 넘기지 않는다.
  raw_url의 NUL도 정규화 전에 거절하며 실제 DB 장애는 수집 오류로 숨기지 않는다.
- `posting_queries.py`·service: URL 잠금 안에서 미참조 실패 행만 재사용한다. 오류·원문·시도 시각을
  갱신하고 이전 시도의 늦은 완료는 무시한다. 성공 자료·기존 run/면접 참조와 HTTP 재시도는 유지한다.
  보존 정책은 [ADR 0006](decisions/0006-task09-failure-records.md)에 기록했다.
- `documents/service.py`: NUL을 제거하고 `/`·`\\` 경로를 제외한 표시용 파일명만 저장한다.
  한글·대소문자·긴 파일명과 기존 확장자·용량 검증은 유지한다. 새 길이 제한은 만들지 않는다.
- 신규 테스트 32건: NUL 13건, 실패 상태 10건, 비기본 TTL 3건, 파일명 6건.
  2일 TTL의 경계·만료뿐 아니라 저장 직전 재확인에도 전달값이 적용되는지 검증한다.
- 공개 API·enum과 기존 `0002_posting_versions` migration은 유지한다. 새 migration은 없다.

### 실행 결과

Windows/Python 3.12, locked 의존성, 전용 PostgreSQL 15·Redis로 실행했다. 외부 HTTP·LLM은 mock한다.

| 작업 디렉터리 / 기준 | 검증 | 결과 |
| --- | --- | --- |
| 보존 통합본 / develop + #79 + 이번 수정 | 전체 `pytest -q` | 749 passed, skip 0, 237.21초 |
| 게시용 브랜치 / backend | Task 9 기존·신규 회귀 10개 파일 | 96 passed, skip 0, 126.24초 |
| 게시용 브랜치 / backend | `uv sync --locked --offline` | 통과 |
| 게시용 브랜치 / backend | Ruff check·format·mypy app | 통과, 형식 226파일·타입 126파일 |
| 게시용 브랜치 / 루트 | 공통 계약 검사 | 2스키마·부분 OpenAPI·fixture 7개 통과 |
| 두 작업 디렉터리 | 전체 추적·신규 파일 내용 대조 | 509파일 일치, 미병합 선행 코드 추가 없음 |
| 수정 전 → 수정 후 회귀 | NUL·실패 상태·파일명 | 각각 기존 오류 재현 후 통과 |
| 외부 환경 | 실제 Wanted·LLM 호출, 브라우저 E2E, 운영 배포 | 미실행 |

### 계약·후속 연결

- #108 `2543e74`의 worker는 settings를 읽어 `fetch_posting(reuse_ttl_days=...)`에 전달한다.
  #79 서비스는 기본 인자를 유지한다. 실제 worker 전달 경로의 통합 회귀는 #108의 검증 범위다.
- 열린 develop PR 14개를 대조했다. 핵심 수정 파일과 신규 테스트는 겹치지 않는다. #108의 분석 router와
  #79 문서 router, #81·#82의 다른 설정 항목 및 공통 문서 추가 구간은 후속 병합에서 함께 보존한다.
- #77의 요구사항 추출 개선과 #99의 AI 도메인 분류, #80·#81·#108의 실행 연결은 복사하지 않았다.
  이 검증은 해당 미병합 PR을 포함한 전체 서비스 연결이나 실제 LLM 품질 검증을 뜻하지 않는다.

## 2026-09-27 — PR #45 GitHub 수집 리뷰 반영

관련 PR: [GitHub 수집 #45](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/45).
검토 기준은 #45 `cbd6bae`, 통합 검증 기준은 develop `aaee6a8`(#50·#67 병합 포함)이다.

### 변경 범위

- `integrations/github/client.py`: Retry-After를 우선하고 primary quota가 소진됐을 때만
  reset을 사용한다. 나머지 제한 응답에는 60초 대기를 전달한다.
- `pipeline/steps/repo_detail.py`: rate limit과 무효 토큰 모두 저장소 순회를 중단하고,
  확보한 데이터와 미호출 저장소의 중단 원인을 보존한다.
- `RepoDetail.repository_inaccessible`: 저장소 단위 languages 404를 명시적으로 전달한다.
  후속 수집에 성공하면 이를 해제한다. 503·timeout·README/브랜치 404만으로 제외하지 않는다.
- `pipeline/steps/repo_select.py`: 제외 후보와 첫 배치 밖의 정상 후보까지 모두 보존한다.
  eligible 후보에서 포트폴리오 최대 3개·기본 순위 최대 5개·기여도 최대 2개를 각각 고른 뒤
  중복 제거하며, 첫 배치의 `batch_no`·`batch_rank`·`selection_reason`을 별도로 표시한다.
  포트폴리오 언급은 필터를 우회하지 않는다. 접근 불가 재분류 시 수집 당시 배치 이력은 유지한다.
- 기여도 순서는 호출부가 근거로 제공한다. 정보가 없거나 후보가 겹쳐 비는 자리는 임의로 채우지
  않는다. 기존 pushed_at 기반 순위를 유지하며 task-10의 종합 점수·기여도 산정·DB 저장은 포함하지 않는다.
- 중복 `pipeline/initial_sync.py`·`workers/tasks/initial_sync.py`는 develop 골격으로 복원하고
  해당 구현 전용 테스트를 제외했다. 토큰 복호화·폐기 상태 영속화·초기 동기화·큐 연결은 #57에서
  통합한다. 이번 분리는 해당 경로의 롤백·부분 저장 문제를 수정 완료했다는 뜻이 아니다.
- 공개 API·DB schema·enum·의존성은 변경하지 않았다. 필요한 오류·선택 경계에 한국어 주석을 추가했다.

### 실행 결과

Windows, Python 3.12, uv locked 환경에서 실행했다. 외부 GitHub 응답은 MockTransport를 사용했다.

| 작업 디렉터리 / 기준 | 검증 | 결과 |
| --- | --- | --- |
| `backend`, 수정한 PR 브랜치 | 전체 pytest, 전용 PostgreSQL 연결 | 384 passed, skip 0 |
| `backend`, develop 통합본 | 전체 pytest, 전용 PostgreSQL 연결 | 385 passed, skip 0 |
| `ai`, develop 통합본 | 전체 pytest | 167 passed |
| `backend`, 양쪽 기준 | Ruff check·format, mypy app | 통과; format 180개, mypy 115개 파일 |
| 루트, develop 통합본 | 공통 계약 검사 | schema 2개·부분 OpenAPI·정상/오류 fixture 7개 통과 |
| 회귀 검증 | 수정 전 실패를 확인한 뒤 동일 사례 재실행 | 제한 대기·토큰 중단·접근 증거·후보 보존·배치 규칙 통과 |
| 독립 검토 | 코드·테스트·DB nullable 계약·중복 범위 | 추가 수정이 필요한 결함 없음 |

PostgreSQL은 전용 로컬 테스트 DB의 임시 schema만 사용했다. 새 DB 쓰기 기능을 검증한 것은 아니다.
실제 GitHub 장애·rate limit을 유발하지 않았으며 서비스 전체 연결이나 배포 검증 결과도 아니다.
공통 계약 스크립트는 부분 형식 검사다.

### 후속 연결

- [#57](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/57)은 #45의 dataclass 반환값과
  저장 직렬화를 맞추고, 인증·작업 ID 중심 worker와 수집 기능을 함께 보존해야 한다.
- 상세 수집 호출부는 전체 후보 중 `filter_status='eligible'`이고 `batch_no=1`인 항목을 사용한다.
  기여도 근거 공급·종합 ranking·후속 page 저장은 task-10에서 연결한다.
- [#68](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/issues/68)의 run partial/failed,
  Redis 제한 기록·SSE 연결은 별도 작업이다. README의 중요한 섹션 중심 축약 정책도 후속 범위다.

## 2026-10-13 — PR #114 호출 주소 누락 방지

검토 기준은 #114 `7c1746f`, 통합 기준은 develop `bbe0121`이다. 아래 10월 9일 기록은 당시
결과로 보존한다. 기존 PR 브랜치에 후속 변경만 추가하며 미병합 소비자 구현은 게시하지 않는다.

- `call_model`의 `base_url` 기본값을 없애 주소 생략 시 HTTP 요청 전에 실패하게 했다.
  공식 주소 기본값은 `LLMSettings`에 유지하고, L1은 검증된 주소·토큰을 함께 전달한다.
- `partial`을 실제 호출하는 누락 회귀는 수정 전 실패를 확인한 뒤 통과했다. 기존 gateway와
  AI 경계 테스트의 직접 연결 주소도 명시했다. 재시도·공유 예산·DB prompt 모델은 유지한다.
- L1은 `Settings.require_llm()`부터 실제 어댑터·gateway를 거쳐 직접/프록시 주소와 인증 정보를
  검증한다. 모든 HTTP는 fixture 토큰과 `MockTransport`를 사용하며 실제 LLM은 호출하지 않았다.
- 이 문서의 기존 기록을 모두 보존하며 #114 기록의 삽입 위치를 조정했다. develop이 추가한
  #79·Task 9 기록과 같은 위치에 삽입해 발생하던 문서 충돌을 피한다.

| 검증 대상 | 이번 실행 결과 |
| --- | --- |
| #114 수정본 BE 전체 `pytest -q` | 585 passed, 141 skipped; DB·Redis 환경을 지정하지 않은 전체 실행 |
| #114 수정본 BE Ruff·format·mypy | 통과; format 214파일, app 118파일 및 추가 scripts 3파일 |
| #114 수정본 AI 전체 `pytest -q` | 193 passed |
| 공통 계약 검사 | schema 2개·부분 OpenAPI·fixture 7개 통과; 전체 호환성 검증은 아님 |
| develop + #114 수정본의 설정·gateway·AI 경계·LLM task 검사 | 249 passed, skip 0; 격리 PostgreSQL 프롬프트 검사 포함 |
| 별도 #82·#119 소비자 보완 통합본 | 연결 관련 129 passed, AI 213 passed; 변경 파일 Ruff·format과 gateway/어댑터 mypy 통과 |

첫 BE 전체 실행에서 테스트 helper의 URL 누락으로 17건 실패해 세 호출을 보완했다. PostgreSQL
검사는 테스트 서버 포트 불일치로 16건 연결 오류가 있었으며, 포트·준비 상태를 확인한 뒤 같은
통합 검사 249건을 다시 실행해 모두 통과했다. 위 표는 보완 후 결과다.

최신 develop의 `tests/test_seed_all.py`는 `app.db.session.dispose_engine` 부재로 수집이
중단된다. 순수 develop에서도 확인한 기존 문제이며 이번 PR에서 수정하거나 테스트를 제외해
전체 통과로 보고하지 않는다. 별도 소비자 통합본에서 이 수집 오류를 제외한 추가 진단은
824 passed, 304 skipped, 74 setup errors였고, 오류 74건은 Task 10의 `TEST_DATABASE_URL`
미설정이었다. 관련 연결 검사 통과와 전체 서비스 검증을 구분한다.

#82 `0e973f3`·#119 `3f945d3`의 어댑터는 주소 전달이 필요하다. 로컬에서 각 어댑터와 회귀
총 4파일을 보완해 누락 실패 4건을 재현·해결했고 #82의 `attempt_sink`도 보존했다. 원격 두 PR은
변경하지 않았다. #114 반영 후 각 PR을 최신 develop에 맞추고 해당 보완을 반영·재검증해야 한다.

## 2026-10-09 — 현재 프록시 환경 설정과 L1 실행 연결

기준 develop `4a3187e`, 원본 작업 브랜치 `fix/llm-proxy-env`.
원본을 보존하고 같은 develop에서 `fix/llm-proxy-config` 게시용 브랜치를 구성했다.
이번 신규 변경 18개 파일만 옮겼으며 실행 코드·테스트는 원본과 일치한다.

### 변경 범위

- `Settings.require_llm()`이 `PROXY_TOKEN`·`CHAT_PROXY_URL`을 함께 선택한다. 일부만 설정하면
  호출 전에 실패하고, 프록시 설정이 없으면 기존 OpenAI 직접 연결을 유지한다.
- 검증된 HTTPS 기본 주소를 공통 gateway와 L1 어댑터에 전달한다. 프록시 앞 경로와 기존
  Responses 요청·strict JSON·재시도 예산을 유지한다. 주소·토큰은 설정 repr에서 숨긴다.
- `OPENAI_MODEL`은 점검·등록 기본 모델로 우선 적용하며 실제 작업의 DB prompt 모델을
  덮어쓰지 않는다. 모델·본문 변경은 새 version으로 등록해 L1 캐시를 구분한다.
- 고정 일곱 v1 seed를 보존하면서 `register_prompt_versions`와 명시적 등록 CLI를 추가했다.
  같은 version의 다른 내용은 거절하며 부분 등록·활성 전환·충돌 처리를 transaction에 묶는다.
- `python -m scripts.check_llm`은 일반 설정 로더와 실제 L1 경로로 합성 저장소 1건을 분석한다.
  임시 URL 변경이나 별도 공급자 구현이 없다. DB는 쓰지 않으며 호출 전 budget·항목 검증
  실패도 안전한 분류로 출력한다. 설정과 실행 방법은 `backend/docs/llm-connection.md`에 둔다.
- 로컬 `.env`의 비밀값은 유지하고 누락된 네 실행 상한만 1건 점검용으로 보완했다.
  `.env`와 원본 백업은 ignored 파일이며 게시 대상에 포함하지 않는다.

### 실행 결과

Windows, Python 3.12.14, locked 의존성 환경. 자동 테스트의 외부 API는 가짜 응답을 사용했다.
PostgreSQL 15·Redis 7은 전용 테스트 DB와 Redis 15에서 검증했다.

| 검증 | 결과 |
| --- | --- |
| 수정 전 관련 기준선 | 133 passed |
| BE 전체 테스트 — 게시본 단독 재검증 | 724 passed, skip 0 |
| 독립 검토 후 점검 명령 오류 분류 회귀 | RED 2 failed → 5 passed (기존 3건 포함) |
| AI 전체 테스트 | 193 passed |
| BE Ruff·format·mypy | 통과; format 214개, app 118개 및 추가 scripts 3개 |
| AI Ruff·format·mypy | 통과; format 40개, mypy 11개 |
| 공통 계약 검사 | schema 2개·부분 OpenAPI·정상/오류 fixture 7개 통과 |
| 실제 L1 호출 — 원본의 동일 실행 코드 | `gpt-6-luna`, 성공 1건·실패 0건, 1회 호출, 4,485ms, 입력 375·출력 330 token |
| 프롬프트 등록 | 격리 PostgreSQL에서 부분 등록·동일 버전 충돌·멱등성·commit/rollback 검증 |
| 독립 코드 검토 | 오류 원인 표시 누락 1건을 수정하고 재검토 완료 |

실제 호출은 원본 작업공간의 `.env`를 `get_settings()`로 읽고 일반 HTTP client를 사용했다. 진단용
`l1_connection_check` 프롬프트와 합성 입력으로 검증했으며 활성 DB prompt나 사용자 자료를
변경하지 않았다. 기록한 모델은 로컬 선택값이며 팀 기본 모델 변경 결정이 아니다.
게시본에는 비밀 `.env`를 복사하지 않았다. 원본의 실제 호출 기록과 게시본의 PostgreSQL·Redis
자동 테스트를 구분하며 게시 과정에서 외부 모델을 중복 호출하지 않았다.

### 선행 PR과 검증 한계

- 미병합 #82의 Director 어댑터 보완은 별도 `fix/llm-proxy-director` 작업공간에 보존했다.
  #82 `0e973f3` + develop `4a3187e` 로컬 통합본에 공통 설정·gateway 변경과 URL 전달을 적용했다.
  #82의 `attempt_sink`를 보존했고, 전용 회귀를 포함해 BE 826개·AI 193개 테스트와
  Ruff·format·mypy가 통과했다. 실제 Director 모델 호출은 수행하지 않았다.
- Director 전용 변경은 어댑터·회귀 테스트 두 파일이며 원본 PR·브랜치를 변경하지 않았다.
  해당 선행 구현을 이번 develop 기반 브랜치에 복사하지 않았다.
- #80의 L1 pipeline과 #108의 API/worker는 `LLMSettings`를 기존 L1 어댑터에 전달하는
  경계를 사용한다. 이번 공통 연결을 적용할 수 있으나 해당 PR들을 병합하거나 전체 서비스
  E2E를 실행하지 않았다. 앞의 Director 통합 테스트 수치를 이 경로의 검증으로 사용하지 않는다.
- 실제 DB 저장까지 포함한 L1 실행, 운영 프롬프트 품질, 다수 저장소 배치의 예산·품질은
  이번 실제 모델 점검 범위에 포함하지 않는다. 공통 계약 검사는 부분 형식 검사다.

## 2026-10-04 — release PR #85 멘토 리뷰 반영 (GitHub 목록 수집)

관련 PR: [release #85](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/85). 브랜치 `refactor/week7-be`.

### 변경 범위

- `integrations/github/client.py`: Link `rel="next"`는 API origin(https·host·port, userinfo 없음)과
  `/user/repos` 경로이고 page가 증가할 때만 따라간다. 아니면 요청 전에 `repo_unreachable`로 실패한다.
  목록 요청은 redirect를 따르지 않고, `request()`는 API origin이 아닌 URL에 토큰을 보내지 않는다.
- 목록 응답이 list가 아니거나 항목 필수 필드가 틀리면 빈 목록 대신 실패한다. 오류 계층은
  [error-reasons.md](../../backend/docs/error-reasons.md#github-수집-오류의-계층)에 정리했다.
- `list_repositories()`는 repo ID 기준으로 중복을 제거한다(위치 유지, 값은 나중 응답). 이에 따라
  `public_repo_count`도 실제 저장 개수와 같다. 429는 헤더가 없어도 `rate_limited`로 분류한다.
- 목록 항목의 `private` 필드를 필수로 보게 되어 `test_github_client.py` 응답 fixture에 추가했다.

### 실행 결과

| 작업 디렉터리 | 검증 | 결과 |
| --- | --- | --- |
| `backend` | `pytest -k "not postgres"` (TEST_DATABASE_URL 미설정) | 497 passed, 97 skipped. 수정 전에는 기존 계약 테스트 18개 실패 |
| `backend` | `ruff check`, `ruff format`, `mypy app` | 통과 |
| `backend` | PostgreSQL 연결 테스트 | 미실행 |

### 남은 작업

- `queued` 작업의 큐 등록 복구(reaper)는 `backend/docs/pipeline.md` 2절 설계이며 아직 구현되지 않았다.
  DB 커밋 뒤 enqueue 전에 프로세스가 종료되고 재로그인도 없으면 reaper 구현 전까지 복구되지 않는다.

## 2026-09-28 — develop 기준 Task 9 API·공고 저장 Draft

상태: **선행 구현에 의존하는 Draft**. 전체 Task 9 완료나 develop 단독 실행 가능 상태가 아니다.
기준은 develop `7e54047`이며, 사용자가 선행 PR을 병합하지 않고 신규 Task 9 변경만 분리하도록 승인했다.
내부 저장 설계는 [BE ADR 0002](decisions/0002-task09-persistence.md)를 따른다.

### 포함한 범위

- `backend/app/features/documents/`: 포트폴리오 Preview API, 파일 형식·크기 검사, 본문 URL 보존과
  규칙 축약, 추출 결과·문서 소유자 저장, 기존 두 필드 응답을 제공하는 연결 코드.
- `backend/app/features/analysis/posting_service.py`, `posting_queries.py`: Wanted URL 정규화,
  성공본 7일 재사용, 동일 내용 ID 유지, 변경 내용의 새 ID, 실패 기록과 공고·요구사항 원자 저장.
- `backend/migrations/versions/0002_posting_versions.py`: 같은 URL의 이전 자료를 보존하도록 UNIQUE를
  조회 인덱스로 변경하며, 이력이 있으면 자료를 삭제하는 downgrade를 거절.
- 해당 API·저장·migration의 신규 검사, 문서 텍스트 상한 설정, 문서 router 등록과 계약 설명.

### 선행 의존성과 검증 범위

- [PR #57](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/57)의 `current_user`와 앱·DB 자원
  연결을 소비한다. 인증·런타임 구현 자체는 이 Draft에 포함하지 않는다.
- [PR #44](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/44)의 기존 PDF/DOCX/TXT/MD 추출
  함수와 GitHub URL 추출 API를 소비한다. 선행 추출기, 파서 의존성·잠금 파일, 기존 추출 테스트는
  가져오지 않는다. 본문에 없는 링크 대상 추출을 전제로 하지 않는다.
- 선행 구현이 없는 develop 기반 Draft에서는 인증·파서 import가 앱 기동과 관련 pytest 수집을
  막는다. 이 상태를 통과로 보고하거나 대체 인증·파서를 추가해 선행 의존성을 숨기지 않는다.
- 로컬 전용 결합 검증은 #57 `0bd0ccd`와 #44 `a0c1ba7`을 별도 환경에 결합해 수행한다.
  결합 결과는 이 Draft의 단독 실행 결과와 구분한다. 선행 추출기·의존성·fixture는 수정하지 않았고,
  두 버전의 앱 구성 차이에 맞춰 문서 router import·등록 두 줄만 연결했다.
  이전 작업의 테스트 수치와 성공 기록은 이 분리본의 검증 근거로 옮기지 않는다.

Windows / Python 3.12.14에서 이번 분리본을 새로 검증했다. 결합 테스트에는 전용 PostgreSQL 15와
Redis를 사용했으며 GitHub·Wanted HTTP는 mock했다. LLM·운영 DB·실제 브라우저 흐름은 검증하지 않았다.

| 환경 / 위치 | 명령 | 결과 |
| --- | --- | --- |
| Draft / `backend` | `uv sync --locked --group dev` | 통과; 선행 PR의 패키지·잠금 파일을 가져오지 않음 |
| Draft / `backend` | `ruff check .`, `ruff format --check .` | 통과, 형식 검사 187개 파일 |
| Draft / `backend` | `mypy app` | 실패: 3개 파일의 7개 오류, 모두 #44 추출 인터페이스·#57 `current_user` 부재 |
| Draft / `backend` | `python -m pytest -q` | 실패: `conftest`가 앱을 import할 때 `current_user` 부재로 수집 전 중단 |
| 로컬 결합본 / `backend` | `python -m pytest -q` | **611 passed, skip 0**; 실제 DB의 API·공고 동시성·migration 왕복 포함 |
| 로컬 결합본 / `backend` | `ruff check .`, `ruff format --check .`, `mypy app` | 통과, 형식 검사 213개·타입 검사 126개 파일 |
| Draft / 루트 | `python .claude/scripts/check_contracts.py` | schema 2개·부분 OpenAPI·정상/오류 fixture 7개 통과; 전체 API 호환성 검증은 아님 |

검증 도구는 `.claude/scripts/requirements-checks.txt`로 전용 가상환경에 설치했다. Ruff의 내부
패키지 분류만 명시해 선행 모듈 유무에 따라 import 정렬 결과가 달라지지 않게 했다.

### 보존한 이전 작업과 후속 범위

- 원본 Task 9 커밋 `0e3c7d3`와 닫힌 [PR #78](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/78)을
  보존한다. 이 Draft를 만들기 위해 원본 커밋이나 해당 PR의 이력을 다시 쓰지 않는다.
- 원본 작업의 PDF/DOCX 숨은 링크 추출, PDF 손상 처리, DOCX 구조 보완은 이번 분리본에서 제외하고
  추출기 후속 작업으로 남긴다.
- [PR #45](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/45)의 최신 포트폴리오 필터 우회
  변경 `e3cc0c7`은 포함하지 않는다. 후보 매칭과 필터 정책의 적용·검증은 별도 작업이다.
- FE의 업로드 형식·자소서 처리 등 기존 실행 코드 수정 보류를 유지한다. 문서 설명 변경만으로
  화면과 실제 API의 연결 완료를 주장하지 않는다.
- 분석 run·worker의 단계 실행, 공고 ID와 문서 ID 연결, 실패 알림은 Task 11에서 이어간다.
- #77 JD 추출 규칙과 #74 도메인 분류 연결은 별도 후속이며 현재 공고의 `domain_category`는 `None`이다.
- 선행 PR 병합 뒤 `.env.example`·설정·앱 구성과 공용 구현 기록을 함께 보존하며 통합해야 한다.
  `implementation.md`의 다른 PR 기록을 이 파일로 덮어쓰지 않고 Task 9 항목을 합친 뒤 다시 검증한다.

## 2026-09-30 — Task 11 단계 경계를 위한 Task 9 후속 보완

기존 PR #79를 유지하고 최신 develop 위로 재배치했다. 인증·GitHub 수집은 이미 develop에 있으며,
문서 router 등록과 #45의 기존 구현 기록을 함께 보존했다. 재작성 전 원본은
`backup/task09-before-followup-20260930`(`3d55a34`)에 보존했다.

- `fetch_posting()`은 7일 캐시 확인 또는 HTTP 원문 수집만 수행한다.
- `complete_posting()`에서 요구사항을 추출·저장하며, 기존 `get_or_fetch_posting()`은 두 함수를
  순서대로 호출한다. Task 11 #81의 `jd_fetch`/`jd_extract` 호출과 일치한다.
- URL 잠금 아래 재검사, 불변 공고·요구사항 ID, 실패 기록, 캐시 TTL은 유지한다.
  HTTP 중에는 DB transaction을 유지하지 않는다. API·schema·migration의 추가 변경은 없다.
- 신규 PostgreSQL 테스트 7건은 변경 전 API 부재로 실패했고 변경 후 통과했다.
  Wanted·JD·문서 Preview 연관 검증은 115건 통과했다.

검증 기준은 `origin/develop fbd46eb`이며, 선행 구현을 로컬 검증 환경에만 결합했다.
전용 PostgreSQL 15·Redis와 HTTP mock을 사용했다. 실제 GitHub·Wanted·유료 LLM·브라우저·운영 배포는 미실행이다.
Task 11 보존 통합본에는 미게시 Task 8 GitHub 보완과 Task 12 SSE 보완도 포함되어 있으므로,
해당 전체 결과를 게시본의 단독 성공으로 해석하지 않는다.

최소 결합본의 GitHub 관련 20건 실패는 수정 없는 develop `fbd46eb`에서 동일한 20건을 실행해
모두 재현했다. 관련 테스트 2개 파일·GitHub 구현 2개 파일의 내용도 양쪽 최소 결합본과 일치한다.
Task 8 후속 범위이며 이번 변경에 가져오지 않았다. Task 12 SSE 후속도 이번 게시 범위 밖이다.

| 환경 | 실행 | 결과 |
| --- | --- | --- |
| 게시본 | `uv sync --locked --group dev` | 통과; 선행 패키지·잠금 파일 복사 없음 |
| 게시본 | `python -m ruff check .`, `python -m ruff format --check .` | 통과; 형식 211파일 |
| 게시본 | `python -m mypy app` | 실패: #44 추출 인터페이스 부재, 2파일 6오류 |
| 게시본 | `python -m pytest -q` | 실패: #44 추출 모듈 부재로 수집 오류 5건 |
| 최소 결합본: 게시본 + #44 `a0c1ba7`의 추출 코드·테스트 | `python -m pytest -q` | 20 failed, 624 passed in 451.70s (0:07:31) |
| 같은 최소 결합본 | Ruff·format·mypy | 통과; 형식 215파일·타입 126파일 |
| Task 11 보존 통합본 + 이번 Task 9·10 변경 | `python -m pytest -q` | 816 passed in 576.90s (0:09:36) |
| 같은 통합본 | Ruff·format·mypy | 통과; 형식 253파일·타입 141파일 |
| 게시본 | 공통 계약 검사 | 2스키마·부분 OpenAPI·fixture 7개 통과 |

최소 결합본은 #44의 parser 의존성이 설치된 검증 전용 Python 환경을 사용했다.
최초 최소 검증은 Task 11 revision이 남은 테스트 DB를 잘못 사용해 setup 오류가 발생했으며,
구성별 새 전용 DB로 분리한 뒤 위 결과를 다시 얻었다. 앱·운영 DB는 사용하지 않았다.

#44 미병합 의존성 때문에 Draft로 표시한다. 숨은 링크·손상 문서 보완, #77 JD 규칙·#74 도메인 분류,
Task 8·12 후속 및 선행 병합 뒤 최종 통합 재검증은 별도로 남는다. 이번 후속은 BE 코드·검증·기록만
수정했으며 기존 PR에 있던 FE 설명 문서 외에 FE 변경을 추가하지 않았다.
