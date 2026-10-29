# AI 구현·검증 기록

## 2026-10-25 — 미게시 면접 실행과 후속 보완의 Draft 게시

### 원본과 신규 범위

- 원본 tree `c8f2cb5d`와 실제 worktree·index를 보존했다.
  `backup/director-unpublished-before-pr-20261025`는 원본 tree를 보존한 commit을 가리킨다.
- 선행 통합 tree `a4d7c1bf` 대비 원본 신규 36파일을 대조했다. 기게시 신규분 10파일,
  일부 게시 11파일, 전부 미게시 13파일, #131 담당으로 제외·보존한 seed 2파일이다.
  파일 수만이 아니라 함수·수정 구간과 테스트 사례까지 대응시켰다.
- 게시 기준은 `develop@dbd7f890`이다. 기존 #124~#127, #131과 다른 선행 PR은 변경·병합하지 않았다.
  초기 설계는 보존하고 실행 명세는 [#132](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/132),
  미적용 Context·L2 보완은 [#133](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/133)으로 분리했다.

| 구간 | 이번 게시의 배치 |
| --- | --- |
| 준비·Director 실행·WS·앱/worker | 신규 실행 코드와 회귀 검사를 이 구현 PR에 게시 |
| 현재 답변 Context·9번째 답변·수집 한계 | #133의 `agent_context.py`, `answer_context.py` 미적용 패치 |
| L2 예산·호출 기록·base URL·한계 | #133의 `repo_deep.py` 미적용 패치 |
| 기존 Director 생성기의 base URL 한 줄 | #133의 어댑터 미적용 패치 |
| 수집 상한 | #126의 8개 설정은 재게시하지 않고 남은 진행 중 조회 3개와 검증만 추가 |
| 준비 테스트 | #126에 옮긴 2함수·3사례를 제외하고 나머지 함수 AST를 보존 |
| WS·준비·현재 답변의 통합 회귀 | 실행 서비스에 의존하므로 이 구현 PR에 함께 게시 |
| seed 실행·추가 seed 검사 | 이번 변경에서 제외. #131 전담과 로컬 원본 보존 유지 |

#133은 일반 Python 파일에 아직 적용하지 않은 검토 자료다. 패치만 병합해도 기능은 활성화되지
않으며 앱·빌드·CI에서 자동 적용하지 않는다. 정확한 선행 base에서 일반 코드에 적용하고
재검증해야 한다. 선행 구현·DB 모델·migration·의존성·기게시 함수 전체를 복사하지 않았다.

### 게시본 단독 검사

| 검사 | 실제 결과 |
| --- | --- |
| 명세 #132의 부분 계약 검사 | schema 2개·부분 OpenAPI·fixture 7개 통과 |
| 실행 게시본 Ruff·format | 통과, format 260파일 |
| 실행 게시본의 조회 상한 검사 | 3 passed |
| 실행 게시본 전체 pytest | 수집 오류 9건. #82의 모델·#120의 router 등 선행 부재와 기존 seed import 오류 |
| 실행 게시본 mypy | 4파일 30오류, 134 source 검사. 선행 어댑터·모델·Context·REST 타입 부재 |
| 패치 4개 | SHA-256·base/result blob 일치, 정확한 선행에서 적용 검사·적용 후 원본 blob 대조 통과 |
| 원본 보존·범위 | 원본 36파일·index 동일, 신규 PR 간 파일 중복 없음, seed·DB 모델·선행 migration 미포함 |

### 별도 로컬 통합 검증

원본 선행 통합과 이번 코드·패치를 결합한 별도 환경을 사용했다. runtime 함수와 분리한 테스트는
원본 AST와 대조했다. 설정 3개와 #126의 나머지 설정도 원본과 일치한다. seed 오류 해결은
게시하지 않고 #131의 seed 두 파일을 검증 환경에만 연결했다. 외부 모델·GitHub는 대역이며
실제 외부 모델·서비스 DB·사용자 자료에 접근하지 않았다.

- 기존 Python 3.12.14, 새 전용 PostgreSQL 15.19·Redis 7.4.11을 사용했다.
- BE 첫 전체 실행: 1,231 passed·74 setup errors·경고 2개. 74건 모두 분석 fixture의
  `task10_test` DB 이름 조건 위반이며 기능 실패는 없었다. 통과·오류를 합쳐 전체 통과로 쓰지 않는다.
- AI 전체 실행: 295 passed. BE/AI Ruff·format·mypy 통과이며 각각 format 292/52파일,
  type 검사 141/12 source다.
- 올바른 새 `task10_test` DB에서 정확히 그 74개 오류 사례만 재실행해 74 passed를 확인했다.
  첫 전체 445.54초·exit 1과 재실행 108.78초·exit 0을 구분하며, 서로 다른 고유 BE 사례
  1,305개를 검증했다. 한 번의 전체 실행이 모두 통과했다고 표시하지 않는다.
- 각 실행 전후 통합 Python 소스 해시는 같았다. 생성한 두 테스트 DB 삭제·임시 schema 0개·
  연결 0개·DB 목록 복원·Redis/PG 종료와 포트 해제를 확인했다. 기존 서비스는 변경하지 않았다.

검증 보조 스크립트의 첫 Redis 기동은 Cygwin의 config 경로 해석으로 중단됐으며 생성 DB·서버를
정리하고 상대 config 경로로 재실행했다. DB 명명 문제도 보조 환경만 수정했으며 Python 소스는
변경하지 않았다. 실제 결과와 오류 목록은 원본 저장소의
`.claude/scratch/director-remaining-publication-20261025/validation-runtime/`에 보존한다.

### 병합 전 조건과 남은 범위

- Draft다. 필요한 선행·#132 명세·#133 후속 패치의 일반 코드 반영 뒤 최신 base에서 통합 재검증한다.
- #124/#125/#127과 공유하는 계약·설정·결정 색인·구현 기록은 각 신규 구간을 합쳐 보존한다.
  이번 PR의 파일 전체로 다른 PR의 추가 구간을 덮어쓰지 않는다.
- 준비 이벤트·preparing WS 유지·정확한 단계 재개·명시적 이탈 wire·일반 lease/reaper는 미완료다.
  Report·음성·다언어/대형 레포의 의미 품질·실제 모델 평가·배포도 이번 완료 범위가 아니다.

## 2026-10-26 — #134를 BE Task 13·14·15로 분할

### 범위 보존과 배치

- 사용자가 #134를 task별로 나누도록 요청했다. 원격 head `f2da245f`와 기존 브랜치를 보존하고
  `backup/pr134-before-task-split-20261026`을 만들었다. 게시본은 모두 `develop@dbd7f890` 기준이다.
- Task 13은 준비·worker·REST 앱 등록과 기존 준비/등록 검사를, Task 14는 Director·답변 분석·
  근거 조회 상한과 서비스/Context 검사를, Task 15는 WS·연결 인계와 WS 앱 등록/검사를 담당한다.
- 실행 ADR0026과 단일 구현 기록은 Task 14, WS ADR0024와 결정 색인은 Task 15에만 둔다.
  원본 18파일을 빠짐없이 배치하고 일반 파일을 중복 게시하지 않았다.
- `main.py`만 REST 등록 2행과 WS 등록 2행으로 나눴다. Task 14 → Task 13 → Task 15 순서로
  반영하며, 공유 삽입 구간의 충돌은 두 등록을 모두 유지해 해결해야 한다. 합성 결과는 원본과 같다.
- 기존 함수·fixture·decorator·설정·테스트를 보존했다. 원본 6개 테스트 파일의 59사례는 그대로며
  Task 15에 실제 앱의 WS 매칭/이름 경로를 검사하는 1사례만 추가했다.

### 이번 실행과 이전 기록의 구분

위 2026-10-25 절은 원본 #134의 검증 이력이다. 당시 전체 1,305개·AI 295개 결과를 이번 분할본의
새 전체 검사 통과로 사용하지 않는다. 이번에는 분할 합성본의 직접 관련 사례와 등록을 재검증한다.

| 범위 | 실제 검사 결과 |
| --- | --- |
| Task 13 게시본 | Ruff·format 255파일 통과. 전체 pytest 수집 6오류·mypy 2파일 10오류, 선행 모델/라우터/서비스 부재와 기존 seed 오류 |
| Task 14 게시본 | Ruff·format 257파일·조회 상한 3사례 통과. 전체 pytest 수집 3오류·mypy 1파일 15오류, 선행 부재 |
| Task 15 게시본 | Ruff·format 255파일 통과. 전체 pytest 수집 6오류·mypy 1파일 7오류, 선행 부재 |
| 새 선행 결합본 | 원본 59사례+새 WS 등록 1사례, 60 passed·2 warnings·102.52초·exit 0. 원본 6개 테스트 파일 byte 동일 |
| 실제 앱 등록 | REST 4경로·WS 1경로의 공개 매칭 API와 WS 이름 경로 확인. 빈 앱에서 새 검사가 실패하는 negative probe 확인 |
| 결합본 정적 검사 | BE Ruff·format 293파일·mypy 141 source, AI Ruff·format 52파일·mypy 12 source 모두 통과 |
| 공개 계약 형식 | 세 게시본의 계약 파일은 동일·무변경. backend venv는 검사 의존성 부재로 미실행 후 기존 전용 venv 재사용, schema 2개·부분 OpenAPI·fixture 7개 통과. 전체 API 호환성 검증은 아님 |
| 실행 후 정리 | 생성 DB 삭제·임시 schema/연결 0개·DB 목록 복원·PG/Redis 종료·16094/16095 포트 해제 확인 |

첫 결합 검사는 공통 설정 파일 전체 교체로 선행 설정이 누락돼 실행 전 중단됐다. 설정은 선행과
신규 구간을 함께 보존하도록 바로잡았다. 다음 등록 probe는 설치 FastAPI의 포함-router 표현을
평탄한 경로 목록으로 가정해 중단됐다. 실제 등록은 정상이며 공개 matches/이름 경로 API로 검사와
추가 테스트를 정리했다. 원본 서비스 코드는 바꾸지 않았다.

검증 복사 필터가 기존 `features/report` 골격 5파일을 제외한 것도 확인했다. 이전 통합본과 byte가
같은 5파일을 복원하고 BE 정적 검사만 재실행했다. 앞서 실행한 450파일은 그대로이며, 복원 후
455파일도 정적 검사 전후 hash가 같다. 관련 60사례를 전체 1,305개 재실행으로 표시하지 않는다.
실제 모델 호출·AI 전체 테스트는 이번에 실행하지 않았다. 이번 로그와 최종 메타는 원본 저장소의
`.claude/scratch/pr134-task-split-20261026/validation-runtime/`에 보존한다.

### 게시와 후속 조건

세 PR은 모두 Draft이며 선행·#132 명세·#133 미적용 후속 패치의 일반 코드 반영 뒤 재검증해야 한다.
새 PR의 실제 원격 범위를 확인한 뒤 #134와 상호 연결하고 기존 PR만 닫는다. 원본 브랜치는 삭제하거나
재작성하지 않는다. seed·#131, 다른 선행 PR, 기존 미완료 범위는 이번 분할로 변경하지 않는다.

## 2026-10-30 — #135 실행 경계의 새 리뷰 반영

- 원본 `b262298`과 별도 로컬 통합본을 보존했다. 신규 실행 보완만 후속 커밋으로 추가하며
  선행 Context와 공통 설정 필드를 복사하지 않는다. 공유 byte 상한 설명은 공통 PR에 둔다.
- `process_answer`의 답변 저장·T3 성공 후 정상 완료 책임을 명시했다. 기존 WS 송신 경계가
  처리하는 예상 I/O 오류와 예상 밖 콜백 예외·실제 취소를 구분한다. 이미 확정한 답변을
  재전송했다고 모델 작업을 자동 재실행하지 않는다. 종료 비교는 기존 9턴 상수를 재사용한다.
- 내부 scope가 없으면 외부 조회 전에 `evidence_scope_invalid`로 거절한다. 준비 호출자는
  같은 DB 세션과 잠근 최신 면접 행을 받는 비동기 guard를 주입한다. 호출 전과 저장 직전에
  소유권·입력 snapshot을 검사하며 외부 HTTP를 실행하지 않는다. 기본 None 경로는 유지한다.
- 테스트 helper 7개를 공용 모듈로 옮겼다. 기존 테스트 14함수·helper 7개의 AST 본문과
  Settings AST를 보존했고, 설정 문단 제목만 담당 구간에서 정리했다.

| 이번 검증 구성 | 결과 |
| --- | --- |
| 최신 develop + #135 + 정확한 Context01/02, 누락 scope·콜백·취소 | RED 1 failed/4 passed → GREEN 5 passed |
| 최종 비동기 DB guard의 두 저장 경계 | RED 2 failed → GREEN 2 passed, skip0 |
| 최종 API의 기존 None 경로 | 별도 28 passed, skip0 |
| 같은 최종 소스의 BE Ruff·format·Mypy | 통과, format 348파일·type 160 source |

위 2개+28개는 서로 다른 집중 사례다. 앞선 동기 guard 구성의 30개와 mutation 검사는
이전 단계의 이력이며 최종 API의 검증 수치에 더하지 않는다. 전체 결합 결과는 같은 기록의
[공통 검증](#director-review-integration-20261030)에서 관리한다. 외부 모델·운영 배포를 검증한
결과가 아니며 필요한 공통 선행 코드가 develop에 반영되기 전에는 Draft를 유지한다.

## 2026-10-28 — #124 후속 검토의 미실행 조회 범위 보존

- #124의 [새 리뷰](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/124#issuecomment-6447685428)에 대응하는
  실행 보완은 #135에 둔다. #124는 계약 문단 위치만 정리하며 선행 service를 복사하지 않는다.
- 기존 정상 경로에는 이미 나머지 요청을 한 라운드 제한으로 실행하지 않았다는 공통 이유가 있었다.
  이번에는 생략한 허용 요청마다 repo·고정 SHA·path와 턴당 1개 제한 사유를 기록한다.
- 실제 I/O는 첫 요청 하나만 실행한다. 해당 실행의 status·items·searched_scope·error_code는 유지하고,
  생략 범위는 ToolResult.limitations와 저장 요약에 더해 보강 T3·후속 T4에 전달한다.
  조회 시작·취소·도구 오류·보강 실패·다음 질문 확정 뒤에도 이 설명을 보존한다.
- 기존 생성기의 `agent.py`를 유지하는 #126의 별도 `runtime_adapter.py`에서 신규 실행자를 import한다.
  새 API·DB 필드·테이블·조회 loop나 예산 초기화는 추가하지 않는다.

| 구성 | 이번에 직접 실행한 검사 | 결과 |
| --- | --- | --- |
| 수정 전 service와 신규 다중 요청 회귀 | 정상 미발견·도구 오류·보강 실패·취소 | 4 failed, 모두 생략 path 누락 재현 |
| develop `09a6f77` + #125 `23873ef` + #126 실행 연결 + #135 + 로컬 Context 후속 | PostgreSQL service·Context 한계·조회 상한 | 23 passed, skip 0, 최종 별도 adapter 연결 후 99.36초 |
| 같은 최종 로컬 결합 | Mypy app·변경한 Python 4파일 Ruff·format | 152 source 및 4파일 통과 |
| #135 단독 게시 소스 | BE Ruff·format·조회 상한 | 통과, format 257파일·3 passed |
| 같은 단독 게시 소스 | Mypy app | 선행 없는 원래 base 기준 1파일 15오류, 134 source |

로컬 Context 보완은 #133 patch01·02의 정확한 base/result blob과 SHA를 확인해 적용했다.
다른 미적용 패치나 선행 코드는 게시본에 복사하지 않았다. 최종 별도 adapter는 #126 후속 수정본을 사용했다.
게시본과 로컬 결합의 service·신규 회귀 bytes는 같으며 기존 service 테스트·도우미의 AST도 보존했다.
기록의 공용 파일 끝 충돌은 기존 실행 기록 내용을 보존한 배치와 이미 병합된 고정 배분 안내만 정리했다.
최신 develop과 게시 head의 실제 merge-tree는 충돌이 없다. 필요한 #125·#126과 Context 후속의 일반 코드
반영 및 실제 게시본 재검증 전에는 단독 실행 완료로 보지 않는다. 위 검사는 새 집중 검사이며 이전
전체 BE·AI 결과나 실제 외부 모델·GitHub·배포·전체 WS 검증 수치를 재사용하지 않는다.

## 기록 관리 기준

AI 작업의 구현·수정 내역, 코드 위치, 실행 결과와 남은 작업을 관리하는 원본이다.
기능 요구사항·초기 설계·검증 방법은 각 명세에, 지속할 결정의 맥락·이유·영향은
[decisions](decisions/README.md)에 보존한다. 문서 역할은
[ADR 0020](decisions/0020-implementation-record-policy.md)을 따른다.

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
