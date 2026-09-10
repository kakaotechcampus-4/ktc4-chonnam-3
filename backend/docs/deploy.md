# 배포 · CORS · 쿠키 · CI

상태: Sprint 1 구현 가이드. 실제 FE 배포 방식은 FE/인프라 결정에 맞춘다.

## API 경로

FE는 API를 상대 경로 `/api`로 호출하는 것을 기본으로 둔다. 배포 환경에서는 reverse proxy 또는 CDN rewrite가 `/api/*`를 backend로 전달해야 한다.

WebSocket 경로는 `/ws/interviews/{...}` 형태지만, identifier가 `interviewId`인지 별도 `sessionId`인지는 `PENDING_FE`다.

## 쿠키와 CORS

DEVON 자체 JWT 전달 방식은 `PENDING_FE`다. 결정 전까지 구현자는 아래 두 경로를 모두 고려해 구조를 분리한다.

- HttpOnly cookie only.
- 응답 body 포함.

쿠키 기반으로 확정될 경우:

- FE 요청은 `credentials: include`를 사용한다.
- same-origin 배포면 CORS 부담이 작다.
- cross-site 배포면 `allow_credentials=True`, 명시 origin allowlist, `Secure`, `SameSite=None`이 필요하다.

## 로컬 개발

- FastAPI: `uv run uvicorn app.main:app --reload --port 8000`
- FE dev server가 proxy를 제공하면 `/api`, `/ws`를 backend로 전달한다.
- proxy가 없으면 CORS allow origin을 로컬 FE 주소로 제한한다.

## CI

backend CI는 다음을 실행한다.

```text
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run pytest
```

GitHub, Wanted, LLM은 CI에서 실제 호출하지 않고 mock한다.

## 보안

- GitHub access token은 FE에 노출하지 않는다.
- GitHub token은 암호화해 DB에 저장한다.
- 로그에 token, authorization header, cookie 값을 남기지 않는다.
- private repo scope를 요청하지 않는다.
