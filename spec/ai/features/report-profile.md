# 리포트 생성과 프로필 요약

상태: 생성 흐름·저장 위치 FIX. Sprint 1 프로필의 LLM 비호출·확정 집계 원칙은 0006에서 Accepted. 상세 피드백·집계 저장 구조는 Proposed, 점수 공식·스케일은 PENDING_TEAM.

원본: [BE 리포트](../../backend/features/report.md), [task-16](../../../backend/docs/task-16-report.md), [공통 OpenAPI](../../shared/contracts/openapi.yaml), [FE 리포트](../../frontend/features/report.md), [ForAI 5](../../../ForAI.md).

## 생성 흐름

리포트는 면접 종료 때 자동 enqueue하지 않는다. `GET /interviews/{id}/report`가 기존 결과를 200으로 반환하거나, 생성 가능하면 `report_generate`를 enqueue하고 202를 반환한다. 생성 중에는 중복 enqueue 없이 202, 생성 불가면 `409 report_unavailable`이다.

ARQ worker가 확정 문답·평가·근거·종료 상태를 읽어 `report_v1`을 실행하고 검증된 결과를 저장한다. 같은 면접의 재실행은 문답을 변경하거나 리포트를 중복 생성하지 않아야 한다. lock·재실행·저장 시점은 BE 작업과 함께 검사한다.

이미 실패한 생성의 재시도 허용 조건과 생성 가능 종료 상태는 상세 검토 대상이다. 본 문서만으로 abandoned의 모든 경우를 생성 가능으로 정하거나 새로운 HTTP reason을 추가하지 않는다.

Redis 생성 lock 만료는 이전 worker의 성공·실패를 증명하지 않는다. 실패 attempt·진행 작업·재enqueue 허용을 어떤 durable 상태로 판정할지 BE가 정해야 한다. 이 소유권과 저장 제약이 없으면 lazy 생성의 멱등성 검증은 보류한다.

## 입력

- 실제 제시한 질문·Persona·Turn 번호와 원본 제출 답변.
- 전달 전 Question Contract와 답변 판정, 후속 질문 연결.
- 유효한 question_basis/evaluation_basis와 출처·한계.
- `answer_vs_code`의 unresolved 차이 및 후속 답변의 설명.
- 면접 종료 상태, 관찰한 영역과 관찰하지 못한 영역.
- prompt/model/version과 검수된 평가 기준. 미합의 점수 seed는 입력으로 가정하지 않는다.

사용자에게 묻지 않은 질문의 모범답안, 다른 사용자 문답, 평가 데이터셋의 정답을 넣지 않는다.

Question Contract와 상세 평가 구조는 [내부 계약](../contracts.md)의 Proposed 항목이다. AI·BE가 채택한 저장본이 있어야 이를 근거로 하는 리포트 동작을 완료로 판정한다. 문서에 입력으로 적혀 있다는 이유로 새 컬럼을 임의 생성하지 않는다.

## 피드백 내용과 근거

종합 피드백은 관찰한 강점, 설명이 부족했던 내용, 추가 확인할 기술·기여, 다음 연습사항을 정리한다. Persona별 피드백은 같은 기록을 각 관점으로 요약한다. 세 명의 독립 전문가가 검증한 것처럼 표현하지 않는다.

각 핵심 관찰은 관련 Turn과 필요한 Evidence를 참조한다. 사용자 답변에 대한 평가는 문답을, 구현 사실에 대한 평가는 코드 원문을 연결한다. 초기 부족함이 후속 답변에서 보완됐으면 그 변경을 반영한다.

미관찰 Persona·기술 영역은 관찰 부족으로 표시한다. 질문 수·자료 부족·도구 오류를 0점으로 변환하지 않는다. unresolved conflict를 확정 거짓말로 서술하지 않는다.

## 내부 피드백 JSON 제안

`interview_reports.feedback_json`에 종합 summary와 Persona별 항목을 담는 방향은 FIX다. 세부 key는 Proposed다.

각 항목의 후보 구조는 `persona`, `observation_status`, `strengths`, `improvements`, `practice_actions`, `turn_refs`, `evidence_refs`, `limitations`다. 관찰 항목마다 근거를 연결할 수 있어야 하며, 공통 API의 `agentFeedbacks`로 변환하는 책임은 service/schema에 있다.

별도 `report_persona_feedbacks` 테이블을 만들지 않는다. 새로운 상세 근거·coverage·headline 필드를 공개 API에 바로 추가하지 않는다. FE가 원하는 내용과 OpenAPI의 차이는 공통 계약에서 해결한다.

## 점수 미합의의 실제 영향

현재 OpenAPI의 리포트 200 응답은 숫자 `totalScore`와 `scores[].score`를 요구한다. 점수 공식·가중치·저장 스케일은 아직 합의되지 않았다.

- 임의의 1~5 또는 0~100 기준·평균·가중치·정규화를 생성하지 않는다.
- 모르는 점수에 0을 넣으면 관찰 사실을 조작하고, null을 넣으면 현재 숫자 schema와 다르다.
- narrative/근거 연결 로직은 score 계산과 분리하여 mock과 내부 데이터로 개발·검증할 수 있다.
- 실제 리포트 200 공개 완료에는 승인된 점수 정책 또는 FE·BE가 함께 승인한 nullable/status 등 계약 변경이 필요하다.
- 점수 준비가 안 됐는데 영구적인 202 “생성 중”으로 숨기지 않는다. 해당 상태를 API에서 어떻게 표현할지도 합의해야 한다.

여섯 score key 등 FE 초안의 표현이 있다는 사실은 산식 승인 근거가 아니다. `score_criteria` 테이블·seed를 만드는 것과 유효한 점수 정책을 정하는 것은 별개다.

## 프로필 요약

`report_generate` 성공 후 `profile_summary`를 enqueue하고, 리포트 응답은 그 완료를 기다리지 않는다. 같은 사용자에 대해 진행 중인 중복 작업을 막는다.

집계 대상은 전체 수집 repo가 아니라 **완료된 면접에 사용된 repo**다. 같은 repo를 여러 면접에서 사용했을 때의 집계 단위·중복 제거를 명시하고 BE와 맞춘다.

[0006 결정](../decisions/0006-task-llm-usage-policy.md)에 따라 Sprint 1 프로필은 job을 유지하되 확정 데이터 집계만 수행하며 LLM을 호출하지 않는다. `profile_summary_v1`은 기존 seed 목록에 유지하고 자연어 LLM 요약 활성화는 후속 검토로 남긴다. 후속 자연어 요약을 도입할 경우에도 확정 집계만 입력으로 사용하고 모델이 통계·수치를 계산하게 하지 않는다. 실제 집계 단위·중복 제거·저장 매핑은 이 결정으로 확정하지 않는다.

프로필 job 실패는 이미 성공한 리포트를 실패로 되돌리지 않는다. 이전에 성공한 요약을 보존하고 갱신 실패를 추적한다. 새 정확한 저장 key·job 인수는 BE와 합의한다.

## 후속 경계

`report_disagreements`는 Sprint 1 migration 작성 시 포함해야 하는 FIX 테이블이며 API·row 생성은 Sprint 2다. 현재 실제 migration이 구현됐다는 뜻은 아니다. 피드백에 불확실성을 남기는 현재 요구와 사용자 이의제기 기능을 혼동하지 않는다.

음성 transcript 정정·자료 삭제 후 리포트 정책·리포트 재생성 이력은 후속 합의 대상이다. 리포트를 다시 만든다는 이유로 질문·답변 원문을 변경하지 않는다.

## 검증

- 같은 GET/worker 재실행에서 200/202/409 의미와 중복 방지가 유지된다.
- 질문·답변·Persona·순서가 원본과 일치하고 미답변은 답변을 지어내지 않는다.
- 모든 주요 평가에 실제 Turn/Evidence 연결이 있고 후속 보완이 반영된다.
- 미관찰·unresolved·도구 실패가 구분된다.
- 점수 미합의 상태에서 숫자를 만들어 공개하지 않는다.
- profile job은 report 저장 성공 후 enqueue되며 실패해도 report 결과가 유지된다.
- profile 집계에 완료 면접에 사용하지 않은 repo가 들어가지 않는다.

실제 모델·통합 검증은 [검증 기준](../verification.md)을 따른다.
