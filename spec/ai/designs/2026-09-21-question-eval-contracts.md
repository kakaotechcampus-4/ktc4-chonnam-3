# 질문·평가 내부 계약 채택안

- 상태: **Proposed** — AI-L02 승인 요청용이며 runtime·저장 계약 채택 기록이 아니다.
- 작성일: 2026-09-21. 범위: Sprint 1 텍스트 면접의 Persona, Question, QuestionContract, AnswerAnalysis, DirectorDecision과 실패·복구 경계.
- 기준 브랜치: `develop` (`854e2aa`) → `docs/ai-question-eval-contracts`. 선행 구현 브랜치 없음.
- 산출물은 이 문서 하나다. [task-02](../../../ai/docs/task-02-contracts.md)에 따라 `ai/src/devon_ai/contracts.py`는 AI-L02 승인 전까지 docstring 상태를 유지한다.

## 1. 목적과 원본

질문이 실제 요구한 내용만 평가하고, 충분성·기술적 정확성·기여 및 근거 정합성을 분리하며, 검증 실패 후보를 사용자 질문이나 성공 결과로 내보내지 않는 내부 경계를 검토한다. 문서 존재나 구조 테스트 통과는 기능 구현 완료가 아니다.

필드 표의 근거 약칭은 다음 원본을 가리킨다. FIX는 기존 공유·서비스 계약, Accepted는 승인된 의미 정책, Proposed는 이 문서에서 검토하는 정확한 필드·타입·표현이다. 한 행에 여러 상태가 있으면 의미 승인과 표현 승인을 구분한 것이다.

| 약칭 | 근거 문서와 적용 범위 |
| --- | --- |
| C | [내부 계약](../contracts.md): 필드 후보·참조·실패·공개 변환 |
| I | [면접](../features/interviewer.md): Persona·질문 검증·9턴·텍스트 WS |
| A | [답변 평가](../features/answer-evaluation.md): 평가 가능 여부·세 축·8개 대조 사례 |
| E | [근거 검색](../features/evidence-retrieval.md): 원문·고정 ref·조회 상태·소유권 |
| J | [Context](../features/job-context.md): 현재 작업 식별과 질문의 불변 사실 |
| D | [도메인 프레임](../features/domain-frames.md): 주입 frame과 개발용 후보·운영 seed 구분 |
| S | [OpenAPI](../../shared/contracts/openapi.yaml), [이관표](../../shared/contracts/migration.md), [용어](../../shared/glossary.md), [공통 계약](../../shared/contracts/README.md) |
| R1/R3/R4 | [ADR 0001](../decisions/0001-ai-baseline.md), [0003](../decisions/0003-evidence-lookup-policy.md), [0004](../decisions/0004-answer-assessment-policy.md): 기준선·조회·평가 |
| R5/R6 | [ADR 0005](../decisions/0005-domain-question-policy.md), [0006](../decisions/0006-task-llm-usage-policy.md): 도메인·작업별 LLM 사용 |
| R8/R10 | [ADR 0008](../decisions/0008-ai-candidate-policy.md), [0010](../decisions/0010-sprint1-interface-runtime-decisions.md): 후보 정책·호출 attempt |
| L | [later.md](../../../later.md): 남은 공동 결정; 각 행의 AI-L 번호 참조 |

추가 읽기 기준은 [아키텍처](../architecture.md), [검증](../verification.md), [AI README](../../../ai/README.md), [pipeline](../../../ai/docs/pipeline.md), [testing](../../../ai/docs/testing.md), [task-03](../../../ai/docs/task-03-llm-boundary.md), [task-09](../../../ai/docs/task-09-answer-analysis.md), [task-10](../../../ai/docs/task-10-director.md), [후속 기능](../features/extensions.md)이다.

## 2. 변경하지 않는 경계

Agent는 Director 하나이며 Persona는 질문 관점이다. Question Generator·Question Validator·Answer Evaluator는 논리적 책임으로, 별도 Agent·모듈·LLM 호출 수를 확정하지 않는다. 직접 구현·검증·디버깅 질문은 `tech_lead` 관점에 둔다. 평가 기준은 Persona에 따라 바꾸지 않는다.

BE가 `prompt_versions`·`domain_question_frames`의 운영 원본, prompt/version·설정 조회, 권한, 실제 I/O, 저장, 상태와 공개 변환을 소유한다. AI는 주입된 값과 승인 후 정의할 provider 중립 Protocol을 소비한다. 운영 Persona 문구·prompt·frame을 AI 상수나 설정 파일로 복제하지 않는다. 향후 설정 파일이 필요해도 테스트 fixture에 한정한다.

`devon_ai`는 `app.*`, FastAPI, SQLAlchemy, Redis, ARQ를 import하지 않는다. import 시 환경변수·네트워크·DB에 접근하지 않는다. 구체 SDK·provider·API model ID를 선택하지 않으며 테스트는 fake만 사용한다.

확정 입력은 `{ "type": "answer", "turn": 3, "text": "답변 내용" }`다. 서버 메시지는 `answerReceived`, `thinking`, `evidenceCheck`, `question`, `interviewEnd`, `error`만 유지한다. 내부 객체를 WS로 직렬화하지 않으며 camelCase 변환은 BE 책임이다. 제출·녹음·재제출 식별자를 추가하지 않는다.

9턴, 첫 질문 `hr_manager`, `tech_lead` 목표 6턴·최소 5턴, HR+domain 합산 최소 3턴을 유지한다. 질문 수와 답변 완료 수를 구분하고 9번째 답변 처리 후 정상 종료한다. Tool·재작성은 턴이 아니며 10번째 질문·소급 Persona 변경은 금지한다. HR/domain 각각의 최소치와 고정 교대는 만들지 않는다.

## 3. Persona 정의와 주입 계약

다음 표는 I의 「역할과 입력」에 있는 질문 책임·피해야 할 전제 표를 원문 그대로 옮겼다.

| Persona | 질문 책임 | 피해야 할 전제 |
| --- | --- | --- |
| `hr_manager` | 긴장 완화, 자기소개, 협업, 본인 역할·판단, 이전 답변 확인 | 조직 repo 접근이나 commit 수로 개인 기여를 확정 |
| `tech_lead` | 실제 코드·설계·기술 선택·문제 해결·answer_vs_code 확인 | 읽지 않은 구현·성능·배포 성공을 사실로 단정 |
| `domain_lead` | 산업/서비스의 개인정보·운영·사용자 맥락 | JD 요건 암기 검사, 사용자의 도메인 실무 경험을 추정 |

Persona 설정은 세 항목이 모두 있는 BE 주입값이다. 식별자의 허용 집합은 코드로 검사하되 책임 문구와 금지 전제의 운영값은 하드코딩하지 않는다. 입력된 문구가 FIX 책임에 반하는 경우도 채택하지 않는다. `domain_lead`를 생략하거나 다른 이름으로 치환하지 않는다.

| 필드 | 제안 타입·검사 | 근거·상태 | 소유자(AI/BE) | 저장·공개 영향 | 남은 미결정 |
| --- | --- | --- | --- | --- | --- |
| `persona` | 세 FIX 식별자 중 하나, 필수·null 불가 | S/I/R1: FIX; 설정 필드 배치 Proposed | BE 공급, AI 검사 | 기존 persona만 BE가 저장·공개 | AI-L02 설정 포장 형식 |
| `question_responsibilities` | 비어 있지 않은 문자열 목록, 필수 | I: FIX 책임; 필드 Proposed | BE 운영 원본, AI 소비 | 내부 입력만; 새 컬럼 없음 | AI-L02·10 운영 문구·version 연결 |
| `avoided_assumptions` | 비어 있지 않은 문자열 목록, 필수 | I: FIX 제약; 필드 Proposed | BE 운영 원본, AI 검사 | 내부 입력만; 새 공개값 없음 | AI-L02·10 문구·검수 연결 |

## 4. Question과 QuestionContract

아래 Question은 모델 후보 본문이다. 확정 질문 식별은 기존 BE `turn_id`에 연결하고 별도 모델 생성 `question_id`·Contract ID를 만들지 않는 안을 제안한다. Contract는 질문에 내장해 함께 검증·확정하며, 정확한 식별·저장 방식은 AI-L02에서 채택한다.

| 필드 | 제안 타입·검사 | 근거·상태 | 소유자(AI/BE) | 저장·공개 영향 | 남은 미결정 |
| --- | --- | --- | --- | --- | --- |
| `persona` | FIX enum, 현재 `allowed_personas`의 원소 | S/I: FIX 값; C: Proposed | AI 후보, BE 최종 확정 | 기존 공개 persona로 BE 변환 | AI-L02 타입 채택 |
| `text` | 비어 있지 않은 문자열, 한 중심 목적, null 불가 | I/R5: Accepted 정책; C: Proposed | AI 생성·검증, BE 확정 | 기존 질문 텍스트만 공개 | AI-L02·04 길이 상한 |
| `topic_code` | 비어 있지 않은 내부 주제 문자열 | C: Proposed | AI 제안, BE 계약 검토 | 내부 후보; 새 taxonomy/FK 없음 | AI-L02 어휘·저장 필요성 |
| `question_contract` | 아래 Contract 필수, 전달 후 불변 | C/J: Proposed; R4: Accepted 평가 범위 | AI 구성·검증, BE 동시 확정 | JSONB 위치 미정, 공개 안 함 | AI-L02 저장·version |
| `evidence_refs` | 주입된 유효 Evidence 참조 목록, 중복 금지 | C: Proposed; E: FIX 범위 | AI 참조 검사, BE 권한·저장 | BE가 question_basis 관계 저장 | AI-L02 durable 참조 표현 |
| `jd_requirement_ids` | 현재 JD의 등록 ID 목록, 중복 금지 | C: Proposed | AI 관련성 검사, BE 소유권 검사 | 내부 연결; 공개 확장 없음 | AI-L02 참조 타입·저장 |
| `question_contract.purpose` | 실제 질문의 중심 목적, 비어 있지 않은 문자열 | C: Proposed; I/R8: Accepted 의미 | AI 구성·검증 | 질문과 함께 BE 보존, 비공개 | AI-L02 표현·version |
| `question_contract.required_points` | 실제로 물은 확인내용 목록, 1개 이상 | C: Proposed; R4: Accepted 범위 | AI 구성·문장 대조 | BE 불변 보존, 비공개 | AI-L02·04 목록 상한 |
| `required_points[].key` | Contract 안에서 유일한 비어 있지 않은 문자열 | C: Proposed | AI 제안·검사 | 후속 평가가 동일 key 참조 | AI-L02 key 규칙 |
| `required_points[].description` | 실제 문장에 대응하는 확인내용 설명 | C: Proposed; R4: Accepted 의미 | AI 검증 | 평가 범위만; 공개 안 함 | AI-L02 의미 검수 방식 |
| `question_contract.assumptions` | 명시한 가정의 문자열 목록; 없으면 빈 목록 | C: Proposed; I/R5/R8: Accepted | AI 구성·검증 | 확인된 사실과 구분해 BE 보존 | AI-L02 가정·근거 대응 표현 |
| `question_contract.basis_refs` | BE가 등록한 자료 참조 목록; 중복 금지 | C: Proposed; E/J: FIX 범위 | AI 대조, BE 권한·ref 확인 | 자료 연결만; 새 Evidence 생성 아님 | AI-L02 source별 참조 타입 |
| `question_contract.evaluation_scope` | 평가할 내용의 비어 있지 않은 설명 | C: Proposed; R4: Accepted 의미 | AI 구성·검증 | required_points 밖 감점 금지 | AI-L02 범위 표현 |

목록은 누락·null과 빈 목록을 구분한다. HR·가정형 domain 질문은 코드 근거 없이 유효할 수 있지만, 구체 구현을 사실로 전제하면 해당 원문이 필요하다. frame 자체를 사용자 프로젝트 Evidence로 만들지 않는다. 근거가 없는 도메인 경험은 가정형으로 질문하고 category 미확인 시 R5의 `etc`를 따른다.

BE가 주입·회수할 식별 문맥은 다음과 같다. 모델이 이 값을 생성하거나 변경하지 못하게 한다. 반환 결과에 같은 문맥을 연결하는 안이며 새 공개 입력 식별자가 아니다.

| 필드 | 제안 타입·검사 | 근거·상태 | 소유자(AI/BE) | 저장·공개 영향 | 남은 미결정 |
| --- | --- | --- | --- | --- | --- |
| `interview_id` | BE가 식별한 면접 ID, 필수 | C/J: Proposed 표현 | BE 발급, AI 원값 연결 | 기존 면접 연결, 공개 확장 없음 | AI-L02 Python ID 타입 |
| `current_turn_id` | 현재 확정 질문의 BE Turn ID; 첫 질문 전만 null | C/J: Proposed | BE 발급, AI 원값 연결 | 분석·결정을 원 질문에 연결 | AI-L02 첫 질문 확정·결과 포장 |
| `turn_no` | BE가 전달한 현재 질문 번호; 생성 대상과 구분 | C/I: Proposed 표현, FIX 9턴 | BE 결정, AI 범위 검사 | 모델이 번호·상태 확정 불가 | AI-L02 첫 질문 전 값 표현 |
| `depth` | BE가 검증·확정한 질문 깊이 | C/J: Proposed | BE 확정 | 기존 질문 관계, 공개 확장 없음 | AI-L02 타입·범위·미적용 표현 |
| `parent_turn_no` | 후속 목적의 기존 질문 번호, 부모 없으면 null | C/J: Proposed | AI 연결 제안, BE 확정 | 원문·최초 분석 덮어쓰기 없음 | AI-L02 저장·참조 방식 |

등록 ID·Persona·quota·범위는 모델 호출 전에 코드로 확인하고, 출력의 참조도 다시 검사한다. BE는 호출 시작과 수용 직전에 현재 상태·입력 일치를 재확인해 종료 후 결과를 차단한다. 위 문맥만으로 재연결·중복·stale 방지가 완성됐다고 주장하지 않으며 CAS 등 세부는 BE 계약에 남긴다.

## 5. AnswerAnalysis

입력은 확정 Question/Contract, 제출 답변 원문, 관련 과거 문답과 BE가 검증한 근거다. 평가 가능 여부를 먼저 판정한 뒤 관찰 가능한 축만 평가한다. `evaluated`는 모든 축이 확정됐다는 뜻이 아니다. 코드 자료가 부족해도 충분성은 판단할 수 있다.

| 필드 | 제안 타입·검사 | 근거·상태 | 소유자(AI/BE) | 저장·공개 영향 | 남은 미결정 |
| --- | --- | --- | --- | --- | --- |
| `evaluation_status` | `evaluated`, `needs_clarification`, `not_evaluable` 중 하나 | C: Proposed; A/R4: Accepted 의미 | AI 판정, BE 수용 | 내부 판정; 서비스 상태·WS 아님 | AI-L02·09 상태 조건·복구 |
| `sufficiency` | `sufficient`, `partial`, `insufficient`; 이 축 평가 불가일 때만 null | C: Proposed; R4: Accepted 의미 | AI | 내부 정성값; 점수 환산 없음 | AI-L02 null·상태 조합 |
| `covered_points` | Contract key와 실제 답변 구절의 목록 | C: Proposed; R4: Accepted 근거 | AI 원문 대조, BE 보존 | 원 답변 연결, 비공개 | AI-L02 부분 충족 표현 |
| `covered_points[].key` | 현재 Contract의 등록 key, 중복 금지 | C: Proposed | AI 참조 검사 | 다른 질문 key 사용 금지 | AI-L02 참조 타입 |
| `covered_points[].answer_quotes` | 제출 원문의 실제 구절 목록, 1개 이상 | C/A: Proposed 표현 | AI 인용 검사 | 모델 요약과 원문 구분 | AI-L02 인용 위치 표현 |
| `missing_points` | 현재 Contract에서 미확인인 key 목록 | C: Proposed; R4: Accepted 범위 | AI | 묻지 않은 내용 추가 금지 | AI-L02 부분 충족·누락 표현 |
| `technical_assessment` | 조건·버전·검토 설명·오류·보류 이유를 담은 구조 | C: Proposed; R4: Accepted 축 분리 | AI 판단, BE 보존 | 공개 점수 아님 | AI-L02 하위 구조 채택 |
| `technical_assessment.explanation` | 검토한 주장과 조건에 대한 비어 있지 않은 설명 | A/R4: Accepted 의미; 필드 Proposed | AI | 내부 서술, 수치·새 enum 없음 | AI-L02 문구·길이 |
| `technical_assessment.answer_quotes` | 검토 대상 답변 원문 구절 목록 | C/A: Proposed 표현 | AI 원문 대조 | 판단과 원문 연결 | AI-L02 위치 표현 |
| `technical_assessment.evidence_refs` | 유효한 근거 참조 목록; 없으면 빈 목록 | C/E: Proposed 표현 | AI 대조, BE 검증 | BE evaluation_basis 연결 | AI-L02 참조·저장 |
| `technical_assessment.limitations` | 조건·자료 부족 및 판단 보류 이유 목록 | C/A/R4: Proposed 표현·Accepted 의미 | AI | 보류를 오류로 변환하지 않음 | AI-L02 축별 한계 표현 |
| `contribution_scope` | `self`, `shared`, `teammate`, `unknown`; 진술된 범위 | C: Proposed; R4: Accepted 의미 | AI 판정 | 코드 존재만으로 개인 기여 확정 금지 | AI-L02 진술·확인 구조 |
| `contribution_quotes` | 기여 판단에 사용한 답변 구절 목록 | A/R4: Accepted 근거; 필드 Proposed | AI 원문 대조 | 후속 정정과 원문을 BE 보존 | AI-L02·18 이력 연결 |
| `claim_checks` | 주장 원문·지지 상태·근거·한계 목록 | C: Proposed; R3/R4: Accepted 의미 | AI 후보, BE 관계 검증 | 문서 Claim row 생성 없음 | AI-L02·18 저장·원문 |
| `claim_checks[].claim_text` | 제출 답변에서 확인한 실제 주장 구절 | C/E: Proposed 표현 | AI 원문 대조 | 답변 주장 원문 연결 | AI-L02 위치 표현 |
| `claim_checks[].status` | `supported`, `partially_supported`, `unverified`, `conflicting` | C: Proposed; R3: Accepted 의미 | AI 판단, BE 수용 | Tool 상태·공개 enum과 별개 | AI-L02 실제 enum 채택 |
| `claim_checks[].evidence_refs` | 현재 선택 repo·고정 ref의 관련 Evidence 참조 목록 | C/E: Proposed 표현 | AI 대조, BE 권한 검사 | 실제 불일치는 BE conflict 후보 | AI-L02 durable 참조 |
| `claim_checks[].limitations` | 미조회·미발견·분석 부족·장애·확인 범위 설명 목록 | C/E/R3: Proposed 표현·Accepted 의미 | AI | 미발견·장애를 허위 주장으로 변환 금지 | AI-L02 ToolResult 대응 |
| `needs_verification` | bool, R3의 세 조건이 모두 참일 때만 true | C: Proposed; R3: Accepted 의미 | AI 제안, BE 실행 허용 | Tool 직접 실행·자동 감점 없음 | AI-L02 요청 정합성 |
| `verification_requests` | 주장·목적·선택 repo·고정 ref·허용 위치의 요청 목록 | C/E: Proposed; R3: Accepted 범위 | AI 제안, BE I/O | 별도 Tool 계약 참조, 공개 안 함 | AI-L02·04·08 요청 구조·상한 |
| `limitations` | 입력·질문 오류, 미평가 및 축별 보류의 설명 목록 | C/A: Proposed 표현; R4: Accepted | AI 반환, BE 보존 | 복구 상태 확정 아님 | AI-L02·09·18 저장·복구 |

전체 평가 불가이면 `sufficiency=null`과 이유를 남기고 확인 불가능한 missing 항목을 만들어내지 않는 안을 제안한다. `needs_clarification`은 평가를 위해 해석 확인이 필요한 경우, `not_evaluable`은 현재 질문/입력으로 평가 근거를 만들 수 없는 경우로 구분하되 재입력을 실행하는 권한은 부여하지 않는다. 축별 보류와 세부 상태 조합은 AI-L02 검토 대상이다.

`covered_points`와 `missing_points`는 실제 요구사항을 기준으로 한다. 항목 일부만 확인되면 같은 key의 관찰 구절과 남은 범위를 함께 설명할 표현이 필요하며 채택 전 임의 분할·추측으로 메우지 않는다. 완전 확인 항목을 missing으로 중복 판정하지 않는다. 정상 “모르겠습니다”는 충분성 판단의 입력이지만 거짓·기술 오류가 아니다. 기여 발언이 없으면 `unknown`과 한계를 남기며 답변 길이·전문용어 수를 기준으로 쓰지 않는다.

## 6. DirectorDecision과 실패·후보 복구

| 필드 | 제안 타입·검사 | 근거·상태 | 소유자(AI/BE) | 저장·공개 영향 | 남은 미결정 |
| --- | --- | --- | --- | --- | --- |
| `next_step` | C의 `ask`, `retrieve`, `finish` 후보 enum | C: Proposed; I: FIX 종료 제한 | AI 제안, BE 확정 | WS 이벤트·DB 상태 추가 없음 | AI-L02 union·필수 조합 |
| `intent` | 보완·심화·전환·확인의 목적 설명, 비어 있지 않은 문자열 | C: Proposed | AI | 내부 판단; 새 enum 아님 | AI-L02 표현·저장 |
| `persona` | ask에 필수인 허용 FIX Persona; 그 외 null 제안 | C: Proposed; S: FIX 값 | AI 후보, BE 최종 검사 | 기존 질문 Persona와 일치 | AI-L02 null 조합 |
| `target` | 주제·질문 목적·현재 답변과의 연결 설명 | C: Proposed; I/R8: Accepted 의미 | AI | 원문/후속 목적 연결 | AI-L02 finish 미적용 표현 |
| `tool_requests` | retrieve일 때 1개 이상, 그 외 빈 목록 제안 | C/E: Proposed; R3/R8: Accepted | AI 제안, BE 실행 | 턴 수 증가·권한 확대 없음 | AI-L02·04·08 Tool 계약 |
| `reason_summary` | 짧은 결정 근거 문자열 | C: Proposed | AI | 숨은 사고과정 저장·공개 금지 | AI-L02·18 길이·보존 |

`ask` 결정과 검증된 Question을 한 결과로 연결하되 Persona·목적·입력 문맥이 일치해야 한다. `retrieve`는 조회 결과의 해석까지 질문 발행 성공이 아니며 `finish`는 BE가 종료 조건을 이미 확인한 경우만 허용한다. 성공 결과 포장·실패 union·Protocol signature와 schema version은 AI-L02의 잔여 결정으로 남긴다.

| 분류·후보 필드 | 판정과 처리 | 근거·상태 | 소유자(AI/BE) | 저장·공개 영향 | 남은 미결정 |
| --- | --- | --- | --- | --- | --- |
| 실패의 `stage` | `parse`: JSON으로 읽을 수 없음; `schema`: 타입·필수값·null·허용 enum 등 구조 위반; `semantic`: 등록되지 않은 참조·허용 Persona·근거·목적·범위 위반 | R8: Accepted 의미; 필드·문자열 Proposed | AI 분류, BE flow 매핑 | 성공 객체와 분리, 공개 enum 아님 | AI-L02 failure 형태 |
| 실패의 `reason_summary` | 실제 실패 원인을 원문 노출 없이 요약 | C/R8: Proposed 표현 | AI 반환, BE 보존 | 사용자 감점·빈 성공 변환 없음 | AI-L02·18 원문·metadata 분리 |
| 복구의 `recovery` | `rewrite`, `replan`, `no_valid_candidate`의 아래 의미 분류 | R8: Accepted 의미; 필드·문자열 Proposed | AI 후보 분류, BE 실행 결정 | `next_step`·정상 종료·WS enum에 추가하지 않음 | AI-L02·04·09 반환·실행 |

검증은 계약·정책 → 전제 타당성 → 현재 맥락 → 표현 → Contract 일치 순서다. raw output은 비신뢰 원문으로만 다루고 parse·schema·semantic 검증을 모두 거친 결과와 분리한다. 기본값·누락값 보충·임시 JSON repair로 성공시키지 않는다. 타입 변환으로 잘못된 null/enum을 숨기지 않는다.

| 복구 의미 | 조건 | 반환과 금지 |
| --- | --- | --- |
| `rewrite` | 전제·목적·필수 확인내용은 유효하고 표현만 복합적·유도적 | 의미 보존 수정 후보; 목적 변경 금지 |
| `replan` | 거짓·stale 전제, 잘못된 목적, 이미 확인한 목적 반복 | 목적·근거를 다시 세울 필요 반환; invalid 질문 발행 금지 |
| `no_valid_candidate` | 공급된 Persona·맥락·근거·범위에서 안전한 후보 없음 또는 허용 budget 내 유효 후보 확보 실패 | 질문 없는 실패 반환; fallback·정상 finish로 위장 금지 |

분류는 실행 권한이 아니다. R10에 따라 timeout/provider/parse/schema 실패는 공통 호출 계층에서 자동 1회 재호출하여 총 2회까지이며 semantic 실패는 재호출 없이 fail-closed다. semantic 오류를 rewrite/replan으로 이름만 바꿔 자동 재호출하지 않는다. R8 복구 후보를 실제 실행하는 loop·상한·상태 매핑은 AI-L04·09 합의 전 보류한다. SDK/provider 중복 retry는 차단하고 ARQ `max_tries=1`은 BE가 소유한다.

## 7. Python 표현 선택과 의존성 영향

| 후보 | 장점 | 비용·주의점 | 제안 |
| --- | --- | --- | --- |
| 표준 라이브러리 dataclass + 명시적 검증 함수 | 현재 runtime 무의존 유지, BE·provider와 분리 | dataclass 자체는 입력 schema 검증기가 아님; 누락·null·enum·알 수 없는 필드·참조를 직접 검사해야 함 | 채택 권고, 승인 전 구현 금지 |
| Pydantic 모델 | 구조 검사·오류 표현을 모델로 관리 가능 | AI runtime 의존성 추가와 lock 갱신 필요; 암묵 변환을 막고 의미·권한 검사는 별도 구현해야 함 | 대안, 현재 의존성에 추가하지 않음 |

dataclass 안은 불변 결과와 불변 컬렉션을 사용하고, 모델 raw 입력을 직접 성공 객체 생성자에 넣지 않는 검증 경계를 함께 채택하는 조건이다. 구조 통과 후보와 의미 검증 완료 결과를 구분하며 type hint나 frozen 설정만으로 검증 완료를 주장하지 않는다. 입력 schema·범위 검증은 DB/네트워크 없이 수행한다.

현재 `ai/pyproject.toml`의 `dependencies=[]`를 유지하며 `typing.Protocol`, dataclass 사용에 외부 SDK가 필요하지 않다. 문서 단계에서는 pyproject와 `uv.lock` 변경이 없다. 승인 후 Pydantic 안으로 바뀌면 의존성 변경과 `uv --directory ai lock` 결과를 별도 보고한다. schema version의 값·호환/이행 정책은 BE 저장 계약과 함께 정하고 임의의 운영 version 기본값을 넣지 않는다.

## 8. 승인 후 작성할 검증 사례 — 현재 미실행

코드 단계는 정상 1건·실패 1건의 테스트를 먼저 작성한 후 구현한다. 아래는 문서상의 기대 결과이며 실행 가능한 테스트나 실제 모델 평가를 만들었다는 뜻이 아니다.

| 사례 | 기대 결과 |
| --- | --- |
| 정상 질문·평가 | 실제 질문이 조회·수정 특성과 캐시 선정 이유를 요구함. “조회가 많아서 DB 부하를 줄이려고 캐시했습니다”는 `partial`; 조회 특성·선정 목적 확인, 수정 특성 미확인 |
| 실패: 묻지 않은 기준 | 위 답변의 `missing_points`에 TTL을 추가하거나 감점 이유로 사용하면 semantic 실패 |
| 실패: 목적 변경 | 수정 특성 확인 목적에서 “TTL은 몇 분인가요?”를 후보로 내면 전달 차단; 목적을 바꾼 문장을 표현 수정 성공으로 처리하지 않음 |
| 계약 정상/실패 | 필수값·null·enum·중복 참조·미등록 참조·조작 ID·raw/검증 결과 혼용을 각각 검사; 모델 생성 ID를 신뢰하지 않음 |
| A의 대조 1 | 같은 질문의 충분·부분·불충분 답변을 Contract와 실제 구절에 연결 |
| A의 대조 2 | 길고 틀린 답변과 짧고 맞는 답변의 충분성·정확성 분리 |
| A의 대조 3 | 질문하지 않은 항목은 missing_points에 없음 |
| A의 대조 4 | 팀원 구현을 본인 구현으로 가정하지 않음; 역할 질문에 “팀원이 했습니다”는 역할 정보 확인, 잘못된 직접 구현 전제라면 전제 정정으로 별도 검사 |
| A의 대조 5 | 유사하지만 무관한 코드·다른 ref를 지지 근거에서 제외 |
| A의 대조 6 | 도구 실패를 허위 주장·감점으로 변환하지 않음 |
| A의 대조 7 | 질문 오류·해석 불가와 실제 설명 부족·정상 “모르겠습니다”를 구분 |
| A의 대조 8 | 후속 보완을 이후 질문·최종 피드백에 연결하고 최초 답변·최초 분석 보존 |
| 후보 실패/복구 | parse/schema/semantic 및 세 복구 의미 대조; fake 호출 수 총 2회 제한·semantic 재호출 0회 |
| 턴·Persona | 첫 HR, 9번째 답변 후 종료, quota 불가능 후보 제외, 10번째 질문 없음; 질문·답변 완료 수 구분 |
| 경계·보류 | BE 종료 후 결과 차단은 통합 검사 대상; 사용자 정정에 따른 입력 복구·재평가는 AI-L09 보류로 기록 |

quota 검사 시 후보를 현재 Persona 횟수에 1회 더한 뒤, 남은 질문 수보다 기술 최소 5회까지 부족분과 HR+domain 합산 최소 3회까지 부족분의 합이 크면 제외한다. 가능한 후보에서 기술 목표 6회와 답변 맥락을 고려한다. 계산식은 I의 실행 제안을 따르며 새 개별 quota를 만들지 않는다.

## 9. 차이 기록과 보류

- **제안: 근거 정정.** 전달된 구현 규칙은 재시도를 ADR 0004 확정사항으로 표현하지만 실제 승인 출처는 R10 「LLM attempt와 worker retry」 및 C·task-03이다. 동작 요구는 일치하며 R4를 재시도 승인 근거로 인용하지 않는다.
- **제안: 구현 근거 구분.** 기준 `develop`에는 `frontend/src/shared/persona.ts`가 없고 `backend/app/db/models/interview.py`의 Persona CHECK는 주석 골격이다. FIX enum의 근거는 S/I로 유지하며 FE 라벨·아바타나 실제 DB 제약 실행을 검증했다고 보고하지 않는다.
- **보류: 공유 문서 정렬.** OpenAPI의 `x-pending`·점수 설명에는 R10/이관표와 다른 과거 보류 표현이 남아 있다. 이번 문서는 명시적인 후속 결정 범위만 참조하고 공유 계약·FE·BE 파일을 자동 변경하지 않는다. 점수 구현은 이번 범위 밖이다.

| 항목 | 상태·남은 결정 | 이번 문서의 경계 |
| --- | --- | --- |
| AI-L01 provider | 보류: 실제 공급자·API model ID·인증·기능 검증 | 주입 Protocol과 fake 방향만, 구체 SDK 없음 |
| AI-L02 계약 채택 | 보류: 표의 필드·null·참조·결과 union·Protocol·schema version·호환 정책·JSONB 위치 | 검토자는 AI·BE, 공개 영향 시 FE; 이 문서 승인을 전체 저장·API 승인으로 확대하지 않음 |
| AI-L04 실행 상한 | 보류: timeout·입력/token·Context·동시성·Tool·재작성·재계획 budget·소진 처리 | R10의 총 2회·semantic 재호출 금지는 확정, 운영 상한을 임의 생성하지 않음 |
| AI-L09 사용자 입력 복구·턴 배분 | 보류: 재입력·재평가·복구 상태와 반환 매핑, HR/domain 개별 최소·교대 | 기존 9턴·기술 최소·비기술 합산 quota와 R8 의미만 유지 |
| AI-L10 운영 설정 | 보류: Persona/prompt/frame 운영 문구·검수·활성 version·저장 연결 | BE 원본 주입, 개발용 후보를 운영 seed로 채택하지 않음 |
| AI-L18 원문 운영 | 보류: raw output·답변·최초 분석·정정·metadata 위치·권한·보존 | 일반 로그 출력·새 이력 테이블로 대체하지 않음 |
| AI-L21 음성 | 보류: Sprint 2 음성 전체 | Persona voice 키, 컬럼·설정·WS 이벤트·모듈 선행 생성 없음 |

문서 검토 후 승인된 정확한 범위를 기록하고 해당 항목에서 멈춘다. 커밋은 사용자 확인 후에만 하며 1번 내부 계약 구현, push, PR 생성은 현재 승인 범위에 포함하지 않는다.

## 10. 이번 문서 작업의 실행 검증

2026-09-21 실행. uv의 캐시·Python 설치 경로는 기존 testing 안내처럼 저장소의 `.claude/scratch/uv-cache`, `.claude/scratch/python`으로 지정했다. 패키지 의존성 선언·lock 변경 없이 Python 3.12.13과 기존 lock의 환경을 복구했다.

| 명령·검사 | 상태·실제 결과 |
| --- | --- |
| `uv --directory ai sync --locked --python 3.12` | 통과. 최초 기본 캐시 접근·다운로드는 실패했으며 저장소 내부 경로 지정과 샌드박스 밖 실행 후 성공 |
| `uv --directory ai run --locked ruff check .` | 통과 |
| `uv --directory ai run --locked ruff format --check .` | 통과, 32개 파일 |
| `uv --directory ai run --locked mypy src` | 통과, 소스 11개 |
| `uv --directory ai run --locked pytest` | 최초 실패: 25개 통과·임시 폴더 권한 오류 1개. 코드 변경 없이 동일 명령을 샌드박스 밖에서 재실행하여 26개 통과 |
| `python .claude/scripts/check_contracts.py` | 미실행: 전역 python 명령 없음. AI 가상환경 직접 실행도 검사 의존성 누락으로 진행 불가 |
| `uv run --no-project --python 3.12 --with-requirements .claude/scripts/requirements-checks.txt python .claude/scripts/check_contracts.py` | 통과: 별도 임시 환경, 스키마 2개·부분 OpenAPI·정상/실패 fixture 7개. runtime·전체 API 호환성 검증 아님 |
| 문서 정적 검사·`git diff --check` | 통과: Persona 표 원문 일치, 상대 링크 28개 존재, 표 열 수·후행 공백, 300줄 이내 |
| `git diff --exit-code develop -- ai frontend backend CLAUDE.md CODEOWNERS .github/workflows` | 통과: 코드·테스트·의존성·보호 파일 변경 없음 |
| 이번 계약·기능의 새 테스트, 실제 모델·DB·WS 통합 | 미실행. 위 pytest는 기존 패키지 구조·import 경계 검사에 한정 |
| AI-L02 채택, AI-L01·04·09·10·18·21 잔여 항목 | 보류. FE/BE 구현·음성·점수 구현·배포는 범위 밖 |
