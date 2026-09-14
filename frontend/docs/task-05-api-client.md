# 작업 05 — API 클라이언트

> 선행: task-04 완료

## 목표

모든 API 호출이 경유할 래퍼와 함수 18개를 만든다.

## 규칙

> [!important] `credentials: 'include'`는 이 파일 한 곳에만 존재한다
> 컴포넌트에서 `fetch`를 직접 쓰지 않는다. 각자 쓰면 누군가는 반드시 빠뜨리고, Mock에서는 안 보이다가 실제 서버 연동에서 전 화면이 401이 된다.

## 래퍼

`src/shared/api.ts`

```ts
import type { ApiError } from '@/types/api';

const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    credentials: 'include',
  });

  if (!res.ok) {
    const error: ApiError = await res.json();
    throw error;
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}
```

JSON 요청은 `Content-Type: application/json` 헤더를 붙이고, multipart는 **붙이지 않는다** (브라우저가 boundary와 함께 자동 생성).

## 함수 목록

명세의 18개 엔드포인트를 `api` 객체에 정의한다.

```ts
export const api = {
  getMe: () => request<MeResponse>('/me'),
  getHome: () => request<HomeResponse>('/me/home'),
  // ...
};
```

### 리다이렉트 경로는 포함하지 않는다

아래는 `fetch`가 아니라 브라우저 이동이므로 이 파일에 넣지 않는다.

- `GET /auth/github/login`
- `GET /auth/github/callback`
- `GET /auth/github/link`
- `GET /auth/github/link/callback`

화면에서 `<a href>` 또는 `window.location`으로 처리한다.

### WebSocket도 제외

`/ws/interviews/{sessionId}` 는 별도 훅에서 `new WebSocket()`으로 처리한다.

## 완료 조건

- [ ] REST 엔드포인트 함수가 모두 정의됨
- [ ] 반환 타입이 `types/api.ts`와 연결됨
- [ ] `fetch`가 이 파일에만 등장
- [ ] `npm run build` 통과

## 커밋

```
feat: add api client wrapper
```