# 0005 — Director 호출·질문 저장과 고정 코드 Evidence 경계

- 상태: Proposed — 구현 검토용
- 날짜: 2026-09-28
- 관련 PR: Task 14 BE 연결부 Draft (`feature/be-task14-draft` → `develop`)
- 검토: BE 구현·독립 코드 검토; 팀 리뷰 대기

## 맥락

현행 AI는 준비된 `QuestionContract`와 독립 `QuestionReviewer`로 질문 하나를 생성한다.
DB·권한·GitHub I/O·구체 LLM client는 BE 책임이다. 질문이 생기기 전 실패한 호출도
보존해야 하며, 외부 호출 동안 DB 잠금을 유지하거나 늦게 도착한 질문을 저장하면 안 된다.
기존 선택 저장소에는 면접 당시의 SHA가 없고 Evidence에는 출처의 줄 위치가 부족하다.

## 결정

- BE는 DB에서 소유권·현재 턴·선택 저장소·허용 persona를 검증한 `Context`만 AI에 전달한다.
  기존 AI 생성기, DB prompt loader, LLM gateway를 연결하고 새 추론·재시도 계층은 만들지 않는다.
  의미 검토기는 호출자가 반드시 제공한다.
- 호출자가 논리 요청 전에 발급한 UUID를 `llm_call_records`의 PK로 사용한다.
  최초 짧은 transaction에서 호출을 확보하고, 외부 호출 후 다시 상태를 검사한다.
  질문·계약·`question_basis`·현재 턴·호출 기록을 같은 transaction에 저장한다.
  상태가 달라진 성공 결과는 질문에 적용하지 않고 `discard_reason`과 호출 기록을 남긴다.
- `attempt_sink`는 기존 gateway의 완료된 시도마다 기록을 수집한다. 재시도·reviewer·최종 저장 중
  취소되어도 수집한 기록을 보존하며 취소/예외 자체는 상위로 전파한다. 모델 실패와 적용 폐기는 구분한다.
- `session_repositories.snapshot_head_sha`를 준비 단계가 검증된 선택 분석에서 확정한다.
  DB가 승인한 정확한 경로만 같은 SHA의 일반 UTF-8 파일로 조회한다. 조회 후 저장 시에도
  소유권·면접 상태·공개 접근·선택 SHA·허용 경로를 재검증한다. 호출 한도는 명시적으로 주입한다.
- `question_contract`·선택 SHA·Evidence 출처 컬럼은 nullable로 추가한다. 과거 자료를 추측해
  backfill하지 않는다. 새 경로는 필요한 자료가 없으면 명시적으로 거절한다.

## 이유와 영향

독립 호출 테이블은 아직 turn이 없는 실패 기록을 보존한다. 기존 turn만 저장하거나 원문을
로그로 남기는 방식은 이를 충족하지 못한다. 내부 결과는 원문 대신 호출/turn ID와 고정 오류만
돌려주며 공개 REST·WS 계약과 FE는 변경하지 않는다.

최초 호출 확보 이후 프로세스 강제 종료나 DB 자체 장애는 정리 transaction도 보장할 수 없다.
준비/턴 worker 연결 시 실제 실행 종료를 확인한 복구가 필요하다. 시간만 보고 중복 LLM 호출을
허용하는 임의 TTL이나 자동 재실행은 추가하지 않는다. 응답이 끝나지 않은 개별 시도의 원문·토큰은
추측하지 않는다. 세부 연결 범위와 검증 결과는 [구현 기록](../implementation.md)에 둔다.

새 migration은 현재 develop의 `0001_initial` 뒤에 추가한다. 다른 미병합 migration과 통합할 때
실제 Alembic graph를 연결하고 기존 데이터 보존을 재검증한다. downgrade는 새 컬럼·호출 기록을
제거하므로 적용된 환경에서 실행하기 전에 해당 자료 보존이 필요하다.

## 관련 기준

- [AI/BE 계약](../../ai/contracts.md), [Task 14](../../../backend/docs/task-14-agents.md)
- [공통 질문 배분 결정](../../shared/decisions/0004-flexible-persona-allocation-restoration.md)

기존 추론·질문 배분·공개 API 정책을 대체하지 않는다.
