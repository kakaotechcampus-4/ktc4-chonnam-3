import { describe, expect, it } from 'vitest';

import { PERSONA_IMAGES, PERSONA_INITIALS, PERSONA_LABELS, PERSONA_ORDER } from '@/shared/persona';

describe('persona', () => {
  it('면접관 이름은 개발팀·기획팀·인사팀으로 표시한다', () => {
    expect(PERSONA_LABELS).toEqual({
      tech_lead: '개발팀',
      domain_lead: '기획팀',
      hr_manager: '인사팀',
    });
  });

  it('세 면접관을 중복 없이 한 번씩 세운다', () => {
    expect([...PERSONA_ORDER].sort()).toEqual(['domain_lead', 'hr_manager', 'tech_lead']);
  });

  it('모든 면접관에 약칭과 아바타 이미지가 있다', () => {
    for (const persona of PERSONA_ORDER) {
      expect(PERSONA_INITIALS[persona]).toBeTruthy();
      expect(PERSONA_IMAGES[persona]).toBeTruthy();
    }
  });
});
