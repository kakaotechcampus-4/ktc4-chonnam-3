import { expect, test } from '@playwright/test';

test('프로필 조회 실패 시 빈 이름·0회 대신 재시도 버튼을 보여준다', async ({ page }) => {
  // 첫 조회와 자동 재시도 1회만 실패시킨다.
  await page.addInitScript(() =>
    localStorage.setItem(
      'msw.faults',
      JSON.stringify([{ path: '/me/profile', status: 500, reason: 'internal_error', times: 2 }]),
    ),
  );
  await page.goto('/mypage');
  await expect(page.getByRole('alert')).toHaveText('정보를 불러오지 못했어요.', {
    timeout: 10_000,
  });
  await expect(page.getByRole('heading', { name: /님의 정보/ })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: '면접 이력', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '다시 시도' }).click();
  await expect(page.getByRole('heading', { name: '김개발 님의 정보' })).toBeVisible();
});

test('이력 2페이지 조회가 실패해도 페이지 이동 UI가 남는다', async ({ page }) => {
  await page.addInitScript(() => {
    const originalFetch = window.fetch;
    window.fetch = async (input, options) => {
      const url = String(input);
      if (!url.includes('/api/me/interviews')) return originalFetch(input, options);
      if (url.includes('page=2')) {
        return new Response(JSON.stringify({ error: { reason: 'internal_error', message: 'x' } }), {
          status: 500,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      return new Response(
        JSON.stringify({ interviews: [], total: 25, page: 1, size: 10, averageScore: null }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    };
  });
  await page.goto('/mypage');
  await page.getByRole('button', { name: '다음' }).click();
  await expect(page.getByText('이력을 불러오지 못했어요.')).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText('2 / 3')).toBeVisible();
  await page.getByRole('button', { name: '이전' }).click();
  await expect(page.getByText('1 / 3')).toBeVisible();
});

test('로그아웃 실패 후 모달을 다시 열면 이전 오류 문구가 남지 않는다', async ({ page }) => {
  await page.addInitScript(() =>
    localStorage.setItem(
      'msw.faults',
      JSON.stringify([
        { path: '/auth/logout', method: 'POST', status: 500, reason: 'internal_error', times: 1 },
      ]),
    ),
  );
  await page.goto('/mypage');
  await page.getByRole('button', { name: '로그아웃', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: '로그아웃', exact: true }).click();
  await expect(dialog.getByRole('alert')).toContainText('로그아웃하지 못했어요.');
  await dialog.getByRole('button', { name: '취소' }).click();
  await page.getByRole('button', { name: '로그아웃', exact: true }).click();
  await expect(page.getByRole('dialog').getByRole('alert')).toHaveCount(0);
});
