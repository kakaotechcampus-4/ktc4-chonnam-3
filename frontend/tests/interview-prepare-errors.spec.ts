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
