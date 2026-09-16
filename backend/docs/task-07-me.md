# task-07 — /me 계열 API

> 선행: task-06
> 근거: `spec/backend/features/report.md`

## 목표

`/me`, `/me/home`, `/me/interviews`, `/me/repositories`를 구현한다.

## 작업

- `/me`는 현재 사용자 기본 정보를 반환한다.
- `/me/home`은 Sprint 1에서 최소 DB 집계와 `user_profile_summaries` 기반 shape를 맞춘다.
- 집계 기준은 완료 면접에 사용된 repo다.
- `/me/interviews`는 pagination으로 면접 목록을 반환한다.
- `/me/repositories`는 수집된 public repo 목록을 반환하되 분석 후보 pagination과 혼동하지 않는다.
- `profile_summary` job은 report 생성 성공 후 백그라운드 갱신한다.

## 완료 조건

- 빈 데이터 사용자, 분석 중 사용자, 완료 면접 보유 사용자 응답을 테스트한다.
- profile summary가 없어도 홈 응답이 깨지지 않는다.
