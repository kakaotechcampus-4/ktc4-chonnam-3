import { describe, expect, it } from 'vitest';

import { queryKeys } from '@/shared/queryKeys';

// TanStack Query는 접두사가 같은 키를 함께 무효화한다. 그 관계가 깨지면 화면이 낡은 값을 그린다.
const startsWith = (key: readonly unknown[], prefix: readonly unknown[]) =>
  prefix.every((part, i) => JSON.stringify(key[i]) === JSON.stringify(part));

describe('queryKeys', () => {
  it('/me/profile 키는 /me 키를 접두사로 가진다', () => {
    expect(startsWith(queryKeys.profile, queryKeys.me)).toBe(true);
  });

  it('면접 목록 키는 페이지가 달라도 interviewsAll 접두사를 공유한다', () => {
    expect(startsWith(queryKeys.interviews(1), queryKeys.interviewsAll)).toBe(true);
    expect(queryKeys.interviews(1)).not.toEqual(queryKeys.interviews(2));
  });

  it('리포트 키는 면접 키를 접두사로 가진다', () => {
    expect(startsWith(queryKeys.report('i1'), queryKeys.interview('i1'))).toBe(true);
    expect(startsWith(queryKeys.report('i1'), queryKeys.interview('i2'))).toBe(false);
  });

  it('분석 결과 키는 같은 run의 분석 키를 접두사로 가진다', () => {
    expect(startsWith(queryKeys.analysisResult('r1'), queryKeys.analysisRun('r1'))).toBe(true);
  });
});
