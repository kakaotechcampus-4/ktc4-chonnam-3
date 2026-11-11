// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';

import { api, BASE } from '@/shared/api';
import { clearSessionQueries } from '@/shared/queryClient';

function stubFetch(response: Response) {
  const fetchMock = vi.fn().mockResolvedValue(response);
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('api 요청 래퍼', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('/api 접두사와 쿠키 포함 옵션으로 요청하고 JSON 본문을 돌려준다', async () => {
    const fetchMock = stubFetch(Response.json({ name: '김개발' }));

    await expect(api.getMe()).resolves.toEqual({ name: '김개발' });

    expect(fetchMock).toHaveBeenCalledWith('/api/me', { credentials: 'include' });
  });

  it('204 응답은 본문 없이 undefined를 돌려준다', async () => {
    const fetchMock = stubFetch(new Response(null, { status: 204 }));

    await expect(api.logout()).resolves.toBeUndefined();

    expect(fetchMock).toHaveBeenCalledWith('/api/auth/logout', {
      method: 'POST',
      credentials: 'include',
    });
  });

  it('오류 본문이 ApiError 형식이면 HTTP 상태를 덧붙여 던진다', async () => {
    stubFetch(
      Response.json({ error: { reason: 'run_expired', message: '만료' } }, { status: 410 }),
    );

    await expect(api.getAnalysisRun('r1')).rejects.toEqual({
      status: 410,
      error: { reason: 'run_expired', message: '만료' },
    });
  });

  it('JSON이 아닌 오류 본문은 unknown_error와 원문 메시지로 던진다', async () => {
    stubFetch(new Response('Bad Gateway', { status: 502 }));

    await expect(api.getMe()).rejects.toEqual({
      status: 502,
      error: { reason: 'unknown_error', message: 'Bad Gateway' },
    });
  });

  it('ApiError 형식이 아닌 JSON 오류도 unknown_error로 던진다', async () => {
    stubFetch(Response.json({ detail: 'nope' }, { status: 500 }));

    await expect(api.getMe()).rejects.toMatchObject({
      status: 500,
      error: { reason: 'unknown_error' },
    });
  });

  it('JSON 본문 요청은 Content-Type과 직렬화된 본문을 보낸다', async () => {
    const fetchMock = stubFetch(Response.json({ ok: true }));
    const body = { reasonType: 'other' } as Parameters<typeof api.submitFeedbackDisagreement>[1];

    await api.submitFeedbackDisagreement('i1', body);

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/interviews/i1/feedback-disagreements',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    );
  });

  it('SSE · WebSocket 주소에도 /api 접두사를 붙인다', () => {
    expect(BASE).toBe('/api');
    expect(api.analysisRunEventsUrl('r1')).toBe('/api/analysis-runs/r1/events');
    // jsdom 주소는 vitest.config.ts에서 https://devon.test로 고정했다.
    expect(api.interviewSocketUrl('s1')).toBe('wss://devon.test/api/ws/interviews/s1');
  });

  // 세션 종료 상태는 모듈 전역이라 되돌릴 수 없다. 이 파일의 마지막 테스트여야 한다.
  it('세션 종료 중에는 HTTP 요청 없이 AbortError를 던진다', async () => {
    const fetchMock = stubFetch(Response.json({}));
    await clearSessionQueries();

    await expect(api.getMe()).rejects.toMatchObject({ name: 'AbortError' });

    expect(fetchMock).not.toHaveBeenCalled();
  });
});
