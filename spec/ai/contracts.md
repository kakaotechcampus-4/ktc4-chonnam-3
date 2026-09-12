# AI 내부 입력·출력 계약

작성일: 2026-09-12. 상태: 정확한 내부 필드·schema·저장은 **Proposed**. 후보 검증·선택 의미는 명시된 Accepted 결정을 따른다.

이 문서는 공개 API나 승인된 DB schema를 대체하지 않는다. [패키지 설계](designs/2026-09-12-ai-package-structure.md)에 따른 AI 원본 위치는 `ai/src/devon_ai/contracts.py`이며 현재 실제 클래스가 없다. 기존 `backend/app/agents/contracts.py`도 연결 계층 안내만 있다. 패키지 구조 승인은 AI-L02의 타입 채택 승인이 아니다. 아래 새 필드·enum·JSON 구조를 저장 계약으로 사용하기 전에 AI·BE가 함께 검토하고 테스트 fixture에 고정한다. 공개 camelCase와 내부 snake_case 변환은 service/schema 계층의 책임이다.

아래 필드 표와 enum은 모두 fixture로 검토할 후보이며, 이 문서만으로 migration·공개 API·WS enum 추가를 승인하지 않는다. 기존 FIX와 [0008 후보 정책](decisions/0008-ai-candidate-policy.md) 등 명시된 Accepted 정책만 승인 범위에서 확정된 요구사항이다.

원본: [아키텍처](architecture.md), [레이어 규칙](../../backend/docs/layer-rules.md), [DB 명세](../../backend/docs/db-schema.md), [ForAI](../../ForAI.md), [미결정 기록](decisions/0001-ai-baseline.md).

## 계약 계층

| 계층 | 내용 | 결정 상태 |
| --- | --- | --- |
| 공개 REST | OpenAPI의 요청·응답 | 기존 FIX, 명시된 PENDING 제외 |
| 공개 WS | 텍스트 답변과 기존 이벤트 의미 | FIX와 PENDING_FE 혼재 |
| 저장 책임 방향 | turn 중심 분석·결정, evidence 관계, report feedback | 테이블 책임은 기존 방향; 정확한 analysis/decision 컬럼·JSON key는 Proposed |
| 내부 데이터의 정확한 필드 | 이 문서의 Context·Question·Evaluation 등 | Proposed |
| 모델 원시 출력 | task별 schema에 맞는 후보 결과 | 신뢰 전 검증 대상 |

모델에게 DB PK·user_id·run_id·최종 status를 생성하게 하지 않는다. 입력에서 전달한 ID를 참조하게 하되, 실제 관계·소유권은 service가 검증한다. raw output과 검증된 결과를 같은 성공 객체로 취급하지 않는다.

## 공통 타입 원칙

- UUID·repository ID·Turn ID는 service가 전달한다. 샘플 식별자를 production 값으로 쓰지 않는다.
- 시간은 timezone이 있는 값이다. 분석은 대상 `head_sha`, 면접의 코드 근거는 `session_repositories.snapshot_head_sha`를 사용한다. 원격 기본 branch의 최신 SHA, 서비스 코드 commit과 혼동하지 않는다.
- `null`은 미확인·미적용 중 문서에서 정의한 경우에만 허용한다. 모르는 값에 0이나 빈 문자열을 넣지 않는다.
- enum 외 값, 필요한 값 누락, 과도한 컬렉션, 중복 참조, 근거 없는 위치·인용은 검증 실패다.
- 사전 수집된 관찰과 LLM 해석은 별도 필드다. 문자열 인용은 해당 원문 또는 답변에서 확인할 수 있어야 한다.
- 아래 길이·token·도구 횟수 상한의 운영값은 미결정이다. 설정 스키마에서 양수·일관성 검사하고, 실제 모델 실행 전에 값을 기록한다.

## Context 입력 제안

| 필드 | 형식·의미 |
| --- | --- |
| `interview_id`, `current_turn_id` | 서버가 식별한 현재 면접과 Turn; 첫 질문 전 Turn ID는 없음 |
| `turn_no`, `total_turns` | 현재 질문 번호와 FIX 상한 9 |
| `persona_counts` | 이미 확정·제시된 질문의 Persona별 횟수 |
| `allowed_personas` | 남은 턴으로 FIX 분포를 만족할 수 있는 후보; Controller 계산 |
| `jd_requirements` | 저장된 ID, 원문, requirement_type, source field, tech_tags |
| `repositories` | 선택 repo ID, 고정 ref, primary 여부, 성공 분석과 분석 범위 |
| `history` | 질문·Persona·제출 답변·판정·참조 ID; 사실과 요약 구분 |
| `current_question_contract` | 전달 전에 확정한 질문 목적과 확인내용 |
| `evidence` | 현재 권한·선택 ref에 유효한 검증 결과 |
| `domain_frames` | 선택 category의 검수·버전 정보가 있는 seed |
| `limits` | 남은 호출·재계획 budget과 현재 정책 버전 |

현재 Context에 과거 raw output 전체나 다른 사용자의 정보를 넣지 않는다. Context Builder는 평가에 유리한 답만 선택하지 않고, 기여 정정·이전 확인사항·미확인 범위를 유지한다. 축약하더라도 원문은 DB에서 조회 가능해야 한다.

## Question과 Question Contract 제안

모델 후보:

| 필드 | 형식·검증 |
| --- | --- |
| `persona` | `tech_lead`, `hr_manager`, `domain_lead` 중 Controller의 허용 후보 |
| `text` | 사용자에게 제시할 한 질문; 질문 목적과 일치 |
| `topic_code` | 내부 주제 식별; 아직 전역 taxonomy/FK를 새로 만들지 않음 |
| `question_contract` | 아래 구조; 전달 전에 확정 |
| `evidence_refs` | 기존 유효 Evidence 참조; 없는 ID 생성 금지 |
| `jd_requirement_ids` | 실제로 연결되는 현재 JD 요구사항만 |

Question Contract는 `purpose`(질문의 목적), `required_points`(질문에서 실제 요구한 확인내용 목록), `assumptions`(명시한 가정), `basis_refs`(전제를 뒷받침하는 자료), `evaluation_scope`(평가할 내용)를 담는 내부 제안이다. `required_points`는 고유 key와 설명을 가진다.

서비스가 확정하는 `turn_id`, `turn_no`, `depth`, `parent_turn_no`는 모델의 제안만으로 결정하지 않는다. 이 설계를 채택하면 질문·Contract·Persona를 함께 저장하고, 답변을 본 뒤 Contract를 바꾸어 감점하지 않는다. 저장할 JSONB 위치·schema_version은 BE와 합의한다. 채택 전에는 검토용 fixture로 검사하고, 저장 경계 없이 Contract 기반 평가·리포트를 완성했다고 보고하지 않는다.

## AnswerAnalysis 제안

기존 스켈레톤에 `specificity`, `verified_claims`, `unverified_claims`, `needs_verification`이라는 이름이 있으나 구현 계약은 없다. 기존 이름 유지·확장은 BE 검토 대상이며, `specificity`를 충분성·정확성·기여의 통합 점수로 사용하지 않는다.

| 필드 | 제안 값·의미 |
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

모델이 `verified_claims`라고 출력해도 service 검증 전에는 확인된 사실이 아니다. 기여 정정과 후속 보완은 원문을 보존한 상태로 이후 Context에 반영한다. 이 계약은 [답변 평가](features/answer-evaluation.md)의 정성 판정을 위한 제안이며 리포트 점수 산식이 아니다.

[0004 결정](decisions/0004-answer-assessment-policy.md)은 세 축의 정성 의미, 평가 가능 여부·축별 보류, 후속 보완·기여 정정과 원문/최초 분석 보존 원칙을 승인한다. 자료 부족만으로 모든 축을 자동 평가 불가로 만들지 않는다. 위 상태 문자열·필드·null 표현·JSONB와 Question Contract는 저장 계약으로 승인된 것이 아니며 AI-L02에서 별도 검토한다. 보존 원칙을 위해 새 이력 테이블이나 재평가 API를 임의 추가하지 않는다.

[0003 결정](decisions/0003-evidence-lookup-policy.md)은 추가 조회 필요성과 결과 해석의 의미 정책만 승인한다. 위 필드·enum·JSON 구조와 ToolResult의 저장·공개 계약은 계속 Proposed다. 실제 조회 없이 `not_found`를 만들거나, 조회 필요성 판단으로 service의 권한·budget 검증을 우회하지 않는다.

## DirectorDecision 제안

| 필드 | 형식·검증 |
| --- | --- |
| `next_step` | `ask`, `retrieve`, `finish`라는 내부 제안 enum |
| `intent` | 보완·심화·전환·확인 목적; 사용자에게 보여줄 질문 자체와 구분 |
| `persona` | ask에 필요; 허용 Persona 중 하나 |
| `target` | 확인할 주제·질문 목적·현재 답변과의 연결 |
| `tool_requests` | retrieve에 필요; 허용 Tool과 범위 |
| `reason_summary` | 짧은 결정 근거; 숨은 사고과정 전체를 요구하거나 저장하지 않음 |

`finish`는 모델의 자율 조기 종료 권한이 아니다. Controller가 종료 조건을 이미 만족한 경우만 허용한다. 정상 Sprint 1은 9턴 완료 후 종료한다. 사용자 종료와 시스템 실패는 service의 별도 처리다.

`retrieve`는 사용자 질문 Turn을 증가시키지 않는다. 결과를 반영한 후 유효한 ask 또는 허용 종료로 수렴해야 한다. 반복 budget 소진 시 질문을 검증 없이 발행하지 않는다. 정확한 내부 enum 채택 전에는 `context/AI.md`의 대문자 행동명을 저장·WS enum으로 승격하지 않는다.

[0008 결정](decisions/0008-ai-candidate-policy.md)은 전제·목적이 유효한 표현 오류는 재작성 후보, 거짓·stale·반복 전제나 목적은 재계획 후보, 공급된 제약에서 안전한 질문을 만들 수 없으면 유효 후보 없음으로 구분한다. 이는 `next_step` enum 채택, 추가 호출, 정상 종료, 사용자 복구나 service 상태를 승인하지 않는다.

## Evidence와 ToolResult 제안

ToolResult는 `status`, `items`, `searched_scope`, `limitations`, `error_code`를 담는다.

- `status`: `found | not_found | insufficient_analysis | tool_error`.
- 상태는 도구 실행 결과이며 특정 주장의 지지 여부와 별개다.
- Evidence item: `repository_id`, `git_ref`, `source_kind`, `path` 또는 metadata key, 실제 위치, `content` 원문, 선택적 `summary`, `tool_name`.
- `start_line/end_line`은 실제 line source가 있을 때만 사용한다. metadata·commit에 임의 줄 번호나 함수명을 붙이지 않는다.
- DB Evidence ID는 저장 계층이 발급한다. 임시 tool-result 참조를 durable ID로 바꾼 후 Turn 관계를 저장한다.
- `usage`는 관계 `turn_evidences`의 `question_basis | evaluation_basis`다. 같은 근거가 두 용도로 연결될 수 있다.

자세한 검색·충돌 규칙은 [근거 검색](features/evidence-retrieval.md)을 따른다.

0008에 따라 조회 후보는 BE가 공급한 범위 안에서 관련 기존 Evidence·원문, 정확히 알려진 파일, 사전 검증된 인접 후보 순으로 제안한다. 주장 종류에 직접 맞고 범위가 좁은 source를 우선하되, 이 순서는 Tool I/O·디렉터리 열거·실행 상한이나 위 ToolResult 필드 채택을 뜻하지 않는다.

## task별 structured output 범위

| prompt version | 성공 결과에 필요한 의미 | 의미 검증 | Sprint 1 호출 정책 |
| --- | --- | --- | --- |
| `repo_shallow_v1` | repo별 목적·주요 기능·project_types·tech_stack·프로젝트 기능/역할 요약·분석 한계 | 입력 repo와 일대일 대응, README 주장/코드 확인 구분; 요약 필드 매핑 별도 합의 | 기존 LLM 방향 유지 |
| `repo_deep_v1` | architecture_summary·notable_areas·확인한 기술·분석 범위 | primary repo ref 고정, notable areas 1~5와 실제 파일 연결 | 기존 LLM 방향 유지 |
| `jd_extract_v1` | 저장 가능한 요구사항·원문 연결 | required/preferred/unknown, Wanted 필드를 추측으로 변경 금지 | LLM 비호출, 구조화 필드 규칙 변환 |
| `answer_analysis_v1` | 질문 범위 안의 정성 평가·검증할 주장 | 답변 인용·Contract key·evidence 관계 일치 | 기존 LLM 방향 유지 |
| `director_v1` | 유효한 다음 질문 또는 bounded Tool 요청 | Persona·9턴·권한·반복·전제 제약 | 기존 LLM 방향 유지 |
| `report_v1` | 종합·Persona 피드백과 실제 문답 근거 | 미관찰 인정, 원문 불변, 미합의 점수 생성 금지 | 기존 LLM 방향 유지 |
| `profile_summary_v1` | 자연어 요약 용도는 후속 검토; Sprint 1 job은 확정 집계만 수행 | 완료 면접에 사용된 repo의 확정 데이터만 | LLM 비호출, job·version 목록 유지 |

위 일곱 version 이름은 기존 FIX 목록이며 삭제하지 않는다. [0006 결정](decisions/0006-task-llm-usage-policy.md)은 Wanted 규칙 변환과 Sprint 1 프로필 집계에서 LLM을 호출하지 않는 처리 원칙을 승인했다. version row가 있다는 이유로 호출하지 않으며, deterministic 변환 version·출처 기록은 BE와 별도 합의한다. prompt version을 변환 version으로 재정의하거나 비호출 결과를 모델 실행 결과로 기록하지 않는다. 세부 출력·저장 필드는 계속 Proposed다.

L1의 생성 요약은 0006에 따라 프로젝트의 기능·역할을 설명하며 README·commit 수로 개인 기여를 추정하지 않는다. `role_summary`는 오래된 task 주석의 필드명으로, 유지·변경과 실제 저장/API 매핑은 BE와 합의한다. 기존 개인 역할 필드를 프로젝트 요약으로 임의 재해석하지 않으며, 근거 없는 개인 기여 값은 빈칸을 추측으로 채우지 않고 미확인으로 다룬다.

## Model Gateway와 실패

입력은 `task_name`, 실제 provider/model 설정, prompt/version, schema/version, 검증된 task input, timeout·호출 budget이다. 출력은 검증된 data 또는 typed failure와 호출 metadata다. token을 받지 못했을 때 0으로 추정하지 않는다.

기존 FIX: timeout/provider 오류/JSON parsing 실패는 **자동 1회 재시도**, 총 2회 실패하면 중단한다. 내부 error_code는 `llm_timeout`, `llm_parse_failed`, `llm_failed`를 사용하고 외부 flow reason으로 매핑한다.

[0008 결정](decisions/0008-ai-candidate-policy.md)에 따라 후보 실패는 parse, schema, semantic 실패로 구분한다. 어떤 invalid 결과도 성공 빈 객체, 추측한 기본값, 누락값 보충이나 ad hoc repair로 통과시키지 않는다. L1 batch의 유효한 항목은 보존하고 잘못된 항목만 실패로 분리하며, 실패는 현재 task에 한정하고 자료·문답 원문을 보존한다.

같은 논리 작업의 attempt는 한 계층에서 관리해 SDK·client·task·worker의 재시도가 곱해지지 않아야 한다. 다만 관리 계층, 운영 상한, semantic 실패의 실제 재호출 여부와 실패 item의 attempt 계산은 0008이 정하지 않았으며 AI·BE가 별도로 합의한다. 깨진 JSON을 위한 별도 repair prompt는 Sprint 1에 추가하지 않는다.

raw output·model·prompt_version·schema_version·input/output tokens·latency·attempt·error를 필요한 범위에서 보존한다. task별 실패 원문의 DB 저장 위치·접근권한·보존기간은 미결정이다. 공개 로그에 원문을 출력하는 것으로 저장 요구사항을 대신하지 않는다.

## public 변환과 합의 경계

- FE 면접 명세의 `question` payload는 `persona`, `text`, `turn`을 사용한다. 이는 소비자 측 문서의 요구이며 공통 WS payload schema와 검수해 확정할 부분이다. 내부 Question 전체를 그대로 직렬화하지 않는다.
- 답변 wire는 `{ "type": "answer", "text": "..." }`다. stale 응답 검사를 위해 필요하더라도 `turnId`나 idempotency key를 승인 없이 추가하지 않는다. 현 계약으로 보장 가능한 범위와 한계는 [면접 명세](features/interviewer.md)에 따른다.
- 현재 리포트 200 schema는 숫자 점수를 필수로 요구한다. 미합의 점수를 null/0으로 채우지 않는다. 피드백 내부 구현과 점수 포함 공개 성공 응답의 완료 조건을 구분한다.
- Question Contract, 자세한 평가, 근거 위치·품질, model metadata를 저장하는 정확한 JSONB 구조와 새 공개 필드는 AI·BE/FE 검토 대상이다.

## 계약 검토 완료 조건

각 task의 성공·실패·경계 fixture, 변환 담당, durable 저장 위치, schema version, 허용 null·enum·상한, 실패 코드가 정해져야 한다. 실제 모델 schema 적합성은 별도 평가하며 mock 통과로 대체하지 않는다. 검토자는 [기준 결정](decisions/0001-ai-baseline.md)과 관련 후속 결정에 채택한 범위와 근거를 남긴다.
