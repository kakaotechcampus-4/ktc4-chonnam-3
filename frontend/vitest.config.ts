import path from 'node:path';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// Playwright 스펙(tests/)과 섞이지 않도록 src 안의 *.test만 단위 테스트로 본다.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, './src') },
  },
  test: {
    include: ['src/**/*.test.{ts,tsx}'],
    environment: 'node',
    // jsdom이 필요한 파일은 맨 위에 `// @vitest-environment jsdom`을 쓴다.
    environmentOptions: { jsdom: { url: 'https://devon.test' } },
  },
});
