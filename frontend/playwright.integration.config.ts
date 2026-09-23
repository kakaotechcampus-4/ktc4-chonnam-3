import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests-integration',
  outputDir: '../.claude/scratch/oauth-session-browser/results',
  workers: 1,
  reporter: 'list',
  use: { baseURL: 'http://localhost:5173', trace: 'retain-on-failure' },
  webServer: [
    {
      // GitHub HTTP만 대체하는 서버로 실제 앱·테스트 DB·Redis의 세션 흐름을 검증한다.
      command:
        'python -m uvicorn oauth_browser_app:app --app-dir tests --host 127.0.0.1 --port 8000 --no-access-log',
      cwd: '../backend',
      url: 'http://127.0.0.1:8000/api/health',
      reuseExistingServer: false,
    },
    {
      command: 'npm run dev -- --host localhost --port 5173 --strictPort',
      url: 'http://localhost:5173',
      env: { VITE_USE_MSW: 'false' },
      reuseExistingServer: false,
    },
  ],
});
