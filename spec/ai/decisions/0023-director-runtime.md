# 0023 Director 질문 결정과 독립 검토의 신규 게시 경계

- 상태: Proposed
- 날짜: 2026-10-23
- 선행 PR: #103, 정책 참조 #97
- 관련 구현: `ai/src/devon_ai/agents/director/runtime.py`

## 맥락

확정 Contract와 외부 reviewer를 받던 생성기에 목적·Contract 선정과 독립 검토가 필요하다.
선행 PR을 로컬에서 결합한 전체 구현과 이번 신규 게시 범위는 구분한다.

## 결정과 이유

1. 단일 Director가 목적·계약·초안을 첫 시도에서 생성하고 독립 검토에 두 번째 시도를 쓴다.
   최대 2회 예산을 공유하며 검토 거절 후 자동 재생성하지 않는다.
2. 검증한 결정·질문과 생성 시도의 model·prompt_version을 구분해 보존한다.
   실패는 선행 #103의 recovery 경계를 재사용하며 그 구현을 복사하지 않는다.
3. 현재·과거 분석과 실제 등록 원문을 두 호출에 전달한다.
   조회 판단은 검증한 분석과 허용 위치만 사용하고 실제 GitHub I/O는 실행하지 않는다.
4. runtime·prompt·테스트만 이 코어 게시에 포함한다. 어댑터·원문 수집·공통 보완은 별도 PR로,
   실제 계약·설계 자체도 별도 PR로 검토한다.

## 영향과 후속

### 기존 생성기와 새 planner의 구분

- 기존 `generate_question`은 호출자가 준비한 QuestionContract를 사용하며 모델에 계약을
  재출력시키지 않는다. 이 경로의 schema v2와 기존 검증은 유지한다.
- 새 `run_director`는 목적·Contract·초안을 함께 선정하는 planner다. 생성 응답의
  `question.question_contract`는 이 새 경로가 소유하며 중첩 객체까지 부가 필드를 거절한다.
  실제 계약·설계 자체는 [#124](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/124)에서 검토한다.
- 독립 검토는 정확한 후보·원문을 해당 review 요청 payload에 넣고 그 호출의 판정을 후보에
  결합한다. 모델이 문장·계약을 다시 출력해 동등성을 입증하는 방식은 아니다.
  코드가 구성한 QuestionReview의 마지막 대조는 후보 교체를 허용하지 않는 내부 경계다.

### 예산·실패·근거 등록

- 한 작업의 총 2회 안에서 생성과 검토에 각각 1회를 배정한다. 각 단계의 timeout·parse·schema
  실패도 재시도하지 않으며 공통 gateway의 요청별 상한을 1로 줄여 사용한다. 실패·거절 후에는
  무검토 질문, 자동 재생성 또는 정상 finish로 대체하지 않는다.
- 두 단계의 호출별 시간 상한은 기존 gateway를 따르며 전체 작업의 합산 deadline이 아니다.
  총량을 늘려 단계별 재시도를 허용하려면 시간·비용·검토 예약 정책을 먼저 재검토한다.
- Context의 remaining_calls는 BE가 실제 잔여·종료 상태와 일치시켜 전달하는 허용량이다.
  AI의 사전 검사가 실제 CallBudget을 예약하거나 다른 작업과의 동시 공유를 허용하지 않는다.
  BE adapter는 두 시도가 없는 작업을 provider 호출 전에 거절한다.
- ToolResult의 유효 items와 실패·한계를 두 호출에 그대로 전달한다. 질문에서 인용할 item은
  BE가 권한·고정 ref를 확인해 Context.evidence에 먼저 등록해야 한다. ToolResult 전달만으로
  임의 Evidence ID를 참조 registry에 등록하지 않는다.
- 검토 모델의 자유 텍스트 사유는 보호된 attempt의 raw_output에 보존한다. 일반 CallFailure는
  고정 요약과 recovery code만 반환하며 모델 문장을 일반 실패 설명에 복사하지 않는다.

`run_director`와 `verification_decision`의 호출자는 선행 #103과 별도 계약 PR이 필요하다.
고정 배분은 #97 정책을 참조하며 이 게시가 그 PR의 병합을 대신하지 않는다.
준비 실행·worker·WS·턴 저장/상태 제어와 실제 모델 품질 평가는 이 코어의 범위 밖이다.

기존 0012~0015의 계약과 0008의 후보 복구 정책을 유지한다.
선행 결합 원본과 제외 변경은 로컬에 보존하며, 실제 실행 결과는
[구현 기록](../implementation.md)에만 남긴다.
