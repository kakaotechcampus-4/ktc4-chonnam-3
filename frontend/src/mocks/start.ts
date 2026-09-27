import { BASE } from '@/shared/api';
import { installMockConsole } from './scenarios';

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
    `[msw] mock API 사용 중 (${BASE}/*). 끄려면 frontend/.env.local 에 VITE_USE_MSW=false 를 둔다.`,
  );

  // 켜 둔 장애 주입 규칙을 잊고 "왜 안 되지"로 시간을 버리는 사고를 막는다.
  installMockConsole();
}
