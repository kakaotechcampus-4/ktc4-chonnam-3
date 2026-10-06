import { expect, test } from '@playwright/test';

for (const [reason, guidance] of [
  ['denied', '취소'],
  ['invalid_state', '다시 로그인'],
  ['invalid_code', '다시 시도'],
  ['provider_unavailable', '잠시 후'],
  ['provider_configuration', '관리자에게 문의'],
  ['github_already_linked', '기존에 연결한 GitHub 계정'],
  ['account_suspended', '정지'],
  ['account_withdrawn', '탈퇴'],
]) {
  test(`${reason} 콜백 오류에는 원인에 맞는 안내와 로그인 경로를 표시한다`, async ({ page }) => {
    await page.goto(`/login?error=${reason}`);
    await expect(page.getByRole('alert')).toContainText(guidance);
    await expect(page.getByRole('link', { name: 'GitHub로 계속하기' })).toHaveAttribute(
      'href',
      '/api/auth/github/login',
    );
  });
}

for (const reason of [
  'denied',
  'invalid_code',
  'provider_unavailable',
  'provider_configuration',
  'github_already_linked',
]) {
  test(`${reason} 재연동 오류는 기존 계정을 유지하는 재연동 경로로 다시 시작한다`, async ({
    page,
  }) => {
    await page.goto(`/login?error=${reason}&flow=link`);
    await expect(page.getByRole('alert')).toBeVisible();
    await expect(
      page.getByText('기존에 연결한 GitHub 계정으로 다시 연동해주세요.', { exact: true }),
    ).toBeVisible();
    await expect(page.getByRole('link', { name: 'GitHub 재연동하기' })).toHaveAttribute(
      'href',
      '/api/auth/github/link',
    );
  });
}

for (const reason of ['unknown', '__proto__', 'constructor', 'toString']) {
  test(`알 수 없는 ${reason} 값은 오류 문구와 재연동 경로로 사용하지 않는다`, async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(`/login?error=${reason}&flow=link`);
    await expect(page.getByRole('link', { name: 'GitHub로 계속하기' })).toHaveAttribute(
      'href',
      '/api/auth/github/login',
    );
    await expect(page.getByRole('alert')).toHaveCount(0);
    expect(errors).toEqual([]);
  });
}

for (const query of [
  'error=invalid_state&flow=link',
  'error=account_suspended&flow=link',
  'error=account_withdrawn&flow=link',
  'error=invalid_code&flow=https://example.com',
  'flow=link',
]) {
  test(`${query} 값으로 재연동이나 외부 이동 경로를 선택할 수 없다`, async ({ page }) => {
    await page.goto(`/login?${query}`);
    await expect(page.getByRole('link', { name: 'GitHub로 계속하기' })).toHaveAttribute(
      'href',
      '/api/auth/github/login',
    );
  });
}
