import { HttpResponse, delay, http, type PathParams } from 'msw';

import type { HomeResponse, InterviewListResponse, MeResponse } from '@/types/api';
import { homeScenarios, interviewPage, me, meUnlinked } from '../fixtures/user';
import { errorResponse, path, pickScenario, type Res } from '../http';

/**
 * GET /me 는 spec/shared/contracts/me-response.schema.json 으로 이관된 계약이다.
 * 나머지 경로는 아직 이관 전이라 frontend/docs/api-spec.md 를 기준으로 둔다.
 * 이관되면 응답 타입을 src/types/contract.ts 로 옮긴다.
 */
export const userHandlers = [
  http.get<PathParams, never, MeResponse>(path('/me'), async ({ request }) => {
    await delay(150);
    const scenario = pickScenario(request, 'me', 'linked');
    if (scenario === 'unlinked') return HttpResponse.json<MeResponse>(meUnlinked);
    return HttpResponse.json<MeResponse>(me);
  }),

  http.post<PathParams, never, undefined>(path('/auth/logout'), async () => {
    await delay(100);
    return new HttpResponse(null, { status: 204 });
  }),

  http.get<PathParams, never, Res<HomeResponse>>(path('/me/home'), async ({ request }) => {
    await delay(300);
    const scenario = pickScenario(request, 'home', 'completed');
    const body = homeScenarios[scenario];
    if (!body) {
      return errorResponse(
        400,
        'internal_error',
        `알 수 없는 mock 시나리오: ${scenario}. 사용 가능: ${Object.keys(homeScenarios).join(', ')}`,
      );
    }
    return HttpResponse.json<HomeResponse>(body);
  }),

  http.get<PathParams, never, InterviewListResponse>(
    path('/me/interviews'),
    async ({ request }) => {
      await delay(300);
      const params = new URL(request.url).searchParams;
      const page = Number(params.get('page') ?? 1);
      const size = Number(params.get('size') ?? 20);
      return HttpResponse.json<InterviewListResponse>(interviewPage(page, size));
    },
  ),
];
