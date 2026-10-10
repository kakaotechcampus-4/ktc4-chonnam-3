import { expect, test, type Page } from '@playwright/test';

async function fault(page: Page, path: string, status: number, reason: string, times?: number) {
  await page.addInitScript((rule) => localStorage.setItem('msw.faults', JSON.stringify([rule])), {
    path,
    status,
    reason,
    message: reason,
    times,
  });
}

test('보호 화면은 /me 인증 완료 전에 표시하지 않고 미인증이면 로그인으로 이동한다', async ({
  page,
}) => {
  await fault(page, '/me', 401, 'unauthenticated');
  await page.goto('/interview/new');
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('heading', { name: '면접 보실 공고를 입력해주세요' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'GitHub로 계속하기' })).toHaveAttribute(
    'href',
    '/api/auth/github/login',
  );
});

test('Query의 401은 재시도와 refresh 없이 한 번만 호출하고 로그인으로 이동한다', async ({
  page,
}) => {
  const requests: string[] = [];
  page.on('request', (request) => requests.push(new URL(request.url()).pathname));
  await fault(page, '/me/home', 401, 'unauthenticated');
  await page.goto('/home');
  await expect(page).toHaveURL(/\/login$/);
  expect(requests.filter((path) => path === '/api/me/home')).toHaveLength(1);
  expect(requests).not.toContain('/api/auth/refresh');
});

test('Mutation의 401도 로그인으로 이동하고 변경 요청을 재시도하지 않는다', async ({ page }) => {
  let submissions = 0;
  page.on('request', (request) => {
    if (new URL(request.url()).pathname === '/api/analysis-runs') submissions++;
  });
  await fault(page, '/analysis-runs', 401, 'unauthenticated');
  await page.goto('/interview/new');
  await page
    .getByPlaceholder('https://careers.example.com/jobs/123')
    .fill('https://www.wanted.co.kr/wd/123');
  await page.getByRole('button', { name: '분석 시작', exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect(submissions).toBe(1);
});

for (const [reason, message] of [
  ['account_suspended', '이용이 정지된 계정이에요.'],
  ['account_withdrawn', '탈퇴한 계정으로는 다시 가입할 수 없어요.'],
]) {
  test(`${reason} 계정에는 상태에 맞는 안내를 표시한다`, async ({ page }) => {
    await fault(page, '/me', 403, reason);
    await page.goto('/home');
    await expect(page.getByRole('alert')).toContainText(message);
    await expect(page).toHaveURL(new RegExp(`/login\\?error=${reason}$`));
  });
}

test('세션 조회 서버 장애는 로그아웃으로 처리하지 않고 재시도 화면을 보여준다', async ({
  page,
}) => {
  await fault(page, '/me', 500, 'internal_error');
  await page.goto('/home');
  await expect(page.getByRole('alert')).toContainText('로그인 상태를 확인하지 못했어요.');
  await expect(page.getByRole('button', { name: '다시 시도' })).toBeVisible();
  await expect(page).toHaveURL(/\/home$/);
});

test('로그아웃 실패는 안내하고 성공 뒤에는 새로고침해도 보호 화면에 접근할 수 없다', async ({
  page,
}) => {
  await fault(page, '/auth/logout', 500, 'internal_error', 1);
  await page.goto('/mypage');
  await page.getByRole('button', { name: '로그아웃', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: '로그아웃', exact: true }).click();
  await expect(page.getByRole('dialog').getByRole('alert')).toContainText('로그아웃하지 못했어요.');
  await expect(page).toHaveURL(/\/mypage$/);
  await page.getByRole('dialog').getByRole('button', { name: '로그아웃', exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto('/home');
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByText('김개발 님')).toHaveCount(0);
});

test('로그아웃은 이전 사용자의 캐시와 진행 중인 조회를 지워 늦은 응답도 복원하지 못한다', async ({
  page,
}) => {
  await page.goto('/mypage');
  await expect(page.getByRole('heading', { name: '김개발 님의 정보' })).toBeVisible();

  await page.evaluate(async () => {
    const moduleUrl = '/src/shared/queryClient.ts';
    const { queryClient } = await import(moduleUrl);
    let finish!: () => void;
    const response = new Promise<void>((resolve) => {
      finish = resolve;
    });
    const pending = queryClient
      .fetchQuery({
        queryKey: ['late-private-data'],
        queryFn: async () => {
          await response;
          return { name: '이전 사용자' };
        },
      })
      .catch(() => undefined);
    Object.assign(window, { finishPendingQuery: finish, pendingQuery: pending });
  });

  await page.getByRole('button', { name: '로그아웃', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: '로그아웃', exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);

  const cached = await page.evaluate(async () => {
    const pending = window as unknown as {
      finishPendingQuery: () => void;
      pendingQuery: Promise<unknown>;
    };
    pending.finishPendingQuery();
    await pending.pendingQuery;
    // Let the settled query notify observers after the delayed result resolves.
    await new Promise((resolve) => setTimeout(resolve, 0));
    const moduleUrl = '/src/shared/queryClient.ts';
    const { queryClient } = await import(moduleUrl);
    return queryClient
      .getQueryCache()
      .getAll()
      .map((query: { state: { data: unknown } }) => query.state.data);
  });
  expect(cached).toEqual([]);
});

test('logout followed by browser Back returns to login without a dead retry screen', async ({
  page,
}) => {
  await page.goto('/home');
  await page.getByRole('link', { name: '마이페이지', exact: true }).first().click();
  await page.getByRole('button', { name: '로그아웃', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: '로그아웃', exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);

  await page.goBack();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('link', { name: 'GitHub로 계속하기' })).toBeVisible();
  await expect(page.getByRole('button', { name: '다시 시도' })).toHaveCount(0);
});
