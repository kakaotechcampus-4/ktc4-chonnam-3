# task-11 — report 구현

> 필요: task-07 (`shared/api.ts`, 인증 가드, 재연동 배너)
> 근거: `spec/frontend/features/report.md`

## 목표

면접 리포트 3탭, 재도전 화면을 구현한다. 피드백 이의 제기는 `spec/shared/contracts/migration.md` FIX(Sprint 1 테이블만, API/row 생성은 Sprint 2)에 따라 버튼만 배치하고 항상 비활성으로 둔다.

## 작업

- 5c-v2 라우트 (경로 미확정)
- 탭 컴포넌트 3개 — `activeTab`은 URL 쿼리와 동기화 (새로고침·공유 시 탭 유지)
- `scores` 6개 시각화
- `coverage` 표시
- `agentFeedbacks` 3개 카드 + 이의 제기 버튼(항상 비활성, 클릭 핸들러·모달 없음)
- `202 generating` 폴링
- `409 report_unavailable` empty state
- 재도전 버튼 + 409/410 분기

Sprint 2 대상이라 이번에 만들지 않는 것: 이의 제기 모달, `POST /reports/{id}/feedback-disagreements` 호출, `disagreementSubmitted` 연동.

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
