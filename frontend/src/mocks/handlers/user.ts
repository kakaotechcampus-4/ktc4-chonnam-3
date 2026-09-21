import { HttpResponse, delay, http, type PathParams } from 'msw';

import type {
  HomeResponse,
  InterviewListResponse,
  MeProfileResponse,
  MeResponse,
} from '@/types/api';
import { homeScenarios, interviewPage, me, meProfile, meUnlinked } from '../fixtures/user';
import { errorResponse, path, pickScenario, type Res } from '../http';

/**
 * 이 파일의 4개 조회 경로는 모두 spec/shared/contracts/openapi.yaml 에 정의돼 있다.
 * 응답 타입은 계약 원본과 일치하는 src/types/api.ts 를 쓴다.
 */
export const userHandlers = [
  http.get<PathParams, never, MeResponse>(path('/me'), async ({ request }) => {
    await delay(150);
    const scenario = pickScenario(request, 'me', 'linked');
    if (scenario === 'unlinked') return HttpResponse.json<MeResponse>(meUnlinked);
    return HttpResponse.json<MeResponse>(me);
  }),

  http.get<PathParams, never, MeProfileResponse>(path('/me/profile'), async () => {
    await delay(200);
    return HttpResponse.json<MeProfileResponse>(meProfile);
  }),

  /**
   * 401 인터셉터가 single-flight 로 호출한다. 자신은 인터셉터 대상에서 제외된다.
   * mock 은 항상 성공한다. 갱신 실패(401) 시나리오는 인증 실패 케이스 작업 범위다.
   */
  http.post<PathParams, never, undefined>(path('/auth/refresh'), async () => {
    await delay(100);
    return new HttpResponse(null, { status: 204 });
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

  /**
   * TODO(contract): status 쿼리 파라미터로 서버 필터링하는 안을 BE에 제안해 둔 상태다(PR #28 리뷰).
   * openapi.yaml 에 아직 없으므로 mock 이 임의로 구현하지 않는다. 합의되면 여기에 추가한다.
   */
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
