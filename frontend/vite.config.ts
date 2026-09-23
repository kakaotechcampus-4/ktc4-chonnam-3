import path from 'node:path';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// https://vite.dev/config/
export default defineConfig({
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
