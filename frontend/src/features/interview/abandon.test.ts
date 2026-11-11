import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  abandonInterview,
  interviewPath,
  previousInterviewIdFrom,
} from '@/features/interview/abandon';
import { api } from '@/shared/api';
import { queryClient } from '@/shared/queryClient';
import { queryKeys } from '@/shared/queryKeys';

const apiError = (status: number, reason: string) => ({
  status,
  error: { reason, message: reason },
});

describe('abandonInterview', () => {
  afterEach(() => vi.restoreAllMocks());

  it('204면 abandoned를 돌려주고 면접·목록 캐시를 무효화한다', async () => {
    vi.spyOn(api, 'abandonInterview').mockResolvedValue(undefined);
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries').mockResolvedValue();

    await expect(abandonInterview('i1')).resolves.toBe('abandoned');

    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.interview('i1') });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.interviewsAll });
  });

  it('404 not_found면 정리할 면접이 없다는 뜻으로 null을 돌려준다', async () => {
    vi.spyOn(api, 'abandonInterview').mockRejectedValue(apiError(404, 'not_found'));

    await expect(abandonInterview('i1')).resolves.toBeNull();
  });

  it('409 already_completed면 면접을 다시 조회해 그 상태를 돌려준다', async () => {
    vi.spyOn(api, 'abandonInterview').mockRejectedValue(apiError(409, 'already_completed'));
    const get = vi
      .spyOn(api, 'getInterview')
      .mockResolvedValue({ status: 'preparing' } as Awaited<ReturnType<typeof api.getInterview>>);

    await expect(abandonInterview('i1')).resolves.toBe('preparing');

    expect(get).toHaveBeenCalledWith('i1');
  });

  it('그 밖의 API 오류는 그대로 던진다', async () => {
    const error = apiError(500, 'internal_error');
    vi.spyOn(api, 'abandonInterview').mockRejectedValue(error);

    await expect(abandonInterview('i1')).rejects.toBe(error);
  });

  it('API 오류가 아닌 예외도 그대로 던진다', async () => {
    const error = new TypeError('network');
    vi.spyOn(api, 'abandonInterview').mockRejectedValue(error);

    await expect(abandonInterview('i1')).rejects.toBe(error);
  });
});

describe('interviewPath', () => {
  it.each([
    ['completed', '/interview/i1/report'],
    ['in_progress', '/interview/i1/session'],
    ['preparing', '/interview/i1/prepare'],
    ['preparing_failed', '/interview/i1/prepare'],
  ] as const)('%s 면접은 %s로 보낸다', (status, path) => {
    expect(interviewPath('i1', status)).toBe(path);
  });
});

describe('previousInterviewIdFrom', () => {
  it('문자열 previousInterviewId만 꺼낸다', () => {
    expect(previousInterviewIdFrom({ previousInterviewId: 'i0' })).toBe('i0');
  });

  it.each([null, undefined, {}, { previousInterviewId: 1 }, 'x'])(
    '%j는 null로 본다',
    (state) => {
      expect(previousInterviewIdFrom(state)).toBeNull();
    },
  );
});
