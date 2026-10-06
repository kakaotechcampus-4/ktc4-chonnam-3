# AI 구현·검증 기록

AI 작업의 구현·수정 내역, 코드 위치, 실행 결과와 남은 작업을 관리하는 원본이다.
기능 요구사항·초기 설계·검증 방법은 각 명세에, 지속할 결정의 맥락·이유·영향은
[decisions](decisions/README.md)에 보존한다. 문서 역할은
[ADR 0020](decisions/0020-implementation-record-policy.md)을 따른다.

## 2026-10-06 — 기여 정정 사례 테스트

관련 작업: AI task-09·10 후속 사례([task-09](../../ai/docs/task-09-answer-analysis.md)). 선행: #102(`feature/ai-answer-analysis-v2`) 위에 쌓은 변경이며 PR 번호는 생성 후 기록한다.

### 기준과 변경

- 기준은 #102 head `28e2663`(origin/develop `ef1a48d` 위)다. 새 구조를 만들지 않는 범위(A안)로 `contracts.py`, 필드, enum, 함수 시그니처,
  의존성은 변경하지 않았다. 기존 `analyze_answer`·`validate_analysis`·`generate_question`의 동작을 사례로 고정한다.
- `ai/tests/llm_tasks/test_answer_correction.py`(8건)를 추가했다. 새 구현이 없어 테스트가 먼저 실패하는 단계는 없다.
  - 역할을 물은 질문에 "팀원이 했습니다"는 역할 정보 확인(`covered`)이며 정정은 `contribution_scope=teammate`로 남는다.
  - 같은 정정 답변도 질문이 요구하지 않은 key로 충분이 될 수 없고, 요구 항목을 설명하지 않았다면 `insufficient`다.
    요구 항목 누락·질문 밖 key로 `sufficient`를 주장하면 semantic 실패다.
  - 직접 구현을 전제로 한 질문에 정정이 오면 `needs_clarification`(충분성 null, 사유 보존)을 받아들이고, 사유 없는 상태 변경은 거절한다.
  - 정정은 새 분석으로만 남고 과거 답변 원문·최초 분석은 그대로이며(frozen) 이력 payload에도 원문으로 전달된다.
  - 정정이 반영된 검증된 분석이 다음 질문의 Director 입력(`answer_analysis`, `history`)에 변경 없이 전달된다.
  - 이력에 이미 있는 Turn의 재제출은 거절한다. 이는 AI-L09 복구·재평가 정책을 구현한 것이 아니라 현재 경계일 뿐이다.

### 실행 결과

Windows, Python 3.12, 격리 worktree의 locked 환경에서 실행했다.

| 작업 디렉터리 | 명령 | 결과 |
| --- | --- | --- |
| 루트 | `uv --directory ai sync --locked --python 3.12` | 통과 |
| 루트 | `uv --directory ai run --locked ruff check .` / `ruff format --check .` | 통과 / 통과 |
| 루트 | `uv --directory ai run --locked mypy` | 통과 |
| 루트 | `uv --directory ai run --locked pytest` | 236 passed(#102 기준 228 + 신규 8) |
| 루트 | `uv --directory backend run --locked pytest tests/agents/test_ai_package_imports.py` | 통과 |
| 루트 | `python .claude/scripts/check_contracts.py` | 미실행(공통 계약 변경 없음) |

### 한계와 후속 작업

- 모델 출력은 고정 fixture다. 정정 여부와 어느 주장에 대한 정정인지의 판단, 질문 전제 오류를 `insufficient`가 아닌
  `needs_clarification`으로 구분하는 것은 모델 판단이며 코드는 구조 모순만 거절한다. 전제 오류를 `evaluated`·`insufficient`로
  낸 결과는 구조상 유효해 코드로 막지 못한다. 실제 판정 품질은 검증하지 않았다(AI-L01, 평가는 task-12).
- 다른 task에서 구현·검증: 정정·후속 보완을 반영한 최종 피드백 입력 구성(task-11, 입력·출력 타입이 아직 미채택).
- 합의가 필요하며 이번 범위에서 구현하지 않음: 정정·보완이 가리키는 이전 Turn의 연결 형식(AI-L02·AI-L18), 이전 분석 내용을 이후
  Director와 피드백 입력에 전달하는 방식(`HistoryTurn`은 `analysis_ref`뿐), 사용자 입력 복구·재제출·재평가의 상태 매핑(AI-L09,
  보류). 이 때문에 정정이 Turn 5 이후 질문의 전제에 지속적으로 반영되는 동작은 아직 구현·검증하지 않았다.

## 2026-10-06 — task-09 답변 분석 task 구현

관련 작업: AI task-09([답변 분석](../../ai/docs/task-09-answer-analysis.md)). PR 번호는 생성 후 기록한다.

### 기준과 변경

- 기준은 origin/develop `ef1a48d`다. 기존 `AnswerAnalysis` 열 개 필드, `validate_analysis`, ADR 0014의 값·저장 위치를
  그대로 쓰며 `contracts.py`, 새 enum, WS 이벤트, DB 컬럼, 의존성은 변경하지 않았다.
- `ai/src/devon_ai/llm_tasks/answer_analysis.py`: `analyze_answer`를 추가했다. 모델 호출 전에 코드로
  (1) 확정 질문(`ContractChecked[Question]`)과 `context.current_question_contract` 일치,
  (2) `turn_id`와 `context.current_turn_id` 일치 및 이미 이력에 있는 Turn 거절,
  (3) 빈 답변(초안·전송 오류) 거절 — 정상 제출된 "모르겠습니다"는 거절하지 않는다,
  (4) 조회 허용 위치·Evidence의 repository/ref가 Context 고정 ref와 일치하는지를 검사한다.
  잘못된 입력은 시도 없이 `answer_analysis_input_invalid`로 반환한다. 시도 소진은 `llm_failed`(budget)다.
- 모델 출력은 열 개 최상위 필드만 허용하고(점수 같은 추가 필드는 schema 실패), `validate_analysis`를 통과한
  `ContractChecked[AnswerAnalysis]`만 반환한다. 주입된 `ModelCall`이 validator를 건너뛰어도 같은 질문·답변으로
  다시 검증하며 실패하면 `answer_analysis_invalid`다. 재시도 루프·Tool 실행은 없고 `verification_requests`는 후보다.
- 모델 payload에서 Persona를 제외했다(평가 기준은 Persona별로 다르지 않다). `tool_results`와 `allowed_locations`는
  BE가 권한을 확인해 선택 인자로 전달하며 근거 ID는 주입된 Evidence·ToolResult 항목만 등록한다.
- `ai/prompts/answer-analysis-v1.md`는 검수 전 초안이며 런타임이 읽지 않는다. 운영 prompt 원본·등록은 BE다.
- 테스트: `test_answer_analysis.py`(입력·호출 경계), `test_answer_analysis_cases.py`(대조 사례 1~4),
  `test_answer_analysis_evidence_cases.py`(대조 사례 5~8), 공용 `conftest.py`. 조회·수정 특성 사례는 경계 테스트에 있다. 거절 사례는 의도한 의미 검증 사유로 실패함을 확인했다.

### 실행 결과

Windows, Python 3.12, 격리 worktree의 locked 환경에서 실행했다.

| 작업 디렉터리 | 명령 | 결과 |
| --- | --- | --- |
| 루트 | `uv --directory ai sync --locked --python 3.12` | 통과 |
| 루트 | `uv --directory ai run --locked ruff check .` / `ruff format --check .` | 통과 / 통과(44개 파일) |
| 루트 | `uv --directory ai run --locked mypy` | 통과(소스 11개 파일) |
| 루트 | `uv --directory ai run --locked pytest` | 228 passed(기준선 193 + 신규 35) |
| 루트 | `uv --directory backend run --locked pytest tests/agents/test_ai_package_imports.py` | 1 passed |
| 루트 | `python .claude/scripts/check_contracts.py` | 미실행(공통 계약 변경 없음) |

### 한계와 후속 작업

- 모든 모델 출력은 고정 fixture다. 실제 모델이 세 축을 올바르게 분리하는지, 유사하지만 무관한 코드를 지지
  근거로 채택하지 않는지 같은 의미 품질은 검증하지 않았다(AI-L01). mock 통과는 모델 품질을 뜻하지 않는다.
- 코드가 확인하는 것은 구조·인용 원문·등록 ID·허용 위치다. 필수 대조 사례 7(평가 불가 vs 설명 부족)과
  1(충분·부분·불충분의 실제 판정)은 모델 판단이며 코드는 모순된 조합만 거절한다.
- 대조 사례 8의 "최종 피드백 연결"은 이력 원문·분석 참조를 변경 없이 전달하는 데까지만 검증했다. 정정·후속
  보완의 최종 피드백 입력 구성은 task 3 범위이며, 사용자 입력 복구·재제출·재평가(AI-L09)는 보류다.
- BE 연동은 미실행이다. `backend/app/llm_tasks/answer_analysis.py`는 골격이며 prompt 로드, `answer_analysis`
  PromptSpec 등록, 분석 저장 순서와 transaction, 종료 후 늦은 결과 차단은 BE 책임이다(AI-L12).
  `tool_results`·`allowed_locations` 산출은 Controller가 맡는 제안이다.
- `decode`는 중첩 객체의 계약 밖 필드를 버리는 기존 동작이며 이번에 바꾸지 않았다. 최상위 추가 필드만 거절한다.

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
