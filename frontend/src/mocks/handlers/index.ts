import { http } from 'msw';

import { errorResponse, path } from '../http';
import { analysisHandlers } from './analysis';
import { documentHandlers } from './documents';
import { interviewHandlers } from './interview';
import { userHandlers } from './user';

/**
 * 핸들러가 없는 API 요청을 잡는 마지막 그물.
 *
 * 이게 없으면 요청이 vite dev server로 흘러가고, SPA fallback이 index.html을 200으로 돌려준다.
 * 화면 쪽은 JSON 대신 HTML을 받아 "왜 데이터가 안 오지"로 시간을 버린다.
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
  ...userHandlers,
  ...documentHandlers,
  ...analysisHandlers,
  ...interviewHandlers,
  missingHandler,
];
