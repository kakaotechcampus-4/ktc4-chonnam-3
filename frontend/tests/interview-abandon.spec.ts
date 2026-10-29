import { expect, test } from '@playwright/test';

// 공통 0009: 나가기·레포 재선택의 abandon과 마이페이지 중단된 면접 행.
// seed id는 src/mocks/db/config.ts를 따른다.
const IN_PROGRESS = 'a3d51c20-1005-4c00-9a00-000000000005';
const PREPARING_FAILED = 'a3d51c20-1009-4c00-9a00-000000000009';

test('면접 종료를 확인하면 abandon을 보낸 뒤 홈으로 간다', async ({ page }) => {
  await page.goto(`/interview/${IN_PROGRESS}/session`);
  await page.getByRole('button', { name: '면접 종료' }).click({ timeout: 15_000 });
  const abandon = page.waitForRequest(
    (request) =>
      request.method() === 'POST' && request.url().endsWith(`/interviews/${IN_PROGRESS}/abandon`),
  );
  await page.getByRole('button', { name: '종료하기' }).click();
  await abandon;
  await expect(page).toHaveURL(/\/home$/);
});

test('레포 재선택은 기존 면접 abandon 후 새 면접을 만들고 뒤로 가기로 레포 선택에 돌아오지 않는다', async ({
  page,
}) => {
  const calls: string[] = [];
  page.on('request', (request) => {
    if (request.method() !== 'POST') return;
    const { pathname } = new URL(request.url());
    if (pathname.endsWith('/abandon')) calls.push('abandon');
    if (pathname.endsWith('/api/interviews')) calls.push('create');
  });

  await page.goto(`/interview/${PREPARING_FAILED}/prepare`);
  await page.getByRole('button', { name: '레포 다시 선택하기' }).click({ timeout: 15_000 });
  await expect(page).toHaveURL(/\/interview\/repos\//);
  await page.getByRole('button', { name: '선택한 레포로 면접 시작' }).click({ timeout: 15_000 });

  await expect(page).toHaveURL(/\/interview\/(?!a3d51c20-1009)[^/]+\/prepare$/);
  expect(calls).toEqual(['abandon', 'create']);
  await page.goBack();
  await expect(page).not.toHaveURL(/\/interview\/repos\//);
});

test('마이페이지 중단된 면접 행은 중단됨과 다시 도전하기를 보여준다', async ({ page }) => {
  await page.goto('/mypage');
  const row = page.getByRole('listitem').filter({ hasText: '중단됨' });
  await expect(row).toHaveCount(1, { timeout: 15_000 });
  await expect(row.getByRole('button', { name: '리포트 보기 →' })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: /완료 \d+회/ })).toBeVisible();

  await row.getByRole('button', { name: '다시 도전하기 →' }).click();
  await expect(page).toHaveURL(/\/interview\/[^/]+\/prepare$/);
});
