import { expect, test } from '@playwright/test';

test('기술 스택이 긴 이력 행도 이력 카드 밖으로 넘치지 않는다', async ({ page }) => {
  await page.goto('/mypage');
  const card = page
    .locator('section')
    .filter({ has: page.getByRole('heading', { name: /면접 이력/ }) });
  const longRow = card.getByRole('listitem').filter({ hasText: '시간 종료 2/9턴 · 리포트 없음' });
  await expect(longRow).toBeVisible({ timeout: 10_000 });

  const cardRight = (await card.boundingBox())!.x + (await card.boundingBox())!.width;
  const overflowing = await card.evaluate((section, right) => {
    return [...section.querySelectorAll('li *')].filter(
      (el) => el.getBoundingClientRect().right > right + 1,
    ).length;
  }, cardRight);
  expect(overflowing).toBe(0);
  await expect(longRow.getByRole('button', { name: '다시 도전하기 →' })).toBeInViewport();
});
