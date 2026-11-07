import { expect, test } from '@playwright/test';

// src/mocks/db/config.ts SEED_PREPARING_FAILED_INTERVIEW_ID — 복구 가능한 준비 실패 면접.
const PREPARE_URL = '/interview/a3d51c20-1009-4c00-9a00-000000000009/prepare';

test('준비 재시도가 session_limit_exceeded면 진행 중인 다른 면접을 안내한다', async ({ page }) => {
  await page.addInitScript(() =>
    localStorage.setItem(
      'msw.faults',
      JSON.stringify([
        {
          path: '/interviews/*/prepare/retry',
          method: 'POST',
          status: 409,
          reason: 'session_limit_exceeded',
        },
      ]),
    ),
  );
  await page.goto(PREPARE_URL);
  await page.getByRole('button', { name: '다시 시도' }).click({ timeout: 15_000 });
  await expect(page.getByText('같은 공고로 진행 중인 면접이 있어요')).toBeVisible();
});

test('같은 run에 진행 중인 면접이 생기면 mock도 준비 재시도를 session_limit_exceeded로 거절한다', async ({
  page,
}) => {
  await page.goto(PREPARE_URL);
  const retry = page.getByRole('button', { name: '다시 시도' });
  await expect(retry).toBeVisible({ timeout: 15_000 });
  // mock 레코드는 메모리에만 있어 새로고침 없이 같은 run(SEED_RUN_ID)의 새 면접을 만든다.
  const created = await page.evaluate(async () => {
    const response = await fetch('/api/interviews', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        runId: '5c7b9e10-0000-4000-8000-00000000aaaa',
        repositoryIds: ['9f1c0a6e-0001-4f00-8a01-000000000001'],
      }),
    });
    return response.status;
  });
  expect(created).toBe(201);
  await retry.click();
  await expect(page.getByText('같은 공고로 진행 중인 면접이 있어요')).toBeVisible();
});
