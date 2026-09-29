import { HttpResponse, delay, http } from 'msw';

import { takeFault } from '../faults';
import { errorResponse, path } from '../http';
import { analysisHandlers } from './analysis';
import { documentHandlers } from './documents';
import { interviewHandlers } from './interview';
import { userHandlers } from './user';
import { interviewWsHandlers } from '../ws/interview';
import { hasMockSession } from '../session';
import { BASE } from '@/shared/api';

/** `timeout` 규칙에서 `delayMs`를 생략했을 때 기다리는 시간. */
const DEFAULT_TIMEOUT_MS = 30_000;

/**
 * 장애 주입을 맨 앞에서 가로챈다.
 *
 * 핸들러마다 실패 분기를 심으면 정상 경로가 지저분해지고 조합도 못 만든다.
 * 여기서 규칙에 맞는 요청만 가로채고, 맞는 규칙이 없으면 `undefined`를 돌려준다.
 * msw는 resolver가 `undefined`를 반환하면 다음 핸들러로 넘긴다 — 정상 흐름은 그대로다.
 */
const faultHandler = http.all(path('/*'), async ({ request }) => {
  const rule = takeFault(request);
  if (!rule) return undefined;

  const { pathname } = new URL(request.url);
  console.warn(`[msw] 장애 주입: ${request.method} ${pathname}`, rule);

  if (rule.kind === 'network') {
    return HttpResponse.error();
  }

  if (rule.kind === 'timeout') {
    // 응답 없이 매달리는 상황. 기다린 뒤에는 네트워크 실패와 같은 모양으로 끝낸다.
    await delay(rule.delayMs ?? DEFAULT_TIMEOUT_MS);
    return HttpResponse.error();
  }

  return errorResponse(
    rule.status ?? 500,
    rule.reason ?? 'internal_error',
    rule.message ?? '장애 주입으로 만든 실패 응답입니다.',
    { details: rule.details, retryAfter: rule.retryAfter },
  );
});

const sessionHandler = http.all(path('/*'), ({ request }) => {
  // 만료된 세션의 로그아웃도 204를 반환해야 하므로 도메인 핸들러까지 통과시킨다.
  if (new URL(request.url).pathname === `${BASE}/auth/logout` || hasMockSession()) {
    return undefined;
  }
  return errorResponse(401, 'unauthenticated', '로그인이 필요합니다.');
});

/**
 * 핸들러가 없는 API 요청을 잡는 마지막 그물.
 *
 * 이게 없으면 미구현 mock 요청이 개발 프록시를 통해 실제 서버로 넘어간다.
 * mock 누락을 서버 오류와 혼동하지 않도록 여기서 명시적인 오류로 반환한다.
 * 실제 서버는 501을 쓰지 않으므로 이 응답은 mock 누락이라는 뜻으로만 읽으면 된다.
 */
const missingHandler = http.all(path('/*'), ({ request }) => {
  const { pathname } = new URL(request.url);
  console.error(`[msw] 핸들러가 없는 요청: ${request.method} ${pathname}`);
  return errorResponse(
    501,
    'internal_error',
    `mock 핸들러가 없는 요청입니다: ${request.method} ${pathname}`,
  );
});

/** 도메인별 핸들러를 한 배열로 모은다. 등록 순서가 곧 매칭 우선순위다. */
export const handlers = [
  ...interviewWsHandlers,
  faultHandler,
  sessionHandler,
  ...userHandlers,
  ...documentHandlers,
  ...analysisHandlers,
  ...interviewHandlers,
  missingHandler,
];
