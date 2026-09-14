# 작업 03 — 라우팅 + 빈 컴포넌트

## 목표

화면 10개의 경로를 미리 등록하고 동결한다.

> [!important] 이 파일은 W5 이후 아무도 건드리지 않는다
> `routes.tsx`는 화면을 만들 때마다 라우트를 추가해야 하므로 가장 충돌이 잦은 파일이다. 10개를 미리 등록해두면 담당자는 자기 컴포넌트 파일 내용만 채우면 된다.

## 작업

### 1. React Router 설치

```bash
npm i react-router-dom
```

### 2. 빈 컴포넌트 10개 생성

각 파일은 껍데기로 둔다.

```tsx
export default function MyPage() {
  return <div>MyPage</div>;
}
```

| 파일 | 화면 |
| --- | --- |
| `src/features/auth/Login.tsx` | 1 로그인 |
| `src/features/home/Home.tsx` | 3 홈 대시보드 |
| `src/features/mypage/MyPage.tsx` | 7 마이페이지 |
| `src/features/analysis/JobInput.tsx` | 4-v2 공고 입력 |
| `src/features/analysis/Analyzing.tsx` | 4-2-v2 분석 중 |
| `src/features/analysis/AnalysisFailed.tsx` | 4-3-v2 분석 실패 |
| `src/features/analysis/RepoSelect.tsx` | 5a-v2 레포 선택 |
| `src/features/interview/InterviewPrepare.tsx` | 5a2-v2 면접 준비 |
| `src/features/interview/InterviewScreen.tsx` | 5b-v2 면접 진행 |
| `src/features/report/Report.tsx` | 5c-v2 면접 리포트 |

### 3. routes.tsx

`src/routes.tsx`

```tsx
import { Routes, Route, Navigate } from 'react-router-dom';

import Login from '@/features/auth/Login';
import Home from '@/features/home/Home';
import MyPage from '@/features/mypage/MyPage';
import JobInput from '@/features/analysis/JobInput';
import Analyzing from '@/features/analysis/Analyzing';
import AnalysisFailed from '@/features/analysis/AnalysisFailed';
import RepoSelect from '@/features/analysis/RepoSelect';
import InterviewPrepare from '@/features/interview/InterviewPrepare';
import InterviewScreen from '@/features/interview/InterviewScreen';
import Report from '@/features/report/Report';

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/home" element={<Home />} />
      <Route path="/mypage" element={<MyPage />} />
      <Route path="/interview/new" element={<JobInput />} />
      <Route path="/interview/analyzing/:runId" element={<Analyzing />} />
      <Route path="/interview/failed/:runId" element={<AnalysisFailed />} />
      <Route path="/interview/repos/:runId" element={<RepoSelect />} />
      <Route path="/interview/:id/prepare" element={<InterviewPrepare />} />
      <Route path="/interview/:id/session" element={<InterviewScreen />} />
      <Route path="/interview/:id/report" element={<Report />} />
      <Route path="*" element={<Navigate to="/home" replace />} />
    </Routes>
  );
}
```

`/interview/new`가 `/interview/:id/...` 보다 먼저 와야 한다.

### 4. main.tsx 연결

`<Routes>`는 `<BrowserRouter>` 안에 있어야 동작한다.

```tsx
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import AppRoutes from './routes';
import './index.css';

createRoot(document.getElementById('root')!).render(
  <BrowserRouter>
    <AppRoutes />
  </BrowserRouter>
);
```

기존 `App.tsx`는 사용하지 않으므로 삭제한다.

## 완료 조건

- [ ] `/home`, `/mypage` 등 각 경로 접속 시 해당 컴포넌트 텍스트가 뜬다
- [ ] `/interview/analyzing/run_abc` 접속 시 Analyzing이 뜬다
- [ ] 정의되지 않은 경로 접속 시 `/home`으로 이동한다
- [ ] `npm run build` 통과한다

## 커밋

```
feat: add routes with placeholder screens
```