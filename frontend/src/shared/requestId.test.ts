import { afterEach, describe, expect, it, vi } from 'vitest';

import { createRequestId } from '@/shared/requestId';

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe('createRequestId', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('UUID v4 형식이고 호출마다 다르다', () => {
    const first = createRequestId();
    expect(first).toMatch(UUID_V4);
    expect(createRequestId()).not.toBe(first);
  });

  it('randomUUID가 없는 환경에서도 UUID v4를 만든다', () => {
    vi.stubGlobal('crypto', {
      getRandomValues: (bytes: Uint8Array) => bytes.fill(0xff),
    });
    // 난수가 전부 0xff여도 version(4)·variant(8~b) 비트는 고정되어야 한다.
    expect(createRequestId()).toBe('ffffffff-ffff-4fff-bfff-ffffffffffff');
  });
});
