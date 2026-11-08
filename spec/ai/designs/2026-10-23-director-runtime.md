# Director 질문 결정과 AI·BE 입력 경계

- 상태: Proposed
- 날짜: 2026-10-23
- 선행: PR #82, #97, #102, #103, #114, #119
- 검토 범위 보완: 2026-10-26. 아래 신규 경로와 기존 Accepted 정책의 부분 대체는 제안이며 자동 승인·구현 완료가 아니다.

기존 Question Contract·flat 분석/결정·ToolResult를 사용하는 후속 설계다.
준비 worker·WebSocket·턴 저장과 상태 전이는 별도 실행 연결의 책임이다.

## 책임과 입력

- AI는 BE 프로세스 안의 `devon_ai` 패키지이며, 질문을 결정하는 Director는 하나다.
- Controller는 권한·면접 상태·고정 Git SHA·허용 Persona·예산과 DB 저장을 책임진다.
- 모델 입력은 실제 질문·답변·Question Contract·등록 원문과 위치·분석 한계를 포함한다.
  과거 분석 ID만으로 내용을 추측하지 않고, 검증한 분석을 별도로 전달한다.
- 첫 HR·기술6/도메인2/HR1 배분은 [공통 ADR 0008][allocation]을 따른다.
  이 문서는 새로운 공개 API 정책을 확정하지 않는다.

## 기존 생성 경로와 부분 대체 제안

[Accepted 기본 생성 설계](2026-09-23-director-question-path.md)의 `generate_question`은
호출자가 확정한 QuestionContract를 입력받는다. 모델은 기존 다섯 필드만 출력하고,
코드가 입력 Contract를 결합한다. 이 경로와 그 출력 schema는 그대로 유지한다.

후속 `run_director`는 목적·Contract·초안을 함께 생성하는 별도 Proposed 경로다.
이 경로의 planner 출력 `Question`에는 `question_contract`가 포함되며, 독립 검토 뒤에만 확정한다.
이를 기존 `generate_question`의 모델 출력 schema에 추가하지 않는다. 공개 WS나 저장 필드의 추가도 아니다.
[ADR 0023 제안][runtime-adr]과 함께 채택할 때, 신규 경로의 Contract 준비 주체와 아래 시도 배분만
기본 생성 경로의 전제에서 부분 대체한다. 기존 경로의 승인, 원문 보존·참조 검증·flat 저장 경계는 유지한다.

## 질문 결정과 독립 검토

신규 `run_director` 한 작업은 생성 1회와 독립 검토 1회를 합쳐 공유 예산 총 2회를 사용한다.
시작 전에 두 시도가 남아 있어야 하며 각 요청은 `max_attempts=1`로 보낸다.
첫 시도는 목적·필수 확인내용·전제·평가 범위와 질문 초안을 함께 생성한다.
두 번째 시도는 같은 후보를 원문·현재 분석·문답 이력과 대조하는 독립 검토다.
생성자의 자기 정당화를 독립 검토의 근거로 사용하지 않는다.

공통 gateway의 일반 timeout·provider·parse/schema 최대 1회 재시도를 각 단계에 적용하지 않는다.
생성에 두 시도를 쓰면 독립 검토가 없어지므로, 이 신규 경로는 각 단계의 자동 재시도를 제한하는 제안이다.
생성의 timeout·provider·parse/schema 실패는 1회에서 종료하고 후보를 확정하지 않는다.
검토 실패·거절·예산 소진에도 질문을 확정·저장·전송하지 않는다. 총 상한을 늘리거나 검토를 생략하지 않는다.
기존 `generate_question`과 다른 task의 공통 gateway 재시도 규칙까지 바꾸는 제안은 아니다.

계획·맥락 오류는 replan, 문장·계약 불일치는 rewrite, 허용 자료에 대안이 없으면
no_valid_candidate로 분류한다. 분류 이후 추가 생성이나 무검토 질문을 자동 실행하지 않는다.
성공 결과는 검증한 결정·질문과 실제 생성 시도의 model·prompt_version을 구분해 반환한다.

## 답변 분석과 조회 판단

현재 질문은 답변을 마친 과거 문답과 분리하여 답변 분석에 전달한다.
저장한 질문 계약·최초 분석·성공한 보강 분석은 당시 원문과 허용 위치에 다시 대조한다.
기여 정정을 반영해도 최초 질문·답변·분석 원형은 덮어쓰지 않는다.

최초·보강 답변 분석 T3는 같은 총 2회 예산을 사용하고, 후속 질문 T4는 별도 예산을 쓴다.
최초 T3가 재시도로 두 시도를 쓰고 필요한 보강 T3를 실행할 수 없거나 보강이 실패하면,
최초 분석과 실패 기록을 보존하되 T4·다음 질문·정상 완료로 진행하지 않는다.
조회·보강이 불필요한 유효 최초 분석은 별도 T4로 넘길 수 있다.
T3 결과 기반 규칙 함수 `verification_decision`이 명시된 필요와 허용 repo·SHA·path에서 조회 요청을 고른다.
이 선택에 별도 모델 호출을 추가하지 않으며, 모델 Director의 새로운 자율 조회 결정으로 해석하지 않는다.
충분한 등록 근거로 supported인 주장은 추가 조회에서 제외한다.
실제 Tool 실행·저장·알림은 Controller 책임이며 조회 판단 함수 자체는 I/O를 수행하지 않는다.
Controller는 턴당 허용 요청의 입력 순서상 첫 1개만 실행한다. 나머지 요청은 미조회 범위와 이유를
한계 기록에 남기며 `not_found`나 검증 완료로 만들지 않는다. 추가 조회 loop나 T3 예산 초기화는 없다.

## 원문 선정·수집 경계

L1 기본 분석과 실제 Git tree를 모델에 전달해 읽을 파일을 선정한다.
고정 repo·SHA와 실제 목록의 경로만 허용하고, BE가 해당 원문을 수집한다.
요청·바이트·시간·파일·구조 깊이에 유한 상한을 두며 읽지 못한 범위를 한계로 전달한다.
tree 열거는 선택된 공개 primary 저장소의 고정 SHA에서 파일명·종류 등 선정용 metadata를 얻는 범위다.
선정 전 모든 파일 본문을 읽거나 Private repo·global code search로 확대하지 않는다.
응답이 상한을 넘거나 열거가 중단되면 미열거 범위를 한계로 남기며 완전한 목록으로 취급하지 않는다.
파일명이나 특정 폴더 구조를 분석의 정답으로 고정하지 않는다.
전용 parser·대형 파일 분할·모든 언어의 분석 품질을 이 경계만으로 보장하지 않는다.

이 metadata 열거도 [Accepted ADR 0002](../decisions/0002-sprint1-vector-search.md) 결정 3의
기존 제한 검색보다 넓어질 수 있으므로, 이름만 달리해 이미 허용된 범위라고 간주하지 않는다.
[ADR 0025 제안][bridge-adr]과 함께 위 유한 열거에 한해서만 부분 대체를 검토한다.
vector·embedding·extension 미도입, Private repo·전역 코드 검색 금지와 나머지 기존 결정은 유지한다.
채택 전 AI·BE가 고정 ref·metadata와 본문 경계·유한 상한·불완전 열거·실제 비용 검증 기준을 확인하고,
후속 결정에 대체 조항과 승인 근거를 남겨야 한다. 이 문서만으로 ADR 0002를 Superseded 처리하지 않는다.

## 공개 계약과 후속 연결

공개 REST·WS wire와 `analysis`/`decision`의 기존 flat JSON 구조는 유지한다.
현재 질문 Context의 DB 로더, L2 어댑터의 예산·한계 전달 보완은 선행 구현 뒤에 연결한다.
[미적용 후속 패치 #133][followups]와 [ADR 0027 제안][followup-adr]은 이 보완의 검토 자료다.
패치 자료 병합은 일반 코드 적용·기능 활성화가 아니다. 최신 선행의 base/result·호출 기록 hook과
예산·현재 질문·과거 분석 전달을 확인하고 실제 적용 뒤 통합 재검증한다.
준비 실행·worker 등록·WS·턴 상태 전이·리포트·음성은 이 설계의 게시 범위 밖이다.

[allocation]: https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/d063d8d55f4744c09897ff51ecb140c45732e591/spec/shared/decisions/0008-fixed-persona-allocation.md
[runtime-adr]: https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/23873ef40f202c48557c672881934fc080aa196c/spec/ai/decisions/0023-director-runtime.md
[bridge-adr]: https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/e29c8f971fa87b32aace1bd5a3d6be1d43c88478/spec/ai/decisions/0025-director-bridge-publication.md
[followups]: https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/133
[followup-adr]: https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/5c10db62847dca28db820e5983580c33dc34bbc9/spec/ai/decisions/0027-unapplied-director-followups.md
