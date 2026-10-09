import { expect, test } from '@playwright/test';

test('홈 조회 실패 시 빈 이름 인사 대신 재시도 버튼을 보여주고 재시도로 복구한다', async ({
  page,
}) => {
  // 첫 조회와 자동 재시도 1회만 실패시킨다.
  await page.addInitScript(() =>
    localStorage.setItem(
      'msw.faults',
      JSON.stringify([{ path: '/me/home', status: 500, reason: 'internal_error', times: 2 }]),
    ),
  );
  await page.goto('/home');
  await expect(page.getByRole('alert')).toHaveText('정보를 불러오지 못했어요.', {
    timeout: 10_000,
  });
  await expect(page.getByRole('heading', { name: /안녕하세요/ })).toHaveCount(0);
  await page.getByRole('button', { name: '다시 시도' }).click();
  await expect(page.getByRole('heading', { name: '안녕하세요, 김개발 님!' })).toBeVisible();
});

test('syncing 폴링 중 오류가 나면 폴링을 멈춘다', async ({ page }) => {
  await page.addInitScript(() => {
    const calls = { count: 0 };
    (window as unknown as { __homeCalls: typeof calls }).__homeCalls = calls;
    const originalFetch = window.fetch;
    window.fetch = async (input, options) => {
      if (!String(input).endsWith('/api/me/home')) return originalFetch(input, options);
      calls.count += 1;
      const body =
        calls.count === 1
          ? {
              name: '김개발',
              githubLinked: true,
              repositoryCount: 3,
              analysisStatus: 'syncing',
              analysis: null,
              recentInterviews: [],
            }
          : { error: { reason: 'github_token_invalid', message: 'GitHub 재연동이 필요해요.' } };
      return new Response(JSON.stringify(body), {
        status: calls.count === 1 ? 200 : 403,
        headers: { 'Content-Type': 'application/json' },
      });
    };
  });
  await page.goto('/home');
  await expect(page.getByText('GitHub 연동이 만료됐어요. 다시 연동해주세요.')).toBeVisible({
    timeout: 10_000,
  });
  // 3초 간격 폴링이 계속되면 7초 동안 2회를 넘는다.
  await page.waitForTimeout(7_000);
  const count = await page.evaluate(
    () => (window as unknown as { __homeCalls: { count: number } }).__homeCalls.count,
  );
  expect(count).toBe(2);
});
