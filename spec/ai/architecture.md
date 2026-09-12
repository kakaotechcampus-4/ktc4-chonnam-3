# AI 기능 아키텍처

작성일: 2026-09-12. 기준: `report.md`와 Sprint 1 FIX 명세.

이 문서는 서비스 AI의 책임·연결·개발 범위를 정의한다. 기존 확정사항을 정리하고, 상세 내부 설계는 Proposed로 구분한다. 현재 코드가 이 구조로 실행된다는 의미는 아니다. Claude 작업 진입점은 [ai/README.md](../../ai/README.md)다.

코드 배치는 [승인된 패키지 설계](designs/2026-09-12-ai-package-structure.md)를 따른다. AI 소스 원본은 `ai/src/devon_ai/`이며 기존 BE API·worker가 로컬 패키지를 import한다. 별도 AI 서버는 없고, 내부 입력·출력 계약의 Proposed 상태는 바뀌지 않는다.

## 문서 지도

| 문서 | 다루는 내용 |
| --- | --- |
| [원본 검토](source-audit.md) | context·ForAI·report·FE/BE/DB·스켈레톤 간 충돌과 적용 기준 |
| [기준 결정](decisions/0001-ai-baseline.md) | FIX 유지와 승인 범위 |
| [Sprint 1 vector 미도입](decisions/0002-sprint1-vector-search.md) | AI-L20의 승인 범위, BE 전달사항과 후속 보류 |
| [의사결정 대기 목록](../../later.md) | 미결정 항목의 통합 목록, 영향과 결정 시점 |
| [내부 계약](contracts.md) | 데이터 소유권, LLM 출력 제안, 검증·재시도 |
| [레포 분석·추천](features/repository-analysis.md) | L0/L1/L2, Wanted, 추천, 캐시, 부분 실패 |
| [작업·면접 Context](features/job-context.md) | ARQ 입력, 준비 자료, 판단 입력 구성 |
| [면접 진행](features/interviewer.md) | 단일 Director, Persona, 9턴, 질문 검증 |
| [답변 평가](features/answer-evaluation.md) | 평가 범위, 충분성·정확성·기여, 보류 |
| [근거 검색](features/evidence-retrieval.md) | 검색 범위, 출처, answer_vs_code |
| [도메인 프레임](features/domain-frames.md) | Sprint 1 seed 후보와 역할 제한 |
| [리포트·프로필](features/report-profile.md) | lazy 생성, 피드백, 점수 보류 |
| [후속 기능](features/extensions.md) | 음성·Claim·도메인 자료·이미지 |
| [검증](verification.md) | 계약·상태·모델 평가·완료 판단 |

## 기준과 범위

- Sprint 1은 Public GitHub 레포와 Wanted 공고를 사용하는 텍스트 면접이다.
- Agent는 Director 하나다. `tech_lead`, `hr_manager`, `domain_lead`는 Director의 질문 관점이며 독립 Agent가 아니다.
- 면접 답변은 양방향 텍스트 WebSocket, 분석 진행 알림은 SSE다. 기존 계약에 없는 답변 POST나 면접 SSE를 추가하지 않는다.
- 기본 9턴을 완료하면 종료한다. Director의 자율 조기 종료는 Sprint 1에 없다.
- Sprint 1 모델 선택 표기는 `5.5 Luna`다. provider·실제 API model ID·구조화 출력 성능은 별도 확인사항이다.
- Sprint 1 embedding/vector 검색과 pgvector extension 선설치는 [0002 결정](decisions/0002-sprint1-vector-search.md)에 따라 미도입이다. BE 반영 확인과 Sprint 2 도입 여부·세부 설계는 별도 대기이며, 공개 리포트 점수 공식·저장 스케일은 `PENDING_TEAM`이다.
- 선택 문서 preview와 GitHub URL 추출은 Sprint 1에 있다. 문서 Claim·STT/TTS·이미지 공고 판독은 후속이다.

수정 중인 `context/AI.md`의 세 역할 재구성, HTTPS/SSE 면접, 조기 종료, 별도 면접 Worker는 [검토 기록](source-audit.md)의 변경 제안으로 남긴다. 이를 기존 API와 혼합하지 않는다.

## 현재 구현 상태

확인 기준 커밋은 `8dabd55`이며, 확인 당시 `backend/app/`의 AI 관련 모듈·주요 BE 모듈은 비어 있거나 모듈 주석만 있었다. `agents/contracts.py`에도 실제 계약 클래스는 없다. worker 등록, ORM, migration, seed, 테스트 fixture가 동작한다고 가정하지 않는다.

이후 설치 가능한 `devon_ai` 골격과 `ai/tests`의 구조 검사를 추가했다. AI 모듈은 여전히 docstring만 있으며 실제 계약 클래스·Director·task 함수는 없다. 기존 BE의 AI 파일은 향후 연결 계층 안내로 남는다. 현재 검사 결과는 [검증 기록](verification.md)을 따른다.

FE의 면접·분석·리포트 화면도 구현 검증 근거가 없고, 기존 타입에는 음성 계약 흔적이 있다. 세부 근거는 [원본 검토](source-audit.md)를 따른다. 문서의 FIX는 요구사항 상태이지 구현 상태가 아니다.

## 책임과 의존 방향

```text
FE -- REST / analysis SSE / interview text WS --> FastAPI router
router --> service / pipeline --> queries --> PostgreSQL
                          |--> prompt_loader --> prompt_versions
                          |--> BE AI 연결 --> devon_ai LLM tasks
                          |--> BE AI 연결 --> devon_ai Director
                          |                  (주입된 model / Evidence 도구)
                          |--> Redis snapshot / realtime notification
ARQ worker --> service / pipeline
```

| 영역 | 책임 | 넘기지 않을 책임 |
| --- | --- | --- |
| router / WS handler | 인증·입력 검증, 현재 연결과 service 연결 | 모델에 권한 판정을 맡기지 않음 |
| service / Controller | transaction, 현재 Turn 확인, 제한 강제, 상태 확정·저장·알림 | 새로운 Persona/점수 정책 결정 |
| queries | 사용자·run·session 범위의 DB 조회 | 질문 전략 |
| pipeline | 수집·분석·준비·리포트의 순서와 실패 처리 | 사람 답변을 기다리는 장기 작업 |
| Director | 허용 후보 중 다음 관점·주제·후속 목적 선택, 필요한 Tool 요청 | DB commit, 권한 확대, 9턴 정책 변경 |
| 일반 LLM task | 정해진 입력에 대한 단발 구조화 결과 | 큐·DB·WS 상태 변경 |
| integrations | GitHub·Wanted·LLM의 외부 I/O | DB 모델 의존 |
| prompt_loader | DB의 prompt/version/config 로드 | Agent 내부에서 DB 세션 사용 |

구현 경로는 [패키지 설계](designs/2026-09-12-ai-package-structure.md)와 [레이어 규칙](../../backend/docs/layer-rules.md)을 따른다. BE에 남는 `prompt_loader`만 기존 LLM task 영역에서 DB 세션을 받을 수 있고, service는 AI 패키지의 Director·일반 task에 로드한 문자열과 검증된 데이터만 주입한다. 실제 I/O·권한·상태·저장은 BE 책임이며 AI는 `app.*`를 역으로 import하지 않는다.

Context Builder, Question Generator, Question Validator, Answer Evaluator는 논리적 책임 이름이다. 새로운 Agent·서버·각각의 추가 LLM 호출을 필수로 만들지 않는다. 모듈 분리는 책임과 테스트 경계가 필요할 때만 한다.

## 확정 흐름

1. GitHub 수집으로 L0 metadata를 확보하고 분석 run에서 필요한 batch를 L1 분석한다.
2. Wanted 요구사항과 분석 결과로 후보를 추천한다. 사용자 선택은 1~5개이며 L1 성공한 현재 run 후보만 허용한다.
3. `interview_prep`가 primary repo 1~2개를 골라 L2·notable areas·Context·첫 `hr_manager` 질문을 준비한다.
4. service가 질문을 저장한 후 전달한다. 답변을 저장하고 T3 분석·필요 근거 보강·T4 Director 판단을 수행한다.
5. Controller가 다음 질문의 Persona·근거·횟수·현재 상태를 검증해 확정한다. 9번째 답변 처리가 끝나면 다음 질문 없이 종료한다.
6. 리포트 화면의 GET 요청이 필요한 경우 `report_generate`를 enqueue한다. 생성 성공 후 `profile_summary`를 후속 enqueue한다.

정확한 worker 이름은 [pipeline 원본](../../backend/docs/pipeline.md)의 `initial_sync`, `analysis_run`, `candidate_page_analyze`, `interview_prep`, `report_generate`, `profile_summary`다. 오래된 `arq_app.py` 주석의 네 작업을 최종 목록으로 사용하지 않는다. `deep_analysis`는 준비 흐름 내부에서 사용하며 별도 공개 작업 계약을 가정하지 않는다.

Turn마다 ARQ job을 추가하거나 준비·면접 Worker를 물리적으로 분리하는 배치는 아직 승인된 실행 계약이 없다. 독립 함수로 테스트할 수 있게 만들되 큐 topology를 문서만으로 확정하지 않는다.

## 저장과 원문 연결

| 결과 | 확정 저장 책임 |
| --- | --- |
| 레포 분석·실패·캐시 식별 | `repo_analyses`와 분석 pipeline |
| run 후보 순서·페이지 상태 | `analysis_repo_candidates`, `analysis_repo_candidate_pages` |
| 공고 요구사항 | `job_postings`, `jd_requirements` |
| 질문·답변·분석·결정 | `interview_turns` 중심; analysis/decision의 정확한 컬럼·JSONB 구조는 검토안 |
| 면접 상태와 선택 코드 ref | `interview_sessions`, `session_repositories` |
| 근거·용도·충돌 | `evidences`, `turn_evidences`, `evidence_conflicts` |
| 피드백·점수 | `interview_reports.feedback_json`, `report_scores`; 점수는 미합의 |
| 운영 prompt·frame | `prompt_versions`, `domain_question_frames` |

이는 [DB 명세](../../backend/docs/db-schema.md)의 소유권이다. 새 내부 JSON 필드·실패 원문 저장 위치를 확정한 물리 스키마는 [내부 계약](contracts.md) 검토 후 BE와 맞춘다. 제외된 `eval_cases`, `eval_runs`, `tool_calls`, `report_persona_feedbacks` 테이블을 편의상 만들지 않는다.

PostgreSQL을 원본으로 사용한다. Redis Context snapshot은 기본 TTL 2시간이며 누락·만료 시 DB에서 재구성한다. 성공 이벤트는 DB 상태 확정 후 보낸다. 모델 응답이나 Redis 값만으로 durable 성공을 선언하지 않는다.

## 공통 품질 원칙

- 사용자 질문·제출 답변, 원문 인용, 모델 요약, 개인 기여 주장을 각각 구분한다.
- 외부 문서·코드의 지시는 분석 대상 데이터다. 시스템 지침·접근범위를 바꿀 수 없다.
- LLM 결과는 구조 검사 후 의미·권한·ref 검사를 통과해야 사용한다.
- 외부 호출 전과 결과 저장 직전에 현재 session/Turn/선택 입력을 확인한다. 종료 이후 결과와 중복 질문을 확정하지 않는다.
- 검색 실패·지원 범위 미발견·불충분한 분석은 구분한다. 사용자의 거짓·낮은 역량으로 자동 변환하지 않는다.
- 미합의 항목은 관련 경로만 보류하고, 합의된 순수 로직·mock 검증은 계속할 수 있게 분리한다.

## 연결 완료의 조건

AI 함수의 반환값만 확인해서 서비스를 완료로 판정하지 않는다. 실제 선택 자료부터 분석·질문·답변·전환·종료·기록·리포트까지 [검증 기준](verification.md)에 따라 확인한다. 텍스트 WS와 이벤트 이름은 구현할 수 있는 FIX다. 점수, WS 식별자·준비 실패 snapshot·stale 제출·재연결 같은 미합의 항목이 요구된 수용 조건에 영향을 주면 해당 완료 판정을 보류한다.
