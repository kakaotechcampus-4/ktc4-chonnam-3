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

## 보류 표시

- `PENDING_FE`: FE 라우팅, 상태머신, UX와 함께 결정해야 한다.
- `PENDING_AI`: AI 리드가 모델/검색/프롬프트 구조를 확정해야 한다.
- `PENDING_TEAM`: 팀 자료 보충 또는 평가 기준 합의가 필요하다.
