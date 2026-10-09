import { expect, test, type Page } from '@playwright/test';

const POSTING_URL = 'https://www.wanted.co.kr/wd/123456';

async function submit(page: Page) {
  await page.goto('/interview/new');
  await page.getByPlaceholder('https://careers.example.com/jobs/123').fill(POSTING_URL);
  await page.getByRole('button', { name: '분석 시작' }).click();
}

test('분석 시작 403 github_token_invalid는 재연동 배너를 보여준다', async ({ page }) => {
  await page.addInitScript(() =>
    localStorage.setItem(
      'msw.faults',
      JSON.stringify([
        { path: '/analysis-runs', method: 'POST', status: 403, reason: 'github_token_invalid' },
      ]),
    ),
  );
  await submit(page);
  await expect(page.getByRole('alert')).toContainText('GitHub 연동이 만료됐어요.');
  await expect(page.getByRole('link', { name: 'GitHub 재연동' })).toHaveAttribute(
    'href',
    '/api/auth/github/link',
  );
  await expect(page).toHaveURL(/\/interview\/new$/);
});

test('프록시 HTML 오류 본문은 화면에 노출하지 않고 기본 문구를 보여준다', async ({ page }) => {
  await page.addInitScript(() => {
    const originalFetch = window.fetch;
    window.fetch = async (input, options) =>
      String(input).endsWith('/api/analysis-runs')
        ? new Response('<html><body><h1>502 Bad Gateway</h1></body></html>', {
            status: 502,
            headers: { 'Content-Type': 'text/html' },
          })
        : originalFetch(input, options);
  });
  await submit(page);
  await expect(page.getByRole('alert')).toHaveText(
    '분석을 시작하지 못했어요. 잠시 후 다시 시도해주세요.',
  );
  await expect(page.getByText('502 Bad Gateway')).toHaveCount(0);
});

test('업로드 413 document_too_large는 FE 문구로 안내한다', async ({ page }) => {
  await page.addInitScript(() =>
    localStorage.setItem(
      'msw.faults',
      JSON.stringify([
        {
          path: '/documents/preview',
          method: 'POST',
          status: 413,
          reason: 'document_too_large',
          message: 'SERVER_MESSAGE',
        },
      ]),
    ),
  );
  await page.goto('/interview/new');
  await page.locator('input[type="file"][accept=".pdf"]').setInputFiles({
    name: 'portfolio.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('%PDF-1.4'),
  });
  await expect(page.getByText('파일 용량이 너무 커요.')).toBeVisible();
  await expect(page.getByText('SERVER_MESSAGE')).toHaveCount(0);
});
