# 작업 01 — 프로젝트 세팅

## 목표

Prettier·ESLint 설정을 완료하고 팀 공유 설정을 커밋한다.

## 작업

### 1. Prettier 설정

`.prettierrc` 생성

```json
{
  "semi": true,
  "singleQuote": true,
  "printWidth": 100,
  "tabWidth": 2,
  "trailingComma": "all"
}
```

`.prettierignore` 생성 — `dist`, `node_modules`, `*.md`

### 2. ESLint + Prettier 연동

Vite 기본 ESLint 설정에 Prettier 충돌 방지 추가.

```bash
npm i -D prettier eslint-config-prettier
```

`eslint.config.js`에 `eslint-config-prettier`를 마지막에 적용한다.

### 3. VS Code 설정 (팀 공유 — 반드시 커밋)

`.vscode/settings.json`

```json
{
  "editor.formatOnSave": true,
  "editor.defaultFormatter": "esbenp.prettier-vscode",
  "editor.codeActionsOnSave": {
    "source.fixAll.eslint": "explicit"
  }
}
```

`.vscode/extensions.json`

```json
{
  "recommendations": [
    "dbaeumer.vscode-eslint",
    "esbenp.prettier-vscode",
    "bradlc.vscode-tailwindcss"
  ]
}
```

### 4. package.json 스크립트

```json
"scripts": {
  "dev": "vite",
  "build": "tsc --noEmit && vite build",
  "lint": "eslint src",
  "format": "prettier --write src",
  "preview": "vite preview"
}
```

`build`에 `tsc --noEmit`을 넣어 타입 에러 시 배포가 실패하게 한다.

## 완료 조건

- [ ] `npm run dev` 실행되고 화면이 뜬다
- [ ] `npm run build` 통과한다
- [ ] `.tsx` 파일 들여쓰기를 망가뜨리고 `Ctrl+S` 하면 자동 정리된다
- [ ] `npm run lint` 통과한다

## 커밋

```
chore: setup prettier, eslint, vscode settings
```
