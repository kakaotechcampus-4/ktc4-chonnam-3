// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import Footer from '@/shared/components/Footer';

describe('Footer', () => {
  afterEach(cleanup);

  it('기본 문구로 저작권과 약관 안내를 보여 준다', () => {
    render(<Footer />);

    expect(screen.getByText('© 2026 DEVON')).toBeTruthy();
    expect(screen.getByText('이용약관 · 개인정보처리방침')).toBeTruthy();
    expect(screen.queryByRole('note')).toBeNull();
  });

  it('note를 넘기면 기본 안내 대신 그 문구를 보여 준다', () => {
    render(<Footer note="이탈하면 면접이 중단돼요" />);

    expect(screen.getByText('이탈하면 면접이 중단돼요')).toBeTruthy();
    expect(screen.queryByText('이용약관 · 개인정보처리방침')).toBeNull();
  });

  it('aiNotice가 있으면 note 역할의 안내를 맨 위에 보여 준다', () => {
    render(<Footer aiNotice="AI 결과를 그대로 믿지 마세요" />);

    expect(screen.getByRole('note').textContent).toContain('AI 결과를 그대로 믿지 마세요');
  });
});
