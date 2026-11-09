import { expect, test, type Page } from '@playwright/test';

const ID = 'a3d51c20-1001-4c00-9a00-000000000001';
const REPORT_URL = `/interview/${ID}/report`;

async function fault(page: Page, reason: string) {
  await page.addInitScript(
    (value) =>
      localStorage.setItem(
        'msw.faults',
        JSON.stringify([
          {
            path: '/interviews/*/feedback-disagreements',
            method: 'POST',
            status: 409,
            reason: value,
          },
        ]),
      ),
    reason,
  );
}

async function openForm(page: Page) {
  await page.goto(REPORT_URL);
  await page
    .getByRole('button', { name: '이 평가에 동의하지 않아요' })
    .first()
    .click({ timeout: 15_000 });
  return page.getByRole('form', { name: '개발팀 평가 이의 제기' });
}

test('의견은 보고 있는 리포트 버전으로 접수하고 점수를 바꾸지 않는다', async ({ page }) => {
  const form = await openForm(page);
  await form.getByLabel('의견 유형').selectOption('insufficient_basis');
  await form.getByLabel('추가 의견').fill('제가 설명한 검증 근거도 확인해주세요.');
  const sent = page.waitForRequest(
    (request) =>
      request.method() === 'POST' &&
      request.url().endsWith(`/interviews/${ID}/feedback-disagreements`),
  );
  await form.getByRole('button', { name: '의견 보내기' }).click();
  expect((await sent).postDataJSON()).toEqual({
    persona: 'tech_lead',
    reasonType: 'insufficient_basis',
    expectedRevision: 1,
    comment: '제가 설명한 검증 근거도 확인해주세요.',
  });
  await expect(page.getByRole('status')).toHaveText('의견이 접수됐어요.');
  await expect(page.getByText('81', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '이 평가에 동의하지 않아요' })).toHaveCount(2);
});

test('이미 접수된 의견은 중복 제출 대신 접수 상태로 표시한다', async ({ page }) => {
  await fault(page, 'already_submitted');
  const form = await openForm(page);
  await form.getByRole('button', { name: '의견 보내기' }).click();
  await expect(page.getByRole('status')).toHaveText('이미 이 평가에 대한 의견이 접수됐어요.');
  await expect(page.getByRole('form')).toHaveCount(0);
});

test('오래된 리포트의 의견은 막고 최신 리포트 조회를 제공한다', async ({ page }) => {
  await fault(page, 'report_unavailable');
  const form = await openForm(page);
  await form.getByRole('button', { name: '의견 보내기' }).click();
  await expect(form.getByRole('alert')).toContainText('최신 리포트를 확인한 뒤 다시 제출해주세요.');
  await expect(form.getByRole('button', { name: '의견 보내기' })).toBeDisabled();
  const refresh = page.waitForRequest(
    (request) => request.method() === 'GET' && request.url().endsWith(`/interviews/${ID}/report`),
  );
  await form.getByRole('button', { name: '최신 리포트 불러오기' }).click();
  await refresh;
});

test('실패한 리포트는 새 면접 없이 리포트 생성만 다시 요청한다', async ({ page }) => {
  // 실제 MSW 저장 상태를 실패로 준비하고 같은 SPA 안에서 리포트 화면으로 이동한다.
  await page.goto('/home');
  await page.getByRole('heading').first().waitFor({ timeout: 15_000 });
  await page.evaluate(
    async ({ id, url }) => {
      const { getInterview } = await import('/src/mocks/db/interviews.ts');
      const record = getInterview(id);
      if (!record) throw new Error('Missing completed interview fixture');
      record.reportFailed = true;
      history.pushState({}, '', url);
      dispatchEvent(new PopStateEvent('popstate'));
    },
    { id: ID, url: REPORT_URL },
  );
  await expect(page.getByRole('alert')).toHaveText('이 면접은 리포트를 만들 수 없어요.');
  const posts: string[] = [];
  page.on('request', (request) => {
    if (request.method() === 'POST') posts.push(new URL(request.url()).pathname);
  });
  await page.getByRole('button', { name: '리포트 생성 다시 시도' }).click();
  await expect(page.getByText('레포트를 만들고 있어요...')).toBeVisible();
  await expect(
    page.getByRole('heading', { name: '결제 도메인의 장애 대응 근거가 뚜렷한 지원자입니다' }),
  ).toBeVisible({ timeout: 15_000 });
  expect(posts).toEqual([`/api/interviews/${ID}/report/retry`]);
  await expect(page).toHaveURL(new RegExp(`/interview/${ID}/report$`));
});

test('생성 재시도가 거절되면 원인을 단정하지 않는 안내를 유지한다', async ({ page }) => {
  await page.addInitScript(() =>
    localStorage.setItem(
      'msw.faults',
      JSON.stringify([
        { path: '/interviews/*/report', status: 409, reason: 'report_unavailable' },
        {
          path: '/interviews/*/report/retry',
          method: 'POST',
          status: 409,
          reason: 'report_unavailable',
        },
      ]),
    ),
  );
  await page.goto(REPORT_URL);
  await page.getByRole('button', { name: '리포트 생성 다시 시도' }).click({ timeout: 15_000 });
  await expect(
    page.getByText(
      '현재 이 리포트를 다시 생성할 수 없어요. 면접 상태를 확인하거나 나중에 다시 시도해주세요.',
    ),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: '홈으로 가기' })).toBeVisible();
});
