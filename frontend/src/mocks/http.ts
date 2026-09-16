import { HttpResponse } from 'msw';

import { BASE } from '@/shared/api';
import type { ContractError } from '@/types/contract';

/** 핸들러가 돌려줄 수 있는 응답 본문. 성공 스키마는 고정하고 공통 에러만 함께 허용한다. */
export type Res<T> = T | ContractError;

/** 핸들러 경로는 항상 api 클라이언트의 BASE를 따라간다. prefix가 바뀌면 mock도 같이 움직인다. */
export function path(suffix: string) {
  return `${BASE}${suffix}`;
}

/**
 * 공통 에러 envelope. `backend/docs/error-reasons.md`의 reason만 사용한다.
 * 새 reason이 필요하면 레지스트리에 먼저 추가하고 쓴다.
 */
export function errorResponse(
  status: number,
  reason: string,
  message: string,
  extra?: { details?: Record<string, unknown>; retryAfter?: number },
) {
  return HttpResponse.json<ContractError>({ error: { reason, message, ...extra } }, { status });
}

/**
 * 시나리오 전환용 스위치.
 * 우선순위: 쿼리스트링 `?scenario=` > localStorage `msw.<key>` > 기본값.
 */
export function pickScenario(request: Request, key: string, fallback: string) {
  const fromQuery = new URL(request.url).searchParams.get('scenario');
  if (fromQuery) return fromQuery;
  try {
    return localStorage.getItem(`msw.${key}`) ?? fallback;
  } catch {
    return fallback;
  }
}
