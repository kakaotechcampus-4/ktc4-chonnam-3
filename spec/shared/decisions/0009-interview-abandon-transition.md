# 0009 면접 abandoned 전환 방법 — 나가기·레포 재선택

- 상태: Proposed
- 날짜: 2026-10-26
- 작성: 진영 (FE)
- 검토자: BE (검토 대기)
- 관련 이슈: [#143](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/issues/143)(전환 방법), [#121](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/issues/121) 1-2(재도전 허용 상태)

## 맥락

`abandoned`가 되는 시점은 정해져 있다. 이탈 확인 모달에서 나가기를 확인했을 때와, 레포를 다시 골라 같은 run에 새 면접을 만들 때의 기존 면접이다([BE 면접 명세](../../backend/features/interview.md), [AI 0010](../../ai/decisions/0010-sprint1-interface-runtime-decisions.md)). 전환 결과는 `status='abandoned'`, `abandoned_at_turn`이다(`backend/docs/pipeline.md` 4.2).

그러나 전환 방법이 계약에 없어 어떤 경로로도 `abandoned`가 되지 않는다.

- 나가기: 서버에 알릴 REST·WS 메시지·close code가 없다([migration.md](../contracts/migration.md) "명시적 이탈 통지", `PENDING_BE`). 이탈 모달은 화면만 닫고 면접은 `in_progress`로 남는다.
- 레포 재선택: 기존 면접을 바꾸는 단계가 없다. 기존 면접이 `in_progress`면 "run당 활성 면접 1개" 규칙으로 `POST /interviews`가 `409 session_limit_exceeded`가 되고, `preparing_failed`면 새 면접은 생기지만 기존 면접이 남아 재시도 거절이 반복된다.
- 재도전 허용 상태: BE 명세는 `completed`·`abandoned`를 허용하지만, `abandoned`는 리포트가 없어 FE에 재도전 진입점이 없다.

## 결정

### 1. `POST /interviews/{id}/abandon`

| 응답 | 조건 |
| --- | --- |
| `204` | 전환 성공. 이미 `abandoned`면 다시 불러도 `204` |
| `404 not_found` | 없거나 남의 면접(`GET /interviews/{id}`와 같은 규칙) |
| `409 already_completed` | `completed`·`preparing` 등 허용하지 않는 상태 |

- 허용 상태는 `in_progress`와 `preparing_failed`다. `preparing_failed` 허용은 레포 재선택으로 그 면접을 버릴 때를 위한 것이며, 준비 실패 자체를 `abandoned`로 바꾸지 않는다.
- 한 번 `abandoned`가 된 면접은 다른 상태로 바뀌지 않는다. 이후 질문·분석이 저장되거나 WS 이벤트가 나가지 않는다. abandon과 엇갈린 질문 생성·답변 분석·면접 종료도 같다.
- abandon 시 서버는 그 면접의 열린 WS 연결을 닫는다. 전용 close code는 두지 않는다. FE는 끊기면 `GET /interviews/{id}`로 상태를 확인하고 `abandoned`면 재연결하지 않는다.

### 2. 호출 순서 (FE)

- 나가기: 이탈 모달 확인 → abandon → `/home`. abandon 요청이 실패해도 홈으로 이동한다.
- 레포 재선택: [레포 다시 선택하기]는 기존 면접 id를 넘기며 레포 선택 화면으로 이동만 한다. [면접 시작]에서 ① 기존 면접 abandon → ② `POST /interviews`를 차례로 보낸다. ①이 성공하고 ②가 실패하면 기존 면접은 중단된 채 레포 선택 화면에 머문다.
- `already_completed`를 받으면 리포트 화면으로 이동한다.
- 면접 생성 후 준비 화면 이동(`RepoSelect`)은 `replace`로 한다. 브라우저 뒤로 가기로 같은 run의 레포 선택 화면에 돌아와 기존 면접 id 없이 새 면접을 만드는 경로를 막는다. 분석 화면 이동은 이미 `replace`다.

### 3. 재도전 허용과 마이페이지

- 재도전(`POST /interviews/{id}/retry`)은 `completed`와 **시작한 뒤 중단된 `abandoned`(`started_at`이 있는 면접)** 만 허용한다. 그 외는 `409 original_not_completed`.
- 준비 단계에서 버린 면접은 질문을 받지 않아 기록할 내용이 없고, 같은 레포 조합이라 재도전해도 실패 가능성이 높다. 준비 실패의 재시도는 실패 화면의 [다시 시도]가 맡는다.
- `GET /me/interviews`는 `completed`와 위 기준의 `abandoned`를 포함한다. `total`은 목록 행 수, `averageScore`는 `completed`만 계산한다.
- 마이페이지 abandoned 행은 [리포트 보기] 대신 [다시 도전하기], 점수 대신 "중단됨", 일시는 `startedAt`으로 표시한다. 헤더는 "완료 {totalCount}회"로 표기한다.

## 이유와 대안

- REST: 이탈 모달은 재연결 중에도 누를 수 있어 소켓이 죽어 있어도 동작해야 한다. WS 메시지·close code는 이 경우 전달되지 않는다. 응답 코드로 성공·실패도 분명하다.
- 레포 재선택에서 서버가 `POST /interviews` 안에서 기존 활성 면접을 자동 abandon하는 안은 택하지 않는다. 다른 탭에서 진행 중인 면접이 사용자 모르게 끝날 수 있다. 기존 면접 id가 없는 남은 경로(주소 직접 입력, 다른 탭)는 드물고 [#121](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/issues/121) 1-4의 `session_limit_exceeded` 구분으로 반복 거절 없이 정리된다.
- 재도전을 `started_at` 기준으로 좁히는 것은 기록할 내용이 있는 면접만 다시 하게 하기 위해서다.

## 영향

- Accepted 후 갱신: `openapi.yaml`(abandon 엔드포인트, `/me/interviews` 설명), [migration.md](../contracts/migration.md) "명시적 이탈 통지"(FIX), `frontend/docs/api-spec.md` #10·#18·#20, BE `spec/backend/features/interview.md`(허용 상태·재도전 조건), `backend/docs/pipeline.md` 4.2(전환 경로, `abandoned_at_turn` 기준 컬럼), `backend/docs/error-reasons.md`(`already_completed`).
- 구현: BE abandon 엔드포인트·엇갈린 결과 무시·WS 닫기·`/me/interviews`·재도전 조건, FE 이탈 모달·레포 재선택 호출·`RepoSelect` 이동·마이페이지 행.
- 공개 enum·DB 컬럼은 바꾸지 않는다. `abandoned_at_turn`은 DB 모델의 `current_turn`을 쓸지 BE가 확정한다(`pipeline.md`는 `turn_count`로 적혀 있다).
- 범위 밖: heartbeat·timeout 기반 자동 판정(Sprint 2), 중단된 면접의 답변 기록 보기·부분 리포트.

## 대체 관계

이전 결정을 대체하지 않는다. 기존 "언제 abandoned가 되는가" 정책([AI 0010](../../ai/decisions/0010-sprint1-interface-runtime-decisions.md))에 전환 방법을 더한다.
