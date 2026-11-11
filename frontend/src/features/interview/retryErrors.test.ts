import { describe, expect, it } from 'vitest';

import { RESTART_REASONS, RETRY_ERROR } from '@/features/interview/retryErrors';

describe('retryErrors', () => {
  it('공고 입력으로 보내는 reason은 모두 안내 문구가 있다', () => {
    for (const reason of RESTART_REASONS) {
      expect(RETRY_ERROR[reason]).toBeTruthy();
    }
  });

  it('재도전 실패 reason 5종을 안내한다', () => {
    expect(Object.keys(RETRY_ERROR).sort()).toEqual([
      'not_found',
      'original_not_completed',
      'repository_unavailable',
      'run_expired',
      'session_limit_exceeded',
    ]);
  });
});
