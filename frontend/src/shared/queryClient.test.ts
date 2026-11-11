import { afterEach, describe, expect, it, vi } from 'vitest';

import { queryClient, refreshMeIfTokenInvalid } from '@/shared/queryClient';
import { queryKeys } from '@/shared/queryKeys';

describe('refreshMeIfTokenInvalid', () => {
  afterEach(() => vi.restoreAllMocks());

  it('github_token_invalid이면 /me 캐시를 무효화한다 (프로필 포함)', () => {
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries').mockResolvedValue();

    refreshMeIfTokenInvalid('github_token_invalid');

    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.me });
  });

  it.each(['run_expired', '', null, undefined])('%s이면 아무것도 무효화하지 않는다', (reason) => {
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries').mockResolvedValue();

    refreshMeIfTokenInvalid(reason);

    expect(invalidate).not.toHaveBeenCalled();
  });
});
