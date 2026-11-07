# 0010 진행 중 질문 생성 실패의 question_failed는 recoverable false

- 상태: Accepted
- 날짜: 2026-11-07
- 작성: BE
- 검토자: FE — 진영 ([#200](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/issues/200) 댓글에서 A안 합의)
- 관련 이슈: [#200](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/issues/200)
- 관련 PR: [#192](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/192) 리뷰(`ws.py` 진행 중 실패 처리 질문)

## 맥락

면접 진행 중 답변 분석(T3)이나 다음 질문 생성(T4)이 실패하면 BE는 `question_failed`를 `recoverable: true`로 보내고 소켓을 닫았다. 답변은 이미 저장됐고 다음 질문은 없는 상태다.

- 재접속하면 `restore()`가 같은 `question_failed`를 다시 보낸다. 설계(`spec/ai/designs/2026-10-25-interview-execution.md`)가 이미 답변된 턴의 실패·미완료 분석을 재접속만으로 다시 실행하지 않는다고 정했기 때문이다.
- FE는 `recoverable: false`일 때만 재연결을 멈춘다. `true`면 복구되지 않는 면접에 계속 재접속한다.

wire 값(`true`)이 설계 의도(재실행 없음)와 어긋나 있었다.

## 결정

진행 중(`in_progress`) 면접의 질문 생성 실패는 `question_failed`를 `recoverable: false`로 보낸다.

| 항목 | 값 |
| --- | --- |
| reason / code | `question_failed` / `ERR_QUESTION_FAILED` (유지) |
| recoverable | `false` — 서버가 연결을 닫고 FE는 재연결하지 않는다 |
| 대상 | 진행 중 T3·T4 실패·폐기, 그리고 답변이 저장된 `in_progress` 면접에 재접속해 다음 질문이 없는 경우 |
| 제외 | 준비 실패(`preparing_failed`)의 `lastError`, 연결 교체·작업 중(`connection_replaced_or_busy`), 예기치 못한 서버 오류(1011) — 기존 값 유지 |

FE는 fatal 화면에서 면접을 abandon한 뒤 같은 레포로 새 면접을 시작하거나 홈으로 나가게 한다(`POST /interviews/{id}/abandon` → `POST /interviews/{id}/retry`). 화면 처리는 FE가 맡는다.

## 이유

- 새 필드나 복구 API 없이 기존 `recoverable` 값만 바꾼다. 설계 문서의 "공개 오류 필드나 복구 API를 추가하지 않는다"와 맞는다.
- 대안 B(`true` 유지, FE가 연속 실패 상한으로 중단)는 서버가 재실행하지 않는데 복구 가능하다고 말하는 불일치를 남기고, FE가 실패 횟수를 세는 로직을 새로 만들어야 한다.
- 진행 중 면접을 이어서 실행하는 복구는 후속 설계로 둔다. 현재 구조에서는 A가 최선이라는 FE 의견과 같다.

## 영향

- BE: `ws.py`의 진행 중 `question_failed` 송신값 변경과 테스트.
- FE: `question_failed`의 `recoverable: false` 처리 화면·문구, MSW 시나리오. `spec/frontend/features/interview.md`와 `frontend/docs/api-spec.md`의 `question_failed` 행(`recoverable` ✅)은 FE가 화면 변경과 함께 갱신한다.
- 계약: 스키마·OpenAPI 변경 없음. [migration.md](../contracts/migration.md)에 한 줄 기록.
- 되돌리기: BE의 송신값을 `true`로 되돌리면 된다. FE가 `false` 처리를 먼저 배포해도 `true`와 호환된다.

## 대체 관계

- 설계 `2026-10-25-interview-execution.md`의 "`question_failed`의 `recoverable: true`는 이어가기 권한이 아니다"를 대체하지 않고 이 결정이 값으로 구현한다. 설계 문서는 덮어쓰지 않는다.
