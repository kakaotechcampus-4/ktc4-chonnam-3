# LLM 호출 경계 구현 기록

상태: 2번 항목의 AI 패키지 구현·fake 검증 완료. BE 연결·운영 검증은 미실행.
사용자의 2026-09-22 지시에 따라 별도 브랜치·분할 커밋·push까지 수행하며 PR은 만들지 않는다.

## 기준과 범위

- 선행 PR #50이 미병합이므로 `feature/ai-contracts`의 `3fe5d07`에서
  `feature/ai-llm-boundary`를 분기했다.
- [내부 계약](../contracts.md#model-gateway와-실패),
  [ADR 0010](../decisions/0010-sprint1-interface-runtime-decisions.md),
  [task-03](../../../ai/docs/task-03-llm-boundary.md)을 따른다.
- 최신 `develop@ebbe13d`의 task-03, 내부 계약, ADR 0011·0014·0015·0018도 대조했다.
  선행 구현을 포함하는 브랜치에서 작업하므로 최신 문서 전체를 이 변경에 복사하거나 병합하지 않았다.
- 최초 지시의 재시도 근거 ADR 0004는 답변 평가 결정이다. 실제 재시도 소유권·총 2회·semantic
  재호출 금지의 근거는 ADR 0010이다.
- 최초 지시의 provider 미정 설명은 최신 ADR 0011의 모델 선택으로 대체된다. 선택 모델은 BE
  설정·seed에서 전달하며 이 구현에는 모델명·credential·운영 prompt 상수와 SDK 의존성이 없다.

## 구현과 책임

기존 `contracts.py`에 호출 요청·원시 응답·실패·attempt·성공 결과 타입을 두고, 기존
`llm_tasks/__init__.py`의 `call_model` 함수가 공통 호출 정책을 처리한다. 별도 gateway 모듈,
client 클래스, facade, Protocol은 추가하지 않는다. 주입 callable은
`Callable[[ModelRequest], Awaitable[ModelResponse]]`이며 정확히 한 번의 transport 시도만 수행한다.

| 입력·출력 | 구현 의미 | 소유권·제한 |
| --- | --- | --- |
| `ModelRequest.task_name`, `model` | 호출할 작업과 요청 모델 | BE가 확정하여 주입 |
| `prompt`, `prompt_version` | 사용할 문자열·버전 | BE prompt loader 책임, DB session을 AI에 전달하지 않음 |
| `schema_json`, `schema_version` | provider에 전달할 schema·버전 | BE/task가 로컬 검증 계약과 일치시킴; 이 문자열만으로 성공을 확정하지 않음 |
| `input_json` | BE가 검증·구성한 작업 입력의 JSON 문자열 | 사용자 원문·입력 준비와 Context 검증은 호출자 책임 |
| `timeout_seconds`, `max_output_tokens` | 필수 주입하는 유한한 양수 timeout·양의 정수 출력 token 상한 | fixture 수치는 운영 기본값이 아님; token 상한의 실제 provider 전달은 adapter 책임 |
| `ModelResponse` | 원시 문자열·실제 응답 모델·input/output tokens | transport가 실제 metadata 수집; token 미수집은 `None`, 관측된 0과 구분 |
| `ModelAttempt` | 요청 식별 정보·버전·시도 번호·지연·응답·실패 분류 | 메모리 내 전달용; DB 저장 schema나 공개 응답이 아님 |
| `ModelSuccess[T]` | `ContractChecked[T]`와 모든 attempt | parse·schema·semantic 검사 통과; BE의 권한·저장·공개 승인과 다름 |
| `ModelFailed` | 마지막 typed failure와 모든 attempt | 성공 `data` 필드 없음; 빈 성공·기본값 추측·원문 수정 없음 |

`contract_type`으로 1번 항목의 구조 검사를 실행하고, 주입된 `validate`가 현재 Context의
참조·Persona·범위 등 semantic 검증을 수행한다. 검증기는 같은 후보를 감싼 `ContractChecked`를
반환해야 한다. 자연어 검증기·답변 분석·Director 기능 자체는 각각 후속 항목이다.

## 실패와 실행 상한

| 실패 | 내부 코드 | 동작 |
| --- | --- | --- |
| timeout | `llm_timeout` | 1회 재호출, 최대 총 2회 |
| provider | `llm_failed` | 1회 재호출, 최대 총 2회 |
| parse | `llm_parse_failed` | 1회 재호출, 최대 총 2회 |
| schema | `llm_failed` | 1회 재호출, 최대 총 2회 |
| semantic | `llm_failed` | 즉시 실패, 재호출 없음 |

두 번째 시도도 같은 요청을 사용한다. 별도 repair prompt·fallback 모델·재작성 호출은 없다.
JSON 중복 key와 NaN/Infinity를 거부하며, Python JSON parser의 정수 크기·재귀 한계 예외도
parse 실패로 처리한다. 해석에 성공했지만 계약에 맞지 않는 scalar/배열/객체는 schema 실패다.

각 transport 시도에 timeout을 적용하고, 취소를 삼킨 adapter가 늦게 반환한 결과도 성공으로
처리하지 않는다. 외부 작업 취소는 그대로 전파한다. adapter의 프로그래밍 오류는 provider
실패로 숨기거나 재시도하지 않으며, 예상 provider 오류만 `ModelProviderError`로 매핑해야 한다.
비동기 취소에 협조하지 않고 영구 대기하거나 event loop를 막는 adapter를 강제로 종료하는
기능은 없다. BE adapter의 자체 transport timeout과 취소 준수가 필요하다.

ContextVar로 한 호출 안에서 공통 호출 경계를 다시 사용하는 중첩을 차단한다. 독립적인
동시 호출은 각자의 attempt 상한을 갖는다. SDK가 내부에서 몰래 재시도하거나 worker가
실패 작업을 재실행하는 동작까지 AI 함수가 관찰·차단한다고 주장하지 않는다. BE 연결 시
SDK/provider retry 비활성화, ARQ `max_tries=1`, 실제 transport 호출 횟수 검증이 필요하다.

## 원문과 metadata

각 시도의 원시 응답을 보존하므로 첫 실패 뒤 성공해도 실패 원문과 실제 응답 모델·token을
확인할 수 있다. transport 응답을 받지 못하면 `response=None`이며 요청 모델을 실제 응답
모델로 추정하지 않는다. latency는 transport 시작부터 해당 후보 검증까지의 시도 시간이다.

prompt·입력·schema·raw output·검증된 data를 자동 `repr`에서 제외하고 로그를 생성하지 않는다.
실패 메시지에는 provider exception 내용이나 거부된 값을 복사하지 않는다. 이것은 모든
직렬화 도구의 마스킹이나 DB 암호화를 제공하는 것이 아니다. BE는 객체 전체를 application
log에 직렬화하지 않고 승인된 저장 위치·접근 권한·마스킹을 적용해야 한다.

호출 기록은 반환하는 메모리 데이터다. 프로세스 중단·외부 취소·DB 쓰기 실패에서의 영구
보존을 보장하지 않는다. 최신 ADR 0018의 내부 보관·재사용 정책은 유지하지만 실제 저장
위치·권한·보관 연결을 이번 AI 단위 구현으로 완료 처리하지 않는다.

## 검증과 인계

- 정상·실패 테스트를 먼저 실행해 실패를 확인한 뒤 각 구현을 추가했다.
- 시작 기준선은 99개, 완료 기준선은 157개 테스트다. 신규 경계 테스트는 58개다.
- 정상 반환, 4종 retry의 성공 복구/상한 소진, semantic 즉시 중단, 미수집 token, 원문 분리,
  엄격 JSON, 중첩 호출, 독립 동시 호출, timeout 취소, 외부 취소, 늦은 응답을 fake로 검증했다.
- Windows `asyncio` 초기화가 import 격리 검사와 충돌하여 실제 함수 호출 시점에 import한다.
  기존 환경변수·네트워크·DB·역의존 import 격리 검사도 통과했다.
- 독립 리뷰의 파서 자원 한계와 만료 응답 처리 지적을 회귀 테스트와 함께 수정하고 재검토했다.
- 실행 명령: `uv --directory ai sync --locked --python 3.12`,
  `uv --directory ai run --locked ruff check .`,
  `uv --directory ai run --locked ruff format --check .`,
  `uv --directory ai run --locked mypy src`, `uv --directory ai run --locked pytest`.
- 공유 계약 검사는 전역 Python 대신 uv의 Python 3.12와 별도 검사 requirements로 실행한다.
  실제 최종 실행 결과와 커밋 목록은 항목 완료 보고에 남긴다.
- **미실행:** 실제 모델·계정 접근·비용·품질, concrete BE adapter·prompt loader·worker 연결,
  DB 영구 저장·공개 오류 매핑·전체 작업 budget 검증.
- **범위 밖:** 3번 답변 분석, 4번 Director 구현, 5번 턴 정책, FE/BE 변경, PR 생성.
- **후속 구현:** 운영 timeout/token/context/tool/동시성 설정과 실측, BE schema/version 정합성,
  SDK retry 비활성화·중복 worker 실행 차단, 원문 보호·영구 보존 연결.
