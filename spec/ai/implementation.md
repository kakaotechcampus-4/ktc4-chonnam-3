# AI 구현·검증 기록

AI 작업의 구현·수정 내역, 코드 위치, 실행 결과와 남은 작업을 관리하는 원본이다.
기능 요구사항·초기 설계·검증 방법은 각 명세에, 지속할 결정의 맥락·이유·영향은
[decisions](decisions/README.md)에 보존한다. 문서 역할은
[ADR 0020](decisions/0020-implementation-record-policy.md)을 따른다.

## 2026-10-06 — task-10 Director 후보 복구 분류 경계

관련 작업: AI task-10 잔여([Director 질문 결정](../../ai/docs/task-10-director.md)). PR 번호는 생성 후 기록한다.

### 기준과 변경

- 기준은 origin/develop `ef1a48d`다. `contracts.py`, 기존 `CandidateRecovery` 필드, 공개 enum·WS 이벤트, DB, 의존성은
  변경하지 않았다. 기존 오류 코드(`director_input_invalid`, `director_candidate_invalid`,
  `director_review_failed`, `director_review_timeout`)와 `ModelResult[ContractChecked[Question]]` 형태를 유지했다.
- `ai/src/devon_ai/agents/director/agent.py`: `QuestionReviewer`의 반환 타입을 `QuestionReview | CandidateRecovery`로
  넓혔다. 기존 검토기는 그대로 호환된다. 검토기가 `CandidateRecovery`를 반환하면 후보는 반환하지 않고
  `semantic` 실패로 변환하며 분류는 `error_code`(`director_candidate_rewrite`, `director_candidate_replan`,
  `director_no_valid_candidate`)로만 전달한다. `candidate_recovery(failure)`는 실패에서 `CandidateRecovery`를 복원한다.
- 분류는 실행 권한이 아니다. 생성 모델·검토기를 다시 호출하지 않고 시도 기록은 그대로 보존하며, 상한 소진이나
  분류 결과로 검증 실패 질문·정상 `finish`를 내보내지 않는다. 형식이 맞지 않는 검토기 반환값(dict·문자열)은
  기존대로 `director_review_failed`다.
- 테스트(`test_director.py`에 4개 함수·11 케이스 추가): 세 분류의 실패 변환·무재호출·시도 기록, 목적이 바뀐 문장("수정 특성 확인"
  목적에 "TTL은 몇 분인가요?")은 분류되어 전달되지 않고 정상 문장은 `ContractChecked`가 되는 대조, 비구조 반환,
  다른 실패의 비분류.
- 이번 범위에서 제외했다: 목적 자동 선정, ask/retrieve/finish 결정 생성, 재작성·재계획 실행(AI-L04). 허용 Persona와
  남은 질문 수는 기존처럼 Controller 입력이며 배분 계산·10번째 질문 차단·finish 수용은 BE 책임이다.

### 실행 결과

Windows, Python 3.12, 격리 worktree의 locked 환경에서 실행했다.

| 작업 디렉터리 | 명령 | 결과 |
| --- | --- | --- |
| 루트 | `uv --directory ai run --locked ruff check .` / `ruff format --check .` | 통과 / 통과 |
| 루트 | `uv --directory ai run --locked mypy` | 통과(소스 11개 파일) |
| 루트 | `uv --directory ai run --locked pytest` | 204 passed(기준선 193 + 신규 11) |
| 루트 | `uv --directory backend run --locked pytest tests/agents/test_ai_package_imports.py tests/integrations/test_director_boundary.py` | 16 passed |
| 루트 | `python .claude/scripts/check_contracts.py` | 미실행(공통 계약 변경 없음) |

### 한계와 후속 작업

- 분류 판단은 주입된 독립 검토기의 몫이다. 코드는 검토기 결과가 이 후보와 결합돼 있는지, 분류 반환값이 구조에 맞는지만
  강제한다. 테스트의 검토기는 합성 대역이며 목적 일치·전제 타당성의 실제 판정 품질은 검증하지 않았다(AI-L01).
- 코드로 결정적으로 막는 것은 기존 입력 검사(허용 Persona·참조·Contract 동일성)뿐이다. 이미 확인한 목적의 반복은
  `HistoryTurn`이 목적을 갖지 않아 코드로 판정하지 않고 검토기 분류에 맡긴다.
- BE 연동은 미실행이다. `backend/app/agents/director/agent.py`(#82)는 `QuestionReviewer`를 타입으로만 쓰므로 변경은
  필요 없다. 새 `error_code`를 소비해 재작성·재계획·실패 안내를 결정하는 부분과 호출 상한은 BE·AI-L04·AI-L09
  합의 대상이다. `spec/ai/contracts.md`는 변경하지 않았다.
- Persona 배분 정책 충돌(공통 0004 vs #97·#82)은 이 변경과 무관하며 AI 코드는 배분을 하드코딩하지 않는다.

## 2026-09-27 — PR #67 JD 분류 계약 리뷰 보완

관련 PR: [JD 분류 category 통일 #67](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/67).

### 기준과 변경

- develop `744a5ad`(#50 병합 포함)과 #67 최초 검토 head `4a8fc09`의 이력을 통합했다.
- `JDRequirement.category`는 `required`/`preferred`/`responsibility`를 그대로 사용한다.
  주요 업무를 `unknown`으로 변환하지 않는 이유를 계약 경계에 한국어 주석으로 남겼다.
- Director 테스트에 7개 사례를 추가했다. 세 분류가 Context 디코딩과 실제 Director의 요청 생성,
  JSON 직렬화에서 보존되는지 확인하고, `unknown` 값과 `category` 없이 구형 필드만 있는 입력을 거절한다.
- AI 검증 기준·BE task-09·OpenAPI 설명을 현행 분류와 맞추고, 공통 ADR 0005에
  AI ADR 0006의 Wanted enum만 대체함을 명시했다. 과거 ADR 본문과 나머지 LLM 정책은 보존했다.
- 이번 보완에서 공개 API 필드·enum, DB schema, Wanted 추출 로직과 의존성은 변경하지 않았다.

### 실행 결과

Windows, Python 3.12, 격리 worktree의 locked 환경에서 확인했다.

| 작업 디렉터리 | 명령 / 시나리오 | 결과 |
| --- | --- | --- |
| `ai` | `python -m pytest -q -p no:cacheprovider` | 167 passed; 신규 회귀 7개 포함 |
| `ai` | 메모리에서 옛 필드·enum으로 되돌린 회귀 검사 | 7개 실패; `unknown`만 재허용하면 해당 1개 실패; 실제 코드에서는 7개 통과 |
| `ai` | `ruff check .`, `ruff format --check .`, `mypy src` | 통과; format 37개, mypy 11개 파일 |
| `backend` | `python -m pytest -q -p no:cacheprovider` | 273 passed, 13 skipped; `TEST_POSTGRES_URL` 미설정으로 PostgreSQL 검사 제외 |
| `backend` | `ruff check .`, `ruff format --check .`, `mypy app` | 통과; format 173개, mypy 114개 파일 |
| 루트 | `.claude/scripts/check_contracts.py` | schema 2개·부분 OpenAPI·정상/오류 fixture 7개 통과 |
| 루트 | `PYTHONUTF8=1`로 `.claude/scripts/tests` unittest | 11개 통과, Windows에서 symlink 생성 불가로 1개 제외 |
| 루트 | 문서 링크·OpenAPI 파싱 비교 | 상대 링크 40개·anchor 7개 유효; OpenAPI는 `JdCategory.description`만 변경 |
| 루트 | 독립 코드 검토·BE 추출 결과의 AI Context 복원 | 추가 결함 없음; 세 분류·`source_field`·`tech_tags` 보존 확인 |

모델 경계는 mock provider로 검증했다. 실제 모델 품질·외부 Wanted API·전체 서비스 연결을
이번 실행에서 새로 검증한 것은 아니다. 공통 계약 검사는 부분 형식 검사다.

## 2026-09-27 — PR #50 계약 검증 재검토 반영

관련 PR: [AI 내부 계약과 순수 검증 경계 #50](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/50).

### 기준과 변경

- develop `c6e0c3c`, #49 `387ba2a`, #50 최초 head `3fe5d07`을 통합했다. #56에서 먼저 반영한
  공통 계약·Director·Model Gateway·BE 소비 코드를 유지하며 기존 PR 이력을 보존했다.
- `ai/src/devon_ai/contracts.py`: 전체 충분성이 null이어도 관찰한 충족·부족 항목을 보존하고,
  공통 decoder가 계약 밖 부가 필드를 제거하는 현행 동작을 유지했다. 두 경계에 한국어 주석을 추가했다.
- `partial`·`insufficient`의 모든 필수 항목을 covered/missing으로 강제하던 조건을 수정했다.
  사유가 있는 판단 보류 항목은 미분류로 남길 수 있다. `sufficient`는 여전히 전체 필수 항목의
  충족을 요구하고, 이유 없는 생략·충분성 모순·잘못된 key·중복·허위 인용은 거절한다.
- `ai/tests/test_contracts.py`: 중첩 부가 필드 제거와 기존 필드 검증, null/부분 충분성의 관찰 보존,
  저장용 직렬화 및 모순된 결과 거절을 보강했다. 새 필드·enum·의존성·DB schema는 추가하지 않았다.
- #49 설계 상태 안내를 보존하고 #50 최초 채택 기록에는 현행 기준으로 대체됐음을 표시했다.
  새 실행 결과는 설계 문서에 추가하지 않는다.
- 열린 #65·#66의 질문 저장·턴 루프는 충분성·관찰 목록을 직접 해석하지 않는다. typed `BasisRef`와
  중첩 `ContributionScope`를 유지하므로 이번 수정에 따른 해당 PR 코드 변경은 필요하지 않다.

### 실행 결과

Windows, Python 3.12, 격리 worktree의 locked 환경에서 실행했다.

| 작업 디렉터리 | 명령 / 시나리오 | 결과 |
| --- | --- | --- |
| `ai`, `backend` | `uv sync --locked --python <Python 3.12 경로>` | 양쪽 성공, lock 변경 없음 |
| `ai` | 수정 전 보류 항목 회귀 검사 | partial/insufficient 2건이 `point coverage`로 실패함을 확인 |
| `ai` | `python -m pytest -q -p no:cacheprovider` | 160 passed; 기존 138개와 회귀 22개 |
| `ai` | `ruff check .`, `ruff format --check .`, `mypy src` | 통과; format 37개, mypy 11개 파일 |
| `backend` | 전용 PostgreSQL의 `TEST_POSTGRES_URL`로 전체 pytest | 285 passed, skip 0; 실제 PostgreSQL prompt 검사 13개 포함 |
| `backend` | `ruff check .`, `ruff format --check .`, `mypy app` | 통과; format 173개, mypy 114개 파일 |
| 루트 | 별도 검사 환경에서 `.claude/scripts/check_contracts.py` | schema 2개·부분 OpenAPI·정상/오류 fixture 7개 통과 |
| 루트 | 독립 코드 검토·문서 로컬 링크·`git diff --check` | 코드 추가 결함 없음, 문서 인코딩 수정 후 확인 |

PostgreSQL은 전용 로컬 테스트 DB의 임시 schema만 사용했다. 테스트 전후 남은 테스트 schema가
없음을 확인했고 직접 시작한 클러스터를 정상 종료했다. 실제 서비스 DB와 `.env`는 변경하지 않았다.
실제 모델의 자연어 평가 품질·답변 분석 생성·WS 전체 서비스 연결은 이번 검증에 포함하지 않았다.
공통 계약 스크립트는 부분 형식 검사이며 전체 공개 API 호환성 검증을 대신하지 않는다.

## PR #56의 현재 범위

관련 PR: [AI task-01~03 기반 및 Director 기본 질문 생성 구현](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/56)

| 영역 | 구현 위치와 범위 | 후속 범위 |
| --- | --- | --- |
| task-01 | `ai/pyproject.toml`, `ai/uv.lock`, `backend/pyproject.toml`: 독립 AI 패키지와 BE editable 설치 | 기능별 서비스 연결 |
| task-02 | `ai/src/devon_ai/contracts.py`: 내부 값 계약, 순수 검증, 저장 값 변환 | DB 존재·소유권·transaction 검증은 BE |
| task-03 | `backend/app/core/config.py`, `backend/app/integrations/llm/client.py`: 단일 환경 진입점, 지연 LLM 설정 검증, HTTP 호출·실패 분류·공유 호출 상한·metadata | 실제 계정 접근, 운영 상한·품질·비용 검증, metadata 영구 저장 |
| prompt | `backend/app/llm_tasks/prompt_loader.py`, `backend/scripts/seed_prompt_versions.py`: 활성 prompt 조회, 7종 seed의 멱등성·불변성·동시성 | 검수된 운영 prompt 등록 |
| Director | `ai/src/devon_ai/agents/director/agent.py`: 준비된 질문 계약을 받아 질문 생성·독립 검토·검증 | 목적 자동 선정, 도구 실행, 실제 검토기, DB·worker·API·WS 연결 |

레포 분석과 JD 분석의 본체를 이 PR에서 완성한 것은 아니다. 위 기반을 소비하는 각 기능 구현과
실제 서비스 연결은 해당 담당 작업에서 이어간다. Director도 준비된 목적의 질문 생성 경로까지다.

## 2026-09-27 — 최신 develop 통합

### 기준과 변경

- 작업 브랜치: `feature/ai-director-define`.
- 통합 전 feature: `b5f8a8ece3a34d807098a803c3557ad186751caf`.
- 통합한 develop: `ec38943722b5fb87132a14b29368a799813f28e9`.
- 기존 공통 조상 `b444c64` 이후의 DB 모델·초기 migration, 공통 오류 처리, API schema·검사,
  CORS 제거 및 develop의 면접 화면 변경을 병합했다.
- 유일한 Git 충돌인 `backend/uv.lock`은 양쪽 `pyproject.toml` 선언을 유지하고 `uv lock`으로
  재생성했다. 기존 패키지 버전은 모두 보존했고 `types-pyyaml`만 새로 추가했다.
  `pyyaml`의 명시적 개발 의존성과 `devon-ai` editable 설치도 유지한다.
- `backend/tests/llm_tasks/test_prompt_postgres.py`는 과거 migration에서 복사한 DDL 대신
  현재 `PromptVersion.__table__.create`로 테이블·제약·인덱스를 생성한다. 테스트별 임시
  schema와 정리 방식은 유지한다. 이 테스트와 전체 migration 검증은 별개다.
- 새 DB session/migration의 `get_settings().database_url` 소비, 일반 앱 기동과 LLM 지연
  설정 검증, CORS 설정·소비자의 동시 제거를 확인했다. AI의 호출 정책·Director 출력 계약은 유지한다.

### 실행 결과

환경: Windows, Python 3.12, uv 0.12.13, 로컬 PostgreSQL 15.19.
아래 결과는 통합한 코드에서 실제 실행한 결과다. 프롬프트 테스트 변경 후 BE 검사를 다시 수행했다.

| 작업 디렉터리 | 명령 / 시나리오 | 결과 |
| --- | --- | --- |
| `ai`, `backend` | `uv sync --locked --python 3.12` | 양쪽 성공 |
| `ai` | `ruff check .`, `ruff format --check .`, `mypy src` | 통과; format 37개, mypy 11개 파일 |
| `ai` | `python -m pytest -q` | 138 passed |
| `backend` | `ruff check .`, `ruff format --check .`, `mypy app` | 통과; format 173개, mypy 114개 파일 |
| `backend` | 명시적 `TEST_POSTGRES_URL`로 `python -m pytest -q` | 285 passed; 실제 PostgreSQL prompt 검사 13개 포함 |
| 저장소 루트 | 검사 의존성을 별도 uv 환경에 주입해 `python .claude/scripts/check_contracts.py` | schema 2개, 부분 OpenAPI, 정상·오류 fixture 7개 통과 |
| `backend` | 격리 DB에 `python -m alembic upgrade head`, `current`, `check` | revision `0001_initial`, 26개 업무 테이블, ORM 대비 추가 변경 없음 |
| `backend` | 실제 migration 테이블에서 테스트 prompt 7종 seed → load → 같은 seed 재실행 | 7종 일치; UUID·시간·본문·활성 상태 보존 |
| `backend` | 격리 DB에서 `downgrade base` → `upgrade head` → `check` → seed/load 재검사 | 업무 테이블 제거·재생성, ORM 일치, 7종 재검사 통과 |

전체 migration 검증은 전용 로컬 클러스터의 새 임시 DB에서만 실행했다. `DATABASE_URL`은 검증
자식 프로세스에만 지정했고 `.env`를 수정하지 않았다. 테스트 prompt는 합성 본문과 `test-model`을
사용했다. 검증 후 임시 DB와 테스트 schema가 남지 않은 것을 확인하고 전용 PostgreSQL을 종료했다.
실제 서비스 DB 적용이나 운영 prompt 등록 결과는 아니다.

### 검증 한계와 후속 작업

- 외부 모델 호출은 mock으로 검증했다. 실제 OpenAI 호출·자연어 품질·비용은 미검증이다.
- 이번 실행에서 FE lint/build는 미실행이다. 현재 실행 셸에서 Node/npm을 찾을 수 없었다.
  develop의 FE 변경을 그대로 수용했으며 별도 FE 구현은 추가하지 않았다.
- 공통 계약 스크립트는 부분 형식 검사다. 전체 API·TypeScript 대응·실서비스 호환성 검증을 대신하지 않는다.
- 기존 설계와 `testing.md`의 과거 기록을 이번 통합에서 일괄 재작성하지 않는다.
  이후 구현 현황과 실행 결과는 이 파일을 갱신한다.

## 2026-09-27 — task-04 L1 호출·재요청과 캐시 판정

### 기준과 변경

- 작업 브랜치: `feature/repo-shallow`, 기준 develop `744a5ad`.
- PR #56 이전에 만든 로컬 커밋(자체 batch 검증 타입)은 `contracts.py`의 L1 계약과 중복돼 폐기했다.
- `ai/src/devon_ai/llm_tasks/repo_shallow.py`
  - `cache_identity`: `(repository_id, "l1", head_sha, prompt_version)`. `analysis_level`은 DB 모델의
    `ANALYSIS_LEVELS = ("l1", "l2")` 값을 쓰며 model은 제외한다. BE `repo_analyze.py` docstring의
    `analysis_level='shallow'`는 DB 제약과 다르므로 BE 연결 때 정정이 필요하다.
  - `analyze_shallow_batch`: 주입된 `model_call`·prompt·limits로 `ModelRequest`를 만들고
    `{"repositories": [...]}` 출력을 `parse_shallow_batch`로 검증한다. 입력에 대응하는 ID가 있는
    schema 실패 항목만 같은 `model_call`로 한 번 재요청하고 semantic 실패는 재호출하지 않는다.
    첫 호출의 시도 수가 2회면 재요청하지 않고, 재요청의 `max_attempts`는 남은 횟수로 제한한다.
    prompt·limits·입력의 타입 오류, prompt 불일치, 빈 입력, 중복 ID는 모델 호출 전에 Director와 같은
    방식(`ModelResult` 실패, attempts 없음)으로 거절한다.
- `ai/src/devon_ai/contracts.py`: `merge_shallow_retry`가 재요청 결과로 식별된 schema 실패만 교체하고
  첫 성공·다른 실패를 보존한다. `parse_shallow_batch`는 L1 계약에 없는 키(L2 관찰·개인 기여 값 등)를
  버리지 않고 해당 항목의 schema 실패로 처리한다. `head_sha` 불일치를 먼저 semantic으로 확정한 뒤 검사해
  다른 ref 결과가 재요청되지 않게 한다. `basis` 내부 키와 `decode` 공통 동작은 바꾸지 않았다.
- `ai/tests/llm_tasks/test_repo_shallow.py`: fake `ModelCall`로 캐시 판정, 순서 무관 대응, provider
  실패(timeout·parse·거부) 전달, 전체 schema 실패, 부분 재요청·결합, semantic 비재호출, 재요청 실패,
  ID 없는 오류 비재요청, L2·개인 기여 키 금지, 호출 전 입력 거절, SHA 불일치 우선 판정, 총 2회
  상한(첫 호출 2회 사용 시 재요청 없음) 검사.

### 실행 결과

환경: WSL2 Linux, uv. `ai`에서 `ruff check .`, `ruff format --check .`, `mypy`(11개 파일) 통과,
`pytest -q` 185 passed. `backend`에서 `tests/agents/test_ai_package_imports.py` 1 passed.

### 해석 기록

- 설계 문서(2026-09-23-ai-foundation.md)의 "첫 배치에서 유효 항목이 있으면 … 실패한 ID만 다시
  요청"을 제한 조건이 아닌 부분 결과 상황의 설명으로 해석했다. 첫 배치에 성공 항목이 없어도 입력에
  대응하는 ID가 있는 schema 실패 항목은 한 번 재요청한다.
- 이유: 출력 전체의 schema 실패는 공통 호출 계층이 한 번 재시도하므로, 모든 항목의 schema 실패도
  재요청해야 두 경우의 처리가 일관된다. 어느 쪽이든 task가 지키는 총 2회 상한은 넘지 않는다.
- 설계 의도가 "성공 항목이 없으면 재요청하지 않음"이라면 `analyze_shallow_batch`에 첫 결과의 성공
  항목 유무 조건만 추가하면 된다. PR 리뷰에서 문서 작성자 확인을 요청한다.

### 검증 한계와 후속 작업

- 실제 provider 호출과 운영 prompt 등록은 미실행이다. AI-L04는 0018로 총 2회·semantic 비재호출이
  채택됐고, 실행 상한 수치는 설정으로 주입해 대표 사례 측정으로 정하는 구현 작업이다. 재요청의 총 2회
  상한은 task가 첫 호출의 시도 수로 직접 지킨다. BE도 한 작업에 같은 `CallBudget`을 묶어 넘기는지는
  BE 연결 작업에서 검증한다.
- AI-L03은 0018로 기존 저장 위치·프로젝트 요약 의미가 채택됐다. BE adapter
  (`backend/app/llm_tasks/repo_shallow.py`)와 `repo_analyze`의 저장 매핑·캐시 조회 구현은 이번 범위
  밖이며 후속 작업이다. L0-b 입력 수집은 BE PR #45 범위다.

## 2026-09-28 — task-04 L1 BE adapter

### 기준과 변경

- 작업 브랜치: `feature/be-repo-shallow-adapter`, 커밋 `f1ab897`. 기준은 위 task-04 L1 커밋(`75f25c0`).
- `backend/app/llm_tasks/repo_shallow.py`
  - `analyze_repositories`: `call_model`에 `CallBudget` 하나를 묶어 `analyze_shallow_batch`에 넘긴다.
    부분 재요청까지 한 작업의 HTTP 요청은 총 2회다. prompt는 service가 `load_active_prompt`로 읽고
    조회 transaction을 끝낸 뒤 넘긴다. 이 모듈은 DB session을 받지 않는다.
  - `to_repo_analysis_rows`: 입력 저장소마다 `repo_analyses` 행 값을 만든다. `analysis_level='l1'`,
    `status`는 `succeeded`/`failed`만 만들며 `partial` 판정은 service 책임이다.
  - 성공 행은 `tech_stack`과 검증된 결과(`result`)를 채운다. 프로젝트 요약의 저장 필드는 BE 합의
    전이라 `summary`는 비우고, 개인 `role_summary`로 매핑하지 않는다(ADR 0006).
  - 실패 행은 요약·기술 기본값을 채우지 않는다. `error_code`는 `llm_timeout`·`llm_parse_failed`·
    `llm_failed` 중 하나이며, 요청 전 입력 크기 상한으로 거절되면 `input_too_large`다.
  - 호출 기록(model·raw_output·token·latency·attempt)은 그 저장소 결과를 만든 시도의 값을 넣는다.
    배치 호출이라 저장소별로 나눌 수 없어 `batch_position`으로 구분한다(`ponytail:` 주석).
- `backend/tests/llm_tasks/test_repo_shallow.py`: 가짜 HTTP 공급자로 성공 배치 행 매핑, schema 실패
  재요청 후 성공 저장, 한 budget의 HTTP 2회 상한, semantic 실패 비재호출·기본값 없음, 전체 timeout,
  호출 전 입력 거절, 입력 byte 상한의 `input_too_large`, 실패 행의 실제 실패 시도 기록, 출력에서
  누락된 저장소의 첫 호출 기록을 검사한다(9개). DB는 쓰지 않는다.

### 실행 결과

환경: WSL2 Linux, uv. `backend`에서 `ruff check .`, `ruff format --check .`, `mypy app`(114개 파일)
통과, `pytest -q` 281 passed, 13 skipped. skip은 모두 `TEST_POSTGRES_URL`이 없는
`tests/llm_tasks/test_prompt_postgres.py`다. `ai`의 `tests/llm_tasks/test_repo_shallow.py` 25 passed.

### 검증 한계와 후속 작업

- `backend/app/features/analysis/pipeline/steps/repo_analyze.py`는 docstring 골격이다. prompt 조회,
  캐시 조회, adapter 호출, run `partial`/`failed` 집계와 `repo_analyses` 저장 연결은 후속 작업이다.
  같은 파일 docstring의 `analysis_level='shallow'`는 DB 값 `l1`로 정정해야 한다.
- PostgreSQL 기준 저장·캐시 검증과 실제 provider 호출, 운영 prompt 등록은 미실행이다. 행 매핑 테스트
  통과를 durable 저장 완료로 보지 않는다.
- 분석 API(`backend/app/features/analysis/router.py`)가 골격이라 L1 결과 조회는 검증하지 않았다.
- 프로젝트 요약의 `summary` 저장 필드는 AI-L03의 BE 합의 후 연결한다.
