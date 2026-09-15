# task-07 — /me 인증 API

> 선행: task-06
> 근거: `spec/shared/contracts/openapi.yaml`

## 목표

현재 로그인 사용자를 확인하는 `/api/me`만 구현한다. dashboard, profile, interview list, repository list API는 이 인증 작업 범위가 아니다.

## 작업

- access JWT를 검증하고 DB의 현재 account status를 확인한다. access 인증은 Redis에 의존하지 않는다.
- 응답은 `{name, avatarUrl, githubLinked}`이며 `avatarUrl`은 nullable이다.
- `githubLinked`는 GitHub account가 존재하고 `token_status=valid`일 때만 true다.

## 완료 조건

- 유효 access, 만료/변조/누락 access, suspended/withdrawn account를 테스트한다.
- standalone `me-response.schema.json` 및 OpenAPI와 응답 필드가 일치한다.
