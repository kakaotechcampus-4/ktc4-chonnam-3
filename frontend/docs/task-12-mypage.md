# task-12 — mypage 구현

> 필요: task-07 (`shared/api.ts`, 인증 가드, 재연동 배너)
> 근거: `spec/frontend/features/mypage.md`

## 목표

마이페이지(내 정보 + 면접 이력 + 로그아웃)를 구현한다.

## 작업

- 마이페이지 라우트: `/mypage` — [기존 라우트](../src/routes.tsx) 유지
- 내 정보 카드
- GitHub 연동 배지
- 면접 이력 테이블 + 페이지네이션
- 이력 0건 empty state
- 로그아웃 확인 모달
- `정보 수정` 버튼 처리 방침 결정 (비활성 vs 미노출, `PENDING_TEAM`)

## 완료 조건

- [ ] 마이페이지 라우트
- [ ] 내 정보 카드
- [ ] GitHub 연동 배지
- [ ] 면접 이력 테이블 + 페이지네이션
- [ ] 이력 0건 empty state
- [ ] 로그아웃 확인 모달
- [ ] `정보 수정` 버튼 처리 방침 결정
- [ ] `npm run build` 통과
- [ ] `npm run lint` 통과

## 후속 — 중단된 면접 행 ([공통 0009](../../spec/shared/decisions/0009-interview-abandon-transition.md), 선행: BE `GET /me/interviews`의 abandoned 포함·재도전 조건 구현)

- `completed`와 `startedAt`이 있는 `abandoned`를 표시
- abandoned 행: 일시 `startedAt`, 점수 자리 "중단됨", `리포트 보기` 대신 `다시 도전하기`(`POST /interviews/{id}/retry`)
- 재도전 실패 안내는 리포트의 reason별 문구를 공용으로 써서 행 아래에 표시
- 헤더를 `완료 {totalCount}회`로 표기
- MSW: `/me/interviews`에 시작 후 중단·준비 중 중단 면접 fixture

### 완료 조건

- [ ] 중단된 면접 행 표시 (준비 단계에서 버린 면접은 제외)
- [ ] `다시 도전하기` 성공 시 준비 화면 이동, 실패 reason별 안내
- [ ] 헤더 `완료 {totalCount}회`
- [ ] MSW fixture와 Playwright 시나리오

## 커밋

```
feat: add my page with interview history
```
