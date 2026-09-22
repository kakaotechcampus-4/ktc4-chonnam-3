# 리포트 생성과 프로필 요약

상태: 생성 흐름·저장 위치 FIX. 기존 프로필 인수·저장소·공개 필드 유지는 [0015](../decisions/0015-existing-contracts-and-tool-results.md), 저장소 중복 제거·언어 비율 계산은 [0016](../decisions/0016-profile-language-aggregation.md), Sprint 1 개인 역할의 LLM 요약 복원은 [0019](../decisions/0019-sprint1-profile-role-summary-restoration.md)에서 Accepted. 통계 집계는 LLM에 맡기지 않는다. 상세 피드백·저장 매핑은 Proposed, 점수 세부 기준 seed는 평가 자료 보강에 따라 갱신 가능.

원본: [BE 리포트](../../backend/features/report.md), [task-16](../../../backend/docs/task-16-report.md), [공통 OpenAPI](../../shared/contracts/openapi.yaml), [FE 리포트](../../frontend/features/report.md). 과거 원본 `ForAI.md` 5항은 현재 저장소에 없다. 현행 리포트 점수는 [0010 결정](../decisions/0010-sprint1-interface-runtime-decisions.md#리포트-점수)을 따른다.

## 생성 흐름

리포트는 면접 종료 때 자동 enqueue하지 않는다. `GET /interviews/{id}/report`가 기존 결과를 200으로 반환하거나, 생성 가능하면 `report_generate`를 enqueue하고 202를 반환한다. 생성 중에는 중복 enqueue 없이 202, 생성 불가면 `409 report_unavailable`이다.

ARQ worker가 확정 문답·평가·근거·종료 상태를 읽어 `report_v1`을 실행하고 검증된 결과를 저장한다. 같은 면접의 재실행은 문답을 변경하거나 리포트를 중복 생성하지 않아야 한다. lock·저장 시점은 BE 작업과 함께 검사한다.

생성 가능 조건은 `interview_sessions.status='completed'`이고 답변 완료 turn이 1개 이상인 경우다. `abandoned`, `preparing`, `preparing_failed`, `in_progress`는 Sprint 1 report 생성 대상이 아니다. 이미 생성된 report는 200으로 반환한다.

이전 `report_generate` 실패 이력이 있으면 Sprint 1에서는 자동 재생성하지 않고 `409 report_unavailable`로 닫는다. report 재생성, 수동 retry, 이의제기 기반 재평가는 Sprint 2로 넘긴다.

## 입력

- 실제 제시한 질문·Persona·Turn 번호와 원본 제출 답변.
- 전달 전 Question Contract와 답변 판정, 후속 질문 연결.
- 유효한 question_basis/evaluation_basis와 출처·한계.
- `answer_vs_code`의 unresolved 차이 및 후속 답변의 설명.
- 면접 종료 상태, 관찰한 영역과 관찰하지 못한 영역.
- prompt/model/version과 검수된 평가 기준. 아직 작성·검수되지 않은 세부 채점 기준 seed는 입력으로 가정하지 않는다.

사용자에게 묻지 않은 질문의 모범답안, 다른 사용자 문답, 평가 데이터셋의 정답을 넣지 않는다.

Question Contract는 `interview_turns.question_contract`에 [저장 형식](../contracts.md#question-contract-저장-형식)을 따라 보관한다. 답변 분석은 [0014 결정](../decisions/0014-minimal-change-revision.md)에 따라 기존 평면 구조를 유지하며 [분석과 판단의 저장](../contracts.md#분석과-판단의-저장)을 따른다. 채택한 계약으로 실제 저장한 질문 기준과 분석 기록이 있어야 이를 근거로 하는 리포트 동작을 완료로 판정한다.

## 피드백 내용과 근거

종합 피드백은 관찰한 강점, 설명이 부족했던 내용, 추가 확인할 기술·기여, 다음 연습사항을 정리한다. Persona별 피드백은 같은 기록을 각 관점으로 요약한다. 세 명의 독립 전문가가 검증한 것처럼 표현하지 않는다.

각 핵심 관찰은 관련 Turn과 필요한 Evidence를 참조한다. 사용자 답변에 대한 평가는 문답을, 구현 사실에 대한 평가는 코드 원문을 연결한다. 초기 부족함이 후속 답변에서 보완됐으면 그 변경을 반영한다.

미관찰 Persona·기술 영역은 관찰 부족으로 표시한다. 질문 수·자료 부족·도구 오류를 0점으로 변환하지 않는다. unresolved conflict를 확정 거짓말로 서술하지 않는다.

## 내부 피드백 JSON 제안

`interview_reports.feedback_json`에 종합 summary와 Persona별 항목을 담는 방향은 FIX다. 세부 key는 Proposed다.

각 항목의 후보 구조는 `persona`, `observation_status`, `strengths`, `improvements`, `practice_actions`, `turn_refs`, `evidence_refs`, `limitations`다. 관찰 항목마다 근거를 연결할 수 있어야 하며, 공통 API의 `agentFeedbacks`로 변환하는 책임은 service/schema에 있다.

별도 `report_persona_feedbacks` 테이블을 만들지 않는다. 새로운 상세 근거·coverage·headline 필드를 공개 API에 바로 추가하지 않는다. FE가 원하는 내용과 OpenAPI의 차이는 공통 계약에서 해결한다.

## 확정된 점수와 세부 기준 검수

현재 OpenAPI의 리포트 200 응답은 숫자 `totalScore`와 `scores[].score`를 요구하며, Sprint 1은 점수를 반드시 포함한다.

- `totalScore`와 `scores[].score`는 0~100 number다.
- score key는 `project_understanding`, `technical_reasoning`, `problem_solving`, `communication`, `contribution_clarity`, `company_job_fit` 6개를 유지한다.
- `totalScore`는 6개 항목 score의 단순 평균이다.
- 가중치, nullable score, status 기반 미계산 표현은 Sprint 1에 사용하지 않는다.
- narrative/근거 연결 로직은 score 계산과 분리하여 mock과 내부 데이터로 개발·검증할 수 있다.

항목별 세부 평가 기준과 `score_criteria` seed 문구·version은 평가 담당자가 자료를 보강하며 갱신할 수 있다.

## 프로필 요약

`report_generate` 성공 후 `profile_summary`를 enqueue하고, 리포트 응답은 그 완료를 기다리지 않는다. 같은 사용자에 대해 진행 중인 중복 작업을 막는다.

[0015 결정](../decisions/0015-existing-contracts-and-tool-results.md)에 따라 기존 `profile_summary(user_id)` 인수를 채택하고 Worker가 해당 사용자의 확정 자료를 다시 조회한다. 저장소는 기존 `user_profile_summaries`를 유지하며 새 테이블이나 job을 추가하지 않는다. 공개 응답의 `basedOnRepoCount`, `languages`, `projectTypes`, `roleSummary`도 기존 이름과 타입을 유지한다.

집계 대상은 전체 수집 repo가 아니라 **완료된 면접에 사용된 repo**다. [0016 결정](../decisions/0016-profile-language-aggregation.md)에 따라 기존 저장소 식별자로 중복을 제거하고, 같은 저장소를 여러 면접·ref에서 사용해도 한 번만 센다. `basedOnRepoCount`는 이 저장소 수다. `languages`는 기존 저장소별 언어 비율의 단순 평균이며 코드량·면접 횟수로 가중하지 않는다. 유효한 언어 분포에 없는 언어는 해당 저장소에서 0으로 계산한다.

기존 저장 언어 자료를 재사용하며 프로필용 추가 수집·과거 ref 복원·새 스냅샷 저장을 요구하지 않는다. 면접 당시 ref별 언어 통계가 보존된다고 가정하지 않으며 상세 저장 연결은 기존 구조 안에서 구현 시 확인한다. 저장소 전체 언어 자료 누락·invalid는 0%나 제외 후 성공으로 바꾸지 않고 기존 갱신 실패 경계에서 직전 성공 요약을 유지한다.

[0019 결정](../decisions/0019-sprint1-profile-role-summary-restoration.md)에 따라 기존 `profile_summary_v1`의 개인 역할 LLM 요약을 Sprint 1 구현 대상으로 복원한다. 언어·유형·저장소 수는 기존 확정 자료로 집계하며 모델이 통계·수치를 계산하거나 바꾸게 하지 않는다. 모델과 공통 호출 정책은 기존 결정을 유지한다.

개인 역할 요약은 기존 `user_profile_summaries.role_summary`에 저장하고 `roleSummary` 문자열로 기존 문단에 표시한다. 모든 응답을 기능 보류 안내로 대체하지 않는다. 기존 자료에서 근거를 확인할 수 있는 역할을 요약하며 사용자 진술과 확인된 사실을 구분한다. L1 프로젝트 설명·README·commit 수만으로 개인 기여를 단정하거나 자료 부족을 추측한 역할 문장으로 채우지 않는다. 입력 자료 선택·프롬프트·검증·저장 연결은 기존 구조 안의 구현 작업이며 원본 답변·분석 이력과 `analysis`가 null인 기존 홈 상태를 유지한다.

프로필 job 실패는 이미 성공한 리포트를 실패로 되돌리지 않는다. Sprint 1에서 실패 재시도·복구·상세 실패 처리는 구현하지 않고 Sprint 2로 넘긴다. 이전에 성공한 요약을 보존하고 갱신 실패는 내부적으로 추적할 수 있다. 이 결정은 인수·저장소·기존 공개 필드의 채택이며 실제 job·DB 저장·집계 구현이 완료됐다는 뜻은 아니다.

## 후속 경계

`report_disagreements`는 Sprint 1 migration 작성 시 포함해야 하는 FIX 테이블이며 API·row 생성은 Sprint 2다. 현재 실제 migration이 구현됐다는 뜻은 아니다. 피드백에 불확실성을 남기는 현재 요구와 사용자 이의제기 기능을 혼동하지 않는다.

음성 transcript 정정·자료 삭제 후 리포트 정책·리포트 재생성 이력은 후속 합의 대상이다. 리포트를 다시 만든다는 이유로 질문·답변 원문을 변경하지 않는다.

## 검증

- 같은 GET/worker 재실행에서 200/202/409 의미와 중복 방지가 유지된다.
- 질문·답변·Persona·순서가 원본과 일치하고 미답변은 답변을 지어내지 않는다.
- 모든 주요 평가에 실제 Turn/Evidence 연결이 있고 후속 보완이 반영된다.
- 미관찰·unresolved·도구 실패가 구분된다.
- 점수는 0~100 number 6개와 단순 평균 `totalScore`를 공개한다.
- profile job은 report 저장 성공 후 enqueue되며 실패해도 report 결과가 유지된다.
- profile 집계에 완료 면접에 사용하지 않은 repo가 들어가지 않는다.
- 같은 repo를 반복 사용해도 중복 집계하지 않고 저장소별 언어 비율에 같은 비중을 준다. Python 100% repo와 Java 100% repo의 평균은 각각 50%다.
- repo 전체 언어 자료 누락을 특정 언어의 0%로 바꾸지 않고 이전 성공 요약을 보존한다.
- 역할 요약은 기존 LLM task·저장 필드·roleSummary 응답에 연결되고 근거 없는 개인 기여를 만들지 않는다. 통계 집계 결과를 모델이 바꾸지 않으며 실제 호출·저장·화면 연결은 구현 후 검증한다.

실제 모델·통합 검증은 [검증 기준](../verification.md)을 따른다.
