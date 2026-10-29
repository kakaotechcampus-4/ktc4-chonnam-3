# AI 구현·검증 기록

AI 작업의 구현·수정 내역, 코드 위치, 실행 결과와 남은 작업을 관리하는 원본이다.
기능 요구사항·초기 설계·검증 방법은 각 명세에, 지속할 결정의 맥락·이유·영향은
[decisions](decisions/README.md)에 보존한다. 문서 역할은
[ADR 0020](decisions/0020-implementation-record-policy.md)을 따른다.

## 2026-10-29 — #126 병합 후 최신 코드의 CI 검증 경로 보완

- 기준 develop은 `e58fff86ef8c876edb220b5e67dd73b4de01c0db`다. #125·#126·#127·#133이 반영돼 있다.
- 과거 Backend CI `40589589648`은 `09a6f77+d0293ec`의 합성 commit `3db9a486`에서
  #125 runtime 부재의 Mypy2오류로 중단됐고 pytest는 미실행이었다. 해당 실패 이력은 보존한다.
- 현재 두 workflow는 PR만 검사해 병합 뒤 develop의 새 결과가 남지 않았다. 기존 검사·권한·DB를
  유지하며 리뷰 준비 완료 이벤트, develop push, 수동 실행과 이벤트·PR/ref별 동시 실행을 추가한다.
- 최신 소스의 새 격리 venv에서 Mypy159 source·기존/신규 adapter와 예산·패키지 연결10건이 통과했다.
  actionlint1.7.12의 두 workflow 검사와 독립 검토도 통과했다. 독립 검토에서 jobs 원문 일치를 확인했다.
- 새 원격 결과는 후속 CI PR의 실제 head·merge SHA 및 실행 링크로 별도 확인한다. 위 로컬 결과를
  원격 CI 통과로 보고하지 않으며 수동·push 경로는 기본 develop에 변경이 반영된 뒤 사용할 수 있다.
- 이번 범위는 CI 검증 경로다. 수집기 경계 결함·미적용 Context/L2·후속 실행 연결의 결과로 확대하지 않는다.

## 2026-10-26 — 사용자 요청에 따라 PR #107 번호 유지

- 사용자가 #107 번호 유지를 명시해 기존 번호 유지 예외를 적용한다. #107의 원본 `ce24c82`와
  #138 수정본 `be1ff99`를 로컬·원격 백업으로 보존하고 원래 head 브랜치만 정리한다.
- 검증한 #138의 정정 테스트·기록을 가져오며 테스트 파일은 byte/AST 그대로다. 이번 새 변경은
  이 번호 복원 기록뿐이다. #102 본체·공용 fixture·다른 선행 구현을 복사하거나 병합하지 않는다.
- 실제 원격 head가 확인한 `ce24c82`와 같은지 다시 검사하고 그 SHA를 명시한
  `--force-with-lease`로 갱신한다. 다른 사람의 변경이 있으면 덮어쓰지 않는다.
- #107은 다시 열어 develop base·Draft로 유지한다. 원격 head·diff 2파일·커밋별 300행 상한과
  기존 리뷰/댓글 보존을 확인한 다음 #138을 연결하고 병합 없이 닫는다. #138 브랜치는 보존한다.
- 기존 정정 8사례와 결합 AI 309·BE 163사례는 이전 검증 이력이다. 테스트/제품 소스가 같음을
  대조해 보존하며 이번 새 서비스 실행 결과로 표시하지 않는다. 게시본 단독의 #102 fixture
  부재에 따른 8 setup errors도 그대로이므로 필요한 선행 반영 후 재검증해야 한다.
- 앞 절들의 #107 종료·#138 대체는 번호 복원 전 이력이다. 현재 검토·반영 대상은 #107이며,
  다른 관련 PR의 정정 사례·구현 기록 링크도 #107과 원래 head 브랜치로 정리한다.

## 2026-10-26 — #99 동시 변경을 보존한 최신 게시 기준 검증

- 게시 전 #99가 팀원의 `ce1019a`로 갱신된 것을 감지해 push 전에 중단했다. 기존 로컬 수정본과
  새 원격 head를 모두 보존하고 새 head 위에 원문 공백·CRLF·prompt v2 검증과 별도 회귀만 추가했다.
  팀원의 기존 테스트 16사례·v1/v2 prompt·Accepted ADR0028·계약은 byte/blob 그대로다.
- 중복될 로컬 ADR0028·명세 PR은 게시하지 않았다. 현재 명세를 준수하는 구현/검사 보완만 반영한다.
- 이 최신 #99와 #102·#103·정정·최종 #119 및 필요한 #114를 새 환경에 결합해 AI 전체
  **309 passed / BE 고유 163 passed**를 확인했다. AI Ruff·format 52·mypy 12 source,
  BE Ruff·format 262·mypy 133 source, 부분 계약 schema 2개·fixture 7개도 통과했다.
- Python 248파일의 검증 전후 hash가 같고 선택 25파일은 각 수정본과 byte가 같다. 실제 모듈은
  새 통합본 경로이며 contracts의 #119 비도메인 AST와 팀원 DomainPostingInput AST를 보존했다.
- 아래의 322사례는 동시 변경 발견 전 로컬 후보의 검증 이력이다. 최신 게시본의 수치에 합치거나
  최신 원격 head의 결과로 재사용하지 않는다. 원격 최신 반영 후 새 의미 품질 평가는 별도다.
- 결과·원본 대응·명령·노드 목록은 원본 저장소
  `.claude/scratch/ai-pr-reviews-20261026/latest99-full-review-integration-result.json`과 관련 로그에 보존한다.

## 2026-10-26 — AI 리뷰 수정 다섯 PR 최종 결합 검증

- 최신 develop `2ff1acf`에 #99 v2·#102 JD 원문·#103 복구 설명·#107 정정 사례·#119 L2 수정과
  필요한 #114 gateway를 별도 로컬 환경에서 결합했다. 선행을 원격 병합하거나 게시본에 복사하지 않았다.
- AI 전체 322 passed, BE 고유 163 passed다. BE는 import 1·Director 15·gateway 72·설정 50·
  L2 18·도메인 7사례이며 실제 고유 노드 목록을 보존했다.
- AI/BE Ruff·format(51/262파일)·mypy(12/133 source), 부분 계약 schema 2개·fixture 7개가 통과했다.
  실제 모듈 경로가 새 통합본이며 Python 247파일의 검증 전후 hash가 같다. 선택 20파일은 각 최종
  수정본과 byte가 같고 contracts는 #119 비도메인 AST와 #99 도메인 입력 AST를 모두 보존했다.
- 제품 코드는 새 통합본 구성 중 수정하지 않았다. 전체 서비스·DB·실제 모델·GitHub API 호출은
  실행하지 않았다. 기술적 통과를 도메인 분류·면접 판단의 의미 품질로 해석하지 않는다.
- 이 결합 결과를 각 게시본 단독 통과로 표시하지 않는다. #119의 #114 의존과 정정 게시본의 #102
  fixture 부재는 그대로다. #133의 일반 코드 반영과 call_model 기록 hook은 별도 후속이다.
- 결과·정확한 노드·구성·원본 대응은 원본 저장소의
  `.claude/scratch/ai-pr-reviews-20261026/full-review-integration-result.json`과 관련 로그에 보존한다.

## 2026-10-26 — PR #107 기여 정정 질문·이력 일치 보완

- 리뷰 원본 `ce24c82`의 사례 수와 검증 목적을 보존했다. 역할 확인은 실제 역할 질문과 역할 계약,
  직접 구현 전제 정정은 실제 직접 구현 질문과 해당 계약으로 검증된 Question을 구성한다.
- 공용 `conftest.py`와 제품 코드는 바꾸지 않았다. 이 테스트 파일의 도우미에서만 문장과 계약을
  함께 만들고, 실제 분석 모델 payload에 그 문장이 전달되는지 검사한다.
- 최초 답변의 질문도 최초 분석과 HistoryTurn에 같은 문자열을 쓰며, 정정 분석 이후 Director에
  전달하는 이력에는 분석에 사용한 역할 질문을 그대로 넣고 원문 일치를 확인한다.
- 먼저 payload 일치 검사를 추가해 잘못된 질문이 쓰인 기존 4사례의 실패(4 failed / 4 passed)를
  재현했다. 수정 후 원본 8사례, AI 전체 236사례가 통과했다. AI Ruff·format 46파일·mypy
  11 source, BE 패키지 import 1사례와 부분 계약 검사(schema 2개·OpenAPI·fixture 7개)도 통과했다.
- 기존 Python 환경을 사용하고 이 worktree의 AI 소스 경로를 명시했다. 외부 모델·GitHub 호출,
  DB 영구 보존·전체 면접 완주·실제 정정 판단 품질은 실행하지 않았다.
- 기존 #107은 선행 #102 base이므로 원본 브랜치·head와 백업을 보존하고 최신 develop에서
  이번 테스트·기록만 별도 게시한다. 선행 답변 분석·공용 fixture·Director는 복사하지 않으며,
  독립 게시본의 실패와 최신 선행 결합 검증 결과는 아래 후속 기록으로 구분한다.

### 독립 게시본과 최신 선행 결합 검증

- `develop@2ff1acf`의 별도 게시본에는 정정 테스트 248행과 원본 #107 기록 40행·이번 보완 기록만
  옮겼다. #102의 답변 분석 본체·공용 conftest와 기존 테스트는 복사하지 않았다.
- 실제 게시본 Ruff·format 41파일은 통과했다. 정정 8사례는 선행 #102의 `kit` fixture 부재로
  모두 setup error다. 이 실패를 기능 통과로 처리하지 않고 Draft로 게시한다.
- 같은 최신 develop에 #102·#103 수정과 정정 테스트만 결합한 별도 환경에서는 AI 전체
  254 passed·Ruff·format 46파일·mypy 11 source, BE 호출 경계 131 passed와 부분 계약 검사가
  통과했다. 실제 모듈 경로가 해당 통합본이며 Python 238파일의 검증 전후 hash가 같다.
- 통합에서 develop #77 기록과 각 PR의 고유 기록을 함께 보존했다. 이 수치를 독립 게시본의
  통과로 사용하지 않으며 원본 #107은 대체 PR 검증·상호 연결 후 병합 없이 닫는다.

## 2026-10-26 — PR #102 참조 JD 입력과 대조 답변 보완

- 기준은 리뷰 원본 `28e2663`이며 초기 설계·공개 계약·`AnswerAnalysis` 출력 필드는 변경하지 않았다.
- `answer_analysis._referenced_jd`는 질문의 `jd_requirement_ids`와 Contract의 `jd_requirement`
  basis 참조를 합쳐 해당 ID·원문·분류·source field·tech tags만 모델 입력으로 전달한다. 미참조 JD는
  제외한다. 필수 원문 누락·중복 ID는 호출 전에 `answer_analysis_input_invalid`(semantic)로 거절한다.
- `test_answer_analysis.py`에 7사례를 추가했다. Kafka/RabbitMQ 원문 변경이 실제 payload에 반영되고,
  두 참조 경로 각각과 함께 쓸 때 원문 유실을 허용하지 않는지 검사한다. 공용 질문 helper는 변경하지 않았다.
- 길고 틀린 답변에 실제로 "별도 갱신 없이도 캐시는 항상 최신 데이터를 보장합니다"라는 주장을 넣고,
  분석의 `answer_quotes`도 그 구절을 인용하도록 맞췄다. 입력에 없는 주장을 비판하는 fixture를 제거했다.
- 수정 전 새 회귀 7사례가 모두 실패함을 확인한 뒤 수정했다. 수정 후 직접 관련 33사례,
  AI 전체 235사례, AI Ruff·format 45파일·mypy 11 source 모두 통과했다.
- 실제 게시 원본 backend의 패키지 import·Director·공통 LLM·설정 경계 131사례가 통과했다.
  실제 BE gateway와 모의 HTTP를 연결한 별도 5시나리오에서도 서로 다른 JD 원문 전달 2건과
  필수 참조 누락의 HTTP 무호출 3건을 확인했다. 원문 전달 응답의 모델·prompt metadata도 보존됐다.
- 기존 `backend/.venv`의 Python을 사용하고 각 worktree의 AI·BE 소스를 명시했다. 외부 API·실제 모델,
  PostgreSQL 저장·면접 전체 흐름·분류 의미 품질은 이번 검증 범위가 아니다. 이전 실행 결과와 구분한다.
- 기존 전용 계약 검사 환경에서 schema 2개·부분 OpenAPI·정상/오류 fixture 7개와 `git diff --check`도
  통과했다. 부분 형식 검사를 전체 API 호환성 검증으로 확대하지 않는다.

## 2026-10-26 — PR #103 검토 결과의 검증 범위 설명 보완

- 리뷰 원본 `742e5a2`의 문서 지적을 반영했다. 승인 `QuestionReview`의 문장·Contract 대조와
  `CandidateRecovery` 분류·사유 전달을 구분하고, 후자의 반환값 자체를 후보와 별도 대조하지 않음을 명시했다.
- 제품 코드·계약·테스트는 바꾸지 않았다. 기존 Python 환경에서 이 worktree 소스를 명시해
  AI 전체 204사례, AI Ruff·format 40파일·mypy 11 source, BE import·Director·LLM·설정 경계
  131사례를 재실행해 모두 통과했다. 실제 검토기의 의미 품질·모델 호출·DB 저장은 검증하지 않았다.
- 기존 전용 계약 검사 환경의 schema 2개·부분 OpenAPI·fixture 7개와 `git diff --check`도 통과했다.

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

- 분류 판단은 주입된 독립 검토기의 몫이다. 승인 결과(`QuestionReview`)는 후보의 문장·질문 계약과 일치하는지 검사한다.
  복구 분류(`CandidateRecovery`)는 현재 검토 호출에서 반환된 분류·사유를 실패 결과로 전달하며, 반환값 자체가
  해당 후보에 대한 판단인지 별도로 대조하지 않는다. 테스트의 검토기는 합성 대역이며 목적 일치·전제 타당성의
  실제 판정 품질은 검증하지 않았다(AI-L01).
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

## 2026-10-26 — PR #125 리뷰 보완과 독립·최신 결합 검증

- 기준은 #125 원본 `70c1dbf`, 최신 결합 기준은 develop `d063d8d`다. 원본 head를
  `backup/pr125-before-review-20261026`에 보존하고 후속 커밋만 추가했다.
- 총 2회·생성/독립 검토 각 1회와 실패·거절 후 중단을 유지한다. 검토의 자유 텍스트 사유는
  일반 CallFailure에서 고정 요약으로 바꾸고 보호된 attempt.raw_output에는 그대로 보존한다.
- 새 planner의 question·contract·required point·basis ref 부가 필드는 호출 경계에서 거절한다.
  공통 decode의 기존 동작, 기존 generate_question, 공개 wire·DB·의존성은 바꾸지 않았다.
- 수정 전 신규 회귀에서 실패 사유 복사 1건과 중첩 부가 필드 4건이 실패했다. 보완 후 runtime
  38건이 통과하며 유효한 부분 Tool item·Context 등록 필요·단계 timeout 중단도 함께 검사한다.
- 원 게시본은 AI Ruff·format 43파일 통과, mypy는 기존 #103의 `_RECOVERY_CODES` 부재 1오류,
  전체 pytest는 `candidate_recovery` import 수집 오류 1건이다. 선행을 복사해 숨기지 않는다.
- 별도 최신 develop + 이 코어 3파일 결합본은 AI 전체 347 passed, Ruff·format 55파일·mypy
  13 source가 통과했다. 기존 Python 3.12 환경에 해당 worktree의 ai/src를 명시했다.
- 이번 347건은 새로 실행한 결합 결과이며 게시본 단독의 성공이 아니다. 실제 모델·원격 GitHub,
  DB·WS·worker·면접 완주·자연어 검토 품질·비용은 미실행이다.
- 10월 23일의 분리 게시 원문은 아래에 그대로 보존한다. 파일 끝의 공통 추가 충돌을 피하려
  #50 기록 앞에 재배치했으며 다른 PR의 기록을 복사·삭제하지 않았다.

## 2026-10-23 — Director 신규 변경의 분리 게시 검증

### 기준과 게시 범위

- 최신 원격 develop `bbe01213`에서 코어·연결 기반·BE 공통 보완·명세의 별도 게시 브랜치를 구성했다.
- 미병합 선행 #82/#102/#103/#107/#114/#119/#120을 결합했던 원본 통합 worktree는 보존했다.
  원본 tree는 `c8f2cb5d`, 선행 결합 기준 tree는 `a4d7c1bf`다. 해당 원본의 신규 차이는
  36파일 +6025/-58이며 아래 게시본의 최종 diff와는 다르다.
- 선행 구현·기존 테스트·패키지 의존성은 게시본에 복사하지 않는다. 모든 PR base는 develop이다.
  코어·연결·공통은 필요한 선행 구현이 없어 단독 검증이 제한되며 Draft로 검토한다.
- 코어는 `ai/.../director/runtime.py`·prompt·테스트를 원형으로 보존한다.
  연결 기반은 새 adapter·원문/과거 분석 복원·실제 tree 수집과 소비하는 8개 설정을 게시한다.
  공통은 seed CLI 수명·migration head 연결·검사 subprocess의 worktree 고정만 보완한다.
- 실제 계약/설계는 별도 명세 PR에, 결정은 0023·별도 연결 PR의 0025·BE 공통 ADR에 둔다.
  이 기록은 세 구현 PR의 결과를 모으는 한 곳이며 각 PR에 같은 현황을 복제하지 않는다.

### 게시본 단독 실행

기존 환경의 Python 3.12와 설치된 도구를 사용했다. 각 worktree의 backend 및 ai/src를
PYTHONPATH로 명시했으며 새 패키지 설치나 실제 모델·GitHub 호출은 하지 않았다.

| 작업 디렉터리 | 명령·범위 | 실제 결과 |
| --- | --- | --- |
| 코어 ai | ruff check / ruff format --check | 통과, format 43파일 |
| 코어 ai | mypy | 실패 1건: #103의 `_RECOVERY_CODES` 부재 |
| 코어 ai | pytest | 수집 실패 1건: #103의 `candidate_recovery` import 불가 |
| 연결 backend | pytest tests/test_config.py tests/core/test_director_limits.py | 10 passed |
| 연결 backend | 수집기·어댑터 런타임 pytest | 수집 실패: 미게시 코어·선행 모듈 부재 |
| 연결 backend | ruff check app tests / ruff format --check app tests | 통과 |
| 연결 backend | mypy app | 실패 19건: 코어 및 #82/#102/#114/#119 입력·모델·API 부재 |
| 공통 backend | seed 및 LLM 설정 pytest | 49 passed |
| 공통 backend | ruff check / format / mypy app | 통과, format 254파일·mypy 133파일 |
| 공통 backend | alembic heads | 실패: #82의 `0002_agent_storage` parent 부재 |
| 명세 루트 | .claude/scripts/check_contracts.py | 2 schemas·partial OpenAPI·7 fixtures 통과 |

공통 seed 검증은 주입 세션을 그대로 쓰는 경로와 CLI 자체 연결의 성공·실패 정리를 확인한다.
연결 검증에는 원래 수집기의 구조 상한 1사례·binary/timeout 부분 실패 2사례를 그대로 옮겼고,
실제 provider 경계의 어댑터·호출 예산·저장 질문 복원 3사례를 추가했다.

### 게시 코드와 선행 구현의 별도 로컬 결합 실행

아래 결합은 무시된 검증 디렉터리에서만 수행했으며 PR diff에는 선행 코드가 없다.
준비 실행·worker·Director 서비스·WS 활성화도 이 결합에 추가하지 않았다.

| 결합 범위 | 실제 실행 결과 |
| --- | --- |
| 코어 게시본 + #103 agent.py 한 파일 | 신규 28 passed, AI 전체 221 passed, mypy 12파일 통과 |
| 연결 게시본 + 선행 tree + 코어 3파일 | 관련 36 passed, mypy app 140파일 통과 |
| 네 게시 범주 + 선행 tree | AI 전체 295 passed, BE 관련 6파일 89 passed |
| 위 결합의 모듈 위치 | 9개 실행 모듈이 모두 해당 overlay에서 로드됨을 확인 |
| 공통 게시본 + #82 migration 한 파일 | 실제 PostgreSQL 새 DB에서 upgrade head 통과 |
| 같은 PostgreSQL DB의 seed CLI 2회 | 평가 기준6·도메인 frame21, 중복 없음·비활성 유지 |
| 같은 PostgreSQL DB | downgrade base 통과, 생성 DB만 삭제·전용 PostgreSQL 종료 확인 |

DB 검사는 SQLite로 대체하지 않았다. 기존 DB·schema·table 목록이 전후 일치하며
추가로 사용한 16086 포트도 해제했다. 원문·모델 provider는 mock으로 검증했다.
위 수치는 이번 게시본으로 새로 실행한 결과이며 원본 통합본의 BE 1302건을 재사용하지 않았다.
계약 검사는 부분 형식 검사이며 runtime·TypeScript·전체 API 호환성 검증이 아니다.

### 보존한 후속과 미검증 범위

- `agent_context.py` 현재 질문·한계 전달 보완 및 `repo_deep.py` 예산·한계 전달 보완은
  선행 구현에 붙는 후속이므로 원본 패치로 보존한다. 선행 반영 뒤 연결·재검증해야 한다.
- 이 보완을 요구하는 `load_answer_context`·반환형, 기존 `generate_question`의 base_url 수정,
  L2 한계 전달 및 Context 서비스 통합 검증도 보류한다. 우회 함수·복제 구현은 만들지 않는다.
- 준비 실행·ARQ 등록·WS·턴 저장/상태 제어·앱 활성화와 전용 테스트, WS ADR0024는 원본에 남긴다.
  BE 실행 전용 3개 상한·quota 예제와 이에 해당하는 테스트·통합 문서 구간도 게시 범위에서 뺀다.
- 공개 OpenAPI·FE·WS wire, 패키지/lockfile, DB 모델은 변경하지 않는다.
  운영 prompt 검수·활성화, 실제 모델 의미 품질·지연·비용, 다언어·대형 파일 전반은 미검증이다.
- 원본·게시·보류·게시용 테스트/문서 조정의 대응표와 패치는 원본 저장소의
  `.claude/scratch/director-publish-20261023`에 보존한다. 선행 병합·보류 보완 후 다시 검증한다.

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

## 2026-10-26 — PR #97 기록 충돌 해소와 최신 develop 결합 검증

- 기준은 #97 `0734b802c42878e6cd42c18eaec27c5782e9822a`와 develop
  `633e8dee65bb85031730f30512b4d0a1e4003e86`이다. 두 변경을 결합한 별도 worktree에서 새로 실행했다.
- 충돌은 문서 머리말 뒤에 각 작업이 기록을 추가한 위치가 겹쳐 발생했다. #97의 고유 기록을
  기존 공통 절 사이로 재배치해 원문과 제목을 보존했다. 제품 코드·테스트·정책 의미는 바꾸지 않았다.
- [후속 리뷰](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/97#issuecomment-6161811626)의
  병합 요청을 확인했다. 실행 프롬프트·Director 보조 입력 검증·실제 면접 연결은 기존 후속 범위다.

Windows / Python 3.12.14, 기존 준비 환경의 Python과 검증본의 명시적 AI·BE 소스 경로를 사용했다.

| 검증 대상 | 실행 | 결과 |
| --- | --- | --- |
| 결합본 AI | 전체 pytest, cacheprovider 제외 | 254 passed |
| 결합본 AI | Ruff check·format, mypy | 통과; format 46개·mypy 11개 파일 |
| 결합본 루트 | hook·계약 스크립트 unittest | 17 passed, 1 skipped; Windows symlink 생성 불가 |
| 결합본 루트 | hook 두 파일의 Ruff isolated 검사 | 통과 |
| 결합본 BE | AI 패키지 import pytest | 1 passed; 검증본의 AI 소스 사용 |
| 결합본 BE | Ruff check·format, mypy app | 통과; format 264개·mypy 133개 파일 |
| 결합본 계약 | 전용 검사 환경의 check_contracts.py | schema 2개·부분 OpenAPI·fixture 7개 통과 |
| 실제 AI hook | uv offline/no-sync, 오류 Write·정상 Edit | F401·T201 검출, 정상 파일 통과, 원문·AI lock 불변 |
| 변경 문서·이력 | md 20개의 링크·앵커와 양쪽 기록 절 대조 | 상대 링크 287개·앵커 포함 19개 유효, 원본 절 누락 없음 |

이 결과는 이번 결합본의 새 실행이며 이전 193개·별도 #82의 24개 결과를 재사용하지 않았다.
실제 Claude UI 기동·Linux·외부 LLM·DB/WS 면접 전체 흐름은 이번에 실행하지 않았다.
부분 계약·AI 단위 검사로 고정 배분의 서비스 적용 완료나 다른 PR의 병합 가능을 판단하지 않는다.

## 2026-10-13 — PR #97 리뷰 대응과 면접 배분 구현 현황 재확인

### 문서 번호와 최신 구현

- 최신 `develop` `bbe01213d0bb791b64504f13fbe73ed4bb88d98b`에는 공통 ADR 0007인
  `0007-voice-interview-contract.md`가 있어, 이번 고정 배분 결정은
  [공통 ADR 0008](../shared/decisions/0008-fixed-persona-allocation.md)로 번호와 참조를 정리했다.
  확인한 열린 PR 14개 중 #81이 0006을 사용하고 있으며, 공통 0008을 새로 사용하는 PR은 없었다.
  아래 10월 6일의 번호 선택·구현 확인 기록은 당시 이력으로 보존한다.
- [PR #82](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/82)의 최신 확인 head는
  `0e973f3377553b13bbea419bfd662f968bf64b97`이다. 기존 `b262f29`와 달리 고정 6/2/1을
  계산하는 `agent_context.allowed_personas`와 설정·이력 검증이 구현돼 있다. 첫 HR 이후에는
  잔여 할당이 있는 기술·도메인만 허용하고, 도메인 할당이 남았는데 활성 프레임이 없으면
  `domain_frames_unavailable`로 거절한다. 미분류 공고는 DB 값을 보존하며 활성 `etc` 프레임을 쓴다.
- #82의 위 코드와 테스트는 이번 PR에 복사하지 않았다. 아래 검증은 #97의 문서·hook 검사와
  #82의 기존 배분 함수 검사를 구분하며, #82 전체의 병합 가능이나 실제 면접 완료를 뜻하지 않는다.

### 리뷰 대응과 남은 실행 연결

- [기존 리뷰](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/97#issuecomment-6107262453)의
  실행 프롬프트·Director 입력 검증 지적은 후속 구현 대상으로 유지한다. #97의 배분 변경 범위는
  문서이며, 현재 AI Director는 허용 목록 밖 출력은 거절하지만 이후 HR·횟수 상한에 맞는
  목록인지까지 검사하지 않는다. 프롬프트 문구 변경만으로 고정 배분이 보장되지는 않는다.
- 후속 구현은 #82의 Controller를 재사용하고, 프롬프트에서 배분 계산과 후보 선택의 책임을
  명확히 한다. Director의 보조 입력 검사에서는 이후 HR·이미 채운 할당과 함께
  `persona_counts` 누락·질문 번호 불일치의 처리 기준을 맞춘다. 별도 배분 계산기를 복제하지 않는다.
- FE mock의 6/1/2 예제, 실제 준비·턴 처리와의 연결, 중복·실패 시 질문 수 불변 및
  9번째 **답변 처리 후** 정상 종료는 후속 통합 검증 범위다. #82의 9문항 저장 테스트는 답변을
  fixture에서 직접 저장하므로 실제 답변 처리·WS 정상 종료를 검증한 것으로 취급하지 않는다.
- #82의 기존 고정 커밋 링크는 당시 ADR 0007에 계속 접근할 수 있다. 이후 현행 정책 참조를
  갱신할 때는 #97의 ADR 0008로 연결하며, 해당 PR의 실행 코드·이력은 이번에 수정하지 않는다.

### 이번 수정의 검증

Windows / Python 3.12, #97 게시 worktree와 최신 develop을 합친 별도 worktree에서 새로 실행했다.
기존 준비 환경의 Python을 사용했고, AI·BE 연결 검사에는 검증할 worktree의 `PYTHONPATH`를 지정했다.

| 검증 대상 | 명령 / 시나리오 | 결과 |
| --- | --- | --- |
| #97 루트 | `PYTHONUTF8=1`, `python -m unittest discover -s .claude/scripts/tests -v` | 17 passed, 1 skipped; Windows symlink 생성 불가 |
| #97 루트 | hook 두 파일의 `ruff check --isolated` | 통과 |
| #97 AI hook | 실제 uv·AI venv로 정상 Edit·오류 Write 실행 | F401·T201 검출, 정상 파일 통과, 소스·lock 불변 |
| #97 `ai` | `python -m pytest -q -p no:cacheprovider`, Ruff·format·mypy | 193 passed; format 40개·mypy 11개 파일 통과 |
| #97 `backend` | `python -m pytest tests/agents/test_ai_package_imports.py -q -p no:cacheprovider` | 1 passed |
| #97·develop 통합본 | `.claude/scripts/check_contracts.py` | 각각 schema 2개·부분 OpenAPI·fixture 7개 통과 |
| develop 통합본 | hook·계약 스크립트 unittest, 문서 링크·ADR 번호·본문 보존 | 17 passed, 1 skipped; 로컬 링크 284개, 번호 중복 없음, 기존 음성 ADR 보존 |
| #97 문서 | 로컬 링크·다른 AI ADR 보존·`git diff --check` | 링크 279개 대상 존재, AI ADR 0007·0008 및 배분 정책 본문 보존, 공백 검사 통과 |
| 별도 #82 `0e973f3` | `python -m pytest tests/agents/test_agent_context.py -q -p no:cacheprovider` | 24 passed; 정상 순서 28가지와 잘못된 횟수 검사 포함 |

실제 Claude UI 기동·Linux·외부 LLM·DB/WS 면접 전체 흐름은 이번에 실행하지 않았다.
#82의 DB 저장 회귀는 코드만 대조했으며 이번 24개 실행 결과에 포함하지 않았다.
독립 검토에서도 추가 결함이 없었고, 이번 수정은 문서 번호·참조·현황 기록에 한정한다.

## 2026-10-06 — 고정 질문 배분 문서와 AI 변경 파일 lint

### 기준과 변경

- `develop`의 `ef1a48d1531b43f382b69dee163419afb5709c6b`에서
  `refactor/interview-policy-ai-lint` 브랜치를 분리했다. 미병합 PR의 코드는 가져오지 않았다.
- [고정 배분 결정](../shared/decisions/0008-fixed-persona-allocation.md)(당시 공통 ADR 0007, 현재 0008)에 따라 정상 완료 면접을
  기술 6회·도메인 2회·HR 1회로 정리했다. 첫 HR을 포함한 총 9문항이며, 이후 기술·도메인 순서는
  허용 후보 안에서 선택한다. 마지막 답변 처리 후 종료한다.
- **면접 배분 변경은 문서에만 반영했다.** 현행 기능·계약·과제·검증 기준과 결정 색인을 맞추고,
  과거 ADR·초기 설계 본문은 보존하면서 현행 정책으로 연결했다.
- 게시 전 열린 PR 13개를 대조해 #81이 공통 ADR 0006을 사용 중임을 확인했다.
  번호 중복을 피하려고 이번 정책은 0007로 지정하고, 관련 문서의 참조를 함께 맞췄다.
- [PR #28의 AI lint 보완 요청](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/28#discussion_r4053030543)에
  맞춰 `.claude/scripts/lint_changed.py`의 AI 무조건 건너뛰기를 제거했다.
  Claude `Edit`·`Write`의 AI Python 변경 파일을 `ai/`에서 로컬 Ruff로 검사하며,
  `--offline`·`--no-sync`를 사용한다. 설치·자동 수정 없이 미준비 환경과 lint 실패를 안내한다.
- `.claude/scripts/tests/test_hooks.py`에 AI 실행·오류 전달·정상 통과·시간 초과·환경 부재·경로 제외
  회귀 검증을 추가했다. 사용 조건과 검사 범위는 [AI 테스트 안내](../../ai/docs/testing.md)에 기록했다.

### 실행 결과

Windows, Python 3.12의 별도 worktree에서 실행했다. 아래 결과는 이번 변경에서 새로 확인한 값이다.

| 작업 디렉터리 | 명령 / 시나리오 | 결과 |
| --- | --- | --- |
| 루트 | 구현 전 AI hook 회귀 검증 | 기존 무조건 skip으로 4개 실패 확인 |
| 루트 | `PYTHONUTF8=1`, BE Python으로 `-m unittest discover -s .claude/scripts/tests -v` | 17 passed, 1 skipped; Windows symlink 생성 불가 |
| 루트 | `ruff check --isolated .claude/scripts/lint_changed.py .claude/scripts/tests/test_hooks.py` | 통과 |
| 루트 | 실제 AI venv·uv로 hook에 `Edit`·`Write` JSON 전달 | 정상 파일 통과, 오류 파일의 F401·T201 검출; 소스·AI lock 불변 |
| `ai` | `uv --offline run --locked ruff check .`, `ruff format --check .`, `mypy` | 통과; format 40개·mypy 11개 파일 |
| `ai` | `uv --offline run --locked pytest -q -p no:cacheprovider` | 193 passed; 기존 구현 검증이며 새 고정 배분 구현 검증은 아님 |
| `backend` | `uv --offline run --locked pytest -q -p no:cacheprovider tests/agents/test_ai_package_imports.py` | 1 passed; 현재 worktree의 AI 패키지 연결 확인 |
| 루트 | 별도 검증 환경의 `.claude/scripts/check_contracts.py` | schema 2개·부분 OpenAPI·정상/오류 fixture 7개 통과 |
| 루트 | 독립 코드·문서 검토, 변경 문서의 로컬 링크 278개와 `git diff --check` | 추가 결함 없음, 링크 대상 존재·공백 검사 통과; 면접 코드·프롬프트·fixture·설정·lock 변경 없음 |

BE 환경 준비는 캐시에 `lxml-stubs`가 없어 offline sync가 실패한 뒤, 일반 `uv sync --locked`로
완료했다. 이는 수동 검증 준비이며 hook은 의존성을 설치하지 않는다. hook 실검증에서는 실행할 Python을
지정하고 자식 프로세스의 PATH에 uv를 추가했다. 실제 Claude UI에서 hook이 시작되는 단계와 Linux 실행은
미실행이다. 공통 계약 검사는 부분 형식 검사이며 전체 API·DB·WS·모델 품질 검증을 뜻하지 않는다.

### 면접 구현의 후속 반영

- 확인한 [PR #82](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/82)의 head는
  `b262f29e335c1115600fe6dc7b306d0ed231263b`이며 미병합 상태다. 기술 최소 5회·도메인/HR 합산 최소 3회,
  첫 질문 이후 HR 허용이라는 유동 정책을 새 고정 배분과 맞춰야 한다. 도메인 프레임 부재 시 도메인을
  제외하는 경로도 도메인 2회 보장과 함께 검토해야 한다.
- `frontend/src/mocks/fixtures/interview.ts`의 기술 6회·도메인 1회·HR 2회 예제와 설명은 아직 유지된다.
  `ai/prompts/director-question-v1.md`의 배분 문구도 후속 구현에서 Controller의 책임과 함께 정합성을 확인한다.
- 면접 제어 코드·프롬프트·FE fixture·설정 예시는 이번에 수정하지 않았다. 후속 구현에서는 허용 후보 계산,
  질문 확정·중복 처리, 9번째 답변 후 종료 및 도메인 준비 조건을 검증해야 한다.
  이번 문서 정리만으로 #82 병합 가능이나 실제 고정 배분 적용 완료를 선언하지 않는다.

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

## 2026-10-26 — PR #119 최신 develop 결합과 병합 준비 검증

- 원본 #119 `93177862fd6bf4f2bcc1191f800b3ba341a115c8`와 develop
  `fca606a979d3b1214e6a5cfd9244d2fa5e10f08e`를 결합한 별도 worktree에서 새로 실행했다.
- #99의 `DomainPostingInput`과 #119의 L2 계약이 같은 위치에 추가돼 충돌했다. L2 정의의 위치만
  조정하고 양쪽 클래스·함수의 AST를 원본과 대조해 보존했다. 검증 로직·공개 계약은 바꾸지 않았다.
- 구현 기록도 #119의 고유 절만 재배치하고 기존 develop 기록은 보존했다. task-05와 저장소 분석
  문서의 과거 미구현 안내는 현재 기록 참조로 바꿨다. #109의 기록 정책 변경은 포함하지 않는다.
- #114는 이미 develop에 반영돼 이번 검증에서 별도 결합하지 않았다. 아래의 단독 실패·Draft
  기록은 당시 결과다. #133의 미적용 patch·호출 기록 hook은 이번에 가져오거나 활성화하지 않았다.

Windows / Python 3.12.14, 기존 준비 환경의 Python과 검증본의 명시적 AI·BE 소스 경로를 사용했다.

| 검증 대상 | 실행 | 결과 |
| --- | --- | --- |
| 결합본 AI | 전체 pytest, cacheprovider 제외 | 309 passed |
| 결합본 AI | Ruff check·format, mypy | 통과; format 52개·mypy 12개 파일 |
| 결합본 BE | L2 실제 adapter→AI→gateway HTTP 대역·패키지 import | 19 passed; L2 18·import 1 |
| 결합본 BE | Ruff check·format, mypy app | 통과; format 266개·mypy 133개 파일 |
| 결합본 계약 | 전용 검사 환경의 check_contracts.py | schema 2개·부분 OpenAPI·fixture 7개 통과 |
| 결합본 루트 | hook·계약 스크립트 unittest | 17 passed, 1 skipped; Windows symlink 생성 불가 |

기존 세 리뷰의 모든 area가 schema인 경우의 복구·ref 우선 semantic 거절·직접/프록시 주소와 토큰 전달을 다시 검사했다.
유효 area와 거절 목록 보존, 혼합/semantic 무재시도, timeout/provider/parse/schema를 합산한 총
HTTP 2회 상한이 통과했다. 과거의 AI 224·별도 결합 309/163을 이번 실행 결과로 재사용하지 않았다.
실제 모델·외부 GitHub·원문 수집·DB 저장·prepare·전체 면접 E2E는 이번에 실행하지 않았다.
구조·참조 검증을 자유 서술의 사실성이나 실제 분석 의미 품질 검증으로 확대하지 않는다.

## 2026-10-26 — PR #119 L2 검증·재시도와 호출 주소 리뷰 반영

- 기준은 원본 `3f945d3`이며 원본 브랜치와 `backup/pr119-before-review-fix-20261026`을 보존했다.
- `parse_deep_analysis`는 repository ID·SHA의 형식을 먼저 검사하고 입력 ref와 대조한다.
  형식이 유효한 다른 ref는 빈 요약·잘못된 area 목록·추가 필드와 함께 와도 semantic 실패다.
  ref 자체의 형식 오류는 schema 실패이며 다른 저장소의 결과를 복구 대상으로 사용하지 않는다.
- 검증된 area가 하나라도 있으면 기존 부분 성공과 거절 목록을 보존한다. 검증된 area가 없고
  거절이 전부 schema일 때 gateway에 schema 오류를 전달해 남은 재시도만 사용한다. semantic
  거절이 섞이면 재호출하지 않는다. task 내부 재시도 loop나 새 gateway·기본 관찰을 만들지 않았다.
- BE adapter는 `base_url=settings.llm_base_url`을 실제 호출에 전달한다. 직접/프록시 주소와 토큰
  조합을 실제 adapter→AI→gateway와 HTTP 대역으로 검사한다. #114의 설정·gateway 본체는 복사하지 않았다.
- #133의 미적용 `03-repo_deep.patch`에도 같은 주소 전달 행이 있으므로 이번 head를 반영해 해당
  중복을 제거하고 exact base/result·manifest를 다시 검증해야 한다. 다른 후속 보완은 보존 대상이다.

### 실행 결과와 범위

아래 표는 최초 리뷰 반영본의 결과이며, 혼합 거절 추가 검토 후의 최종 결과는 다음 절에 구분한다.

| 환경 | 실행 | 실제 결과 |
| --- | --- | --- |
| 원본 코드 + 새 회귀 | L2 AI / BE 테스트 | 5 failed·20 passed / 7 failed·7 passed로 두 검증 문제 재현 |
| #114 결합 + 새 주소 검사, 수정 전 | 직접/프록시 2사례 | 둘 다 필수 `base_url` 누락으로 실패, 외부 요청 없음 |
| 수정 게시본 AI | 전체 pytest·Ruff·format·mypy | 223 passed, format 41파일·type 11 source 모두 통과 |
| 수정 게시본 BE | AI package import·Ruff·format | 1 passed, format 250파일·Ruff 통과 |
| 수정 게시본 BE | L2 pytest·mypy app | 실패: L2 17사례 모두 #114의 `llm_base_url` 필드 부재. mypy 1파일 2오류·133 source로 선행 의존 확인 |
| 최신 develop `2ff1acf` + #119 수정 + #114 `6135275` | AI 전체·BE L2/gateway/proxy 설정/import | 223 passed / 124 passed. L2 17사례 포함, raw·오류 기록·총 HTTP 2회·semantic 무재호출·직접/프록시 전달 확인 |
| 같은 통합본 | AI·BE Ruff·format·mypy | 모두 통과. format 41/261파일, type 11/133 source |
| 수정 게시본 루트 | 기존 전용 venv로 계약 검사 | schema 2개·부분 OpenAPI·fixture 7개 통과. 전체 API 호환성 검증은 아님 |

검증 전후 AI·BE 실행 소스 해시는 동일하다. 실제 모델·GitHub·DB 저장·전체 서비스 E2E는 실행하지
않았다. 테스트 통과를 언어·규모별 분석 의미 품질로 해석하지 않는다. 단독 실행은 #114 미병합으로
제한되므로 Draft로 검토하고 필요한 선행을 반영한 최신 base에서 재검증해야 한다. 실행 로그는
원본 저장소 `.claude/scratch/ai-pr-reviews-20261026/pr119-validation/`에 보존한다.

### 추가 검토: 혼합 거절과 #133 후속 패치 동기화

- 채택 area가 없고 schema·semantic 거절이 함께 있으면 전체 재시도가 semantic area도 다시
  평가하는 것을 확인했다. AI 단위 1건·실제 gateway 대역 1건을 실패시킨 뒤, 거절이 전부 schema인
  경우에만 재시도하도록 좁혔다. 빈 목록은 재시도하지 않으며 혼합 거절의 원문·거절 목록은 보존한다.
- 최종 수정본은 AI 전체 224 passed, BE import 1 passed, AI/BE Ruff·format 통과(41/250파일),
  AI mypy 11 source 통과다. BE L2 18사례와 mypy 1파일 2오류는 여전히 선행 #114 부재로 실패한다.
- #114 통합본에서 AI 전체 224 passed, BE 관련 125 passed와 AI/BE Ruff·format·mypy를 재확인했다.
  이 통합 경로에는 별도 #99 검증 자료도 추가돼 format 42/262파일·type 12/133 source다. L2의
  호출 주소·gateway·기존 입력은 그대로이며, 실행 전후 소스 해시도 같다. 최초 결과와 로그를 덮어쓰지
  않고 `pr119-validation-mixed/`에 별도 보존했다.
- #133의 patch 3은 새 #119 adapter blob `6948791b`를 base로 재생성했다. 최종 result blob
  `8ce0d810`은 그대로이며, 이미 반영한 `base_url`은 문맥 행으로 유지해 추가/삭제가 0행이다.
  남은 후속은 공유 budget·즉시 시도 기록·수집 한계 전달이다. manifest의 patch 3 base·해시·선행
  #119 head와 적용 안내만 갱신하고 원본 source/integration tree ID와 다른 3패치는 보존한다.
- 4패치 모두 정확한 base hash·SHA-256·`git apply --check`·적용 후 기존 result blob 일치를
  확인했다. 기존 patch 4의 합성 base는 객체 DB에 없으므로 보존 result에서 역적용해 복원하고
  원래 base hash부터 대조했다. 기존 패치를 수정하거나 base 검사를 생략하지 않았다.
- 별도 보존 실행 통합본에 새 L2 검증과 patch 3을 결합해 AI L2 31 passed, BE 23 passed를
  확인했다. BE는 L2 18·기존 bridge 3·공유 예산/원문 한계/취소 시 기록 보존 probe 2사례다.
  BE Ruff·format 293파일·mypy 141 source도 통과했다. 원본 gateway를 바꾸지 않았다.
- 이 보존 실행 통합본의 gateway에는 아직 #114 단독에 없는 `attempt_sink` 보완이 있다.
  따라서 위 실행 성공은 #133 자료만으로 일반 코드가 활성화되거나 #119+#114만으로 후속 patch 3의
  실행 선행이 모두 충족됐다는 뜻이 아니다. 해당 gateway 보완의 실제 반영·통합 재검증은 후속이며
  이번에 새 gateway 기능을 만들지 않았다. 정확한 적용 증거와 실행 로그는
  `.claude/scratch/ai-pr-reviews-20261026/pr133-sync/`에 원본 백업과 함께 보존한다.

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

## 2026-10-25 — #127 seed 범위 제외와 공통 보완 재검증

### 게시 범위와 원본 보존

- 사용자가 seed 오류 수정을 #131에 맡기고 #127에서 제외하도록 요청했다.
  #131을 병합하거나 수정하지 않고, `develop@dbd7f890`에서 남은 신규 변경만 구성했다.
- 기존 #127의 `eaea0e4b`는 `backup/pr127-before-seed-review-20261025`와 원본 worktree에
  보존했다. 제외한 seed 실행 코드·추가 테스트도 이 원본에서 확인할 수 있다.
- `backend/scripts/seed_all.py`, `backend/tests/test_seed_all.py`는 develop과 동일하다.
  #131의 질문 저장 변경 세 파일도 가져오지 않았다. 이 다섯 파일은 기준선과 내용이 같은지 검사했다.
- 남은 구현은 DDL 없는 `0003_director_runtime` merge revision과 검사 subprocess의
  현재 worktree BE·AI 소스 경로 지정이다. 공개 계약·seed 데이터·활성화 정책은 변경하지 않는다.
- seed 제외와 선행 의존은 [BE ADR](../backend/decisions/0008-director-foundation-publication.md)에
  기록한다. 이전 통합본의 seed 실행 결과를 이번 게시본의 검증 결과로 사용하지 않는다.

### 실제 실행 결과

기존 Windows Python 3.12.14 환경을 사용했다. 아래 단독 검사는 실제 게시용 worktree에서 실행했다.

| 범위 | 검사 | 결과 |
| --- | --- | --- |
| 게시본 backend | `pytest tests/core/test_llm_config.py -q` | 46 passed |
| 게시본 backend | `ruff check .`, `ruff format --check .`, `mypy app` | 통과, format 254파일·mypy 133파일 |
| 게시본 backend | 전체 `pytest -q` | 실패, 기존 `tests/test_seed_all.py`의 삭제된 `dispose_engine` import로 수집 중단 |
| 게시본 backend | `alembic heads` | 실패, #82의 `0002_agent_storage` parent 부재 |
| 별도 로컬 결합 | 게시본 + #82 migration 한 파일, PostgreSQL 15.19 | 단일 head `0003_director_runtime` 확인 |
| 같은 결합 환경 | 초기 revision → 기존 사용자 행 추가 → `upgrade head` | 통과, 기존 행·추가 테이블과 컬럼 확인 |
| 같은 결합 환경 | `downgrade base` → `upgrade head` | 통과 |

로컬 결합은 #82 `0e973f33`의 `0002_agent_storage.py` 한 파일만 사용했고 seed·#131 코드는
결합하지 않았다. 새 전용 cluster·테스트 DB를 사용했으며 생성 DB 삭제·DB 목록 보존·서버 종료를
확인했다. 첫 실행 보조 스크립트는 Windows 자식 프로세스의 pipe 대기로 중단됐고, 해당 전용 서버를
종료한 뒤 파일 로그 방식과 새 cluster로 재실행했다. 위 PostgreSQL 결과는 재실행에서 확인했다.

### 미완료와 병합 조건

- seed import 오류는 #131의 별도 범위다. 이번 변경이 seed 실행을 해결했다고 보고하지 않는다.
- #82가 없는 게시본은 migration graph를 해석할 수 없으므로 Draft로 유지한다.
  선행 반영 후 실제 graph에서 merge 필요성을 다시 확인하고 PostgreSQL에서 재검증한다.
- migration 한 파일의 결합 검증은 #82 전체 모델·서비스 통합이나 전체 pytest 통과가 아니다.
  실제 면접 실행·외부 모델 호출·seed 활성화 검증은 이번 범위가 아니다.

## 2026-10-27 — #127 기존 DB 이력 보존과 최종 합류 검증

### 수정과 선행

- `0003_director_runtime`과 #82·#108의 기존 revision ID·부모·DDL을 보존한다.
  #82의 신규 `0003_agent_storage_merge`, 기존 Director merge, #108 분석 실행을
  DDL 없는 `0004_interview_foundation_merge`에서 합친다.
- 신규 graph 검사는 최종 head 하나와 저장·공고·분석·Director의 기존 이력을 확인한다.
  선행 파일을 테스트에 복사하거나 가짜 revision으로 대체하지 않는다.
- BE ADR은 기존 Task 9의 0002와 구분해 [0008](../backend/decisions/0008-director-foundation-publication.md)로
  연결하고 색인에 추가했다. 원래 #127의 고유 실행 기록은 위에 보존하고 위치만 분리했다.
- #131 반영 이후 seed import 수집 오류는 현재 실패 원인이 아니다. 당시 실패 기록과
  최신 상태를 구분하며 seed 구현은 이번 게시본에 추가하지 않았다.
- Director 분리 게시·통합 검증의 원본은 AI 기록에 유지한다. BE ADR은 이 기록을 참조하며
  현황을 중복 작성하지 않는다. 이는 루트 CLAUDE 문서 원칙과 AI ADR 0020을 따른다.

### 이번 실행 결과

Windows Python 3.12, `develop@d063d8d` 기준이다. PostgreSQL은 새 전용 로컬 cluster를 사용했다.

| 범위 | 검사 | 결과 |
| --- | --- | --- |
| 최신 develop + #127 | `pytest tests/core/test_llm_config.py -q` | 50 passed |
| 같은 게시 범위 | Ruff·format·mypy app | 통과, format 279파일·mypy 136 source |
| 같은 게시 범위 | `alembic heads`·신규 graph 검사 | 선행 #82 부재로 실패, `0002_agent_storage` 없음 |
| 로컬 #81·#82·#108·#127 결합 | 설정 + 신규 graph pytest | 51 passed |
| 같은 결합의 실제 PostgreSQL | 초기·공고·Agent·Agent merge·기존 Director merge·분석 실행의 6개 출발점 → head | 모두 단일 `0004_interview_foundation_merge`, 기존 사용자 행 보존 |
| 같은 6개 DB | 명시한 출발 revision으로 downgrade → upgrade head | 모두 통과, 기존 사용자 행·호출 기록 테이블·분석 지표 컬럼 확인 |
| 초기 출발 DB | `downgrade base` → `upgrade head` | 통과 |
| 검증 자원 | 경로별 전용 DB 생성·삭제 | 6개 모두 정리 |

DB 경로 검사의 코드 tree는 `afd5adf1ceb4f27e237e0836d6ffe233fa1ecd71`이다.
이 로컬 결합에서 #108 main의 충돌은 문서 router와 분석 router 등록을 모두 보존해 해소했다.
이는 #108의 원격 코드 수정이나 해당 PR 전체 검증 결과가 아니다.

처음 사용한 상대 `downgrade -1`은 합류 경로가 모호해 실패했다. 대상 revision을 명시하여
다시 검사한 위 결과와 구분한다. 과거 리뷰어의 전체 pytest 수치를 이번 결과로 사용하지 않았다.

### 최종 PR 조합의 추가 확인

#81·#82·#108·#124·#125·#126·#127·#132를 최신 develop에 로컬 결합했다.
검증 tree `742d924a39480a118607487c589f8901ecca10d7`에서 AI 전체 347 passed,
BE의 저장·예산·gateway·설정·graph·분석 API/worker 집중 검사 423 passed·1 skipped였다.
AI Ruff·format 57파일·mypy 13 source와 BE Ruff·format 331파일·mypy 158 source,
부분 계약 2개·fixture 7개 및 단일 Alembic head를 확인했다. 검사 전후 Python 원문 hash는 같고
실제 import 경로도 해당 결합 worktree의 AI·BE 소스였다. BE 전체 pytest 수치는 아니다.

제외된 #108 migration 검사는 이름이 고정된 별도 DB를 요구했다. 전용 DB로 실행하니
`alembic_version` 첫 행만 비교하는 기존 단일 가지 가정이 드러났다. #108에서 실패 전후
revision 전체 집합·기존 자료·위험 downgrade 차단을 보존하도록 고친 뒤 같은 누적 코드의
전용 PostgreSQL 검사 1 passed와 health 5 passed를 확인했다. analysis·documents·me·health
등록도 함께 확인했고 전용 DB는 삭제했다. #108 자체 source는 #81이 없으면 import할 수 없으므로
이 결과를 단독 완료로 보고하지 않는다. 최종 보완은 migration DDL을 바꾸지 않는다.

#126 결합에서는 기존 `generate_question`과 새 `execute_director`를 모두 보존했다.
두 함수는 각 게시본과 AST가 같음을 독립 대조했고, 공통 gateway의 주소·timeout·시도 기록도
유지했다. 이 해소본은 로컬 검증에만 사용하며 선행 구현을 다른 게시본에 복사하지 않았다.

### 병합 조건

#82·#108이 없는 게시본은 graph를 실행할 수 없으므로 develop base의 Draft로 검토한다.
두 선행 반영 후 그 시점의 실제 graph·기존 자료·전체 BE 회귀와 CI를 다시 확인해야 한다.
이 검증은 외부 모델 품질·면접 완주·운영 DB 배포 확인을 포함하지 않는다.

## 2026-10-27 — #127 순차 게시 graph의 누락 보완과 자료 보존 재검사

### 실제 결함과 수정

앞선 6개 출발점과 최종 PR 조합 검증은 #127까지 결합한 graph의 결과였다.
develop → #82 → #108만 반영한 중간 snapshot에 두 head가 남는 문제를 놓쳤다.
이전 실행 기록을 보존하고 순차 게시 단계 자체를 새 회귀 범위로 추가한다.

- #108 `ef237c56`의 신규 `0004_analysis_storage_merge`가 저장·분석 이력을 먼저 합친다.
  최종 #108 `d0704b97`에서도 해당 migration 원문은 같다.
- #127 `78d39238`은 그 신규 합류와 기존 `0004_interview_foundation_merge`를 부모로 하는
  DDL 없는 `0005_director_foundation_merge`를 추가한다. 기존 migration ID·부모·DDL은 보존한다.
- 최종 head 검사와 기존 이력 검사를 유지하고, 실제 Script의 ID·부모 metadata로
  develop·#82·#108·#127 네 snapshot의 head를 각각 확인한다. 선행 코드는 게시본에 복사하지 않는다.
- [BE ADR 0008](../backend/decisions/0008-director-foundation-publication.md)의 새 절에
  현재 목표 0005와 이전 최종 0004의 관계를 기록한다. Proposed 상태는 유지한다.

### 이번 실행 결과

Windows Python 3.12, `develop@d063d8d` 기준이다. 결합 migration source tree는
`00996aa3ae9f572ff7c67275930c291e3bb36ee7`이며, 새 전용 PostgreSQL DB에서 합성 자료를 사용했다.
아래 수치는 앞선 통합 검증 수치를 재사용한 것이 아니다.

| 범위 | 검사 | 결과 |
| --- | --- | --- |
| 새 #108 + 기존 #127 결합, 신규 회귀 | 수정 전 graph 검사 | 2 failed·3 passed, 실제 두 head와 0005 부재 확인 |
| 새 #108 + 보완 #127 결합 | `pytest tests/core/test_director_migration_graph.py -q` | 5 passed, 기존 Alembic 설정 경고 5개 |
| 같은 결합의 최신 설정 검사 포함 | 설정 + graph pytest | 55 passed, 5 warnings |
| 변경한 Python 두 파일 | Ruff·format | 통과, 2 files already formatted |
| 최신 develop + #127 게시 범위 | 설정 pytest | 50 passed |
| 같은 게시 범위 + 신규 graph 회귀 | graph pytest | 5 failed, 모두 선행 `0002_agent_storage` 부재 |
| 실제 PostgreSQL 순차 게시 | 공고 → #82 merge → #108 merge → head | 각 게시 단계 단일 head, 최종 0005, 기존 모든 fixture 행 보존 |
| 기존 branch의 두 적용 순서 | Agent → Director → Analysis, Analysis → Director → Agent → 신규 merge들 | 두 경로 모두 최종 0005, 모든 fixture 행 보존 |
| 위 세 경로 각각 | 활성 분석 작업 3개 상태에서 `downgrade 0002_posting_versions` | 기존 분석 downgrade 차단, version 전체 집합과 모든 fixture 행 보존 |
| 위 세 경로 각각 | 명시한 #108 merge로 downgrade → head 재적용 | 통과, sibling 기존 #127 merge 이력과 모든 fixture 행 보존 |
| 검사 자원·원문 | 세 경로 후 base 정리, migration SHA-256 전후 대조 | 전용 DB public 테이블 0개로 복원, 원문 hash 동일 |

fixture는 사용자·공고 원문 JSON·작업 steps·질문 Contract·호출 raw·후보 페이지 지표를 포함한다.
전진·실패 rollback·merge-only 왕복에서 해당 테이블의 전체 행 JSON을 대조했다.
위험 downgrade의 첫 probe는 저장 merge를 대상으로 삼아 분석 branch를 내리지 않았다.
공통 조상으로 대상을 교정해 실제 분석 차단을 호출한 뒤 위 세 경로를 새로 실행했다.

이 결과는 #82·새 #108을 로컬 결합한 검증이며, 미병합 선행을 포함하지 않는 단독 CI 통과가 아니다.
#127은 develop base의 Draft를 유지한다. 선행 반영 후 실제 게시 순서와 최종 BE 회귀·CI를 다시
확인해야 한다. 외부 모델·면접 완주·운영 DB 적용과 전체 BE pytest는 이번 검사에 포함하지 않았다.

## 2026-10-28 — #127 선행 병합 후 이력 보존과 검증 기록 정리

- 기준 develop은 `4e511a992d7954fa310146bcba2f2d4c6358fb69`다. #82와 #108은 모두 반영됐고,
  현재 develop+#127의 실제 graph는 `0005_director_foundation_merge` 단일 head다.
  10월28일11:20 KST 리뷰의 #108 미병합 조건은 같은 날16:15 병합 이후 해소됐다.
- 원본 #127 `d580863`을 `backup/pr127-before-review-fix-20261028`에 보존했다.
  이번 보완은 설명·검증 기록만 정리하며 기존 migration 파일 전체의 Git blob을 유지한다.
- 같은 부모를 가진 `0003_director_runtime`은 기존 경로의 이력을 보존한다. 실제 개발자·공유·운영 DB의
  전수 적용 이력은 확인하지 못했으므로 적용된 DB가 없다고 단정하지 않는다. 부모에서만 제거하면
  별도 head가 남고 파일까지 없애면 그 revision을 가리키는 DB의 이력 해석을 깨뜨릴 수 있다.
- [BE ADR0008](../backend/decisions/0008-director-foundation-publication.md)은 Proposed·날짜 이력,
  기존 ID·부모·DDL 보존 이유, 현재 합류 관계와 rollback 보호 조건을 유지했다.
  검증 실수의 반복 서술은 줄이고 상세 실행 결과는 이 기록을 원본으로 삼는다.

| 구성 | 이번에 직접 실행한 검사 | 결과 |
| --- | --- | --- |
| 최신 develop+#127 | 설정·실제 Script graph pytest | 55 passed, skip0, 34.67초, 기존 Alembic 경고5개 |
| 같은 구성 | BE Ruff·format·Mypy app | 통과, format330파일·156 source |
| 같은 구성 | 부분 계약 검사 | schema2개·fixture7개 통과. 전체 API 호환성 검증은 아님 |
| 별도 전용 DB와 격리 schema | 기존 위험 downgrade 회귀·두 선행 적용 순서 회귀 | 3 passed, skip0, 53.27초 |
| 전용 PostgreSQL15.19 | 순차 게시·Agent→Director→Analysis·역순의 세 경로 | 모두0005, 기존 fixture 전체 행 보존 |
| 위 세 경로 각각 | 중복 active 분석이 있는 위험 downgrade | 기존 guard로 차단, 자료와 version 전체 집합 보존 |
| 위 세 경로 각각 | 명시0004_analysis_storage_merge로 downgrade→head | 기존 sibling 이력과 fixture 행 보존 |
| 같은 전용 DB | base→head 재적용 후 base 정리 | 통과, 마지막 public 테이블0개·migration 원문 hash 동일 |

DB fixture는 사용자·공고 원문 JSON·분석 steps·질문 Contract·호출 raw·페이지 지표를 포함한다.
수치와 DB 결과는 이번 최신 develop 결합에서 새로 실행했으며 이전 전체1438/347 결과를 재사용하지 않았다.
리뷰에서 보고한 설정 검사 간헐 실패는 이번55개 실행에서 재현되지 않았다. 최초 실패명·traceback이 없어
원인이나 해결 여부를 확정하지 않으며 재실행 통과를 오류 수정으로 보고하지 않는다.
최신 base의 원격 CI는 게시 후 별도로 확인하고 통과 전에는 Draft 해제나 병합 가능 상태로 단정하지 않는다.
전체BE·AI·외부 모델·운영 DB·배포·면접 완주 검증은 이번 집중·합성 자료 검사의 범위 밖이다.
이전 절의 seed 오류·선행 부재·예전 목표 head는 당시 기준의 기록으로 보존한다.

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

## 2026-10-28 — PR #126 기존 어댑터 보존과 수집 한계 지침

- 원본 `68c088f`를 `backup/pr126-before-review-fix-20261028`에 보존했다. 기존 `agent.py`는
  develop `09a6f77` 원문으로 유지하고 신규 `execute_director`는 `runtime_adapter.py`로
  분리했다. 기존 함수는 전체 파일 blob, 신규 함수는 원문 AST가 같다. 신규 두 테스트의 import와
  패키지 import 검사를 갱신하고 실제 소비자인 #135의 import 경로를 함께 조정한다.
- `repo-deep-runtime-v1.md`는 입력 `source_limitations`의 미확인 범위를 확인한 것처럼
  설명하지 않고 관찰·결과의 한계에 반영하도록 명시한다. 이 지침은 모델 응답을 코드로 강제하는
  보장이 아니다. 수집 메타데이터의 별도 보존과 모델 출력의 한계를 구분한다.
- 최신 develop `09a6f77`, 이번 변경과 미병합 #125 `23873ef` runtime을 별도 로컬 사본에서
  결합했다. 기존·신규 adapter, gateway, 예산, 원문 수집·패키지 집중 검사는 104 passed, skip 0이었다.
  생성·검토 각각에서 실제 task를 취소하는 새 2사례는 취소 전파와 완료된 plan 기록만 보존함을
  확인한다. AI runtime은 38 passed, BE mypy 151 source·Ruff·format 312파일이 통과했다.
- 게시본에는 #125 runtime을 복사하지 않는다. 최신 develop 결합에서 #125를 제외하면
  runtime import와 파생 Any 반환의 mypy 2오류가 남는다. 이전 d063d8d 기준 CI의 11오류와
  이번 결과를 구분한다. #125 반영 후 실제 게시본을 다시 검사하기 전에는 Draft다.
- 최신 develop와 최종 게시 head의 merge-tree는 충돌 없이 병합된다. 대형 develop merge commit을
  게시하지 않고 소규모 후속만 추가했으며 신규 구현·검증·문서 커밋은 각각 추가+삭제 300줄 이하다.
- #133 patch03은 아직 일반 Python에 적용하지 않은 자료다. #136의 수집 한계가 실제 모델 입력에
  전달되는 실행 연결은 해당 일반 코드 반영 후 다시 검증한다. 이번에 실제 모델·외부 GitHub,
  PostgreSQL 전체 검사·면접 완주·운영 배포는 실행하지 않았다.

## 2026-10-27 — PR #126 실제 예산 경계와 선행 결합 검증

- #126 원본 `e29c8f9`를 `backup/pr126-before-budget-review-20261026`에 보존하고 후속만 추가했다.
  게시본에는 미병합 #82의 저장·도구 구현과 #125 코어를 복사하지 않는다.
- CallBudget의 읽기 전용 remaining_attempts·terminal_failure를 통해 BE가 실제 잔여량과
  종료 상태를 확인한다. Context와 실제 예산 중 작은 값을 전달하며 두 시도가 없으면
  plan 요청 전에 중단한다. 조회는 예약이 아니므로 한 예산을 다른 작업·동시 실행과 공유하지 않는다.
- 실제 gateway를 먼저 소모하는 새 회귀에서 수정 전 2 failed·2 passed를 재현했다.
  수정 후 새 예산·gateway 회귀 77건과 게시본 단독의 설정·gateway 회귀 79건이 통과했다.
- 게시본 단독 전체 pytest는 #125 runtime 2건·dispose_engine 1건의 수집 오류이고,
  mypy는 선행 모듈·API 부재 19오류다. Ruff·format 259파일은 통과했다.
- 별도 로컬 환경에 develop `d063d8d`, #82 `c38d655`, 수정 #125 `23873ef`와 #126을 결합했다.
  새 예산·기존/새 adapter·gateway 경계 95 passed, AI 전체 347 passed, AI Ruff·format 57파일·
  mypy 13 source와 BE mypy 143 source가 통과했다. BE 전체는 전용 PostgreSQL·Redis에서
  새로 실행해 1,302 passed, 0 skipped(676.97초)였다. BE Ruff·format 299파일도 통과했다.
- 결합 adapter의 generate_question은 #82, execute_director는 #126 원문과 AST가 같다.
  공통 gateway의 기존 정의는 develop+#82 결합본과 동일하며 예산 조회 속성 두 개만 추가했다.
  base_url·deadline·attempt_sink와 #97 고정 배분을 보존한다. 준비 상한의 env 블록은
  면접 정책 끝의 동시 수정과 분리했다. adapter는 선행 #82와 합쳐 두 함수를 모두 보존해야 한다.
- 이 결과는 결합본의 새 검사이며 게시본 단독 성공이 아니다. 직접 선행 #82·#125와 명세를
  반영하고 최종 호출 경로를 다시 검사하기 전에는 Draft다. 준비·worker·WS 활성화, 면접 완주,
  실제 모델 품질·외부 GitHub는 이번 검증에 포함하지 않았다.

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

## 2026-09-28 — jd_requirements 초안 정리 (불릿·상한 배분)

- 구현: `backend/app/llm_tasks/jd_extract.py`. 원문 줄머리 목록 기호(`•`·`∘`·`-` 등)를 떼고 기호만 있는 줄은 버린다.
  합계가 20개(`MAX_REQUIREMENTS`)를 넘으면 필수 요건을 먼저 담고, 남은 자리는 우대와 주요 업무가 한 줄씩 번갈아 나눈다.
  이전에는 필수→우대→업무 순으로 채워 우대가 긴 공고에서 주요 업무가 잘렸다(341487은 업무 15개가 모두 빠짐).
- 검증: `backend`에서 `uv run python -m pytest tests/llm_tasks` 20 passed(13 skipped), 변경 파일 대상 `ruff check`·`ruff format --check`·`mypy` 통과.
  실제 원티드 공고 5건(359638·281356·229817·341487·380611)에서 필수 요건이 잘리지 않고 주요 업무가 남는 것을 확인했다.
- 범위 밖: 회사가 자격요건 칸에 우대 문장("~이면 좋아요")을 넣은 경우의 재분류는 `jd_extract_v1`의
  "Wanted 필드를 추측으로 변경 금지"(`spec/ai/contracts.md`)에 따라 하지 않는다. "[함께 할 업무예요]" 같은
  섹션 제목 줄도 내용 판단이 필요해 거르지 않았다.

## 2026-10-05 — #77 리뷰 반영 (내용 속 `*`·`-` 보존, 상한 경계)

- 리뷰(동한님): 기호 뒤 `\s*` 때문에 `*nix`·`*.yaml`·`-40°C`의 `*`·`-`까지 지워져 원문 의미가 바뀜.
  `•`·`∘` 같은 전용 기호는 그대로 떼고, `*`·`-`는 뒤에 공백이 오거나 기호만 있는 줄일 때만 떼도록 고쳤다.
- 상한 정책은 유지하고 경계를 명시했다: 카테고리별 최소 개수 보장 없음. (필수 19, 우대 1, 업무 1) → (19, 1, 0),
  필수 20개 이상이면 필수 앞 20개만 남는다. docstring과 `test_cap_boundaries`에 기록.
- 검증: `backend`에서 `python -m pytest tests/llm_tasks/test_jd_extract.py tests/integrations` 155 passed,
  변경 파일 대상 `ruff check`·`ruff format --check`·`mypy` 통과.

## 2026-10-06 — 도메인 category LLM 판정 (0022)

### 기준과 변경

- 작업 브랜치: `feature/domain-category-llm`, 기준 develop `ef1a48d`. #74의 키워드 규칙안은 채택하지 않았다.
- `ai/src/devon_ai/contracts.py`: `DomainPostingInput`(position·intro·main_tasks·requirements·preferred_points).
  회사명·`industry_name` 필드가 없어 구조상 입력할 수 없다.
- `ai/src/devon_ai/llm_tasks/domain_category.py`: `classify_domain`이 주입된 `model_call`로 한 번 호출하고
  `{category, evidence}`를 검증한다. `etc`가 아닌데 공백 정규화한 근거가 원문에 없으면 `etc`, schema·provider
  실패도 `etc`로 돌려준다(재호출 없음). 원문이 비면 호출하지 않는다. prompt·limits·입력 타입 오류는 호출 전에
  거절한다.
- `ai/prompts/domain-category-v1.md`: 검수 전 prompt 초안.
- `ai/tests/llm_tasks/test_domain_category.py`: 입력 계약 필드, 근거 채택·정규화, 근거 불일치·빈 근거의 `etc`,
  schema 위반 4종, provider 실패, 원문 없음 비호출, prompt 불일치 거절.

### 실행 결과

환경: Windows, uv. `ai`에서 `ruff check .`, `ruff format --check .`, `mypy`(12개 파일) 통과, `pytest -q`
205 passed. `backend`에서 `tests/agents/test_ai_package_imports.py` 1 passed.

### 검증 한계와 후속 작업

- 실제 provider 호출과 정확도 평가는 미실행이다(API 키 없음). 평가 도구는 원티드 개발 공고 100건 표본과
  미검토 라벨로 준비돼 있으며, 실행 시 데이터셋·모델 버전·비용·지표를 함께 기록한다.
- BE 연결은 범위 밖이다: `PostingContent.intro` 필드, `jd_extract` 단계 안 호출, `seed_prompt_versions.py`의
  `domain_category` 등록, BE adapter와 `postings.domain_category` 저장.

## 2026-10-26 — 도메인 category v2: 근거 문단 ID와 semantic 실패 기록 (0028, #99 리뷰 반영)

### 기준과 변경

- 작업 브랜치: `feature/domain-category-llm`, develop `2ff1acf`로 rebase. 리뷰 기준 원본은 `be44f00`.
- `ai/src/devon_ai/llm_tasks/domain_category.py`: 입력 필드를 `[{id, text}]` 문단 목록으로 바꿔 보내고
  `{category, evidence_id}`를 받는다. 요청별 문단 표로 만든 validator가 schema·semantic을 검사하고, 선택한
  ID의 원문을 `evidence`로 복원한다. 근거 검증이 공통 호출 계층 안으로 들어가 semantic 실패가 `failure`와
  attempt `error_stage/error_code`로 남는다(리뷰 P2).
- `ai/prompts/domain-category-v2.md`: 문단 ID 선택, 산업 전용 지원 서비스와 `mobility` 범위·경계. v1은 보존.
- `ai/tests/llm_tasks/test_domain_category.py`: 문단 변환(빈 줄 분리, 문단 안 줄바꿈 유지), ID의 원문 복원,
  정상 `etc` 성공, 잘못된 ID 4종(없는 ID, 인용문을 ID로, non-etc `null`, `etc`의 ID)의 semantic 기록·무재시도,
  schema 위반 5종, provider 실패, 원문 없음 비호출, prompt 불일치 거절.

### 실행 결과 (이 브랜치, 2026-10-26)

환경: Windows, uv. `ai`에서 `ruff check .`·`ruff format --check .`·`mypy`(12개 파일) 통과, `pytest -q` 209 passed.
`backend`에서 `tests/agents/test_ai_package_imports.py` 1 passed.

실제 BE `call_model` + `httpx.MockTransport`(외부 호출 없음)로 4개 응답을 확인했다.

| 모델 응답 | category | failure | attempt 오류 | HTTP 호출 |
| --- | --- | --- | --- | --- |
| `medical`, 있는 ID | `medical`(원문 복원) | 없음 | 없음 | 1 |
| `medical`, 없는 ID | `etc` | semantic | (semantic, llm_failed) | 1 |
| `medical`, `null` | `etc` | semantic | (semantic, llm_failed) | 1 |
| `etc`, `null` | `etc` | 없음 | 없음 | 1 |

### 리뷰어 실측 (동한님, 2026-10-12, 로컬 수정 후보 기준 — 이 브랜치 코드로 재실행하지 않음)

모델 `gpt-6-luna`, PR #114 gateway.

- v1, 원티드 공고 500건: 의료 4·금융 3건이 인용 재작성으로 `etc`, 실패 기록 누락 재현.
- v2, 같은 500건: 호출·근거 검증 실패 0건, 위 7건 medical 4 / finance 3 채택. 입력 토큰 916,031 → 1,244,571(+35.9%).
- v2, 회귀 61사례 61/61, 신규 회사 공고 40건 사전 기대 38/40(허용 경계 포함 39/40). 기대값은 확정된 사람
  정답표가 아니다.

### 검증 한계와 후속 작업

- 이 브랜치의 v2 코드·prompt로 실제 모델을 호출하지 않았다(API 키 없음). 리뷰어 수치는 같은 설계의 로컬 후보 결과다.
- ID 검증 성공은 분류 정확도를 보증하지 않는다. 사람 라벨 평가는 0022의 100건 표본 계획을 따른다.
- BE 연결은 0022와 같은 후속 범위이며, 등록할 prompt version은 `domain_category_v2`다.

## 2026-10-26 — #99 동시 갱신 보존 후 원문·version 회귀 보완

- 리뷰 대응 중 팀원 head가 `be44f001`에서 `ce1019a9`로 갱신된 것을 확인했다. 기존 로컬 수정·
  게시 후보는 보존하고 최신 head에서 새 작업 트리를 만들었다. 팀원의 v2 코드·기존 AI 테스트
  16사례·prompt·Accepted ADR0028·계약·실행 기록을 유지하며, 별도 중복 설계·ADR은 추가하지 않는다.
- 원문 ID·semantic 기록·산업 지원 범위의 주요 리뷰는 최신 팀원 변경이 해결했다. 이번 추가는
  원문 복원과 v2/schema 2 일치라는 같은 계약을 끝까지 지키는 보완과 실제 gateway 회귀다.
- `_paragraphs`에서 양 끝 공백을 지우지 않고 빈 문단만 제외한다. CRLF 빈 줄 경계는 정확히
  분리하되 문단 내부 줄바꿈·비가시 문자·오탈자·공백을 그대로 반환한다. v1/v3 prompt는 schema 2와
  혼용하지 않도록 모델 호출 전에 거절한다. 분류 정책·공개 API·DB 구조는 바꾸지 않는다.
- 팀원 테스트 파일은 교체하지 않고 `test_domain_category_review.py`에 8사례를 추가했다.
  source에 존재하는 ID도 현재 요청의 원문에서 복원하는지 검사한다. 산업 의미의 정확도 검사는 아니다.
- 실제 gateway 7사례는 `test_domain_category.py`에 별도로 둔다. raw·오류·실제 모델·token·version,
  semantic 무재시도·정상 etc·schema 오류 후 총 2회 상한을 검사한다. 테스트 helper만 #114의
  주소 인자가 있으면 명시적 fixture 주소를 주입한다. 제품의 기본 주소·호환 gateway는 추가하지 않는다.

| 최신 head 기준 이번 검증 | 실제 결과 |
| --- | --- |
| 보완 전 새 AI 회귀 | 7 failed / 1 passed. 공백·CRLF·버전 혼용을 실제로 재현 |
| 보완 후 팀원 기존 16 + 새 8사례 | 24 passed. 기존 테스트 파일 무변경 |
| AI 전체 pytest | 217 passed. 이전 로컬 후보 230개 결과와 구분 |
| BE import·기존 gateway·새 도메인 회귀 | 77 passed. 새 도메인 7사례 포함 |
| AI / BE Ruff·format·mypy | 모두 통과. format 45/254파일, type 12/133 source |
| 기존 전용 환경의 부분 계약 검사 | schema 2개·부분 OpenAPI·fixture 7개 통과. 전체 API/FE 호환성은 아님 |

검사 전후 Python 소스 해시는 같다. 외부 모델·GitHub 호출·패키지 설치는 0회이며 DB·서비스 완주와
실제 분류 품질은 검증하지 않았다. 로그는 `.claude/scratch/ai-pr-reviews-20261026/pr99-concurrent/`에
보존한다. 이전 v1·로컬 v2 후보·팀원 원본의 검증 수치를 이번 보완본의 새 결과로 합치지 않는다.
다른 PR과 새로 결합한 결과 및 실제 게시 head는 후속 게시·재검증에서 구분해 기록한다.
