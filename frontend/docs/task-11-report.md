# task-11 — report 구현

> 필요: task-07 (`shared/api.ts`, 인증 가드, 재연동 배너)
> 근거: `spec/frontend/features/report.md`

## 목표

면접 리포트 3탭, 재도전 화면을 구현한다. 피드백 이의 제기는 `spec/shared/contracts/migration.md` FIX(Sprint 1 테이블만, API/row 생성은 Sprint 2)에 따라 버튼만 배치하고 항상 비활성으로 둔다.

## 작업

- 5c-v2 라우트: `/interview/:id/report` — [기존 라우트](../src/routes.tsx)의 `:id`는 `interviewId`
- 탭 컴포넌트 3개 — `activeTab`은 URL 쿼리와 동기화 (새로고침·공유 시 탭 유지)
- `scores` 6개 시각화
- `coverage` 표시
- `agentFeedbacks` 3개 카드 + 이의 제기 버튼(항상 비활성, 클릭 핸들러·모달 없음)
- `202 generating` 폴링
- `409 report_unavailable` empty state
- 재도전 버튼 + 409/410 분기

Sprint 2 대상이라 이번에 만들지 않는 것: 이의 제기 모달, `POST /reports/{id}/feedback-disagreements` 호출, `disagreementSubmitted` 연동.

## 확인된 오류 — 수정 필요·보류

2026-09-22 사용자 승인에 따라 **리포트 화면의 통신 오류 처리 문제를 기록하고 실제 수정은 보류**한다.

- 현재 [Report.tsx](../src/features/report/Report.tsx)의 `reportQuery.error` 처리에서 일반 네트워크 오류에도 `.error.reason`을 읽어 추가 예외가 발생한다. 해당 표현에 `TypeError('Failed to fetch')`를 넣어 재현했으며, 같은 날 확인한 열린 [PR #34](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/34)의 `5e5d48123800661ed2953122b926fe041dc0c633`에도 동일한 코드가 남아 있다.
- 후속 보완은 기존 [isApiError](../src/types/api.ts)로 오류 형식을 확인한 뒤 `reason`을 읽도록 화면 코드를 맞추는 것이다. 일반 오류에는 기존 “리포트를 불러오지 못했어요.” 안내를 표시하고, `report_unavailable`의 기존 분기는 유지한다.
- DB 구조·API 형식·기존 안내 문구 변경은 필요 없다. 이번에는 코드와 원격 PR을 수정하지 않으며 수정·검증 완료로 처리하지 않는다.

## 완료 조건

- [ ] 5c-v2 라우트
- [ ] 탭 컴포넌트 3개
- [ ] `scores` 6개 시각화
- [ ] `coverage` 표시
- [ ] `agentFeedbacks` 3개 카드
- [ ] 이의 제기 버튼 항상 비활성 확인
- [ ] `202 generating` 폴링
- [ ] `409 report_unavailable` empty state
- [ ] 재도전 버튼 + 409/410 분기
- [ ] `npm run build` 통과
- [ ] `npm run lint` 통과

## 커밋

```
feat: add interview report screen with tabs and retry flow
```
