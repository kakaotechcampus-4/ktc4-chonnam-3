# 배포 · CORS · 쿠키 · CI

## 1. API 요청 경로 — Vercel rewrite

FE 는 Vercel 이고 `vercel.json` 은 지금 **SPA 폴백만** 있다.

```json
{ "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }] }
```

`shared/api.ts` 가 `BASE = '/api'` 로 **상대 경로**를 쓰므로, 이대로 배포하면 모든 API 요청이
`index.html` 을 받는다. 선택지 둘.

| | 방식 | 판단 |
|---|---|---|
| A | `vercel.json` 에 `/api/(.*)` → `https://api.../$1` rewrite 를 **SPA 폴백보다 앞에** 추가 | ✓ FE 코드 무수정. REST 는 same-origin 이 되어 쿠키가 단순해진다 |
| B | `VITE_API_BASE` 로 절대 URL | FE 수정 필요 |

**A 채택.** 단 WebSocket 은 Vercel rewrite 로 프록시되지 않으므로 **WS 만 백엔드 도메인에
직접 붙는다** (`wss://api.../ws/interviews/{sessionId}`). WS URL 은 `shared/api.ts` 에 없으니
(별도 훅) 충돌하지 않는다.

## 2. 쿠키 · CORS

WS 가 백엔드 도메인에 직접 붙으므로 쿠키는 **cross-site 전송이 가능해야 한다.**

```
Set-Cookie: devon_session=...; HttpOnly; Secure; SameSite=None; Path=/
```

CORS 는 `allow_credentials=True` + `allow_origins=[FRONTEND_ORIGIN]`
(**와일드카드 금지** — credentials 와 함께 쓸 수 없다).

| 환경 | Secure | SameSite | CORS |
|---|---|---|---|
| local (vite proxy) | false | lax | 불필요 |
| prod | true | none | Vercel 도메인만 허용 |

⚠ `SameSite=None` 은 `Secure` 없이는 브라우저가 버린다. **prod 는 HTTPS 필수다.**

## 3. 로컬 — vite 프록시

`frontend/vite.config.ts` 에 프록시를 추가해야 한다 (현재 없음 — **FE 작업 항목**).

```ts
server: {
  proxy: {
    '/api': { target: 'http://localhost:8000', changeOrigin: true },
    '/ws':  { target: 'ws://localhost:8000', ws: true },
  },
}
```

→ 로컬은 같은 오리진이 되므로 `SameSite=lax` 로 충분하고 CORS 설정이 필요 없다.

## 4. CI

`.github/workflows/backend-ci.yml` 을 **새로 추가**한다.

```yaml
on:
  pull_request:
    paths: ['backend/**']       # FE PR 에서 BE CI 가 돌지 않게
jobs: ruff → mypy → pytest (services: postgres:15, redis:7)
```

CODEOWNERS 의 [팀 자유 영역] 이 팀 자체 CI 추가를 명시적으로 허용한다. 운영 3파일
(`assign-mentor` / `notify-discord` / `convention-check`)과 `CODEOWNERS` 만 건드리지 않으면 된다.

## 5. 브랜치 / PR

`frontend/README.md` 와 동일한 규칙이다.

- `develop` 에서 분기, PR 도 `develop` 으로
- 브랜치명 `feature/be-xxx`, `fix/be-xxx`
- `develop → main` PR 만 멘토 리뷰 + 컨벤션 봇 발동

## 6. 보안

🚨 **이 repo 는 public 이다.** 키를 코드·문서·노트북 본문에 붙여넣지 않는다. 실수했으면 지우는
게 아니라 **폐기(rotate)** 한다. (`.gitignore` 상단 경고 참조 — 1단계에 실제로 8건 유출됐다.)

GitHub 토큰은 `BYTEA` + AES-GCM 으로 암호화해 저장한다 (`app/core/crypto.py`, 키는
`TOKEN_ENCRYPTION_KEY`). 평문 저장 금지.
