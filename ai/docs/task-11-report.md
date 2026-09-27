# task-11 - 리포트 서술

상태: 구현 가이드. 현재 runtime은 docstring 스켈레톤이며 리포트 생성 동작은 미구현이다.

## 목표

확정된 문답, 답변 평가와 근거를 바탕으로 종합 및 Persona별 narrative 후보를 생성한다.
관찰한 내용과 미관찰 영역을 구분하고 모든 주요 피드백을 실제 Turn과 필요한 Evidence에
연결한다. 공개 점수는 기존 6개 0~100 값과 단순 평균을 유지하며, 서술 검사와 실제 평가 기준·seed 검수를 구분한다.

전체 순서는 [AI 구현 파이프라인](pipeline.md)을 따른다. 선행 작업은
[task-02 계약](task-02-contracts.md), [task-03 LLM 경계](task-03-llm-boundary.md),
[task-06 입력 준비](task-06-context-preparation.md),
[task-08 근거 도구](task-08-evidence-tools.md),
[task-09 답변 분석](task-09-answer-analysis.md), [task-10 Director](task-10-director.md)다.

## 근거

- [리포트와 프로필](../../spec/ai/features/report-profile.md)의 생성 흐름, 입력, 피드백 내용,
  기존 공개 점수와 프로필 경계를 따른다.
- [답변 평가](../../spec/ai/features/answer-evaluation.md)의 후속 보완·기여 정정·원문 보존
  정책을 최종 피드백에도 적용한다.
- [0006 LLM 사용 정책](../../spec/ai/decisions/0006-task-llm-usage-policy.md)과 후속 [0019](../../spec/ai/decisions/0019-sprint1-profile-role-summary-restoration.md)에 따라 리포트·개인 역할의 LLM 요약과 프로필 통계의 비LLM 집계를 구분한다.
- [BE task-16](../../backend/docs/task-16-report.md)의 lazy 생성과 profile 후속 enqueue는
  통합 대상이지 AI 함수가 직접 소유할 상태 전이가 아니다.
- [0018 기존안 일괄 채택](../../spec/ai/decisions/0018-existing-baseline-bulk-resolution.md)에 따라 같은 점수·저장 정책을 다시 선택하지 않고 [구현·검수 인계](pipeline.md#기존-id별-구현검수-인계)를 따른다.

## 선행 조건

- [ ] 실제 제시한 질문, Persona, Turn 번호와 확정 답변 원문만 입력으로 사용한다.
- [ ] 평가와 근거가 같은 Turn의 유효한 `question_basis` 또는 `evaluation_basis`인지 확인한다.
- [ ] 후속 답변 연결, 기여 정정, unresolved conflict와 미관찰 영역을 입력에서 보존한다.
- [ ] Question Contract와 평가 구조는 채택한 내부 계약을 사용하고 상세 타입·저장 연결은 기존 경계에서 확인한다.
- [ ] 선택한 모델의 provider 연결을 검증하고 실행 상한은 운영 조건·대표 사례 측정으로 설정한다. 기존 재시도 정책은 유지한다.

## 대상 파일과 책임

- [리포트 원본](../src/devon_ai/llm_tasks/report.py): `report_v1`의 narrative 및 Persona별
  피드백 후보를 생성하고 의미 검증한다.
- [AI 계약 위치](../src/devon_ai/contracts.py): 승인된 report 입력·출력 타입만 둔다.
- [BE 리포트 연결](../../backend/app/llm_tasks/report.py): prompt와 provider I/O를 AI task에
  주입하고 typed 실패를 service에 돌려준다.
- [BE report service](../../backend/app/features/report/service.py): 생성 가능 상태, 중복 방지,
  저장과 공개 응답을 소유한다.
- [BE profile 경계](../../backend/app/llm_tasks/profile_summary.py): 완료 면접의 기존 자료로 통계를 집계하고 개인 역할만 LLM으로 요약한다. 기존 저장·공개 필드·job을 유지하며 실제 연결은 구현 대기다.

## 작업

- [ ] 종합 피드백에 관찰한 강점, 설명이 부족했던 내용, 추가 확인점과 연습사항을 구분한다.
- [ ] Persona별 피드백은 같은 면접 기록을 각 관점에서 요약하고 독립 전문가 검증처럼 쓰지 않는다.
- [ ] 각 핵심 관찰에 실제 `turn_ref`를 연결하고 구현 사실에는 유효한 `evidence_ref`를 연결한다.
- [ ] 질문에 없던 기준, 다른 사용자 문답, 평가용 기대 정답을 입력하거나 피드백에 사용하지 않는다.
- [ ] 초기 부족함이 후속 답변에서 보완되면 최신 관찰에 반영하고 원문·최초 분석은 보존한다.
- [ ] 사용자가 개인 기여를 정정하면 이후 피드백 전제를 갱신하고 코드 존재와 개인 기여를 분리한다.
- [ ] 미관찰 Persona·기술 영역은 관찰 부족으로 표시하고 내용이나 평가를 지어내지 않는다.
- [ ] 질문 수 부족, 자료 부족, Tool 오류를 0점이나 사용자 역량 부족으로 변환하지 않는다.
- [ ] `answer_vs_code`의 unresolved 상태를 거짓말이나 확정 오류로 서술하지 않는다.
- [ ] narrative와 근거 연결을 점수 산식과 분리하여 fixture로 개발한다.
- [ ] `feedback_json` 상세 key와 참조·null은 기존 피드백 의미·저장 위치·공개 변환에 맞춰 구현하고 검증한다.
- [ ] 별도 Persona 피드백 테이블이나 새 공개 headline·coverage·근거 필드를 추가하지 않는다.
- [ ] 기존 score key 6개와 0~100 number를 유지하고 `totalScore`는 단순 평균으로 계산한다. null·임의 기본 점수·새 가중치로 대체하지 않는다.
- [ ] `score_criteria`의 실제 세부 기준·seed·version과 미관찰 사례를 자료로 검수한다. 부족한 검증을 영구 202나 점수 없는 공개 리포트로 우회하지 않는다.
- [ ] report 성공 뒤 profile job을 enqueue하는 책임은 BE에 남기고 AI report task가 직접 큐를 다루지 않는다.
- [ ] 프로필 통계를 LLM으로 계산하거나 전체 수집 repo까지 집계 범위를 넓히지 않는다.
- [ ] 프로필은 [0016 결정](../../spec/ai/decisions/0016-profile-language-aggregation.md)의 저장소 중복 제거·저장소별 언어 비율의 동일 비중 평균을 따른다. 기존 저장 자료를 사용하고 누락을 0%로 채우지 않는다.
- [ ] Sprint 1 roleSummary는 0019의 기존 LLM 역할 요약을 사용한다. 입력 근거를 넘는 개인 기여를 만들지 않고 사용자 진술과 확인 사실을 구분하며, 기존 문자열·저장 위치로 연결한다.

## 검증

추가 예정, 현재 없음: `ai/tests/llm_tasks/test_report.py`.

- [ ] 실제 질문·답변·Persona 순서와 생성 결과의 Turn 참조가 일치하는지 검사한다.
- [ ] 후속 보완과 기여 정정 전후 fixture에서 최종 피드백이 바뀌고 원문은 유지되는지 검사한다.
- [ ] 미답변, 미관찰 Persona, 자료 부족, Tool 오류와 unresolved conflict를 서로 구분한다.
- [ ] 존재하지 않거나 다른 ref의 Evidence를 주요 관찰 근거로 채택하지 않는다.
- [ ] 공개 점수가 기존 6개 0~100 값·단순 평균을 지키고, 정성 판정을 임의 숫자로 환산하거나 자료 부족을 0점으로 바꾸지 않는지 검사한다.
- [ ] timeout, parse/schema 실패와 의미 검증 실패를 빈 성공 결과로 바꾸지 않는다.
- [ ] lazy 200/202/409, 중복 worker와 profile enqueue는 task-13 및 BE 통합 테스트로 분리한다.

Mock narrative 통과는 실제 모델 품질, report 저장, 공개 200 응답이나 프로필 갱신 완료가 아니다.

## 완료 조건

- [ ] 종합·Persona별 narrative가 실제 Turn/Evidence와 한계를 추적할 수 있다.
- [ ] 후속 보완·기여 정정·미관찰 원칙을 대조 fixture로 검증한다.
- [ ] 점수와 공개 응답, 저장·queue 책임이 AI task 밖으로 분리된다.
- [ ] 실패·보류를 숨기지 않고 미승인 필드나 숫자를 생성하지 않는다.

## 구현·검수 인계

| 항목 | 독립 작업 | 실제 연결 전 확인 |
| --- | --- | --- |
| AI-L02 내부 계약 | narrative와 참조 fixture 검토 | 기존 feedback 필드·참조·null·저장·응답 변환 구현 |
| AI-L15 공개 점수 | 서술·점수 검사를 분리한 fixture | 기존 6개 0~100 점수·평균에 적용할 세부 기준·seed와 미관찰 사례의 실제 검수 |
| AI-L16 report 실패 처리 | 기존 생성 조건·실패 시나리오 작성 | 성공본 재사용·중복 enqueue 방지·이전 생성 실패 시 409, Sprint 1 재생성 없음의 연결 검사 |
| 프로필 집계·역할 요약 — AI-L17 결정 해소 | 채택한 중복 제거·언어 비율 평균·0019 역할 요약 근거 검증 mock | 기존 저장 필드·LLM 역할 요약·갱신·응답의 실제 구현과 검증 |
| AI-L18 원문 운영 | 비식별 fixture와 로그 제외 검사 | 0018의 확정한 내부 보관·재사용 정책에 맞는 원문·raw output 권한·접근·보관의 실제 연결 검증 |

[0018](../../spec/ai/decisions/0018-existing-baseline-bulk-resolution.md)과 [작업 지도](pipeline.md#기존-id별-구현검수-인계)를 따른다. 서술만 검사하는 fixture는 점수 없는 공개 리포트 승인이 아니다. 자료 정책은 0018의 보관 유지 결정을 적용하며 구현·자료 검수 완료를 문서 채택으로 대신하지 않는다.
