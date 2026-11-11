# AI 내부 입력·출력 계약

작성일: 2026-09-12. 갱신일: 2026-11-11. 상태: [0014](decisions/0014-minimal-change-revision.md)의 질문 기준·분석·판단 구성과 저장 흐름, [0015](decisions/0015-existing-contracts-and-tool-results.md)의 기존 Context·Question·Evidence 기본 필드와 ToolResult 다섯 필드·네 상태·부분 오류 해석은 Accepted다. [0052](decisions/0052-director-problem-oriented-evaluation.md)의 v9 입력·조건부 후속·빈 조회 재사용은 로컬 구현 범위에서 Accepted이며 사람·도메인 검수 승인이 아니다. 그 밖에 명시한 기본 표현 외 상세 객체·참조·공개 변환 등 미채택 부분은 **Proposed**다.

이 문서는 공개 API나 승인된 DB schema를 대체하지 않는다. [패키지 설계](designs/2026-09-12-ai-package-structure.md)에 따른 AI 원본 위치는 `ai/src/devon_ai/contracts.py`다. task-02~03의 Python 계약·순수 검증과 BE 호출 경계는 [구현 인계](designs/2026-09-23-ai-foundation.md)에 기록했다. 0014·0015에서 채택한 필드·값·저장 위치는 유지하고, 상세 객체·참조·변환은 기존 표현을 따라 테스트 fixture에 고정한다. 공개 camelCase와 내부 snake_case 변환은 service/schema 계층의 책임이다.

아래 필드 표와 enum은 명시적으로 Accepted인 범위 외에는 fixture로 검토할 후보이며, 이 문서만으로 migration·공개 API·WS enum 추가를 승인하지 않는다. 기존 FIX와 [0008 후보 정책](decisions/0008-ai-candidate-policy.md) 등 명시된 Accepted 정책만 승인 범위에서 확정된 요구사항이다.

여기서 Proposed·미채택은 명시한 상세 계약의 승인 상태다. 채택된 범위의 구현·연결·검증 조건과 구분하며, 현재 적용 여부·실행 결과는 [구현 기록](implementation.md)에서 확인한다. 공통 해석은 [상태 표현과 문서 역할](../../ai/README.md#ai-document-status)을 따른다.

원본: [아키텍처](architecture.md), [레이어 규칙](../../backend/docs/layer-rules.md), [DB 명세](../../backend/docs/db-schema.md), [미결정 기록](decisions/0001-ai-baseline.md). 과거 원본 `ForAI.md`는 현재 저장소에 없으며, 당시 검토 내역은 [원본 감사 기록](source-audit.md)을 참고한다.

## 계약 계층

### 최종 서비스 확장 계약 — 검토안

[ADR 0031](decisions/0031-final-service-runtime-boundaries.md)의 후속 제안이다.
아래 확장은 내부 호출·저장의 명시적 계약이며 기존 Accepted 기본 계약을 일괄 대체하지 않는다.
공유 API에 해당하는 문서 선택·질문 음성 경로는 OpenAPI의 해당 정의를 함께 검토한다.
구현 현황·실행 결과는 이 문서에 중복하지 않고 [구현 기록](implementation.md)에서 관리한다.

| 객체 | 추가 필드와 의미 |
| --- | --- |
| `CallLimits` | 선택 `reasoning_effort`, `stream=false`. 공급자가 지원하는 추론량만 설정하며, stream은 SSE를 전체 수신·검증한 결과 하나로 반환하는 전송 방식이다. 시간·입출력 바이트·시도 상한은 동일하게 적용한다 |
| `Context` | `evaluation_targets`, `supplemental_sources`, `external_searches`, `supplemental_limitations`. 모두 기본 빈 목록이며 서버가 검증한 현재 자료·평가 기회·검색 상태·미확인 범위를 전달한다 |
| `QuestionContract` | 선택 `evaluation_keys=[]`. 질문이 제공한 평가 기회이며 답변의 관찰·충분성·점수가 아니다. 옛 계약을 읽을 때 생략을 허용한다 |
| `Question` | `question_type=main`, `parent_turn_id=null`. 후속이면 실제 이전 턴·같은 persona·허용 depth를 검증한다. 자유 문장의 intent에서 관계를 추정하지 않는다 |
| `AnswerAnalysis` | `external_queries=[]`의 항목은 `query`, `purpose`다. 실제 조회 결과가 아닌 확인 요청이며 `needs_verification`과 일치해야 한다. 기존 답변 원문 인용·질문 범위 검증은 유지한다 |
| `BasisRef.kind` | 기존 종류에 `document_claim`, `document_visual`, `document_claim_comparison`, `external_source`를 추가한다. 실제 등록 ID만 허용하며 모두 개인 구현·기여의 확정 증명이 아니다 |
| `SupplementalSource` | `source_id`, `kind`, `content`, `location`, `version`, `limitations`, 선택 `title`, `retrieved_at`. version은 저장 원문 또는 원본 파일의 SHA-256이며 생성 설명과 전사 원문을 구분한다 |
| `ExternalSearchStatus` | `status`, `source_ids`, `searched_scope`, `limitations`, 선택 `error_code`. found/not_found/insufficient_analysis/tool_error를 실제 실행 상태대로 유지한다 |
| `ToolResult` | insufficient_analysis에도 실제 읽고 검증한 부분 `items`를 담을 수 있다. 한계는 필수이며 미확인 꼬리 영역을 부재로 판정하지 않는다. 동일 ID 재조회는 동일 원문일 때만 재사용한다 |
| `ReportInput` | 선택 `limitations=[]`, `source_notes=[]`. 최종 보강 분석과 실제 턴별 ToolResult는 저장 원문·질문·답변에 재검증한 뒤 전달하며 최초 분석을 덮어쓰지 않는다. 공고 전사 출처는 별도 `JDSourceNote`로 유지한다 |
| `ReportTurn` | 선택 `jd_requirement_ids=[]`. 실제 질문에서 요구한 JD만 서술·점수 판정 원문에 연결한다. 예전 저장 입력은 빈 값으로 호환한다 |
| `JDSourceNote` | `requirement_id`, `block_id`, `source_field=job_posting.source_blocks`, `content`, `location`, `text_hash`, `image_hash`, `limitations`, `read_scope=entire_block/prefix_excerpt`. 저장 전사·원본 이미지 해시와 위치를 보존한다. 일부 구간이면 한계가 필수이며 전체 좌표를 해당 구간의 좌표로 추정하지 않는다. 코드·개인 기여 Evidence로 쓰지 않는다 |

현재 모델 Context는 유한한 원문 예산을 사용한다. 과거 인용 복원에 사용하는 전체 registry를
그대로 모델 입력에 넣지 않는다. 문서 추출 prompt 변경 후에는 현재 Claim 집합을 다시 정하되
과거 질문이 참조한 Claim·위치·원문 버전을 삭제하지 않는다.

문서 Claim·시각 해석·외부 자료의 실패와 미확인 범위는 사용자 역량의 부족으로 환산하지 않는다.
공개 점수 nullable 표현과 품질 gate는 이 확장에서 자동 승인하지 않는다.

### 기존 기본 계약

| 계층 | 내용 | 결정 상태 |
| --- | --- | --- |
| 공개 REST | OpenAPI의 요청·응답 | 기존 FIX, 명시된 PENDING 제외 |
| 공개 WS | 텍스트 답변, `turn`, `answerReceived`, `sessionId` 경로와 기존 이벤트 의미 | Sprint 1 FIX. 사용자 종료 wire는 별도 확인 |
| 저장 책임 방향 | turn 중심 분석·결정, evidence 관계, report feedback | 기존 테이블 책임 유지; `question_contract`, `analysis`, `decision`의 JSONB 저장 위치는 0014 Accepted. 새로운 공통 바깥 객체는 추가하지 않음 |
| Question Contract·분석·판단 | 기존 내용 필드와 평가·행동 코드 | 아래 명시한 범위는 0014 Accepted; 상세 객체의 미채택 형식·공개 변환은 Proposed |
| Context·Question·Evidence·ToolResult | 기존 기본 필드와 명시한 표현·도구 결과 상태 | 0015 Accepted; 상세 객체·위치·Tool 인수·공개 변환은 미채택 범위 |
| 모델 원시 출력 | task별 schema에 맞는 후보 결과 | 신뢰 전 검증 대상 |

모델에게 DB PK·user_id·run_id·최종 status를 생성하게 하지 않는다. 입력에서 전달한 ID를 참조하게 하되, 실제 관계·소유권은 service가 검증한다. raw output과 검증된 결과를 같은 성공 객체로 취급하지 않는다.

## 공통 타입 원칙

- UUID·repository ID·Turn ID는 service가 전달한다. 샘플 식별자를 production 값으로 쓰지 않는다.
- 시간은 timezone이 있는 값이다. 분석은 대상 `head_sha`, 면접의 코드 근거는 `session_repositories.snapshot_head_sha`를 사용한다. 원격 기본 branch의 최신 SHA, 서비스 코드 commit과 혼동하지 않는다.
- `null`은 미확인·미적용 중 문서에서 정의한 경우에만 허용한다. 모르는 값에 0이나 빈 문자열을 넣지 않는다.
- enum 외 값, 필요한 값 누락, 과도한 컬렉션, 중복 참조, 근거 없는 위치·인용은 검증 실패다.
- 사전 수집된 관찰과 LLM 해석은 별도 필드다. 문자열 인용은 해당 원문 또는 답변에서 확인할 수 있어야 한다.
- 아래 길이·token·도구 횟수 상한의 운영값은 문서에 고정하지 않는다. [0018](decisions/0018-existing-baseline-bulk-resolution.md)에 따라 기존 범위의 운영 조건·대표 사례 실측으로 정하고, 설정 스키마에서 양수·일관성 검사한 뒤 실제 모델 실행 전에 값을 기록한다.

## Context 입력

[0015 결정](decisions/0015-existing-contracts-and-tool-results.md)에 따라 기존 필드 목록과 의미를 유지·채택한다. 서비스가 검증한 자료 중 현재 task에 필요한 항목만 구성하며 별도 Context 저장소나 Agent를 추가하지 않는다.

| 필드 | 형식·의미 |
| --- | --- |
| `interview_id`, `current_turn_id` | 서버가 식별한 현재 면접과 Turn; 첫 질문 전 Turn ID는 없음 |
| `turn_no`, `total_turns` | 현재 질문 번호와 FIX 상한 9 |
| `persona_counts` | 이미 확정·제시된 질문의 Persona별 횟수 |
| `allowed_personas` | [공통 0008](../shared/decisions/0008-fixed-persona-allocation.md)에 따라 Controller가 확정·제시한 질문 수와 남은 할당으로 계산한 후보; 첫 질문은 HR, 이후에는 기술 6회·도메인 2회·HR 1회의 할당을 넘지 않고 정상 9턴 완주가 가능한 기술·도메인 Persona만 허용하며 순서는 고정하지 않음 |
| `jd_requirements` | 저장된 ID, 원문, category, source field, tech_tags |
| `repositories` | 선택 repo ID, 고정 ref, primary 여부, 성공 분석과 분석 범위 |
| `history` | 질문·Persona·제출 답변·판정·참조 ID; 사실과 요약 구분 |
| `current_question_contract` | 전달 전에 확정한 질문 목적과 확인내용 |
| `evidence` | 현재 권한·선택 ref에 유효한 검증 결과 |
| `domain_frames` | 선택 category의 검수·버전 정보가 있는 seed |
| `limits` | 남은 호출·재계획 budget과 현재 정책 버전 |
| `presented_evaluation_keys` | 기본 빈 목록. 확정 질문 계약의 `evaluation_keys`를 중복 없이 합친 평가 기회이며 답변 충분성·역량·점수가 아님. 최초 질문에 선언이 없던 구형 면접에는 과거 평가 범위를 추측해 채우지 않음 |
| `follow_up_options` | 기본 빈 목록. v9에서 현재 질문 계약·실제 답변에 재검증한 분석으로 계산하는 내부 `FollowUpOption` 목록. 모델이 작성하거나 과거 옵션을 그대로 재사용하지 않음 |

현재 Context에 과거 raw output 전체나 다른 사용자의 정보를 넣지 않는다. Context Builder는 평가에 유리한 답만 선택하지 않고, 기여 정정·이전 확인사항·미확인 범위를 유지한다. 축약하더라도 원문은 DB에서 조회 가능해야 한다.

첫 질문 전 아직 없는 current_turn_id와 current_question_contract는 null, 이전 문답은 history의 빈 목록으로 표현한다. Persona 횟수는 서버가 확인한 실제 정수이며 첫 질문 전에는 0이다. total_turns는 기존 9를 유지한다. 현재 답변 Turn과 생성할 질문 Turn의 번호·상세 자료 타입은 기존 서비스 흐름에 맞춰 구체화한다.

### v9의 후속 선택과 모델 전용 입력

[0052](decisions/0052-director-problem-oriented-evaluation.md)의 로컬 구현 계약이다.
`FollowUpOption`은 아래 필드를 갖는 불변 내부 객체이며 공개 REST·WS 응답을 추가하지 않는다.

| 필드 | 형식·의미 |
| --- | --- |
| `persona` | 현재 허용 Persona이며 실제 부모 질문의 Persona와 같음 |
| `parent_turn_id` | 실제 history에 있는 `current_turn_id`와 일치하는 직전 답변 Turn |
| `evaluation_keys` | 부모 질문 계약과 같은 평가 항목. 새 질문의 기본 `evaluation_targets`를 덮어쓰지 않음 |
| `missing_point_keys` | 보완·명확화할 원래 `required_points.key` 목록. `clarify`에서는 판단하지 못한 항목도 포함하므로 감점이나 부족 확정으로 해석하지 않음 |
| `intent` | `complete` 또는 `clarify`. 자유 문장의 `DirectorDecision.intent`를 대체하는 공개 행동 enum이 아님 |

v9는 저장용 Context를 변경하지 않고 지역 복사본에서 옵션을 재계산한다. 입력의 기존 옵션은
먼저 비우며, 검증 완료 분석도 현재 계약의 확인 항목·답변 인용·근거·조회 범위에 다시 대조한다.
`evaluated/partial`은 보완 후보, `needs_clarification`은 명확화 후보가 될 수 있다. 검증 실패,
미해결 조회, `not_evaluable`, 충분한 답변 또는 정상적인 모름을 후속 질문의 자동 허가로 바꾸지 않는다.
후속은 선택지이며 반드시 실행해야 하는 지시가 아니다.

후속 후보를 제공하기 전에 남은 Persona 슬롯으로 현재 자료에서 적용 가능한 미질문 평가 영역을
확보할 수 있는지 코드로 검사한다. 질문을 선택할 때마다 이 조건을 유지하며 9턴·기술 6·도메인 2·HR 1과
Controller의 종료 권한을 바꾸지 않는다. main 후보는 기존 배정과 일치해야 하고, follow_up 후보는
허용 옵션의 Persona·부모 Turn·평가 키와 일치하며 확인점 키가 해당 옵션의 부분집합이어야 한다.
이 검사는 질문 문장·전제·반복 여부에 대한 별도 Review를 대신하지 않는다.

v9의 모델 입력 표지는 `input_version=director-input.v1`이다. 현재 질문·답변·당시 계약은
`current_answer`에 두고 `context.history`에서 같은 현재 Turn을 제외한다. 현재 분석은
`answer_analysis`에 두고 `prior_analyses`에서 제외하며 `context.current_question_contract`의
중복 전달도 제거한다. 다른 과거 문답·기여 정정·원문 위치·버전·미확인 범위는 보존한다.
v1~v8과 기존 기본 생성 경로에는 두 새 Context 필드를 소급 주입하지 않는다.

공고는 본문·직무·요구사항과 필요한 이미지 전사 출처·추출 한계를 선택한 표시용 자료로 구성한다.
표시할 본문 필드가 없는 구조화 공고의 참조는 허용 목록에서도 제외하고, 비구조화 원문은 의미를
추측하여 새로 요약하지 않는다. 원본 registry·저장 자료·과거 질문 복원은 유지한다.
Plan과 Review는 같은 표시용 원문 범위를 사용하며 생성 스키마의 ID 선택과 최종 참조 검증도
그 범위에 맞춘다. DB에 존재하지만 이번 모델에 제공하지 않은 원문을 인용하도록 허용하지 않는다.

지원 기능은 프롬프트 버전별 capability로 정한다. 턴 상태·실제 ID 제약·복구 피드백·입력 projection·
후속 정책·빈 조회 분석 재사용을 서로 다른 기본값으로 추정하지 않으며, 알 수 없는 버전은 거절한다.
기존 버전의 입력·검증 의미는 유지한다.

### v12의 전체 문답 뷰와 자동 재계획 경계

[0054](decisions/0054-director-dialogue-view-and-bounded-replan.md)의 로컬 후보 계약이다.
v12는 `input_version=director-input.v2`이며 과거 `context.history`와 `prior_analyses`를
모델 전용 `answered_turns`로 배치한다. 각 항목에는 원래 Turn의 ID·Persona·질문·전체 답변·
분석 참조와 같은 ID의 검증된 `analysis`를 둔다. 분석이 없으면 null과
`analysis_status=unavailable`을 쓰며 답변 부재나 평가 불가로 해석하지 않는다.
`goal_source=question`은 과거 질문 원문이 비교 대상이라는 뜻이며 당시 계약 목적을 복원하거나
추측한 요약이 아니다. 현재 Turn은 기존 `current_answer`와 `answer_analysis`에 한 번만 둔다.
저장용 Context·공개 응답·v1~v11의 모델 입력은 이 표시 변경의 대상이 아니다.

답변 뒤의 자동 복구에서 v12의 안전한 `replan`과 `rewrite`는 기존 target별 자동 슬롯 하나를
공유한다. 최초 실패의 원시 Plan·Review에서 복구 피드백을 검증해 복원할 수 있어야 한다.
최초 모델 I/O 전에 저장한 typed 입력·정책 지문을 예약·결과 확정 때 다시 검사한다.
이 지문은 투영된 payload의 바이트 지문이 아니라 Context·현재/과거 분석·참조 원문·조회 결과·
프롬프트 정체성을 포함한 보수적인 입력 동일성 검사다. 원문 자체는 상태에 중복 저장하지 않는다.
예약 항목에는 원래 실패의 호출 ID·실패 내용·전체 시도 기록을 묶은 별도 지문도 둔다.
이 지문은 예약부터 결과 확정까지 검사하며 부모·자동 자식이 공유하는 입력 지문과 분리한다.
지문이 없거나 입력·모델·정책·소유권이 달라지면 자동 실행하지 않는다. 활성 버전만 바꿔
과거 버전 실패를 v12 자동 재계획으로 승격하지 않으며 `no_valid_candidate`도 자동 실행하지 않는다.
최초 실패와 새 라운드 기록은 분리한다. 첫 질문 준비·공급자 재시도 정책·수동 복구 상한은
이 후보 계약으로 늘어나지 않는다.

평가 bridge의 Director 입력은 선택적으로 `prior_analyses`와 `recovery_feedback`을 받는다.
과거 분석은 실제 history의 이전 답변·당시 `question_contract`·원문 참조에 재검증한 뒤 전달한다.
복구 피드백은 기존 `director-recovery.v1`의 네 필드만 허용하고 Plan에만 전달한다.
평가용 과거 계약은 검증 자료이며 모델에 새 과거 계약 필드를 추가하지 않는다.

### v14 필수점별 Review

[0056](decisions/0056-director-required-point-review.md)의 로컬 후보 계약이다.
`director-review.v2`는 기존 Review의 다섯 boolean과 짧은 사유에 `point_coverage`를
추가한다. 이 객체의 키는 후보 `required_points.key` 집합과 정확히 일치해야 한다.
각 값은 `status`와 `question_excerpt`를 포함한다.

| status | 의미 |
| --- | --- |
| `asked` | 필수점의 모든 요구가 실제 질문의 답에 필요하다. 질문의 연속 원문 구절을 인용한다. |
| `premise_only` | 질문에서 배경·가정으로 준 내용이 별도 필수 요구로 들어 있다. |
| `not_asked` | 질문에서 직접 요구하지 않은 설명이 필수점에 포함됐다. |
| `unclear` | 질문 원문만으로 판정하기 어렵다. |

`asked` 이외 상태는 인용을 null로 둘 수 있다. 인용을 제공할 경우 비어 있지 않은 실제
질문 원문이어야 한다. 전체 계약 판정이 적합하고 모든 필수점이 `asked`일 때만 해당
계약을 승인할 수 있다. 키·인용 형식 오류는 스키마 실패이며 유효한 의미 반려는 기존
복구 분류를 사용한다. 이 진단은 저장 Question의 새 필드가 아니며 v1~v13의
`director-review.v1` 응답과 저장 복구는 기존 형식으로 읽는다.

v15도 같은 `director-review.v2`와 전체 문답·복구 조건을 사용한다. 등록한 전체 정책을
Plan과 Review에 동일하게 전달하며 `operation`과 각 출력 스키마로 단계의 일을 구분한다.
v13/v14의 단계별 지침 배치는 기존 의미를 유지한다. 정책 배치 비교는
[0057](decisions/0057-director-shared-policy-comparison.md)을 따른다.

### v16 고정 필수점 검토 형식

[0058](decisions/0058-director-stable-review-schema.md)의 로컬 후보 계약이다.
`director-review.v3`는 같은 다섯 boolean·사유와 `point_coverage` 배열을 받는다.
각 원소는 `key`, `status`, `question_excerpt`를 포함한다. 응답 스키마에 후보별 키나
개수 제한을 넣지 않고 실행 코드에서 실제 필수점의 정확한 키 집합·중복·누락을 검사한다.
상태·원문 인용·승인·반려·복구 의미는 v2와 같고, v16도 단계별 정책과 전체 문답을 사용한다.
기존 버전의 응답 형식은 유지하며 저장 Question이나 공개 wire에 새 필드를 추가하지 않는다.

### v17 실제 요청에서 구성하는 Plan 계약

[0059](decisions/0059-director-request-bound-question-contract.md)의 로컬 후보 계약이다.
`director-plan.v4`의 question은 기존 text 대신 사실·명시적 가정의 preamble과 답을
요구하는 request를 가진다. question_contract는 point_key 하나와 assumptions·basis_refs·
평가 범위의 evaluation_keys를 제안한다. Persona·topic_code·참조·question_type·parent_turn_id는
기존 제약을 따른다. 요청·지시·추가 질문은 request에만 두며 preamble은 근거·가정만 제공한다.

코드는 표시 본문을 preamble과 request로 조합하고 purpose 및 단일 required_point.description을
request 전체로 구성한다. evaluation_scope는 직접 질문한 답만 평가하는 고정 문구다.
assumptions는 표시 본문의 비어 있지 않은 연속 원문이어야 한다. 부분 구절만 골라 실제
요구를 누락하거나 자유로운 설명으로 의무를 더하지 않는다. 같은 필수점의 일부만 답했으면
기존 partial·답변 인용·limitations로 남은 내용을 구분하고 후속에서도 이미 답한 부분은 반복하지 않는다.

원시 Planv4 복원과 새 생성은 같은 디코더를 사용하며 v17의 복구는 Planv4로만 읽는다.
Review v3는 유지하고 최종 본문 전체의 전제·반복·직무·표현·계약 일치를 검토한다.
기존 v1~v16과 저장된 질문·분석, 공개 Question/REST/WS/DB 형식은 유지한다.

v17의 생성 스키마는 실제 main·follow_up 선택지의 Persona·question_type·parent_turn_id·
평가 키·후속 필수점 키를 조합별로 제한한다. 허용된 후속이 없으면 main/null만 남긴다.
새 생성의 assumptions 배열은 비워 두고 필요한 조건은 표시 문장에 쓴다. 복원 디코더는
과거 v17의 유효한 원문 인용 가정을 계속 지원한다. 키 중복·정확한 후속 순서·참조와
계약 원문 결합의 실행 검사는 유지한다. 적격 조합이 없으면 모델 전송 전에 입력을 거절한다.

[0063](decisions/0063-director-topic-storage-boundary.md)에 따라 신규 v17 생성의 topic_code는
기존 PostgreSQL VARCHAR(50)에 맞춰 50자 이하로 제한한다. 해당 생성 필드의 maxLength와
신규 후보 검증·재검사에 같은 상한을 적용하며 UTF-8 바이트가 아닌 Unicode 문자 수로 센다.
초과 값을 절단·정규화해 통과시키지 않는다. 과거 원시 Plan의 공유 디코더·복원 규칙과
공개 Question/REST/WS, DB 필드·마이그레이션, Review 및 v1~v16 생성 규칙은 유지한다.

[0064](decisions/0064-director-evaluation-key-semantic-fit.md)의 실험 정책
director_v17@semantic-fit는 problem_solving이 배정된 신규 main에서 문제·실패·제약
상황의 원인 범위·해결 접근·가설을 구별할 확인 중 하나를 실제 request로 요구한다.
단순 변수·상수·호출 순서 설명만으로 답이 끝나는 질문은 그 목적에 부족하다.
기존 plan_valid와 안전 대안·복구 판정을 사용하며 새 wire 필드를 추가하지 않는다.
다른 영역의 코드 이해·기존 미답의 follow_up과 과거 충분성·점수 기준은 유지한다.
선언한 평가 키의 구조적 일치와 의미 적합성·충분한 역량 관찰은 구분한다.

### 사적 평가 원문과 검토 진단

[0053](decisions/0053-director-review-diagnostics-and-lossless-context.md)의 평가 경계다.
`director-model-sources.v3`는 실제 Plan·Review payload와 정책 원문을 그대로 보존한다.
파생 평가 문맥에서만 내용 지문이 같은 공통 payload 필드를 공유하고 요청별 delta·공통
자료 참조·원 payload 지문을 남긴다. 각 요청을 무손실 복원할 수 있어야 하며 v1/v2의
기존 파생 문맥과 판정 지문을 소급 변경하지 않는다.

`director-diagnostics.v2`는 검증된 Review의 다섯 boolean·짧은 판단 요약·복구 분류를
별도 보존한다. 요청·정책·실제 응답 모델·원응답 바이트 지문·JSON 내용 지문·시도 위치를
모두 결합하며 판단 내용도 원응답 JSON의 내용 지문과 일치해야 한다. v1의 원형·바이트
결합 읽기는 유지하되 내용 결합 보장이 없는 과거 형식으로 구분한다. 진단은 Judge의 사실
근거나 승인 결과가 아니며 공개 REST·WS 응답과 Langfuse 전송에 포함하지 않는다.
`director-review.v2`와 `director-review.v3`는 원래 질문·정책 버전 및 두 지문을 확인한
`director-diagnostics.v2`에서만 읽는다. 기존의 다섯 boolean과 필수점별 응답을 보존하고
실제 runtime의 판정기로 복구 분류를 다시 계산한다.

v17의 사적 평가 시도 요약에는 실제 Planv4 원문을 공통 디코더로 복원한
`canonical_question_sha256`를 결합한다. 원문 Plan의 intent·reason까지 실제 검증 결과와
일치해야 하며 Review 요청의 canonical Question도 같은 지문이어야 한다. 이 표시는
Planv4에만 허용하고 구형 버전으로 재표기해 읽지 않는다. 기존 source snapshot v3의
형식·과거 지문을 유지하며 공개 응답과 Langfuse에 원문을 추가하지 않는다.

## Question과 Question Contract

[0015 결정](decisions/0015-existing-contracts-and-tool-results.md)에 따라 아래 기존 여섯 필드를 유지한다. 모델 후보를 service가 검증한 뒤 사용하며 필드 구성이 같아도 검증 전후의 신뢰 경계는 유지한다.

| 필드 | 형식·검증 |
| --- | --- |
| `persona` | `tech_lead`, `hr_manager`, `domain_lead` 중 Controller의 허용 후보 |
| `text` | 사용자에게 제시할 한 질문; 질문 목적과 일치 |
| `topic_code` | 내부 주제 식별; 아직 전역 taxonomy/FK를 새로 만들지 않음 |
| `question_contract` | 아래 구조; 전달 전에 확정 |
| `evidence_refs` | 기존 유효 Evidence 참조; 없는 ID 생성 금지 |
| `jd_requirement_ids` | 실제로 연결되는 현재 JD 요구사항만 |

실제 연결할 자료가 없는 질문의 evidence_refs·jd_requirement_ids는 빈 목록이다. 필수 근거 유실·준비 실패를 빈 목록으로 바꾸거나 ID를 지어내지 않는다. Question의 상세 직렬화와 공개 메시지 변환은 기존 서비스 책임이다.

준비된 목적을 사용하는 [Director 기본 생성 경로](designs/2026-09-23-director-question-path.md)는 모델 출력에서 question_contract를 제외하고 입력 원본을 코드로 결합한다. 이 경로의 evidence_refs·jd_requirement_ids는 Context에 등록되었으면서 준비 계약 basis_refs의 같은 kind에 포함된 ID만 선택할 수 있다. 모델 원시 schema v2의 다섯 필드와 최종 Question의 기존 여섯 필드를 구분하며, 독립 검토가 정확한 문장·원본 계약에 결합되었는지도 검사한다.

위 규칙은 호출자가 Contract를 준비하는 `generate_question`의 Accepted 경계다.
Contract까지 planner가 생성하는 별도 `run_director`의 초기 경계는 [후속 Proposed 설계](designs/2026-10-23-director-runtime.md#기존-생성-경로와-부분-대체-제안)에 남긴다. 이 문서에 명시한 v9 로컬 채택 범위는 0052를 따른다.
신규 경로의 출력 Contract를 기존 생성기의 schema에 섞지 않으며, 부분 대체 채택 전 기존 경로의 승인을 바꾸지 않는다.

### Question Contract 저장 형식

[0014 결정](decisions/0014-minimal-change-revision.md)에 따라 기존 다섯 필드를 해당 질문의 `interview_turns.question_contract` JSONB에 저장한다. 별도 기준 테이블이나 JSON 안의 필수 `schema_version` 필드는 추가하지 않는다.

| 필드 | 저장 내용 |
| --- | --- |
| `purpose` | 질문 목적을 나타내는 비어 있지 않은 문자열 |
| `required_points` | `{key, description}` 목록. 실제 질문에서 요구한 내용이 1개 이상이며 key는 질문 안에서 고유 |
| `assumptions` | 질문에 명시한 가정의 문자열 목록. 없으면 `[]` |
| `basis_refs` | `{kind, id}` 목록. 출처 종류와 실제 저장 자료 ID만 연결하며 본문은 복사하지 않음 |
| `evaluation_scope` | 실제 질문에서 평가할 범위와 제외할 내용을 나타내는 비어 있지 않은 문자열 |

다섯 필드를 유지하고 필수 내용 누락·타입 오류를 기본값으로 메우지 않는다. key·description은 비어 있지 않아야 하며 전달 후 key를 바꾸지 않는다. 가정·근거 없음은 빈 목록으로 표현하고 `null`로 바꾸지 않는다. 기존 0008 검증 정책을 따르며, 모든 모델 후보에 별도의 알 수 없는 필드 일괄 거부 정책을 추가하지 않는다.

근거 종류는 `evidence`, `jd_requirement`, `job_posting`, `answer_turn`으로 구분한다. ID는 기존 DB의 실제 UUID이며 BE가 존재·권한·면접 범위를 확인한다. 이전 답변은 같은 면접의 이전 제출 완료 Turn을 가리킨다. Tool 임시 참조는 저장 ID로 변환한 뒤 확정한다. 같은 참조는 중복 저장하지 않는다. 사실 근거가 필요 없는 질문의 빈 목록과 필수 근거 유실·조회 실패를 구분한다.

연결 대상은 질문 당시 자료를 계속 가리켜야 한다. 코드 Evidence의 고정 ref·원문 보존과 기존 답변 원문을 재사용한다. 공고는 [공통 0002 결정](../shared/decisions/0002-local-policy-baseline.md)에 따라 normalized Wanted URL과 7일 TTL로 재사용하되, 재조회 내용이 달라지면 기존 공고·요구사항 테이블의 새 ID로 남기고 이전 참조를 보존한다. 별도 이력 테이블은 만들지 않는다. 이는 근거 보존에 필요한 저장 방식 보완이며 DB 영향이 없는 결정은 아니다.

서비스가 확정하는 `turn_id`, `turn_no`, `depth`, `parent_turn_no`는 모델의 제안만으로 결정하지 않는다. 질문·Contract·Persona를 전달 전에 함께 확정·저장하며 답변을 본 뒤 평가 기준을 바꾸지 않는다. Question의 기본 필드는 0015를 따르되 이 채택을 모델 원시 출력의 전체 schema·공개 API 채택이나 실제 DB 구현 완료로 확대하지 않는다. 호출의 schema/version metadata는 기존 Gateway 책임으로 남긴다.

## 분석과 판단의 저장

`interview_turns.analysis`와 `interview_turns.decision`의 별도 JSONB 위치를 유지하고 아래 기존 평면 계약을 직접 저장한다. 결과를 다시 `schema_version/status/result/error`로 감싸거나 작업마다 네 실행 상태를 추가하지 않는다. JSON 내용에도 변경 비용이 있으므로 새 테이블이 없다는 이유만으로 저장 형식을 확대하지 않는다.

기존 Turn service 설계의 T3(분석 저장), T4(판단과 Context 갱신)를 유지한다. 검증 전에는 유효한 결과로 저장하지 않으며 유효한 저장 결과가 없으면 해당 컬럼은 SQL NULL이다. NULL만으로 미시작·처리 중·실패를 구분하지 않는다. 이미 저장한 최초 분석은 이후 판단 실패·후속 답변으로 지우거나 덮어쓰지 않는다.

성공한 판단에는 실제 조회 여부·확인 범위·결과·한계를 기존 `reason_summary`에 짧게 포함하여 기존 T4 판단 저장 시점에 함께 저장하고, 근거는 기존 Evidence 관계로 보존한다. 기존 조회 결과 전달·작성 지침·검증을 필요한 범위에서 보완하며 이 요약을 위한 새 저장 필드·별도 모델 호출은 추가하지 않는다. 별도 `retrievals` 사본이나 조회마다 DB 쓰기를 추가하지 않는다. 조회 요약은 모델의 숨은 사고과정이 아니며 실제 Tool 결과와 일치해야 한다. 조회 결과는 0015에서 채택한 ToolResult 의미로 해석하며 전체 Tool I/O의 미채택 형식을 함께 승인하지 않는다.

감지한 실패·중단에서도 0003이 요구한 조회 여부·범위·중단 또는 미조회 사유를 보존한다. 유효한 판단이 없으면 실패 요약을 성공한 DirectorDecision으로 위장하지 않는다. 실패 기록의 정확한 영구 저장 위치·형식은 기존 AI-L02·AI-L18에서 정하고, 저장 충돌·DB 쓰기 실패·중단 복구는 AI-L12에서 정한다. 이 경계가 확정되기 전에는 실패 기록 보존 구현이 끝났다고 판단하지 않는다. 기존 events에 새 이벤트를 추가하거나 로그 출력만으로 영구 보존을 대신하지 않는다.

외부 호출 동안 긴 transaction을 유지하지 않는다. 정상 T3/T4 또는 감지된 실패 정리 시점에 저장하며, 조회별 저장 지점이 없으므로 프로세스 강제 종료·DB 장애 직전의 모든 중간 조회가 보존된다고 보장하지 않는다. 기존 Gateway의 실패 분류·재시도 횟수·원문 보존 책임은 유지한다.

## AnswerAnalysis

과거 스켈레톤의 `specificity`, `verified_claims`, `unverified_claims` 표기는 아래 0014의 채택 필드를 대체하지 않는다. `specificity`를 충분성·정확성·기여의 통합 점수로 사용하지 않는다. 순수 계약·검증은 구현되어 있으며 실제 답변 분석 생성·저장 service 연결은 별도 task에서 구현됐다. 적용 범위는 [구현 기록](implementation.md)을 따른다.

[0014 결정](decisions/0014-minimal-change-revision.md)에 따라 기존 최상위 필드와 아래 명시한 값은 유지·채택한다. 목록 항목·근거 참조·판단 객체의 상세 형식은 AI-L02에서 기존 자료 표현에 맞춰 정한다.

| 필드 | 채택한 값·의미 |
| --- | --- |
| `evaluation_status` | `evaluated`, `needs_clarification`, `not_evaluable` |
| `sufficiency` | `sufficient`, `partial`, `insufficient`; 해당 충분성을 평가할 수 없으면 null |
| `covered_points`, `missing_points` | Question Contract의 key 참조와 답변 근거 |
| `technical_assessment` | 검토한 설명·조건·오류·판단 보류 이유; 공개 점수 아님 |
| `contribution_scope` | `self`, `shared`, `teammate`, `unknown`과 사용자 발언 근거 |
| `claim_checks` | 주장 원문, `supported`/`partially_supported`/`unverified`/`conflicting`, evidence refs, 한계 |
| `needs_verification` | 0003의 기존 근거 부족·판단 영향·허용 범위 내 확인 가능 조건을 모두 만족하는지 |
| `verification_requests` | 확인할 주장·목적·선택 repo·고정 ref·허용 위치 |
| `limitations` | 입력·질문·자료의 불확실성과 미평가 사유 |

모델이 `verified_claims`라고 출력해도 service 검증 전에는 확인된 사실이 아니다. 기여 정정과 후속 보완은 원문을 보존한 상태로 이후 Context에 반영한다. 이 계약은 [답변 평가](features/answer-evaluation.md)의 정성 판정을 위한 것이며 리포트 점수 산식이 아니다.

[0004 결정](decisions/0004-answer-assessment-policy.md)은 세 축의 정성 의미, 평가 가능 여부·축별 보류, 후속 보완·기여 정정과 원문/최초 분석 보존 원칙을 승인한다. 자료 부족만으로 모든 축을 자동 평가 불가로 만들지 않는다. 기존 필드·명시한 값·저장 위치는 0014에서 채택했으며 상세 객체·참조 형식은 AI-L02에 남는다. 보존 원칙을 위해 새 이력 테이블이나 재평가 API를 임의 추가하지 않는다.

[0003 결정](decisions/0003-evidence-lookup-policy.md) 자체는 추가 조회 필요성과 결과 해석의 의미 정책만 승인했다. 기존 분석 필드·명시한 값·저장 위치는 0014, ToolResult의 기존 구성·상태·부분 오류 해석은 0015에서 채택했다. 미채택 상세 객체·참조와 ToolResult의 전체 저장·공개 계약은 계속 Proposed다. 실제 조회 없이 `not_found`를 만들거나, 조회 필요성 판단으로 service의 권한·budget 검증을 우회하지 않는다.

### 평가 상태와 보류

`evaluation_status`는 기존 `evaluated`, `needs_clarification`, `not_evaluable`를 유지한다. evaluated는 유효한 질문·답변에 대해 판단 가능한 내용을 분석했음을 나타내며 모든 주장·평가축의 외부 검증 완료를 뜻하지 않는다. 질문·답변 해석의 확인이 필요하면 needs_clarification, 유효한 기준으로 평가할 수 없으면 not_evaluable로 구분하고 이유를 남긴다. 이 상태로 BE 처리 성공·실패나 사용자 복구 동작을 새로 정의하지 않는다.

판단 가능한 내용은 해당 기존 필드에 남기고, 보류한 범위와 이유는 `technical_assessment`·`claim_checks`의 한계 또는 공통 `limitations`에 기록한다. 기여 미확인은 기존 `unknown`을 사용한다. 항목별 `status/assessment/deferred` 객체, `partially_evaluated` 상태, 모든 평가 항목에 같은 null 구조를 적용하는 규칙은 추가하지 않는다.

충분성을 판단할 수 있으면 기존 `sufficient/partial/insufficient` 중 하나를, 평가 범위 밖이거나 충분성 자체를 판단할 수 없으면 `null`과 이유를 남긴다. 다른 축의 미확인만으로 충분성까지 비우지 않는다. `covered_points`와 `missing_points`는 기존 위치의 두 목록으로 유지하며, 같은 key라도 실제 충족한 부분과 부족한 부분이 다르면 각각 기록한다. 판단 불가를 부족으로 단정하지 않고 `limitations`에 남긴다. 전체 충분성이 null이어도 이미 확인한 부분을 지우지 않는다. 목록 항목의 상세 형식은 기존 근거 참조와 함께 정한다.

### 사적 주장 인용 형식

AnswerAnalysis v6의 사적 모델 응답은 현재 답변의 `quote_id`를 선택하고 해당 unit 전체를
기존 `ClaimCheck.claim_text`로 복원한다. v7의 실험 형식은 `quote_id`와 `claim_excerpt`를
함께 전달하며, 선택한 unit 안의 비어 있지 않은 연속 원문만 `claim_text`로 복원한다.
같은 unit의 서로 다른 구절은 보존하되 동일 ID·구절 쌍의 중복, 잘못된 ID, 다른 unit의
구절, 공백 및 원문 변경은 거절한다. 버전별 응답 형식과 복원 규칙을 함께 검증한다.

모델이 선택한 주장·판정·근거·한계는 기존 공개 계약으로 검증하며 코드는 판정을
대신 고치지 않는다. 설계 제안·의견만으로 claim을 만들 필요는 없고, 사실과 제안이
섞였다면 사실 구절만 선택한다. 정확한 인용이 의미적 진위나 개인 기여를 증명하지는
않는다. 기존 v6 및 과거 저장 형식·다른 인용·조회 경계·공개 필드는 유지한다.
[0060 결정](decisions/0060-answer-claim-literal-excerpts.md)을 따른다.

가정형 설계 제안의 주어가 본인이라는 사실만으로 기존 구현·운영 기여를 확정하지 않는다.
별도 기여 진술이 없는 제안은 해당 기여를 `unknown`으로 두며, 실제 본인·팀원·공동 기여
진술과 정정이 있으면 그 원문에 따라 구분한다.

## DirectorDecision

[0014 결정](decisions/0014-minimal-change-revision.md)에 따라 기존 여섯 필드를 유지한다. 모델 제안과 검증된 결과의 경계는 유지하되 최종 저장 전용 다섯 필드 객체를 따로 만들지 않는다. intent는 기존 보완·심화·전환·확인 의미를 유지하고 하나의 중심 목적을 기록한다. 별도 영문 코드 enum은 요구하지 않는다. 상세 타입·행동별 null·Tool 요청 형식은 기존 AI-L02 검토 범위다.

| 필드 | 형식·검증 |
| --- | --- |
| `next_step` | 기존 `ask`, `retrieve`, `finish` 채택; 중간 조회와 질문·정상 종료를 구분 |
| `intent` | 보완·심화·전환·확인 목적; 사용자에게 보여줄 질문 자체와 구분 |
| `persona` | ask에 필요; 허용 Persona 중 하나 |
| `target` | 확인할 주제·질문 목적·현재 답변과의 연결 |
| `tool_requests` | retrieve에 필요; 허용 Tool과 범위 |
| `reason_summary` | 짧은 결정 근거; 숨은 사고과정 전체를 요구하거나 저장하지 않음 |

`finish`는 모델의 자율 조기 종료 권한이 아니다. Controller가 종료 조건을 이미 만족한 경우만 허용한다. 정상 Sprint 1은 9턴 완료 후 종료한다. 사용자 종료와 시스템 실패는 service의 별도 처리다.

`retrieve`는 사용자 질문 Turn을 증가시키지 않는다. 결과를 반영한 후 유효한 ask 또는 허용 종료로 수렴해야 한다. 반복 budget 소진 시 질문을 검증 없이 발행하지 않는다. 내부 세 값의 채택으로 `context/AI.md`의 대문자 행동명이나 공개 WS enum을 추가하지 않는다.

[후속 Proposed 실행 흐름](designs/2026-10-23-director-runtime.md#답변-분석과-조회-판단)은
T3 결과 기반 규칙 함수로 조회를 고르고 Controller가 턴당 첫 허용 요청 1개만 실행하는 제안이다.
미조회 요청은 한계로 보존하고, 필요한 보강 T3의 실패·예산 소진 뒤 T4나 정상 완료로 진행하지 않는다.
기존 `retrieve` 값 자체를 새 모델 호출이나 무제한 조회의 승인으로 해석하지 않는다.

### Director 후속 실행 경로

Director의 초기 후속 경계는 [질문 결정과 AI·BE 입력 설계](designs/2026-10-23-director-runtime.md)의 Proposed 이력이다. 아래에서 명시한 v9 입력·후속 선택·빈 조회 정책은 0052의 로컬 채택 범위다.
`run_director`는 목적·질문 생성 1회와 독립 검토 1회에 공유 예산 총 2회를 사용하며 각 요청은 `max_attempts=1`이다.
이 신규 경로는 검토 시도를 확보하기 위해 단계별 자동 재시도를 제한하며, 실패 후 질문을 확정하지 않는다.
다른 task와 기존 생성 경로의 공통 gateway 재시도 규칙은 유지한다.
검증한 결정·질문과 실제 생성 시도 metadata를 구분해 반환한다.
현재 질문과 과거 문답은 답변 분석 입력에서 구분한다. 최초·보강 T3는 같은 2회 예산,
후속 T4는 별도 예산이며 기존 flat `analysis`/`decision`과 공개 wire 구조를 유지한다.
제한 조회 판단은 허용 repo·SHA·path를 확인한 요청을 반환하고 실제 I/O·저장은 Controller가 맡는다.

v9의 `reuse_empty_lookup_analysis` capability는 ToolResult의 `items`가 비었고 상태가
`not_found`, `tool_error`, `insufficient_analysis`인 경우에만 최초 유효 T3 분석 재사용을 허용한다.
분석·claim 판정·`needs_verification`을 덮어쓰지 않고 실제 ToolResult와 한계를 DB trace,
다음 Plan/Review, 질문 복구 입력에 보존한다. 유효한 원문 항목이 있으면 상태와 무관하게
기존 보강 T3를 유지한다. 최초·보강 T3의 공유 2회 상한을 늘리거나 새로운 재시도를 허용하지 않는다.

이 최적화의 정책 snapshot은 활성 Director의 task·version·model·template로 고정한다.
다음 질문을 생성하는 `start_director(expected_prompt=...)`는 실제 활성 prompt가 같은지 확인하고,
다르면 모델 호출 전에 `context_changed` 폐기 기록을 남긴다. 같은 요청 재전송도 그 결과를 재생한다.
비어 있는 조회에 최초 T3를 재사용했다면 이 네 필드를
`director_retry_inputs[target].analysis_reuse_prompt`에도 저장한다. 자동·수동 복구의 예약과
전송 직전에도 같은 정책인지 확인하며, 버전·모델·본문이 달라지거나 snapshot 형식이 잘못되면
추가 호출 전에 복구를 거절한다. snapshot 없는 기존 복구 입력의 형식은 유지한다.
마지막 답변에는 다음 Plan이 없으며 읽은 정책 버전·생략 사유·조회 한계를 종료 결정에 보존한다.
구형 버전이나 정책 확인 실패에는 빈 조회 최적화를 적용하지 않고 기존 경로를 유지한다.

[0008 결정](decisions/0008-ai-candidate-policy.md)은 전제·목적이 유효한 표현 오류는 재작성 후보, 거짓·stale·반복 전제나 목적은 재계획 후보, 공급된 제약에서 안전한 질문을 만들 수 없으면 유효 후보 없음으로 구분한다. 0008 자체는 내부 enum이나 추가 호출·정상 종료·사용자 복구·service 상태를 승인하지 않는다. 위 내부 enum의 후속 채택은 0014 범위에 한한다.

## Evidence와 ToolResult

[0015 결정](decisions/0015-existing-contracts-and-tool-results.md)에 따라 ToolResult의 기존 `status`, `items`, `searched_scope`, `limitations`, `error_code`와 아래 상태를 유지·채택한다. Evidence도 기존 필드 구성과 출처 의미를 유지하며 상세 위치 타입·Tool 인수·공개 변환은 생산자와 소비자에 맞춰 구체화한다.

- `status`: `found | not_found | insufficient_analysis | tool_error`.
- 상태는 도구 실행 결과이며 특정 주장의 지지 여부와 별개다.
- Evidence item: `repository_id`, `git_ref`, `source_kind`, `path` 또는 metadata key, 실제 위치, `content` 원문, 선택적 `summary`, `tool_name`.
- `start_line/end_line`은 실제 line source가 있을 때만 사용한다. metadata·commit에 임의 줄 번호나 함수명을 붙이지 않는다.
- DB Evidence ID는 저장 계층이 발급한다. 임시 tool-result 참조를 durable ID로 바꾼 후 Turn 관계를 저장한다.
- `usage`는 관계 `turn_evidences`의 `question_basis | evaluation_basis`다. 같은 근거가 두 용도로 연결될 수 있다.

선택적 summary와 적용되지 않는 줄 번호는 생략할 수 있다. 사전 L2 분석에서 만든 Evidence의 tool_name은 기존대로 null을 허용하고, 실제 도구 산출물에는 수행한 도구 이름을 남긴다. 원문·고정 ref·권한 검증은 두 경로 모두 필요하다.

같은 도구 실행에서 유효한 근거를 일부 확보한 뒤 오류가 발생하면 status는 tool_error이며 검증된 items는 보존한다. searched_scope는 실제 확인한 범위, limitations는 미완료·미확인 범위와 이유를 담는다. error_code는 실제 오류에 맞는 코드이며 오류가 없으면 null이다. 독립된 A 실행의 성공을 후속 B 실행의 오류로 소급 변경하지 않는다.

tool_error만으로 확보 근거를 버리거나 사용자 감점·Director 전체 실패·자동 재조회를 결정하지 않는다. 상태는 실행 결과이고 주장 지지 여부는 별도 검증한다. 정상 조회 후 미발견과 미조회·자료 준비 부족·도구 오류를 구분하며, invalid 출력이나 출처 검증에 실패한 자료를 유효한 items로 보존하지 않는다.

자세한 검색·충돌 규칙은 [근거 검색](features/evidence-retrieval.md)을 따른다.

0008에 따라 조회 후보는 BE가 공급한 범위 안에서 관련 기존 Evidence·원문, 정확히 알려진 파일, 사전 검증된 인접 후보 순으로 제안한다. 주장 종류에 직접 맞고 범위가 좁은 source를 우선한다. ToolResult의 위 후속 채택과 별개로 Tool I/O·디렉터리 열거·실행 상한은 해당 기존 검토 범위다.

## task별 structured output 범위

| prompt version | 성공 결과에 필요한 의미 | 의미 검증 | Sprint 1 호출 정책 |
| --- | --- | --- | --- |
| `repo_shallow_v1` | repo별 목적·주요 기능·project_types·tech_stack·프로젝트 기능/역할 요약·분석 한계 | 입력 repo와 일대일 대응, README 주장/코드 확인 구분; 요약 필드 매핑 별도 합의 | 기존 LLM 방향 유지 |
| `repo_deep_v1` | architecture_summary·notable_areas·확인한 기술·분석 범위 | primary repo ref 고정, notable areas 1~5와 실제 파일 연결 | 기존 LLM 방향 유지 |
| `jd_extract_v1` | 저장 가능한 요구사항·원문 연결 | required/preferred/responsibility, Wanted 필드를 추측으로 변경 금지 | LLM 비호출, 구조화 필드 규칙 변환 |
| `answer_analysis_v1` | 질문 범위 안의 정성 평가·검증할 주장 | 답변 인용·Contract key·evidence 관계 일치 | 기존 LLM 방향 유지 |
| `director_v1` | 유효한 다음 질문 또는 bounded Tool 요청 | Persona·9턴·권한·반복·전제 제약 | 기존 LLM 방향 유지 |
| `report_v1` | 종합·Persona 피드백과 실제 문답 근거 | 미관찰 인정, 원문 불변, 확정한 공개 점수 구조 유지·미검수 세부 채점 기준의 임의 생성 금지 | 기존 LLM 방향 유지 |
| `profile_summary_v1` | 기존 개인 역할의 자연어 요약; 언어·유형 통계는 별도 확정 집계 | 기존 자료의 역할 근거·사용자 진술과 확인 사실 구분, 통계 변경 금지 | 0019에 따라 역할 요약의 LLM 사용 복원, job·version 목록 유지 |
| `domain_category_v2` | 공고 1건의 도메인 category 7종 중 하나와 근거 문단 ID(`etc`는 `null`) | category enum, non-etc의 ID는 이번 요청의 문단 ID여야 함(위반은 semantic 실패, 무재시도); 코드가 ID로 원문 복원; 실패는 `etc` | [0022](decisions/0022-domain-category-llm.md)·[0028](decisions/0028-domain-category-evidence-id.md)에 따라 LLM 호출, 공고당 1회. v1 prompt는 이력 |

기존 일곱 version 이름은 FIX 목록이며 삭제하지 않는다. `domain_category_v1`은 [0022](decisions/0022-domain-category-llm.md)로 추가했고 [0028](decisions/0028-domain-category-evidence-id.md)에서 `domain_category_v2`로 바꿨다. [0006 결정](decisions/0006-task-llm-usage-policy.md)의 Wanted 규칙 변환·프로필 통계 집계 비호출은 유지하되, 개인 역할의 자연어 요약은 [0019](decisions/0019-sprint1-profile-role-summary-restoration.md)에 따라 LLM으로 생성한다. version row만으로 호출 범위를 확대하지 않으며 deterministic 변환 version·출처 기록은 BE와 맞춘다. prompt version을 변환 version으로 재정의하거나 비호출 결과를 모델 실행 결과로 기록하지 않는다. 기존 role_summary·roleSummary 필드와 저장 구조를 유지하며 상세 입력·검증·연결은 구현 작업이다.

L1의 생성 요약은 0006에 따라 프로젝트의 기능·역할을 설명하며 README·commit 수로 개인 기여를 추정하지 않는다. `role_summary`는 오래된 task 주석의 필드명으로, 유지·변경과 실제 저장/API 매핑은 BE와 합의한다. 기존 개인 역할 필드를 프로젝트 요약으로 임의 재해석하지 않으며, 근거 없는 개인 기여 값은 빈칸을 추측으로 채우지 않고 미확인으로 다룬다.

### 문서 Claim의 후속 AI 모듈 계약

이 계약은 독립 추출 모듈의 입력·출력·검증 범위다. Sprint 1 preview·`doc_extract`의 Claim 생성·저장이나 면접 사용을 활성화하는 결정이 아니다. [0029](decisions/0029-document-claims.md)의 내부 추출 설계와 [0030](decisions/0030-document-claims-validation-boundary.md)의 검증·연결 경계를 함께 따른다. 실제 연결·검증 현황은 [구현 기록](implementation.md)에서 관리한다.

| prompt version | 성공 결과에 필요한 의미 | 검증 | 서비스 연결 조건 |
| --- | --- | --- | --- |
| `doc_claims_v1` | 포트폴리오 추출 텍스트의 Claim 최대 20개(`claim_text`, `claim_type` 4종, `tech_tags` 최대 5개)와 근거 줄 ID | 전체 응답의 schema를 먼저 검사하고, 통과한 응답의 줄 ID가 이번 요청에 있는지 검사한다. schema 실패는 공통 재시도 정책, 없는 ID는 semantic 실패·무재시도다. 한 항목 위반도 전체 거절하며 빈 Claim 목록은 성공이다. | BE 호출·prompt 등록·저장·처리 상태와 Director 소비 계약을 확인한 뒤 연결한다. 문서별 중복 호출 방지와 실패 기록은 호출자 책임이다. |

`paragraph_no`는 입력에 사용한 저장 `extracted_text`에서 빈 줄을 제외한 0번 시작 줄 순번이다. PDF 페이지나 원본 DOCX 문단 번호가 아니며, 두 줄에 걸친 주장은 시작 줄을 가리킨다. 줄 ID의 존재와 원문 한 줄 복원은 Claim 내용·기술·수치의 충실성이나 진위를 보장하지 않는다. 문서 Claim을 현재 답변 인용을 검사하는 기존 `claim_checks`에 그대로 넣지 않는다.

## Model Gateway와 실패

입력은 `task_name`, 실제 provider/model 설정, prompt/version, schema/version, 검증된 task input, timeout·호출 budget이다. 출력은 검증된 data 또는 typed failure와 호출 metadata다. token을 받지 못했을 때 0으로 추정하지 않는다.

기존 FIX의 총 2회 상한을 유지한다. timeout·재시도 가능한 provider 오류·JSON parsing·schema 실패는 공통 호출 계층에서 최대 1회 재시도한다. 2026-09-23 PR #56 리뷰 반영으로 HTTP 400·401·403·404 등 영구적인 요청 오류와 429의 quota/결제 한도 소진은 `provider` 실패로 즉시 종료한다. HTTP 408·409·429의 일시적 제한·5xx는 남은 공유 예산 안에서 재시도한다. 내부 error_code는 `llm_timeout`, `llm_parse_failed`, `llm_failed`를 유지하고 외부 flow reason으로 매핑한다.

일시적 429 및 재시도 가능한 오류의 `Retry-After`는 초 또는 HTTP-date로 해석한다. 대기 상한은 요청의 `timeout_seconds`이며 서버가 요구한 최소 대기가 이를 넘으면 줄여서 재시도하지 않고 종료한다. 일시적 429의 헤더가 없거나 잘못됐으면 `min(1초, timeout_seconds)`의 0.5~1배 범위에서 한 번 대기한다. 각 HTTP 시도 timeout과 대기 상한은 별개이며 함수 전체 deadline을 뜻하지 않는다. 취소는 전파한다. 이번 호출에 남은 시도가 없으면 대기 없이 반환하되, 같은 `CallBudget`을 재사용하는 다음 호출은 저장된 대기 시점의 잔여 시간을 지켜야 한다.

JSON 객체·배열의 깊이는 루트 container 1부터 최대 64로 제한하며 scalar는 container 깊이에 포함하지 않는다. 반복문으로 검사하고 파서 자체 `RecursionError`도 처리한다. 공급자 봉투의 오류는 `provider`, 모델 출력의 오류는 `parse`다. HTTP 오류는 성공 응답의 byte budget과 분리한다. 재시도가 허용된 429 본문은 quota 판별을 위해 응답 byte 상한까지만 읽어 보호된 metadata에 보존하고, 다른 HTTP 오류는 상태만 기록하며 본문은 읽지 않는다. 원문은 일반 로그에 쓰지 않는다.

[0008 결정](decisions/0008-ai-candidate-policy.md)에 따라 후보 실패는 parse, schema, semantic 실패로 구분한다. 어떤 invalid 결과도 성공 빈 객체, 추측한 기본값, 누락값 보충이나 ad hoc repair로 통과시키지 않는다. L1 batch의 유효한 항목은 보존하고 잘못된 항목만 실패로 분리하며, 실패는 현재 task에 한정하고 자료·문답 원문을 보존한다. semantic 실패는 Sprint 1에서 재호출하지 않는다.

같은 논리 작업의 attempt는 공통 LLM gateway/task 호출 계층에서만 관리한다. SDK·provider retry와 ARQ retry가 곱해지지 않도록 SDK/provider retry는 끄거나 최소화하고, ARQ `max_tries=1`을 사용한다. 깨진 JSON을 위한 별도 repair prompt는 Sprint 1에 추가하지 않는다. task별 timeout·token·context·tool budget은 별도 설정으로 남는다.

`ModelResult.attempts`는 이번 `call_model` 실행에서 발생한 기록만 반환한다. 같은 `CallBudget`의 첫 결과가 `[1]`이면 다음 호출분은 `[2]`이며, 실제 호출 없는 예산 소진·종료 결과는 빈 tuple이다. attempt 번호와 총 2회 상한은 공유 작업 전체에서 유지한다. 저장자는 각 결과를 수집하고, 전송 실패로 같은 결과를 다시 저장하는 경우의 멱등성은 저장 계층에서 별도로 처리한다.

raw output·model·prompt_version·schema_version·input/output tokens·latency·attempt·error를 필요한 범위에서 보존한다. [0018의 자료 선택](decisions/0018-existing-baseline-bulk-resolution.md#ai-l18-후속-내부-비교-검증-자료)에 따라 실제 문답·연결 분석·리포트·실패 기록은 필요한 팀 검수자의 후속 내부 비교 검증에도 보관·재사용한다. 최종 내부 비교 검증 뒤에도 보관하며 별도의 자동 삭제 기한은 두지 않는다. task별 영구 저장 위치·마스킹·실제 권한·복사본 및 파생 자료 관리는 구현에서 확인한다. 공개 로그에 원문을 출력하는 것으로 저장 요구사항을 대신하지 않는다.

### 사적 응답 구간 계측

[0061 결정](decisions/0061-review-calibration-and-response-timing.md)에 따라 아래 값은
공개 AttemptMetadata에 추가하지 않고 사적 실행 장부의 허용 metadata로 기록한다.

| 키 | version 1·2의 공통 의미 |
| --- | --- |
| `response_timing_version` | 1은 기존 monotonic, 2는 별도 perf_counter 시점·구간 계측. 과거 미계측 기록에는 키가 없음 |
| `response_headers_ms` | attempt 시작부터 HTTP 응답 헤더를 받은 시점까지 |
| `first_sse_event_ms` | attempt 시작부터 첫 유효 SSE data 이벤트를 포함한 chunk를 받은 시점까지 |
| `first_output_text_delta_ms` | attempt 시작부터 첫 비어 있지 않은 output_text.delta 이벤트를 포함한 chunk를 받은 시점까지 |
| `response_read_ms` | HTTP 본문 읽기 구간의 소요 시간. 중단 시 도달한 구간까지 |
| `response_decode_ms` | 완독 후 봉투/SSE 완료 응답 파싱·완료/모델/ID 확인·최종 출력 strict JSON 해석 구간 |
| `validation_ms` | 작업별 validator 구간. 형식·의미 반려 시에도 실제 실행 시간 기록 |
| `response_read_complete` | 미시작 null, 읽기 중 중단 false, 완독 true |
| `sse_timing_limited` | SSE 계측용 현재 frame의 64KiB 상한으로 관측을 중단했는지 |

시간은 0 이상 정수 ms 또는 null이며 도달하지 않은 값은 0으로 추정하지 않는다.
정수 ms의 0은 반올림·해상도 이하의 관측일 수 있으며 정확한 0이 아니다. version2의
시계 분리·과거 원문 보존은 [0062 결정](decisions/0062-response-timing-high-resolution-clock.md)을 따른다.
완성된 이벤트의 관측은 로컬 수신 기준으로, 공급자 토큰 생성 시각이 아니다. 비스트림이나
delta 없는 완료 응답에는 SSE/delta 시간을 만들지 않는다. 계측 한계는 기존 권위 파서·
byte 상한·호출 결과를 바꾸지 않는다. 본문·헤더 내용·인증값·주소는 이 필드에 기록하지 않는다.

실제 면접의 선택 실행 장부는 I/O 오류가 정상 모델 결과·답변 저장을 중단시키지 않도록
장부 초기화·start·finish의 `OSError`·SQLite `OperationalError`만 격리한다.
누락·미완료 관측은 성공이나 사용량 0으로 보충하지 않는다. 평가 장부의 기본 strict
실패 전파, 검증 오류와 프로그래밍 오류, 원래 업무 예외·취소는 유지한다.
서비스 적용과 롤백 경계는 [0065 결정](decisions/0065-director-service-rollout.md)을 따른다.

## 면접 실행 서비스의 후속 경계

[면접 준비·답변·전송 실행 설계](designs/2026-10-25-interview-execution.md)는 Proposed 후속 설계다.
준비 claim, 답변 commit 이후 전송, 분석 후 상태 전이와 WS 인계의 Controller 책임을 정의한다.
기존 내부 입력 계약과 공개 wire를 대체하지 않으며, 선행 구현의 병합이나 전체 실행 완료를 뜻하지 않는다.
준비 이벤트·실패 단계 재개·명시적 이탈 통지의 기존 요구와 미구현 상태는 해당 설계의 한계를 함께 따른다.

## public 변환과 합의 경계

- FE 면접 명세의 `question` payload는 `persona`, `text`, `turn`을 사용한다. 이는 소비자 측 문서의 요구이며 공통 WS payload schema와 검수해 확정할 부분이다. 내부 Question 전체를 그대로 직렬화하지 않는다.
- 답변 wire는 `{ "type": "answer", "turn": 3, "text": "..." }`다. 별도 `clientSubmissionId`는 Sprint 1에 추가하지 않는다. 현 계약으로 보장 가능한 범위와 한계는 [면접 명세](features/interviewer.md)에 따른다.
- 현재 리포트 200 schema는 숫자 점수를 필수로 요구한다. Sprint 1은 0~100 score 6개와 단순 평균 `totalScore`를 공개한다. 가중치와 nullable/status 표현은 사용하지 않는다.
- Question Contract와 분석·판단의 위 채택 범위는 0014를 따른다. 미채택 상세 평가·근거 표현·model metadata 저장과 새 공개 필드는 AI·BE/FE 검토 대상이다.

## 계약 검토 완료 조건

각 task의 성공·실패·경계 fixture, 변환 담당, durable 저장 위치, schema version, 허용 null·enum·상한, 실패 코드가 정해져야 한다. 실제 모델 schema 적합성은 별도 평가하며 mock 통과로 대체하지 않는다. 검토자는 [기준 결정](decisions/0001-ai-baseline.md)과 관련 후속 결정에 채택한 범위와 근거를 남긴다.
