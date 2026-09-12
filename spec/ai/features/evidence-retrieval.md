# Evidence Retriever와 답변·코드 충돌

상태: Sprint 1 범위·저장 소유권 FIX. 추가 조회·결과 해석은 0003, 공급된 범위 안의 후보 우선순위는 0008에서 Accepted. 상세 도구 반환·운영 계약은 Proposed.

원본: [BE 면접 Evidence/Conflict](../../backend/features/interview.md), [ForAI 1·4](../../../ForAI.md), [레이어 규칙](../../../backend/docs/layer-rules.md), [DB 명세](../../../backend/docs/db-schema.md). 내부 반환 제안은 [contracts.md](../contracts.md)를 따른다.

## 검색 목적

질문의 구현 전제를 확인하거나, 답변의 구체적 주장을 검증할 때 필요한 원문을 찾는다. 전체 repo를 자유 탐색하는 Agent, 사용자 코드를 실행하는 sandbox, 별도 검색 서비스는 Sprint 1 요구사항이 아니다.

검색 범위는 README, repository metadata, languages, commit metadata, L2 `notable_areas[].path` 주변 파일이다. 전체 tree scan·전역 keyword search·Private repo 조회는 제외한다. [0002 결정](../decisions/0002-sprint1-vector-search.md)에 따라 Sprint 1에는 embedding/vector 검색을 도입하지 않고 pgvector extension도 선설치하지 않는다. 실제 검색 실패 사례를 바탕으로 Sprint 2의 필요성을 재평가하며, 후속 도입 여부·model·dimension·chunking·저장소는 미정이다. BE 문서·migration 반영 확인은 별도 대기다.

## 입력과 Tool 경계

요청은 현재 사용자/면접의 검증된 선택 repo, `session_repositories.snapshot_head_sha`, 확인 목적, 주장 또는 질문 전제, 알려진 경로·검색 조건, 남은 budget을 가진다. 모델이 전달한 repo·path를 그대로 외부 API에 넣지 않는다.

기존 도구 후보 이름은 `search_code`, `read_file`, `list_commits`다. 실제 함수는 아직 없다. `search_code`를 구현하더라도 위 허용 자료 안의 제한 검색으로 정의하며 이름을 근거로 GitHub 전체 코드 검색을 켜지 않는다.

`read_file`은 허용된 repo/ref/path만, `list_commits`는 선택 ref와 일관된 commit metadata만 읽는다. traversal 경로, 예상하지 않은 외부 URL·redirect, 다른 사용자 repo는 거절한다. 파일을 실행·수정하지 않는다.

## 추가 조회 정책과 구현 제안

### 확정된 추가 조회 조건

[0003 결정](../decisions/0003-evidence-lookup-policy.md)에 따라 기존 근거만으로 주장을 확인할 수 없고, 확인 결과가 현재 질문·후속 질문·평가에 영향을 주며, 선택 repo의 고정 SHA·허용 경로에서 확인 가능한 경우에만 추가 조회를 요청한다. 세 조건을 모두 만족해야 한다.

조회하지 않은 경우를 정상 검색 후 미발견으로 기록하지 않는다. 이 정책과 별개로 service의 권한·ref/path 검증과 실행 budget을 지켜야 한다. 숫자 상한·파일 열거 방식은 아직 미정이며 승인 없이 무제한으로 연결하지 않는다.

### 확정된 후보 우선순위

[0008 결정](../decisions/0008-ai-candidate-policy.md)에 따라 추가 조회 후보는 BE가 공급하고 검증할 수 있는 범위 안에서 다음 순서로 제안한다.

1. 현재 주장·질문 목적과 관련된 기존 Evidence와 이미 수집한 원문
2. 현재 주장에 직접 연결된 정확히 알려진 파일
3. 사전에 검증된 인접 범위의 후보

같은 단계에서는 구현 주장은 실제 코드, 프로젝트 목적은 README, 언어·저장소 사실은 해당 metadata처럼 주장 종류에 직접 맞는 source를 우선한다. 직접성이 같으면 확인 범위가 더 좁고 명확한 후보를 먼저 둔다. 이미 있는 직접 근거가 충분하면 새 조회를 제안하지 않는다.

“주변 파일”의 깊이·허용 개수·byte/token 상한은 실제 구현 전 설정으로 합의한다. 미정이라는 이유로 무제한 탐색하지 않는다. 새 JD 때문에 전체 L2를 반복하거나, 미발견마다 전체 tree를 수집하지 않는다.

notable area가 디렉터리면 그 path를 `read_file`에 넘기지 않는다. 해당 디렉터리의 제한된 파일 목록을 확보할 방법·깊이·상한을 AI·BE가 먼저 합의한다. 디렉터리 한 건을 근거로 전체 repo 재귀 탐색을 허용하지 않는다.

후보 우선순위 승인은 디렉터리 파일 열거, 인접 후보 생성, Tool transport, 권한 검증, 호출·파일·byte/token/time 상한과 중단 처리를 승인하지 않는다.

## 출처와 실행 상태

0003에서 확정한 결과 해석은 다음과 같다. 정상 조회 후 미발견은 `unverified`로 두고 코드 부재·거짓으로 단정하지 않는다. 분석 부족·도구 장애는 검증 불가 사유를 남기고 감점하지 않는다. 실제 코드 불일치는 버전·조건을 확인하는 중립 후속 질문이 필요한 충돌 후보로 다룬다. 아래 상태 이름의 실제 저장 enum·API 채택은 이 의미 정책과 별개로 미정이다.

| 반환 상태 제안 | 의미 | downstream 처리 |
| --- | --- | --- |
| `found` | 허용 범위에서 관련 원문 발견 | 주장과 원문 관계를 별도 판단 |
| `not_found` | 정상 검색했으나 해당 범위에서 미발견 | `unverified`; 코드 부재·거짓 단정 금지 |
| `insufficient_analysis` | 분석·원문 준비가 부족하여 확인 불가 | 제한된 보강 또는 준비 실패 구분 |
| `tool_error` | 외부 오류·timeout 등으로 검색 실패 | 오류 기록, 사용자 역량 평가에 전가하지 않음 |

Evidence에는 실제 repo·git_ref·파일/metadata 항목·위치·원문·요약·조회 방법·분석 한계를 보존한다. 원문에 없는 함수명·줄 번호·인용문을 생성하지 않는다. path가 같아도 ref가 다르면 같은 근거로 보지 않는다.

commit metadata는 기여를 질문할 신호일 수 있지만 개인 작성·업무 책임·코드 품질의 증명이 아니다. README의 기술 사용 선언도 실제 코드 확인과 구분한다.

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

출처가 검증되지 않은 결과가 질문·리포트에 인용되지 않고, 질문/평가 usage가 구분되며, 조회 실패가 false claim으로 바뀌지 않아야 한다. 실제 모델 평가에는 검색이 필요한 경우와 불필요한 경우를 모두 포함한다.
