# 공통 계약

상태: Sprint 1 FIX. 이 디렉터리는 FE/BE가 함께 맞추는 API 계약 원본이다.

## 원본

- API surface: `openapi.yaml`
- 공통 오류 envelope: `api-error.schema.json`
- 변경/보류 추적: `migration.md`

다음 세 가지는 `frontend/docs/api-spec.md`에서 별도로 정의한다(`openapi.yaml`의 `info.description` 참고).

| 대상 | 경로 | api-spec.md 번호 |
| --- | --- | --- |
| WebSocket 업그레이드 | `/ws/interviews/{sessionId}` | #18 |
| SSE 스트림 | `/analysis-runs/{runId}/events` | #13 |
| 브라우저 이동 경로 | `/auth/github/login`, `/auth/github/callback`, `/auth/github/link`, `/auth/github/link/callback` | #1 · #2 · #7 · #8 |

이 범위 밖에서 FE 문서와 backend docs가 이 계약과 충돌하면 `openapi.yaml`을 우선한다. 단, `PENDING_FE`, `PENDING_AI`, `PENDING_TEAM`으로 표시된 항목은 구현자가 임의 확정하지 않는다.

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

인증의 저장·보안 결정은 [0002 GitHub OAuth와 DEVON 세션](../decisions/0002-github-oauth.md)을 따른다. `/auth/github/link*`와 초기 저장소 동기화는 현재 로그인 구현에 포함하지 않는다. 오류의 `details`는 선택 필드이며 현재 인증 서버는 빈 객체라도 반환한다.

## 보류 표시

- `PENDING_FE`: FE 라우팅, 상태머신, UX와 함께 결정해야 한다.
- `PENDING_AI`: AI 리드가 모델/검색/프롬프트 구조를 확정해야 한다.
- `PENDING_TEAM`: 팀 자료 보충 또는 평가 기준 합의가 필요하다.
