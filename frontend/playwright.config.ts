import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  outputDir: '../.claude/scratch/oauth-session-frontend/results',
  fullyParallel: true,
  workers: 3,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:5174',
    trace: 'retain-on-failure',
  },
  webServer: {
    // 개발 중인 서버의 MSW 설정에 좌우되지 않도록 별도 포트에 테스트 서버를 띄운다.
    command: 'npm run dev -- --host localhost --port 5174 --strictPort',
    url: 'http://localhost:5174',
    reuseExistingServer: false,
    env: { VITE_USE_MSW: 'true' },
  },
});
