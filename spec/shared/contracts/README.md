# 공통 계약

상태: Sprint 1 FIX. 이 디렉터리는 FE/BE가 함께 맞추는 API 계약 원본이다.

## 원본

- API surface: `openapi.yaml`
- 공통 오류 envelope: `api-error.schema.json`
- 변경/보류 추적: `migration.md`

FE 문서와 backend docs가 이 계약과 충돌하면 `openapi.yaml`을 우선한다. 단, `PENDING_FE`, `PENDING_AI`, `PENDING_TEAM`으로 표시된 항목은 구현자가 임의 확정하지 않는다.

## 공통 규약

- API 요청/응답 필드는 camelCase.
- Python/DB 필드는 snake_case.
- 모든 4xx/5xx는 공통 envelope를 사용한다.

```json
{
  "error": {
    "reason": "invalid_repository",
    "message": "선택할 수 없는 레포지토리입니다.",
    "details": {}
  }
}
```

- `reason`은 FE 분기용 stable string이다.
- 내부 job/LLM 실패는 DB `error_code`에 남기고 API 표면에서는 flow별 reason으로 매핑한다.

## 인증 계약

- 현재 인증 API는 `/api/auth/github/login`, `/api/auth/github/callback`, `/api/auth/refresh`, `/api/auth/logout`, `/api/me` 다섯 개다.
- DEVON access/refresh JWT는 HttpOnly cookie로만 전달하며 body나 브라우저 저장소에 노출하지 않는다.
- `/api/me`는 `name`, nullable `avatarUrl`, `githubLinked`를 항상 반환한다. `githubLinked`는 GitHub account가 있고 `token_status=valid`이며 access 또는 refresh가 사용 가능할 때 true다. 기존 비만료 token은 valid이면 true다. 이 판정은 DB만 읽으며 GitHub API 호출·갱신을 실행하지 않는다.
- GitHub token의 갱신·폐기는 BE 내부에서 처리하며 DEVON JWT session과 별개다. GitHub token·만료 시각을 응답에 추가하거나 새 공개 갱신 경로를 만들지 않는다.
- refresh/logout은 `Origin`이 정확한 `FRONTEND_ORIGIN`과 같아야 한다. PostgreSQL만 Refresh 유효·폐기의 원본이며 DB 장애를 성공으로 숨기지 않는다. Redis 장애는 OAuth state에 영향을 주지만 기존 session의 refresh/logout에는 영향을 주지 않는다.
- 상세 보안·저장 결정은 [0002 GitHub OAuth와 DEVON 세션](../decisions/0002-github-oauth.md)을 따른다.

## 보류 표시

- `PENDING_FE`: FE 라우팅, 상태머신, UX와 함께 결정해야 한다.
- `PENDING_AI`: AI 리드가 모델/검색/프롬프트 구조를 확정해야 한다.
- `PENDING_TEAM`: 팀 자료 보충 또는 평가 기준 합의가 필요하다.
