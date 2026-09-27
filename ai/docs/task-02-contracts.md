# task-02 - AI 내부 계약 검토와 채택

> 상태: 구현 가이드. AI runtime과 내부 DTO/schema/Protocol은 아직 구현되지 않았다.
> 선행: [전체 순서](pipeline.md), [task-01 패키지 셋업](task-01-setup.md)

## 목표

`devon_ai`와 BE 연결 계층이 공유할 내부 입력·출력 후보를 fixture로 검토하고, 승인된 범위만 명시적 계약으로 채택한다. 문서의 Proposed 필드가 존재한다는 이유만으로 저장 schema, 공개 API 또는 Python Protocol을 확정하지 않는다.

## 근거

- [AI 내부 계약](../../spec/ai/contracts.md)의 `계약 계층`, `공통 타입 원칙`, `public 변환과 합의 경계`
- [AI 작업 Context](../../spec/ai/features/job-context.md)의 `Context Builder 입력`, `질문의 불변 사실`, `LLM 경계`
- [AI 구현 기준선](../../spec/ai/decisions/0001-ai-baseline.md)의 FIX/PENDING/Proposed 구분
- [0015 기존 계약과 ToolResult 채택](../../spec/ai/decisions/0015-existing-contracts-and-tool-results.md)의 Context·Question·Evidence 필드 구성과 ToolResult 부분 오류 처리
- [구현·검수 인계](pipeline.md#기존-id별-구현검수-인계)의 `AI-L02 내부 입출력과 저장 계약`, `AI-L18 원문·호출 기록·정정의 운영 연결`
- 현재 AI 원본 [contracts.py](../src/devon_ai/contracts.py)와 BE 연결 경계 [contracts.py](../../backend/app/agents/contracts.py)

## 선행 조건

- [0014 최소 변경 재결정](../../spec/ai/decisions/0014-minimal-change-revision.md)의 질문 계약·기존 분석/판단 필드·저장 위치는 채택됐다. 미채택 부분은 비식별 fixture와 순수 검증 규칙부터 검토한다.
- 0015의 Context·Question·Evidence 필드 구성·기본 표현과 ToolResult 다섯 필드·네 상태·부분 오류 처리를 따른다. 정확한 모든 DTO·DB·공개 API 형식까지 채택된 것은 아니다.
- 미채택 상세 객체·참조·형식 버전 관리와 공개 변환은 기존 구조에 맞춰 구체화한다. 기존 규칙에서 명확한 타입·null·빈 목록 표현은 기록하고 진행하며 필드별 사용자 재승인을 요구하지 않는다. 서비스 동작·지원 범위·운영 조건이 달라지는 선택은 해당 AI-L 항목에서 결정하고 공개 필드 영향은 FE와 함께 확인한다. 별도 공통 저장 객체나 모든 JSON의 버전 필드는 요구하지 않는다.
- `question_contract`·`analysis`·`decision`의 Turn JSONB 위치는 0014의 채택 범위를 사용한다. 상세 참조·직렬화·공개 변환과 실패 기록의 영구 저장 연결은 기존 구조 안에서 구현·검증한다.
- 실패 원문과 호출 기록은 0018의 확정한 내부 보관·재사용 정책을 따른다. 실제 자료의 사용 권한과 저장·마스킹·접근·보관 연결을 확인한 뒤 실제 자료로 검증한다.
- 기존 FIX와 Accepted 정책은 유지하되 Proposed 예시를 승인된 값으로 승격하지 않는다.

## 대상 파일과 책임

- [ai/src/devon_ai/contracts.py](../src/devon_ai/contracts.py): 채택된 내부 계약과 순수 검증 경계의 구현 위치다. 현재 로컬은 docstring뿐이며, 상세 타입·참조·변환은 채택 범위에 맞춰 구체화한다.
- [backend/app/agents/contracts.py](../../backend/app/agents/contracts.py): 채택된 AI 계약의 BE adapter와 service/public 변환 경계만 맡는다.
- `ai/tests/test_contracts.py` (추가 예정, 현재 없음): 비식별 후보 fixture, 정상·오류 검증, 계층 간 의존성 검사를 둔다.
- DB migration, ORM, 공개 OpenAPI/WS schema, 새 Agent·gateway·provider 모듈은 이 작업의 대상이 아니다.

## 작업

- [ ] Context, Question/Contract, AnswerAnalysis, DirectorDecision, Evidence/ToolResult, feedback 후보별 생산자·소비자·소유자를 표로 검토한다.
- [ ] 각 후보에서 FIX/Accepted 의미와 Proposed 필드·enum·저장 표현을 분리한 검토 fixture를 만든다.
- [ ] [최소 변경 확인 조건](../../spec/ai/verification.md#최소-변경-재결정-확인)에 따라 기존 필드와 보존 원칙을 검사하고, 철회한 공통 객체·상태·조회 사본을 다시 요구하지 않는다.
- [ ] 0015의 채택 범위와 미채택 상세 형식을 구분하고, 부분 Tool 오류에서 유효 근거 보존을 invalid 결과의 허용으로 해석하지 않는다.
- [ ] service가 발급·검증하는 사용자, 저장소, run, session, Turn 식별자를 모델 생성값과 구분한다.
- [ ] 원문, 사전 수집 관찰, 모델 해석, 검증 완료 결과를 서로 다른 출처로 판별할 수 있는지 검사한다.
- [ ] 고정 SHA, timezone 포함 시간, 실제 참조 ID가 없는 예시가 production 기본값으로 흘러가지 않게 한다.
- [ ] raw output과 parse/schema/의미 검증을 통과한 결과를 동일한 성공 객체로 취급하지 않는 실패 fixture를 만든다.
- [ ] 누락, 알 수 없는 enum, 중복 참조, 다른 사용자·저장소 참조, 근거 없는 위치를 각각 별도 오류로 검토한다.
- [ ] 내부 snake_case 후보를 공개 camelCase 응답에 그대로 직렬화하지 않고 BE 변환 책임으로 남긴다.
- [ ] 모델이 DB PK, 사용자 소유권, 최종 상태, Turn 번호, 종료를 확정하지 못하는 경계를 검토한다.
- [ ] 채택안에는 결정 ID, 승인된 정확한 범위, schema/version 호환 정책, 저장·공개 영향과 소비자를 기록한다.
- [ ] 0014·0015에서 채택된 범위의 타입을 `devon_ai.contracts`에 구현하고 BE adapter import 방향을 검사한다. 미채택 상세는 기존 규칙에 맞춰 기록·검토한다.
- [ ] 승인되지 않은 편의 `dict[str, Any]`, 임시 DTO 또는 Protocol을 사실상 영구 계약으로 남기지 않는다.

## 검증

- [ ] 정상 fixture가 외부 I/O 없이 동일한 검증 결과를 내는지 확인한다.
- [ ] 필수값 누락, 잘못된 null/enum, 중복·미등록 reference가 성공 결과로 통과하지 않는지 확인한다.
- [ ] 모델이 반환한 식별자나 상태를 service가 검증하지 않고 신뢰하는 경로가 없는지 확인한다.
- [ ] raw/invalid 결과가 저장 완료, 질문 발행, evidence 또는 public serializer로 전달되지 않는지 확인한다.
- [ ] AI 패키지가 `backend.app`을 import하지 않고 BE adapter가 canonical 계약만 참조하는지 확인한다.
- [ ] 계획 테스트를 추가한 뒤 [테스트 안내](testing.md)의 Ruff, mypy, pytest와 import boundary 검사를 실행한다.
- [ ] mock 검증과 실제 DB/API/모델 연결 미실행 범위를 결과에 분리해 기록한다.

## 완료 조건

- [ ] 채택된 계약마다 AI-L02 결정 근거와 책임 계층이 추적된다.
- [ ] 승인 범위 밖 필드·enum·schema·Protocol·DB/API 변경이 없다.
- [ ] 정상·오류·권한/ref 불일치 fixture가 독립적으로 검토되고 계약 테스트에 고정된다.
- [ ] 소비자와 저장 경계를 포함한 검증이 끝나기 전 runtime 구현 완료로 보고하지 않는다.

## 결정 대기와 재개 조건

- AI-L02가 남아 있어도 0014·0015에서 채택한 범위의 fixture와 타입 검증은 진행한다. 미채택 상세 형식은 기존 규칙에 맞춰 기록하고, 저장·공개 동작에 영향을 주는 결정은 해당 경계의 검토 뒤 연결한다.
- AI-L18은 [0018](../../spec/ai/decisions/0018-existing-baseline-bulk-resolution.md)의 확정한 내부 보관·재사용 정책을 따른다. 비식별 fixture와 비밀값 제외 검사는 먼저 진행하고, 실제 자료의 권한·원문·raw output·호출 metadata 저장 위치·접근·마스킹·보관 연결을 확인한 뒤 실제 자료 보존 검증을 진행한다.
- 결정이 일부 유형만 승인하면 그 유형만 구현하며, 나머지 계약 때문에 독립적으로 승인된 작업을 중단하지 않는다.
