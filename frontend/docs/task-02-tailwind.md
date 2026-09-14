# 작업 02 — Tailwind + 경로 alias

## 목표

디자인 토큰을 이식하고 `@` alias를 설정한다.

## 작업

### 1. Tailwind 설치

```bash
npm i -D tailwindcss @tailwindcss/vite
```

Tailwind v4 기준으로 설치한다. v3와 설정 방식이 다르므로 버전을 먼저 확인하고, 확실하지 않으면 물어본다.

### 2. 디자인 토큰

프로토타입 확정값이다. 그대로 적용한다.

| 토큰 | 값 |
| --- | --- |
| ink | #1B1C20 |
| muted | #6C7078 |
| line | #CDD2D8 |
| line-soft | #E6E8EB |
| accent | #3652FF |
| accent-soft | #ECEFFF |
| paper | #F6F6F3 |
| surface | #FFFFFF |
| error | #E5484D |
| error-soft | #FDECEC |

- 폰트: `Pretendard Variable` → `Pretendard` → `-apple-system` → `sans-serif`
- 카드 radius: `10px` (`borderRadius.card`)
- 다크 모드는 **미지원** — 토큰을 만들지 않는다

### 3. 경로 alias

`@` → `src` 를 **양쪽 모두**에 설정한다.

- `vite.config.ts` — `resolve.alias`
- `tsconfig.json` — `compilerOptions.paths`

한쪽만 하면 `npm run dev`는 되고 `npm run build`가 실패한다.

## 완료 조건

- [ ] `className="bg-accent text-ink"` 가 동작한다
- [ ] Tailwind IntelliSense 자동완성에 토큰이 뜬다
- [ ] `import x from '@/shared/...'` 가 동작한다
- [ ] `npm run build` 통과한다

## 커밋

```
chore: add tailwind design tokens and path alias
```