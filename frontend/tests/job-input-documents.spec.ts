import { expect, test, type Page } from '@playwright/test';

type Captured = {
  uploads: { docType: string | null; filename: string; documentId: string }[];
  run: { postingUrl: string; documentId?: string; coverLetterDocumentId?: string } | null;
};

async function captureSelections(page: Page) {
  const captured: Captured = { uploads: [], run: null };
  await page.exposeFunction('captureDocumentSelection', (entry: Captured) => {
    captured.uploads.push(...entry.uploads);
    if (entry.run) captured.run = entry.run;
  });
  await page.addInitScript(() => {
    const record = (
      window as unknown as { captureDocumentSelection: (entry: Captured) => Promise<void> }
    ).captureDocumentSelection;
    const original = window.fetch;
    window.fetch = async (input, options) => {
      const response = await original(input, options);
      if (String(input).endsWith('/api/documents/preview') && options?.body instanceof FormData) {
        const preview = await response.clone().json();
        const file = options.body.get('file') as File;
        await record({
          uploads: [
            {
              docType: options.body.get('docType') as string | null,
              filename: file.name,
              documentId: preview.documentId,
            },
          ],
          run: null,
        });
      }
      if (String(input).endsWith('/api/analysis-runs') && options?.method === 'POST') {
        await record({ uploads: [], run: JSON.parse(String(options.body)) });
      }
      return response;
    };
  });
  return captured;
}

test('자소서와 포트폴리오의 종류·선택 ID를 각각 전달한다', async ({ page }) => {
  const captured = await captureSelections(page);
  await page.goto('/interview/new');
  await page.locator('input[type="file"][accept=".pdf,.docx"]').setInputFiles({
    name: 'letter.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('%PDF-1.4'),
  });
  await expect.poll(() => captured.uploads.length).toBe(1);
  await page.locator('input[type="file"][accept=".pdf"]').setInputFiles({
    name: 'portfolio.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('%PDF-1.4'),
  });
  await expect.poll(() => captured.uploads.length).toBe(2);
  await page
    .getByPlaceholder('https://careers.example.com/jobs/123')
    .fill('https://www.wanted.co.kr/wd/123456');
  await page.getByRole('button', { name: '분석 시작' }).click();
  await expect.poll(() => captured.run).not.toBeNull();
  expect(captured.uploads.map(({ docType }) => docType)).toEqual(['cover_letter', 'portfolio']);
  expect(captured.run).toEqual({
    postingUrl: 'https://www.wanted.co.kr/wd/123456',
    documentId: captured.uploads[1].documentId,
    coverLetterDocumentId: captured.uploads[0].documentId,
  });
});

test('실패한 자소서를 제외하고 진행하면 선택하지 않은 문서 ID를 보내지 않는다', async ({
  page,
}) => {
  const captured = await captureSelections(page);
  await page.goto('/interview/new');
  await page.locator('input[type="file"][accept=".pdf,.docx"]').setInputFiles({
    name: 'letter-fail.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('%PDF-1.4'),
  });
  await page.getByRole('button', { name: '문서 없이 계속 진행' }).click();
  await page
    .getByPlaceholder('https://careers.example.com/jobs/123')
    .fill('https://www.wanted.co.kr/wd/123456');
  await page.getByRole('button', { name: '분석 시작' }).click();
  await expect.poll(() => captured.run).not.toBeNull();
  expect(captured.run).toEqual({ postingUrl: 'https://www.wanted.co.kr/wd/123456' });
});

test('모의 서버도 자소서가 다른 분석을 구분하고 같은 입력만 재사용한다', async ({ page }) => {
  await page.goto('/interview/new');
  const result = await page.evaluate(async () => {
    const moduleUrl = '/src/mocks/db/runs.ts';
    const { createRun } = await import(moduleUrl);
    const url = 'https://www.wanted.co.kr/wd/123456';
    const first = createRun(url, null, 'letter-1');
    const second = createRun(url, null, 'letter-2');
    const repeated = createRun(url, null, 'letter-1');
    return {
      first: first.run.runId,
      second: second.run.runId,
      repeated: repeated.run.runId,
      reused: repeated.reused,
    };
  });
  expect(result.first).not.toBe(result.second);
  expect(result.repeated).toBe(result.first);
  expect(result.reused).toBe(true);
});
