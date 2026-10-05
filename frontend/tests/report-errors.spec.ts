import { expect, test, type Page } from '@playwright/test';

// src/mocks/db/config.ts SEED_INTERVIEW_ID — 종료된 면접이라 리포트를 바로 열 수 있다.
const REPORT_URL = '/interview/a3d51c20-1001-4c00-9a00-000000000001/report';

async function faults(page: Page, rules: Record<string, unknown>[]) {
  await page.addInitScript(
    (value) => localStorage.setItem('msw.faults', JSON.stringify(value)),
    rules,
  );
}

test('리포트 조회 네트워크 오류는 흰 화면 대신 오류 문구와 이동 버튼을 보여준다', async ({
  page,
}) => {
  await faults(page, [{ path: '/interviews/*/report', kind: 'network' }]);
  await page.goto(REPORT_URL);
  await expect(page.getByRole('alert')).toHaveText('리포트를 불러오지 못했어요.', {
    timeout: 15_000,
  });
  await expect(page.getByRole('button', { name: '다시 불러오기' })).toBeVisible();
  await page.getByRole('button', { name: '홈으로 가기' }).click();
  await expect(page).toHaveURL(/\/home$/);
});

test('report_unavailable은 원인을 단정하지 않고 홈 이동만 제공한다', async ({ page }) => {
  await faults(page, [{ path: '/interviews/*/report', status: 409, reason: 'report_unavailable' }]);
  await page.goto(REPORT_URL);
  await expect(page.getByRole('alert')).toHaveText('이 면접은 리포트를 만들 수 없어요.');
  await expect(page.getByRole('button', { name: '홈으로 가기' })).toBeVisible();
  await expect(page.getByRole('button', { name: '다시 불러오기' })).toHaveCount(0);
});

test('재도전 410은 만료 안내와 공고 입력 이동 버튼을 보여준다', async ({ page }) => {
  await faults(page, [
    { path: '/interviews/*/retry', method: 'POST', status: 410, reason: 'run_expired' },
  ]);
  await page.goto(REPORT_URL);
  await page.getByRole('button', { name: '새 모의면접 시작하기' }).click({ timeout: 15_000 });
  await expect(page.getByRole('alert')).toContainText('분석 결과가 만료됐어요.');
  await page.getByRole('button', { name: '공고 입력부터 다시' }).click();
  await expect(page).toHaveURL(/\/interview\/new$/);
});

test('202 응답에 retryAfter가 없어도 기본 간격으로 폴링을 이어간다', async ({ page }) => {
  await page.addInitScript(() => {
    const calls = { count: 0 };
    (window as unknown as { __reportCalls: typeof calls }).__reportCalls = calls;
    const originalFetch = window.fetch;
    window.fetch = async (input, options) => {
      if (!String(input).endsWith('/report')) return originalFetch(input, options);
      calls.count += 1;
      return new Response(JSON.stringify({ status: 'generating' }), {
        status: 202,
        headers: { 'Content-Type': 'application/json' },
      });
    };
  });
  await page.goto(REPORT_URL);
  await expect(page.getByText('리포트를 만들고 있어요...')).toBeVisible();
  await expect
    .poll(
      () =>
        page.evaluate(
          () => (window as unknown as { __reportCalls: { count: number } }).__reportCalls.count,
        ),
      {
        timeout: 8_000,
      },
    )
    .toBeGreaterThanOrEqual(2);
});
