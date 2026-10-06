import path from 'node:path';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { createLogger, defineConfig } from 'vite';

const logger = createLogger();
const logError = logger.error;
logger.error = (message, options) => {
  // 프록시 연결 실패 로그의 전체 URL에 OAuth code·state가 포함될 수 있다.
  logError(
    message.includes('http proxy error:') ? 'API 프록시 요청을 전달하지 못했습니다.' : message,
    options,
  );
};

// https://vite.dev/config/
export default defineConfig({
  customLogger: logger,
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true, ws: true },
      // 공개 콜백 경로와 oauthState 쿠키 경로는 유지하고 서버에 전달할 때만 /api를 붙인다.
      '/auth/github': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (url) => `/api${url}`,
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
});
