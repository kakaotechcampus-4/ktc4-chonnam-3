# Evidence Retriever와 답변·코드 충돌

상태: Sprint 1 범위·저장 소유권 FIX. 추가 조회·결과 해석은 0003, 공급된 범위 안의 후보 우선순위는 0008, 기존 Evidence·ToolResult 필드 구성과 부분 오류 처리는 0015에서 Accepted. 상세 I/O·저장은 기존 구조 안에서 구현·검증하며 운영 상한은 운영 조건과 실측으로 정한다.

원본: [BE 면접 Evidence/Conflict](../../backend/features/interview.md), [레이어 규칙](../../../backend/docs/layer-rules.md), [DB 명세](../../../backend/docs/db-schema.md). 과거 원본 `ForAI.md` 1·4항은 현재 저장소에 없다. 조회 정책은 [0003 결정](../decisions/0003-evidence-lookup-policy.md), 내부 반환 계약은 [Evidence와 ToolResult](../contracts.md#evidence와-toolresult)를 따른다.

## 검색 목적

질문의 구현 전제를 확인하거나, 답변의 구체적 주장을 검증할 때 필요한 원문을 찾는다. 전체 repo를 자유 탐색하는 Agent, 사용자 코드를 실행하는 sandbox, 별도 검색 서비스는 Sprint 1 요구사항이 아니다.

검색 범위는 README, repository metadata, languages, commit metadata, L2 `notable_areas[].path` 주변 파일이다. 전체 tree scan·전역 keyword search·Private repo 조회는 제외한다. [0002 결정](../decisions/0002-sprint1-vector-search.md)에 따라 Sprint 1에는 embedding/vector 검색을 도입하지 않고 pgvector extension도 선설치하지 않는다. 실제 검색 실패 사례를 바탕으로 Sprint 2의 필요성을 재평가하며, 후속 도입 여부·model·dimension·chunking·저장소는 미정이다. BE 문서·migration 반영 확인은 별도 대기다.

## 입력과 Tool 경계

요청은 현재 사용자/면접의 검증된 선택 repo, `session_repositories.snapshot_head_sha`, 확인 목적, 주장 또는 질문 전제, 알려진 경로·검색 조건, 남은 budget을 가진다. 모델이 전달한 repo·path를 그대로 외부 API에 넣지 않는다.

기존 도구 후보 이름은 `search_code`, `read_file`, `list_commits`다. 실제 함수는 아직 없다. `search_code`를 구현하더라도 위 허용 자료 안의 제한 검색으로 정의하며 이름을 근거로 GitHub 전체 코드 검색을 켜지 않는다.

`read_file`은 허용된 repo/ref/path만, `list_commits`는 선택 ref와 일관된 commit metadata만 읽는다. traversal 경로, 예상하지 않은 외부 URL·redirect, 다른 사용자 repo는 거절한다. 파일을 실행·수정하지 않는다.

[0018 결정](../decisions/0018-existing-baseline-bulk-resolution.md)에 따라 Tool 인수·상세 위치·허용 범위 안의 파일 열거 방식·저장 연결은 기존 생산자와 소비자에 맞춰 구현하고 fixture로 확인한다. 이를 사용자에게 세부 선택으로 다시 묻지 않는다. 호출·파일·깊이·byte/token/time·동시성 상한은 LLM·Worker 제한과 함께 운영 조건·대표 사례 실측으로 정하고, 수치를 임의로 채우거나 미설정 상태를 무제한 조회로 연결하지 않는다.

## 추가 조회 정책과 구현 제안

### 확정된 추가 조회 조건

[0003 결정](../decisions/0003-evidence-lookup-policy.md)에 따라 기존 근거만으로 주장을 확인할 수 없고, 확인 결과가 현재 질문·후속 질문·평가에 영향을 주며, 선택 repo의 고정 SHA·허용 경로에서 확인 가능한 경우에만 추가 조회를 요청한다. 세 조건을 모두 만족해야 한다.

조회하지 않은 경우를 정상 검색 후 미발견으로 기록하지 않는다. 이 정책과 별개로 service의 권한·ref/path 검증과 실행 budget을 지켜야 한다. 실제 조회는 필요한 상한을 설정하고 검증한 뒤 연결한다.

### 확정된 후보 우선순위

[0008 결정](../decisions/0008-ai-candidate-policy.md)에 따라 추가 조회 후보는 BE가 공급하고 검증할 수 있는 범위 안에서 다음 순서로 제안한다.

1. 현재 주장·질문 목적과 관련된 기존 Evidence와 이미 수집한 원문
2. 현재 주장에 직접 연결된 정확히 알려진 파일
3. 사전에 검증된 인접 범위의 후보

같은 단계에서는 구현 주장은 실제 코드, 프로젝트 목적은 README, 언어·저장소 사실은 해당 metadata처럼 주장 종류에 직접 맞는 source를 우선한다. 직접성이 같으면 확인 범위가 더 좁고 명확한 후보를 먼저 둔다. 이미 있는 직접 근거가 충분하면 새 조회를 제안하지 않는다.

“주변 파일”은 설정된 깊이·허용 개수·byte/token/time 상한 안에서만 읽는다. 새 JD 때문에 전체 L2를 반복하거나, 미발견마다 전체 tree를 수집하지 않는다.

notable area가 디렉터리면 그 path를 `read_file`에 넘기지 않는다. 기존 허용 범위에서 제한된 파일 목록을 확보하고 ref·경로·상한 검사를 구현·검증한다. 디렉터리 한 건을 근거로 전체 repo 재귀 탐색을 허용하지 않는다.

후보 우선순위의 채택만으로 디렉터리 열거·Tool transport·권한 검사·상한과 중단 처리가 구현·검증됐다고 보지 않는다. 허용 검색 범위는 그대로 유지한다.

## 출처와 실행 상태

0003에서 확정한 결과 해석은 다음과 같다. 정상 조회 후 미발견은 `unverified`로 두고 코드 부재·거짓으로 단정하지 않는다. 분석 부족·도구 장애는 검증 불가 사유를 남기고 감점하지 않는다. 실제 코드 불일치는 버전·조건을 확인하는 중립 후속 질문이 필요한 충돌 후보로 다룬다. 아래 내부 반환 상태와 기존 다섯 필드는 [0015 결정](../decisions/0015-existing-contracts-and-tool-results.md)에서 채택했으며 DB enum·공개 API를 추가하는 결정은 아니다.

| 반환 상태 | 의미 | downstream 처리 |
| --- | --- | --- |
| `found` | 허용 범위에서 관련 원문 발견 | 주장과 원문 관계를 별도 판단 |
| `not_found` | 정상 검색했으나 해당 범위에서 미발견 | `unverified`; 코드 부재·거짓 단정 금지 |
| `insufficient_analysis` | 분석·원문 준비가 부족하여 확인 불가 | 제한된 보강 또는 준비 실패 구분 |
| `tool_error` | 외부 오류·timeout 등으로 검색 실패 | 오류 기록, 사용자 역량 평가에 전가하지 않음 |

같은 도구 실행에서 유효한 일부 근거를 확보한 뒤 오류가 발생하면 `tool_error`와 확보한 `items`를 함께 반환한다. 실제 확인 범위·미완료 범위·오류는 [기존 ToolResult 필드](../contracts.md#evidence와-toolresult)로 구분한다. 독립된 다른 실행의 성공 결과를 소급 실패로 바꾸거나, 오류만으로 자동 재조회·전체 판단 실패·유효 근거 폐기를 결정하지 않는다. 검증되지 않은 결과를 유효한 일부 결과로 살려 쓰지는 않는다.

Evidence에는 실제 repo·git_ref·파일/metadata 항목·위치·원문·요약·조회 방법·분석 한계를 보존한다. 원문에 없는 함수명·줄 번호·인용문을 생성하지 않는다. path가 같아도 ref가 다르면 같은 근거로 보지 않는다.

commit metadata는 기여를 질문할 신호일 수 있지만 개인 작성·업무 책임·코드 품질의 증명이 아니다. README의 기술 사용 선언도 실제 코드 확인과 구분한다.

조회 요약은 [0014](../decisions/0014-minimal-change-revision.md)에 따라 기존 판단의 `reason_summary`와 Evidence 관계로 남기며 별도 일곱 필드 사본·조회마다 DB 쓰기는 추가하지 않는다. 실패·중단의 조회 사실·범위·사유도 0003대로 보존해야 한다. 영구 기록의 보관 정책은 [0018의 확정 자료 정책](../decisions/0018-existing-baseline-bulk-resolution.md#ai-l18-후속-내부-비교-검증-자료)을 따르며, Tool 요청·상세 참조·저장 연결은 [구현·검증 체크](../../../ai/docs/pipeline.md)에서 확인한다.

## 질문 근거와 평가 근거

`question_basis`는 질문 생성 때 전제로 사용한 근거다. `evaluation_basis`는 답변·피드백·충돌 판단에 사용한 근거다. 같은 Evidence가 두 용도를 가질 수 있으며 관계에 usage를 남긴다.

`tech_lead` 질문은 가능한 한 question_basis를 붙인다. 구체적 구현을 사실로 전제한다면 근거가 필요하지만 모든 일반 기술 질문에 가짜 근거를 강제하지 않는다. 첫 HR 질문과 domain/HR 질문은 Evidence 없이도 가능하다.

어떤 Persona의 답변이든 검증 가능한 코드 주장이 나오면 evaluation_basis를 보강할 수 있다. Persona 변경 때문에 기존 근거·기여 정정을 잃지 않는다.

## answer_vs_code 저장

유효한 코드와 사용자 답변이 다를 때 아래 FIX를 따른다.

| 필드 | 의미 |
| --- | --- |
| `turn_id` | 주장이 나온 답변 Turn |
| `evidence_id` | 확인한 실제 Evidence |
| `claim_id` | NULL; Sprint 1 문서 Claim FK 없음 |
| `source` | `answer_vs_code` |
| `claim_text` | 사용자 주장 원문 |
| `evidence_text` | 비교한 근거 스냅샷 |
| `verdict` | `unresolved` |

도구는 후보와 출처를 반환하고 service/queries가 관계를 저장한다. 같은 Turn의 재처리로 동일 충돌을 중복 확정하지 않는 키/제약은 BE와 합의한다. 문서 주장용 `llm_tasks/conflict.py`의 오래된 “Sprint 1 행 없음” 설명을 이 흐름에 적용하지 않는다.

차이가 있으면 환경·버전·다른 코드 경로·분석 오류 가능성을 확인하는 꼬리질문을 제안한다. Sprint 1에서 자동 유죄 판정·벌점·`resolution` 확정·문서 Claim 대조를 추가하지 않는다.

## 검증

정상 검색, 기존 직접 근거 우선, 정확한 파일과 사전 검증된 인접 후보의 순서, 잘못된 ref, 실제 위치와 다른 인용, 무관한 유사 파일, 미발견, 분석 부족, timeout, 다른 사용자 repo, path traversal, 외부 지시가 있는 README를 fixture로 검사한다.

일부 근거 확보 뒤 오류에서는 `tool_error`와 유효 items가 공존하는지, 실제 확인·미완료 범위가 구분되는지 검사한다. 독립 실행의 성공 보존과 invalid 결과의 거부도 함께 확인한다.

출처가 검증되지 않은 결과가 질문·리포트에 인용되지 않고, 질문/평가 usage가 구분되며, 조회 실패가 false claim으로 바뀌지 않아야 한다. 실제 모델 평가에는 검색이 필요한 경우와 불필요한 경우를 모두 포함한다.
