# BE 구현·검증 기록

구현 범위와 실제 실행 결과를 기록한다. 기능 요구사항은 각 features 문서와 task 문서를 따른다.

## 2026-10-06 — Task 14 Director·Evidence 연결과 고정 질문 배분

게시 대상은 [PR #82](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/82)이며 기준 브랜치는 develop이다.
정상 면접의 배분은 [#97의 공통 ADR 0007](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/f2f1011af2aa72c7034948c2c71699cf25e47a18/spec/shared/decisions/0007-fixed-persona-allocation.md)을 따른다.
현재 BE 연결부의 구현·검증 기록이며 자동 면접이나 Task 14 전체 완료를 의미하지 않는다.
저장 경계의 초기 설계는 [ADR 0005](decisions/0005-director-storage-boundary.md)에 보존한다.

### 구현 범위

- `core/config.py`는 총 9문항·기술 6·도메인 2·HR 1만 허용한다. 잘못된 역할·횟수·중복 환경 입력과
  bool/float의 암묵 변환을 거절하고 기존 설정값을 Context 구성에 전달한다.
- `agent_context.py`는 활성 사용자·소유권·면접 상태·답변 이력·선택 저장소의 공개 접근·고정 SHA를 확인한다.
  첫 질문은 HR이며 이후에는 할당이 남은 기술·도메인만 허용한다. 순서와 교대를 강제하지 않는다.
  할당 초과·잘못된 과거 이력·10번째 질문 생성을 거절하며 이미 제시한 Persona를 바꾸지 않는다.
- 미분류 공고에는 [기존 도메인 정책](../ai/decisions/0005-domain-question-policy.md)에 따라 Context에만 활성
  `etc` 프레임을 사용한다. 공고의 `domain_category=NULL`은 보존하고 확인된 category를 임의로 대체하지 않는다.
  도메인 할당이 남았는데 활성 프레임이 없으면 첫 HR 생성 전부터 내부 `domain_frames_unavailable`로 중단한다.
  이때 모델 호출·호출 기록·질문·턴 증가가 발생하지 않는다. 도메인 2회가 끝났다면 프레임 부재만으로
  남은 기술 질문을 막지 않는다. 질문 횟수 외에 프레임 수·축별 할당 규칙을 추가하지 않는다.
- `agents/director/agent.py`는 기존 AI 생성기와 BE LLM gateway를 연결한다. DB prompt loader가 실제
  prompt/model/version을 공급하고 호출자가 독립 `QuestionReviewer`와 준비 계약을 전달한다.
- `agent_service.py`는 동일한 설정 배분으로 생성 전·저장 직전 Context를 검사한다. 질문·계약·근거 연결·턴 증가·
  호출 기록을 같은 transaction에 저장하며 외부 모델 호출 동안에는 DB 잠금을 유지하지 않는다.
  동일 call ID 재전달은 기존 결과를 반환하고 진행 중인 같은 턴의 중복 호출은 거절한다.
  늦은 응답이나 프레임 변경으로 Context가 달라지면 질문을 폐기하고 호출 시도 기록을 남긴다.
- `attempt_sink`는 기존 gateway의 완료된 시도를 보존한다. 재시도·reviewer·최종 저장 중 취소/예외가 나도
  확보한 원문·토큰·모델·prompt version을 기록하며 모델 실패와 적용 폐기를 구분한다.
- `agents/director/tools.py`, `integrations/github/evidence.py`는 DB 승인 경로와 고정 SHA의 일반 UTF-8 파일만 읽는다.
  commit/tree/blob·경로·원문 hash·줄 위치를 검사하고 원문 요청에 인증을 상속하지 않는다.
  redirect·심볼릭 링크·submodule·전역 탐색을 허용하지 않으며 유한 파일/요청/시간/byte 상한과 부분 결과를 보존한다.
- `agent_queries.py`는 소유권·면접 상태·접근·선택 SHA·경로를 재검사하고 근거 원문과 출처를 저장한다.
  같은 SHA의 분석·Evidence만 Context에 넣으며 불완전한 과거 자료는 추측해 복구하지 않는다.
- `0002_agent_storage`는 이 Task에서 필요한 질문 계약·선택 SHA·Evidence 출처 컬럼 및 `llm_call_records`를 추가한다.
  `0001_initial`은 유지하고 과거 자료를 추측해 backfill하지 않는다. 이번 배분 변경 때문에 추가 migration을 만들지 않았다.

### 게시 이력과 변경 범위

사용자가 기존 PR 번호를 유지하고 유동 배분 커밋을 고정 구현으로 교체하도록 요청했다.
기존 게시 HEAD `b262f29`는 `backup/be-task14-flexible-20261006`, 수정본 `8aee453`은
`fix/be-task14-fixed-allocation`에 보존했으며 별도 Git bundle도 만들었다. 최초 개발 원본 `feature/be-agents`도 보존했다.
최신 develop `ef1a48d`에서 별도 게시 이력을 재구성했으며 Context·service·배분 테스트는 최초 추가부터 고정 구현이다.
이전 PR의 14개 커밋은 새 게시 HEAD의 조상이 아니다. 수정본의 runtime/test 24개 파일은 검증 통합본과 동일하다.
설정 파일의 최신 인증 변경을 보존했고, #97 문서·hook이나 다른 미병합 PR의 코드·테스트·의존성을 복사하지 않았다.
공개 REST·WS 계약·Persona enum·FE·AI 제품 소스·의존성은 변경하지 않았다.

### 실제 게시본 검증

2026-10-06, Windows / Python 3.12 / PostgreSQL 15.19 / Redis 7.4.
작업 디렉터리와 BE·AI import 경로를 새 게시 worktree로 지정해 실행했다. 의존성 환경은 기존 locked venv를 사용했다.
`TEST_POSTGRES_URL`은 로컬 `task14_test`의 임시 schema, `TEST_DATABASE_URL`은 별도 `task14_rewrite_publish_test`,
`TEST_REDIS_URL`은 검증 전용 Redis DB 15를 지정했다. 외부 GitHub·LLM·reviewer는 fixture다.
이전 수정본의 557건·통합본의 825건을 이번 게시본 실행 결과로 재사용하지 않는다.

| 작업 디렉터리 | 검증 | 결과 |
| --- | --- | --- |
| `backend` | 전체 `pytest -q -p no:cacheprovider -ra`, 위 세 테스트 환경 변수 지정 | 825 passed, skip 0, 194.55초 |
| `backend` | Ruff check·format·mypy app | 통과, format 222개·mypy 123개 파일 |
| `ai` | 전체 `pytest -q -p no:cacheprovider` | 193 passed |
| 루트 | `check_contracts.py` | schema 2개·부분 OpenAPI·정상/오류 fixture 7개 통과 |
| 게시 이력 | 원본 보존·runtime/test 비교·모든 중간 커밋의 고정 구현·커밋별 줄 수 | 독립 검토 통과 |
| 실제 서비스 | 자동 면접 E2E·실제 모델 의미 품질·운영 seed 설치·배포 | 미실행, 준비·턴 실행·실제 생산자 연결 필요 |

단위 테스트는 첫 HR 이후 가능한 28가지 순서 모두 6/2/1로 완주하는지 확인한다. DB 테스트는 실제 9문항 저장,
중복 재전달·초과 질문·허용 밖 Persona·프레임 부재와 상태 변경을 검증한다. 답변은 fixture에서 직접 저장하므로
실제 답변 처리·정상 종료 검증은 아니다. 공통 계약 스크립트도 부분 형식 검사이며 전체 API 호환성을 증명하지 않는다.

### 후속 연결과 협업 조건

- Task 13의 생성 서비스 #64는 병합됐지만 준비 worker 연결은 남아 있다. 검증된 선택 분석 SHA를 `snapshot_head_sha`에
  고정하고 준비 계약·독립 reviewer를 공급해야 한다. 프레임 부재는 기존 `prep_failed`·`preparing_failed`·재시도에 연결한다.
- Task 15 #65·#66은 질문 저장 책임을 이 서비스와 하나로 통합해야 한다. `compose → save_question`에 그대로 연결하면
  저장이 겹치므로 검증된 Persona·QuestionContract를 덮어쓰거나 턴을 다시 증가시키지 않아야 한다.
  T3/T4·WS 및 9번째 답변 처리 완료 후 정상 종료·`interviewEnd` 검증이 남는다.
- #69 도메인 프레임의 팀 검수와 실제 공급, 별도의 활성 prompt 공급, 실제 reviewer·자동 목적 선정·L2·답변 분석·리포트 연결이 남는다.
  개발 후보를 운영 seed로 자동 활성화하거나 임시 분류기·대체 질문·가짜 승인기를 추가하지 않았다.
  실행 프롬프트와 FE mock의 이전 정책 정합화도 별도 범위다.
- #79·#81의 migration과 합치면 `0002_agent_storage` 및 `0003_analysis_runs` 두 head가 생긴다.
  확인한 migration 사이에 직접 중복 컬럼은 없으며 실제 graph 연결과 기존 DB upgrade·downgrade·재적용을 재검증해야 한다.
  현재 단독 migration 검증은 이 통합 검증을 대신하지 않는다.
- 고정 공고 본문·버전·권한 연결 전에는 `job_posting` 본문 참조를 `director_input_invalid`로 거절한다.
  metadata·languages·commit의 시점별 근거, 전역 탐색, `evaluation_basis`·conflict 저장은 후속 범위다.
- call ID는 같은 논리 요청 재전달에만 재사용한다. 강제 프로세스 종료·DB 장애 뒤 미완료 호출 복구는 worker가
  실제 실행 종료를 확인한 뒤 처리해야 하며 완료되지 않은 원문·토큰을 추측하지 않는다.

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

