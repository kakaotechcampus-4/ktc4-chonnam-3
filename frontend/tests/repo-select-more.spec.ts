import { expect, test, type Page } from '@playwright/test';

// 5a-v2 레포 선택의 "내 레포 더 보기"(GET /analysis-runs/{runId}/candidates?page=N).
// mock page 2는 202 analyzing 뒤 카드 3개, page 3부터는 빈 배열(마지막)이다.
const DONE_RUN = '5c7b9e10-0000-4000-8000-00000000aaaa';

function candidatePages(page: Page) {
  const pages: string[] = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.pathname.endsWith('/candidates')) pages.push(url.searchParams.get('page') ?? '');
  });
  return pages;
}

async function openRepoSelect(page: Page, faults: unknown[] = []) {
  await page.addInitScript(
    (rules) => localStorage.setItem('msw.faults', JSON.stringify(rules)),
    faults,
  );
  await page.goto(`/interview/repos/${DONE_RUN}`);
  await expect(page.getByRole('button', { name: '내 레포 더 보기' })).toBeVisible();
}

test('더 보기는 분석 중 안내 뒤 카드를 붙이고 선택을 유지하며 마지막 page에서 버튼을 숨긴다', async ({
  page,
}) => {
  const pages = candidatePages(page);
  await openRepoSelect(page);
  const selectedCount = await page.getByText(/개 레포 선택됨$/).textContent();

  await page.getByRole('button', { name: '내 레포 더 보기' }).click();
  await expect(page.getByRole('button', { name: '레포를 분석하고 있어요...' })).toBeDisabled();
  await expect(page.getByText('notification-worker')).toBeVisible({ timeout: 10_000 });
  // page 2의 AI 추천 카드가 붙어도 사용자가 보던 선택은 그대로다.
  await expect(page.getByText(/개 레포 선택됨$/)).toHaveText(selectedCount ?? '');

  await page.getByRole('button', { name: '내 레포 더 보기' }).click();
  await expect(
    page.getByRole('button', { name: /내 레포 더 보기|레포를 분석하고 있어요/ }),
  ).toHaveCount(0, { timeout: 10_000 });
  expect([...new Set(pages)]).toEqual(['2', '3']);
});

test('page 분석이 실패하면 안내하고 다음 더 보기는 다음 page를 부른다', async ({ page }) => {
  const pages = candidatePages(page);
  await openRepoSelect(page, [
    {
      path: '/analysis-runs/*/candidates',
      status: 409,
      reason: 'candidate_page_failed',
      message: '추가 레포지토리 분석에 실패했습니다.',
      times: 1,
    },
  ]);

  await page.getByRole('button', { name: '내 레포 더 보기' }).click();
  await expect(page.getByRole('alert')).toHaveText(
    '이 묶음의 레포를 분석하지 못했어요. 더 보기로 다음 레포를 볼 수 있어요.',
  );
  await page.getByRole('button', { name: '내 레포 더 보기' }).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(
    page.getByRole('button', { name: /내 레포 더 보기|레포를 분석하고 있어요/ }),
  ).toHaveCount(0, { timeout: 10_000 });
  // 실패한 page 2를 다시 부르지 않는다. BE는 같은 page를 다시 분석하지 않는다.
  expect([...new Set(pages)]).toEqual(['2', '3']);
});

test('run이 만료되면 안내하고 더 보기 버튼을 숨긴다', async ({ page }) => {
  await openRepoSelect(page, [
    {
      path: '/analysis-runs/*/candidates',
      status: 410,
      reason: 'run_expired',
      message: '분석 요청을 찾을 수 없어요.',
      times: 1,
    },
  ]);

  await page.getByRole('button', { name: '내 레포 더 보기' }).click();
  await expect(page.getByRole('alert')).toHaveText(
    '분석 결과가 만료됐어요. 공고 입력부터 다시 시작해주세요.',
  );
  await expect(page.getByRole('button', { name: '내 레포 더 보기' })).toHaveCount(0);
});
