# AI 명세 원본 감사

검토일: 2026-09-12.

검토 기준: `feature/spec-ai-docs`, `8dabd55`.
상태: 기준선 감사 완료. 세부 설계는 각 문서의 상태를 따른다.

이 문서는 AI 구현 명세가 어떤 원본을 따라야 하는지와 현재 자료 사이의 충돌을 기록한다. 원본 문서를 대체하지 않으며, 미합의 항목을 확정하지 않는다.

## 원본 우선순위

1. 사용자의 현재 지시와 승인 범위.
2. [공통 계약](../shared/contracts/README.md), [계약 이관표](../shared/contracts/migration.md), `openapi.yaml`에 명시된 `FIX` 계약.
3. [공통 용어](../shared/glossary.md)와 Sprint 1 `FIX` 상태의 기능·아키텍처 문서.
4. [기획 변경·확정 Report](../../report.md)의 확정 항목.
5. Sprint 1 `FIX` 명세가 명시적으로 연결한 `backend/docs/*` 구현 체크리스트와 운영 가이드. 상위 계약을 바꾸지는 못하지만 구현 순서와 상세 경계를 함께 확인한다.
6. `PENDING_FE`, `PENDING_AI`, `PENDING_TEAM` 항목. 결정되기 전에는 구현값을 만들지 않는다.
7. `context/*` 회의 기록과 검토 초안. 승인된 기준과 일치하는 배경 설명만 참고하고, 차이는 변경 제안으로 다룬다.
8. 이관 전 `frontend/docs/*`, README, 현재 타입과 코드 스켈레톤. 최신 FIX 명세와 일치할 때만 구현 상태 참고자료로 사용한다.

[루트 작업 지침](../../CLAUDE.md)은 서비스 요구사항과 계약의 원본을 `spec/`으로 지정한다. [spec 안내](../README.md)는 이관이 끝나지 않은 문서 전체를 최종 구현 기준으로 간주하지 말라고 경고한다. 이 일반 경고는 최신 계약 이관표의 항목별 `FIX`를 무효화하지 않는다. 이 감사에서는 사용자가 `report.md`와 명시적 `FIX` 명세를 기준선으로 승인했고, 작업 트리의 `context/AI.md` 차이는 변경 제안으로 분류했다.

## 검토한 원본

| 원본 | 확인 위치 | 적용 방식 |
| --- | --- | --- |
| 루트·팀 지침 | `CLAUDE.md`, `ai/CLAUDE.md`, `backend/CLAUDE.md` | 문서 라우팅과 구현 경계 |
| 공통 명세 | `spec/README.md`, `spec/shared/glossary.md`, `spec/shared/contracts/*` | 용어, API, 상태, 보류 항목 |
| 고정 기능 명세 | `spec/backend/architecture.md`, `features/interview.md`, `features/report.md`, `features/analysis-run.md`, `features/documents.md` | Sprint 1 동작 기준 |
| AI 기존 명세 | `spec/ai/architecture.md`, `features/interviewer.md`, `verification.md` | 보완 대상인 기존 초안 |
| 확정·검토 기록 | `report.md`, `ForAI.md` | 최신 확정과 AI 결정 대기 항목 |
| 기획 배경 | `context/AI.md`의 HEAD 원본과 작업 트리 diff, `context/FE.md`, `context/BE.md`, `context/DB.md` | 원래 비전, 과거 계약·스키마와 변경 제안 추적 |
| FE 명세·현 상태 | `spec/frontend/features/analysis.md`, `features/interview.md`, `features/report.md`, `frontend/docs/api-spec.md`, `frontend/src/types/api.ts`, `frontend/src/shared/api.ts` | 소비자 요구와 현재 타입·호출 drift 확인 |
| 구현 안내·스켈레톤 | `backend/docs/pipeline.md`, `backend/docs/task-*.md`, `backend/app/agents`, `backend/app/llm_tasks`, `backend/app/workers` | FIX 구현 상세와 현재 구현 준비 상태 비교 |
| 검증 도구 | `.claude/scripts/check_contracts.py`, `requirements-checks.txt`, 관련 script tests | 검증 가능 범위와 도구 자체 제한 확인 |

검토 당시 `context/AI.md`는 `+653/-182`의 미커밋 변경이 있었다. 이 파일은 수정하지 않았다.

## 기준선으로 고정된 내용

### 핵심 범위와 전송

- Sprint 1은 W4~W7의 텍스트 면접이다. 음성, STT, TTS는 Sprint 2다 (`report.md:5-17`, `migration.md:12-13`).
- 답변은 양방향 텍스트 WebSocket의 `{ "type": "answer", "text": "..." }`로 전달한다. 서버 이벤트는 `answerReceived`, `thinking`, `evidenceCheck`, `question`, `interviewEnd`, `error`다 (`interview.md:46-68`).
- Public repository와 Wanted 공고만 지원한다. 선택 repository는 1~5개이며 current run, accessible, eligible, L1 성공 조건을 만족해야 한다 (`analysis-run.md:71-80`, `interview.md:5-19`).
- Sprint 1 문서 preview는 PDF, DOCX, TXT, MD의 텍스트와 GitHub URL을 보조 신호로 추출한다. Claim row 생성과 Claim 기반 면접은 Sprint 2다 (`documents.md:3-29`).

### 면접관과 Director

- Persona enum은 `tech_lead`, `hr_manager`, `domain_lead`다 (`glossary.md:20-24`, `migration.md:19`, `openapi.yaml:458-460`).
- Persona는 독립 Agent가 아니라 Director가 취하는 질문 관점이다. Agent는 Director 하나이며 Evidence Retriever는 Director tool이다 (`glossary.md:14-16`, `backend/architecture.md:33-34`). 별도 `Strategist` Agent를 만들지 않는다.
- 기본 면접은 9턴이며 Sprint 1 Director 조기 종료는 없다. 첫 질문은 `hr_manager`, 2턴부터 Director가 Persona를 선택한다. `tech_lead`는 목표 6턴·최소 5턴이고 `domain_lead + hr_manager`는 합산 최소 3턴이다 (`interview.md:70-80`).
- `domain_lead`는 JD 요구사항 질문자가 아니라 산업·서비스 관점의 질문자다. 7개 domain category마다 기본 question frame 3개를 seed하고 코드에 하드코딩하지 않는다 (`interview.md:82-98`).

### 모델, 근거, 리포트

- Sprint 1의 모든 LLM 작업은 설정·seed에서 읽는 `5.5 Luna` 기준선으로 실행한다. 코드 상수로 고정하지 않고 실제 모델 문자열, prompt version, token, latency를 기록한다 (`backend/architecture.md:12-17`, `report.md:523-545`).
- JSON 구조화 출력 파싱 실패는 자동 1회 재시도한 뒤 실패 처리한다. 깨진 JSON을 복구해 downstream에 전달하지 않는다 (`report.md:551-563`, `ForAI.md:38-47`).
- `question_basis`와 `evaluation_basis`를 구분한다. `tech_lead` 질문에는 가능한 한 질문 근거를 연결하고, 답변의 검증 가능한 주장은 제한된 Evidence Retriever로 후속 확인한다 (`interview.md:100-117`).
- 리포트는 lazy generation이고 Persona별 피드백은 `interview_reports.feedback_json`에 둔다. 성공 후 profile summary job을 enqueue하며 Sprint 1 summary는 완료 면접에 사용된 repository의 단순 집계가 중심이다 (`report.md`가 아닌 `spec/backend/features/report.md:5-27,35-43`).

## 충돌과 판정

| 주제 | 기존·제안 내용 | 기준선 판정 |
| --- | --- | --- |
| Persona | 작업 트리 `context/AI.md:124-136,725-727`은 Manager, Senior Developer, Tech Lead를 사용한다. | FIX enum인 `hr_manager`, `domain_lead`, `tech_lead`를 사용한다. Senior Developer는 승인된 Persona가 아니다. |
| 통신 | `context/AI.md:191-215`는 HTTPS 답변 제출과 SSE 알림을 제안한다. | Sprint 1 면접 문답은 텍스트 WebSocket이다. SSE 전환은 별도 계약 변경 없이는 구현하지 않는다. |
| 종료 전략 | `context/AI.md:409-434`는 `END_TOPIC`, `END_INTERVIEW`와 적응형 종료를 설명한다. | Sprint 1은 9턴 고정이고 Director 조기 종료가 없다. 사용자 이탈·중단은 Director의 조기 종료 결정과 구분한다. 액션 이름도 아직 공통 enum으로 승인되지 않았다. |
| Domain | `context/AI.md:138-146,250-258`은 검수된 외부 Domain Knowledge Tool을 후속단계로 둔다. | Sprint 1의 `domain_lead` question frame은 FIX다. 외부 domain 자료/RAG tool은 별개의 Sprint 2 제안이며 공급원·스키마·수용기준이 미정이다. |
| 문서 | `context/AI.md:114-122`는 선택 문서와 Claim을 모두 후속단계로 묶는다. | Sprint 1에는 문서 preview와 GitHub URL 보조 신호가 있고 Claim 추출·활용만 Sprint 2다. |
| Profile summary | `context/AI.md` 통합안에는 Sprint 1 profile summary 계약이 명확하지 않다. | Sprint 1 DB와 report 후속 job에 포함한다. 다만 LLM 자연어 고도화는 Sprint 2다. |
| 모델 | 기존 `spec/ai/architecture.md:14`, `features/interviewer.md:12`는 모델이 미확정이라고 쓴다. | 최신 기준선은 `5.5 Luna`다. 단, 실제 provider/API model ID와 schema 생성 적합성은 검증이 남았다. |
| 음성 | HEAD의 `context/AI.md:249-251,295-301`은 Sprint 1 전체 음성면접을 포함했고, 작업 트리 문서는 W8~W9의 상세 TTS 목소리 연결을 제안한다. | 음성의 Sprint 2 이동만 FIX다. provider, voice ID, 전사 정정, 보존·재생, 텍스트 병행·전환은 미확정이다. |
| 평가·종료 | 작업 트리 `context/AI.md:383-451`은 정성 판정과 자율 행동을 상세히 제안한다. | 정성 판단은 후속 질문과 근거 연결의 설계 입력으로 사용할 수 있으나 공용 점수 공식이나 Sprint 1 조기 종료 규칙으로 승격하지 않는다. |
| 과거 스텁 | 기존 AI 명세와 일부 코드 파일은 제목·docstring 또는 빈 골격만 가진다. | 파일 존재나 과거 task 문구는 구현 완료·스키마 승인·모델 성능의 증거가 아니다. |

## 구현·계약 drift 스냅샷

다음은 검토 시점의 차이다. AI 구현 문서가 이 차이를 전제로 삼아서는 안 되며, 실제 구현 작업에서는 소유 팀과 계약을 먼저 맞춰야 한다.

| 영역 | 관찰한 차이 | 영향·판정 |
| --- | --- | --- |
| FE Persona 필드 | `frontend/src/types/api.ts:168-172,210-214`는 turn과 feedback에 `role`을 사용하지만 OpenAPI는 `persona`를 사용한다. | 현재 TypeScript 타입은 canonical contract와 다르다. AI 출력과 저장 계약은 `persona` 기준이며 FE 타입 이관이 필요하다. |
| FE 면접 프로토콜 | `frontend/src/types/api.ts:189-200`은 `answerStart`/`answerEnd`, `transcript`, `questionEnd`, `role` 질문을 선언한다. | 음성 시절 타입이다. Sprint 1의 단일 text `answer`와 `persona` 질문 계약으로 바뀌어야 한다. |
| 분석 요청 | `frontend/src/types/api.ts:93-100`과 `frontend/src/shared/api.ts:52-56`은 `jobUrl`, 파일 필드, `FormData`를 사용한다. OpenAPI `:44-60`은 JSON `postingUrl`과 optional `documentId`를 요구한다. | 현재 FE 호출은 canonical request와 호환되지 않는다. 파일은 `/documents/preview`에서 먼저 처리한다. |
| StepStatus | 현재 FE 타입은 `pending`, `running`, `completed`이고 `frontend/docs/api-spec.md:49`는 여기에 `failed`를 더한다. OpenAPI `:290-292`는 `pending`, `running`, `succeeded`, `failed`다. | 성공 상태 이름을 계약대로 통일해야 한다. 이벤트 표시용 별도 매핑이 필요하면 명시적 계약으로 정한다. |
| Interview snapshot | OpenAPI는 `preparing_failed` status를 포함하지만 `InterviewDetailResponse`에 FE 명세가 요구하는 `answerMode`, `lastError`가 없다 (`openapi.yaml:461-497`, `spec/frontend/features/interview.md:102-121`). 현재 FE 타입은 `preparing`과 `preparing_failed`도 누락한다 (`frontend/src/types/api.ts:4`). | 새로고침 복구와 Sprint 2 분기 요구가 canonical snapshot에 완전히 이관되지 않았다. AI가 누락 필드를 내부 출력으로 대신 만들지 않는다. |
| Prepare 순서 | FE 기능 명세는 `analyze_repo → build_persona → compose_question → set_criteria` 순서다 (`spec/frontend/features/interview.md:19-23`). BE 명세는 criteria를 구성한 뒤 첫 질문을 생성한다 (`spec/backend/features/interview.md:32-37`). | 질문 생성은 JD, domain category, 평가 기준에 의존하므로 `set_criteria`가 `compose_question`보다 먼저여야 한다. 화면 표시 순서도 계약 검토가 필요하다. |
| Report score | OpenAPI는 `totalScore`와 각 `score`를 필수 number로 둔다 (`openapi.yaml:507-529`). | 공식·스케일은 `PENDING_TEAM`이다. `0`, `null`, 임시 환산값을 채우는 것으로 불일치를 숨기지 않는다. |
| Worker 목록 | `backend/app/workers/arq_app.py:1-10` docstring은 `initial_sync`, `interview_prep`, `deep_analysis`, `report_generate` 4개를 적는다. Sprint 1 FIX pipeline은 `initial_sync`, `analysis_run`, `candidate_page_analyze`, `interview_prep`, `report_generate`, `profile_summary` 6개다 (`backend/docs/pipeline.md:1-20`). | 현재 worker docstring은 과거 snapshot이다. FIX 6개 작업과 enqueue 경계를 기준으로 registry·테스트를 구현해야 한다. |

## 구현·검증 준비 상태

- `backend/app/agents`, `backend/app/llm_tasks`, `backend/app/workers`의 Python 파일에는 검토 시점에 호출 가능한 함수나 class가 없고 docstring만 있다. 특히 `arq_app.py`에도 `WorkerSettings`가 없다.
- `backend/tests`에는 `conftest.py`와 빈 package `__init__.py` 4개만 있어 Agent, LLM task, worker 동작을 검증하는 테스트가 없다.
- `backend/uv.lock`이 없어 `pyproject.toml`의 의존성 버전이 고정되지 않았다. 문서의 `uv sync`, `uv run pytest` 예시는 실행 성공의 증거가 아니다.
- 따라서 현재 파일 배치는 목표 구조를 보여주는 스켈레톤이다. 실제 Luna 호출, Director tool loop, queue 등록, JSON 재시도, 저장·복구가 동작한다고 판단하지 않는다.

계약 검사 명령 `python .claude/scripts/check_contracts.py`도 검토 시점에는 필요한 검사 패키지가 없어 미실행으로 종료됐다. 도구에는 별도 결함도 있다. `openapi.yaml`은 일반 YAML 문법인데 checker와 `test_contract_refs.py`는 이를 `json.loads`로 읽고 JSON subset이라고 가정한다 (`check_contracts.py:49-51`). 의존성을 설치해도 현재 파일을 올바르게 파싱할 수 없으므로 YAML parser 또는 validator의 파일 로더가 필요하다. 이는 **검사 도구의 실패**이며, 문서 내용이 자동으로 유효하거나 무효하다는 판정은 아니다. `openapi-spec-validator` 부재, YAML 파서 결함, OpenAPI 의미 검증, FE/BE 구현 일치는 각각 따로 보고한다.

## 아직 결정하지 않은 내용

### `ForAI.md` 결정 지도

| 항목 | 상태 | 문서화·구현 제한 |
| --- | --- | --- |
| pgvector / embedding | `PENDING_AI` | extension, embedding model, dimension, chunk, 재색인, 저장소를 추측하지 않는다. Sprint 1 제한 검색은 vector 없이 동작해야 한다 (`ForAI.md:7-30`). |
| 구조화 출력 적합성 | 검증 필요 | Luna가 task별 schema를 안정적으로 생성하는지 실제 평가한다. `notable_areas`, answer claim 분리, Director persona/turn 출력을 우선 확인한다 (`ForAI.md:32-47`). |
| Domain frame 품질 | AI 검토 필요 | 7개 category와 3개 frame seed는 FIX지만 실제 문구, 중복 방지 guard, `etc` fallback 품질은 검수한다 (`ForAI.md:49-64`). |
| Evidence 범위 확장 | AI 검토 필요 | Sprint 1 검색 범위는 FIX다. full tree/global search 도입 시점과 `unverified` 기준은 별도 결정한다 (`ForAI.md:66-82`). |
| Report score | `PENDING_TEAM` | 0~100, 1~5, 가중치, 합산, 임계값을 정하지 않는다 (`ForAI.md:84-97`). |
| Sprint 2 모델·검색 | Sprint 2 재검토 | task별 모델 분리, 음성 provider, 고비용 task, vector 도입 효과를 측정 뒤 결정한다 (`ForAI.md:99-113`). |

### 계약상 주의할 미해결점

- `openapi.yaml:509-529`는 `totalScore`와 `scores[].score`를 필수 number로 요구하지만 공식과 스케일은 `PENDING_TEAM`이다. 임의의 `0`, `null`, 가짜 환산식을 넣지 않는다. 구현 전에 계약을 유지할 실제 산정 기준이나 nullable/status 전환 중 하나를 팀이 결정해야 한다.
- 현재 OpenAPI는 외부 API shape의 부분 이관본이다. Question Contract, 평가 세부 결과, DirectorDecision, evidence provenance 같은 내부 LLM JSON key를 승인하지 않는다. [내부 계약](contracts.md)의 Proposed 구조는 BE 저장·서비스 경계 검토 후 채택한다.
- `5.5 Luna`는 승인된 논리적 모델 기준선이지만 실제 provider와 호출 가능한 model identifier는 문서에서 확인되지 않았다. 이름을 임의 provider ID로 번역하지 않는다.
- 음성 원본 보존, 삭제, 다시 듣기, 전사 정정과 입력 채널 전환은 사용자 자료를 수집하기 전에 별도 결정해야 한다.

## 후속 문서 연결

- [AI 아키텍처](architecture.md): 기준선 구성요소와 책임
- [AI 내부 계약](contracts.md): Proposed LLM task 입출력과 오류 경계
- [AI 검증](verification.md): mock 단위시험과 실제 모델 평가의 구분
- [AI 기준선 결정](decisions/0001-ai-baseline.md): 이번 감사에서 채택한 기준선과 변경 절차
