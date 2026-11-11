// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';

import { QUESTION_TEXT_KEY, readQuestionText } from '@/features/interview/questionText';

describe('readQuestionText', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it('저장된 값이 없으면 질문 텍스트를 보여 준다', () => {
    expect(readQuestionText()).toBe(true);
  });

  it("'false'로 꺼 둔 경우에만 숨긴다", () => {
    localStorage.setItem(QUESTION_TEXT_KEY, 'false');
    expect(readQuestionText()).toBe(false);

    localStorage.setItem(QUESTION_TEXT_KEY, 'true');
    expect(readQuestionText()).toBe(true);
  });

  it('저장소 접근이 막혀도 보여 주는 쪽으로 동작한다', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });

    expect(readQuestionText()).toBe(true);
  });
});
