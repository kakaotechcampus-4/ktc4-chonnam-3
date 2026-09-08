# task-06 — GitHub OAuth 인증

> 선행: task-03, task-05
> 설계 근거: [becontext.md](../../becontext.md) · [db-schema.md](db-schema.md)

## 목표

GitHub OAuth 4경로 + Redis 세션 + `/me` + `/auth/logout`.

## 확정본 반영 (becontext.md 대비 변경)

- **`core/crypto.py` 신규** — 토큰은 AES-GCM 으로 암호화해 `BYTEA` 에 넣는다. 평문 저장 금지.
- 401 수신 시 `github_accounts.token_status=revoked` UPDATE → 이후 요청은 GitHub 호출 전 차단.
- 연동 직후 **`initial_sync`(M1) 를 enqueue** 한다.
- `users.status` 가 `suspended` / `withdrawn` 이면 로그인 차단 (대응 reason 미확정).

## 작업

- [ ] TODO

## 완료 조건

- [ ] TODO

## 커밋 메시지

```
TODO
```
