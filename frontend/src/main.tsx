import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import AppRoutes from './routes';
import { Providers } from './providers';
import './index.css';

/**
 * mock 워커는 첫 요청보다 먼저 준비돼야 한다.
 * start()를 기다리지 않고 렌더하면 초기 쿼리가 워커를 비켜 나간다.
 */
async function bootstrap() {
  if (import.meta.env.DEV && import.meta.env.VITE_USE_MSW !== 'false') {
    const { startMockWorker } = await import('./mocks/start');
    try {
      await startMockWorker();
    } catch (error) {
      /**
       * 워커 등록은 브라우저 설정·시크릿 창·확장 프로그램 때문에 실패할 수 있다.
       * 여기서 throw하면 render까지 못 가 화면이 통째로 비어 원인을 찾기 어려워진다.
       * mock 없이라도 앱은 띄우고, API 요청이 왜 HTML을 받는지 콘솔로 알린다.
       */
      console.error(
        '[msw] 워커를 시작하지 못했습니다. mock 없이 앱만 띄웁니다. /api 요청은 dev server로 넘어가 index.html을 받습니다.',
        error,
      );
    }
  }

  createRoot(document.getElementById('root')!).render(
    <Providers>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </Providers>,
  );
}

void bootstrap();
