# 0015 면접 제한 시간은 [면접 시작하기] 클릭부터 센다

- 상태: Proposed
- 날짜: 2026-11-11 (제안)
- 작성: 이건영 (BE·FE 구현 담당)
- 검토자: GitHub `jinyeonggg` — [PR #260](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/260) 리뷰에서 openapi와 `startedAt` 의미 변경의 반영을 요청했다. 승인 기록은 아니다. AI 담당 확인 대기(미결 항목의 `interview_started` 이벤트 시점).
- 관련 이슈: [#259](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/issues/259), 선행 [#246](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/issues/246)
- 관련 PR: [#260](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/260)
- 대체 관계: [공통 0009](0009-interview-abandon-transition.md) §3의 "시작한 뒤"(`started_at`이 있는 면접)의 기준, [공통 0013](0013-interview-time-limit-and-early-end-report.md) §1 표의 "첫 질문 생성: `started_at`이 첫 질문 저장 뒤에 찍힌다"를 부분 대체한다. 두 문서의 원문은 보존한다.

## 맥락

준비 worker가 첫 질문을 저장하며 `status=in_progress`와 `started_at=now()`를 함께 기록했다. 그래서 제한 시간은 [면접 시작하기] 버튼이 활성화되는 순간부터 줄었다. 클릭은 서버에 아무것도 보내지 않아 마이크 확인, 망설이는 시간, 버튼을 누르지 않고 방치한 시간이 모두 면접 시간에서 빠졌다. 사용자가 면접을 시작했다고 느끼는 시점은 버튼을 누른 때다.

## 결정

1. **`started_at`은 시작 클릭 시각이다.** 준비 완료는 `status`만 `in_progress`로 바꾸고 `started_at`을 기록하지 않는다. 클릭 전에는 `in_progress`여도 `started_at`이 null이고, `remainingSeconds`는 전체 시간이며 만료도 일어나지 않는다.
2. **`POST /interviews/{id}/start`를 추가한다.** 응답 `204`. 멱등이라 다시 호출해도 처음 시각을 유지한다. `in_progress`가 아니면(`preparing`, `preparing_failed`, `completed`, `abandoned`) `409 not_ready`, 없거나 남의 면접이면 `404`, 미로그인이면 `401`. 새 reason은 만들지 않는다.
3. **진행 화면이 `in_progress`로 열릴 때도 FE가 start를 한 번 호출한다.** 준비 완료 뒤 새로고침, 대기 중 재연결 조회, 홈의 이어하기처럼 버튼을 거치지 않는 진입도 질문을 보는 순간부터 센다. start가 멱등이라 버튼으로 이미 시작했으면 처음 시각이 유지된다.
4. **시작 신호 없이 첫 답변이 오면 서버가 `started_at`을 첫 질문 저장 시각으로 보정한다.** 구버전 클라이언트나 직접 호출에서 타이머가 영영 돌지 않아 시간 제한이 없어지는 것을 막는 안전장치다. 시작 기록은 FE가 보장하며, 이 보정이 쓰이면 기다린 시간만큼 남은 시간이 한꺼번에 줄 수 있다.
5. **재도전과 마이페이지의 "시작한 뒤"는 start가 기록된 면접이다.** 0009 §3의 기준(`started_at` 있음)은 그대로이고 `started_at`의 의미만 바뀐다. 준비가 끝났지만 진행 화면을 한 번도 열지 않고 나간 면접은 `started_at`이 없어 목록과 재도전에서 빠진다.

## 이유와 대안

- 새 필드(`timer_started_at`)를 두는 안은 택하지 않았다. 마이그레이션과 계약 필드가 늘고, `started_at`을 읽는 곳(재도전, 마이페이지, 남은 시간, 만료)이 모두 "클릭 뒤에야 의미가 있는 면접"을 가리켜 한 필드로 충분하다. 클릭 전에 나간 면접은 답변이 없어 0009의 "기록할 내용이 있는 면접만 재도전" 취지와도 맞는다.
- 클릭을 WS 최초 연결로 알리는 안은 택하지 않았다. 새 경로는 없지만 URL 직접 진입과 새로고침이 시작을 숨은 부수 효과로 일으키고, 테스트와 계약 설명이 어렵다. 명시 REST가 단순하다.
- 클릭 없이 답이 온 경우를 거절하는 안은 택하지 않았다. 계약은 엄격해지지만 FE 오류 경로가 늘고, 시간 제한이 없어지는 문제는 보정만으로 막힌다.

## 영향

- BE: `prepare.py`의 `started_at` 기록 두 곳 제거, `start_interview` 서비스·라우트 추가, `save_answer` 보정. `_remaining_seconds`·`expire_if_due`는 `started_at`이 null이면 전체 시간·만료 없음으로 이미 처리해 바꾸지 않았다.
- FE: `InterviewPrepare`의 [면접 시작하기]와 `InterviewScreen` 진입이 start를 호출하고 호출 뒤 재조회한다. MSW 목은 클릭 기준으로 바꿨다.
- 계약: `openapi.yaml`에 새 경로와 `startedAt`·`remainingSeconds` 설명을 반영했다.
- 동작 변화: 클릭 전에 나간 면접은 마이페이지 목록과 재도전에서 빠진다. 0013의 "첫 질문 생성 대기는 이미 제외된다"는 결과는 같고 이유만 바뀐다(첫 질문은 클릭 전에 저장돼 있다).
- 되돌리기: `prepare.py`의 기록을 되살리고 FE의 start 호출을 지우면 된다. 마이그레이션은 없다.

## 미결

- `interview_started` 이벤트가 여전히 준비 완료 시점에 나간다. 클릭 시점으로 옮길지는 AI 담당 확인 뒤 정한다.
