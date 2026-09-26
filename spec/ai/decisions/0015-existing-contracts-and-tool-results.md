# 0015 기존 내부 계약·작업 인수 유지와 부분 조회 오류 처리

- 상태: Accepted — 아래 명시한 기존 구성과 처리 의미
- 날짜: 2026-09-22
- 결정자: 현재 사용자
- 관련 PR: 없음
- 직접 선택: 조회 일부 실패 시 오류로 표시하되 확보한 근거는 유지하는 1번 안.
- 진행 지시: “기존안으로 해서 정할 수 있는 건 그대로 하고 질문이 필요한 것들만 질문해.”에 따라 기존 명세와 충돌하지 않는 구성은 추가 질문 없이 유지·채택한다.

## 목적과 채택 범위

[0014 최소 변경 기준](0014-minimal-change-revision.md)을 따른다. 기존 Context·Question·Evidence 필드와 작업 인수를 새로운 구조로 바꾸지 않고, 실제 미정이던 부분 조회 오류의 해석을 기존 ToolResult 안에서 정한다. 이 결정은 문서상의 내부 계약 채택이며 구현·DB migration·운영 검증 완료를 뜻하지 않는다.

| 묶음 | 채택한 기존안 | 근거 |
| --- | --- | --- |
| Context | 현재 내부 계약의 필드 목록과 의미. 서비스가 검증한 자료 중 해당 task에 필요한 내용만 전달 | [Context 입력](../contracts.md#context-입력), [Context Builder](../features/job-context.md#context-builder-입력) |
| Question | persona·text·topic_code·question_contract·evidence_refs·jd_requirement_ids 여섯 필드 | [Question](../contracts.md#question과-question-contract) |
| Evidence | 기존 출처·고정 ref·실제 위치·원문·선택적 요약·조회 방법과 Turn 관계 | [Evidence와 ToolResult](../contracts.md#evidence와-toolresult) |
| ToolResult | status·items·searched_scope·limitations·error_code 다섯 필드와 기존 네 상태 | 같은 내부 계약과 아래 부분 오류 규칙 |
| 기존 다섯 job 인수 | analysis_run(run_id), candidate_page_analyze(run_id, page_no), interview_prep(interview_id), report_generate(interview_id), profile_summary(user_id) | [ARQ 전달 계약](../features/job-context.md#arq-전달-계약) |
| 프로필 저장·공개 구조 | user_profile_summaries와 기존 공개 basedOnRepoCount·languages·projectTypes·roleSummary 유지 | [프로필](../features/report-profile.md#프로필-요약), 기존 OpenAPI |

## 내부 필드의 기본 표현

- 첫 질문 전 아직 없는 current_turn_id와 current_question_contract는 null, 이전 문답은 빈 history 목록으로 표현한다. total_turns는 기존 9이며 Persona 횟수는 서버가 확인한 실제 정수다.
- 실제 연결된 근거·JD 요구사항이 없으면 해당 참조 목록은 비운다. 필수 근거 유실·준비 실패를 빈 목록으로 숨기거나 ID를 만들어 채우지 않는다.
- Evidence의 선택적 summary와 해당하지 않는 줄 번호는 생략할 수 있다. 실제 줄 번호가 없는 자료에 0번 줄이나 가짜 위치를 넣지 않는다.
- 기존 사전 L2 분석에서 만든 Evidence의 tool_name은 null을 허용한다. 실제 도구로 확보한 자료에는 수행한 도구 이름을 기록한다. 두 경로의 고정 ref·원문·권한 검증은 유지한다.
- 질문 목적·평가 기준·Persona를 함께 확정하는 0014 규칙과 기존 서비스 소유권을 유지한다. 새 주제 분류 enum·FK·공개 필드를 만들지 않는다.

## ToolResult와 일부 조회 오류

기존 status 값은 found·not_found·insufficient_analysis·tool_error를 그대로 사용한다. 정상 조회 후 관련 원문을 찾았으면 found, 정상 조회를 마쳤으나 해당 범위에서 찾지 못했으면 not_found다. 분석·원문 준비 부족은 insufficient_analysis, 실제 도구 오류·시간 초과는 tool_error로 구분한다. 미조회는 not_found가 아니다.

**같은 도구 실행 안에서 일부 유효한 근거를 확보한 뒤 오류가 나면 대표 상태는 tool_error로 기록한다.**

- items에는 출처·권한·고정 ref·내용 검증을 통과한 결과를 보존한다. 오류 발생을 이유로 비우지 않는다.
- searched_scope에는 실제 확인한 범위를, limitations에는 미완료·미확인 범위와 이유를 남긴다. 시도만 한 위치를 확인 완료로 기록하지 않는다.
- error_code에는 실제 오류에 맞는 코드를 기록한다. 오류가 없으면 null이며, 전체 도구별 코드 매핑은 구현 경계에서 정리한다.
- 독립된 도구 실행 A가 성공하고 B가 실패한 경우에는 각 결과를 구분한다. B의 실패로 A의 결과를 소급하여 실패로 바꾸지 않는다.
- tool_error만으로 사용자 감점·확보 자료 폐기·Director 전체 실패·자동 재조회를 결정하지 않는다. 검증된 근거만 사용할 수 있으며 부족한 근거를 성공 자료로 꾸미거나 invalid 객체를 부분 JSON으로 살리지 않는다.

예를 들어 한 제한 조회에서 파일 A의 원문을 확보한 뒤 파일 B에서 시간이 초과되면, tool_error와 검증된 A의 items를 함께 반환한다. 실제 확인 범위와 B를 확인하지 못한 이유를 구분하며 A만으로 판단 가능한 범위는 보존한다.

별도 partial 상태·결과 사본·조회별 DB 저장·새 API는 추가하지 않는다. 짧은 조회 요약은 0014대로 기존 판단 근거와 저장 시점을 사용한다. 실패·중단 기록의 영구 저장 위치는 AI-L02·AI-L18, 복구·동시성은 AI-L12의 기존 잔여 범위다.

## 작업 전달과 프로필 경계

채택한 다섯 job은 기존 식별자만 전달하고 Worker가 DB 원본을 다시 읽는다. ORM 객체·토큰·원문·LLM client를 큐에 넣지 않는다. 기존 여섯 job 이름·단일 queue/worker·ARQ max_tries=1은 유지한다.

initial_sync의 사용자/account 식별자 선택은 기존 인증 관계와 소유권에 맞춰 구현 단계에서 정리한다. Python 타입·직렬화·Turn 번호 같은 통상적인 구현 세부는 사용자에게 항목별로 다시 묻지 않는다. 근거 없는 timeout·동시성·실행 상한은 확정값으로 만들지 않고 AI-L04·AI-L11에서 운영 요구와 함께 정한다.

프로필은 report_generate 성공 뒤 profile_summary(user_id)를 실행하고 완료 면접에 사용된 repo만 집계한다. 기존 user_profile_summaries와 공개 응답 필드는 유지한다. 같은 repo·다른 ref의 집계 단위, 언어 비율 계산, 개인 역할을 나타내는 roleSummary의 내용은 기존 확정 기준이 없어 별도 의미 결정이 필요하다. 개인 기여를 추정하거나 프로젝트 요약으로 바꾸지 않으며, Sprint 1 LLM 비호출 원칙도 유지한다.

후속 결정: [0016](0016-profile-language-aggregation.md)에서 저장소 중복 제거·언어 비율의 저장소별 동일 비중 평균을 확정했다. 당시 역할 요약 보류·안내 표시는 후속 [0019](0019-sprint1-profile-role-summary-restoration.md)에서 철회하고 기존 LLM 역할 요약을 구현 대상으로 복원했다. 위 미정 목록과 비호출 설명은 0015 작성 당시 기록이며 기존 저장·공개 구조는 유지한다.

## 확인과 남은 범위

- 검증 시 정상 발견·정상 미발견·준비 부족·전체 도구 오류·일부 근거 뒤 오류를 대조한다. 일부 오류에서도 유효한 근거와 실제 확인 범위가 보존되어야 한다.
- Context와 Question의 필드 구성, 첫 질문의 없음 표현, 실제 참조 목록과 필수 근거 유실의 차이, 사전 Evidence의 tool_name null을 확인한다.
- 상세 객체·위치·인수 표현은 기존 생산자와 소비자에 맞춰 구현 시 구체화한다. 현재 내부 필드 채택을 DB 컬럼·공개 API·실행 상한의 일괄 승인으로 확대하지 않는다.
- AI-L02의 채택된 기본 구성·ToolResult 상태와 부분 오류 해석, AI-L11의 다섯 job 인수, AI-L17의 저장소·공개 구조·job 인수만 해소한다. 작성 당시 남은 범위의 후속 결정은 [최신 결정 기록](README.md), 현재 실제 작업은 [구현·검수 인계](../../../ai/docs/pipeline.md#기존-id별-구현검수-인계)에서 확인한다.
- 기존 0003·0004의 의미·보존과 0014의 최소 변경 기준은 유지한다. 과거 결정의 작성 당시 Proposed 기록은 이 문서가 채택한 범위에서만 후속 대체한다.
