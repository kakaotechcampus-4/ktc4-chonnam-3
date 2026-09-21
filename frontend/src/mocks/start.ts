import { BASE } from '@/shared/api';

/**
 * mock 워커를 켠다. 프로덕션 번들에 들어가지 않도록 항상 동적 import로만 부른다.
 */
export async function startMockWorker() {
  const { worker } = await import('./browser');

  await worker.start({
    serviceWorker: { url: '/mockServiceWorker.js' },
    /**
     * `${BASE}/*` 는 handlers의 마지막 catch-all이 501로 잡아 준다.
     * 그 밖의 요청(vite 정적 자산·HMR 등)은 그대로 통과시켜야 앱이 뜬다.
     */
    onUnhandledRequest: 'bypass',
  });

  console.info(
    `[msw] mock API 사용 중 (${BASE}/*). 실제 로그인 검증 시 VITE_USE_MSW를 제거하거나 false로 설정한다.`,
  );
}
