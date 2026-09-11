# task-08 — home 구현

> 필요: task-07 (`shared/api.ts`, 인증 가드, 재연동 배너)
> 근거: `spec/frontend/features/home.md`

## 목표

로그인 직후 도착하는 홈 화면(프로필 패널 4상태, 최근 면접, 새 면접 시작)을 구현한다.

## 작업

- 헤더 컴포넌트 (탭, GitHub 배지, 아바타) — 전 화면 공용. 탭 활성 상태는 라우터 현재 경로에서 파생 (별도 상태 없음)
- 프로필 패널 4가지 상태 분기 (`syncing` / `no_repository` / `no_interview` / `completed`)
- 언어 비율 그래프
- 최근 면접 리스트
- `syncing` 폴링 — 간격은 `PENDING_TEAM`, 확정 후 적용
- 403 재연동 배너 연결

## 완료 조건

- [ ] 헤더 컴포넌트 (탭, GitHub 배지, 아바타)
- [ ] 프로필 패널 4가지 상태 분기
- [ ] 언어 비율 그래프
- [ ] 최근 면접 리스트
- [ ] `syncing` 폴링 (간격 확정 후)
- [ ] 403 재연동 배너 연결
- [ ] `npm run build` 통과
- [ ] `npm run lint` 통과

## 커밋

```
feat: add home dashboard screen
```
