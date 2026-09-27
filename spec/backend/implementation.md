# BE 구현·검증 기록

구현 범위와 실제 실행 결과를 기록한다. 기능 요구사항은 각 features 문서와 task 문서를 따른다.

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
