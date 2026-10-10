# BE 구현·검증 기록

구현 범위와 실제 실행 결과를 기록한다. 기능 요구사항은 각 features 문서와 task 문서를 따른다.

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

