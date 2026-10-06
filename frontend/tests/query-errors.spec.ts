import { expect, test } from '@playwright/test';

test('Query JSON 파싱 오류는 본문 없이 분류만 기록하고 로그인으로 이동하지 않는다', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  await page.goto('/home');
  await expect(page.getByRole('heading', { name: '안녕하세요, 김개발 님!' })).toBeVisible();
  await page.evaluate(async () => {
    const apiUrl = '/src/shared/api.ts';
    const queryUrl = '/src/shared/queryClient.ts';
    const { api } = await import(apiUrl);
    const { queryClient } = await import(queryUrl);
    const originalFetch = window.fetch;
    window.fetch = async (input, options) =>
      input === '/api/me'
        ? new Response('PRIVATEX not JSON', { status: 200 })
        : originalFetch(input, options);
    try {
      await queryClient
        .fetchQuery({ queryKey: ['invalid-json'], queryFn: api.getMe, retry: false })
        .catch(() => undefined);
    } finally {
      window.fetch = originalFetch;
    }
  });
  expect(errors.filter((message) => message.startsWith('Unexpected non-API error'))).toEqual([
    'Unexpected non-API error SyntaxError',
  ]);
  expect(errors.join('\n')).not.toContain('PRIVATEX');
  await expect(page).toHaveURL(/\/home$/);
});

test('Mutation 네트워크 오류는 예외 이름과 원문 없이 분류만 기록하고 화면을 유지한다', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  await page.goto('/mypage');
  await expect(page.getByRole('heading', { name: '김개발 님의 정보' })).toBeVisible();
  await page.evaluate(() => {
    const originalFetch = window.fetch;
    window.fetch = async (input, options) => {
      if (input === '/api/auth/logout') {
        const error = new TypeError('PRIVATE_NETWORK_MARKER');
        error.name = 'PRIVATE_ERROR_NAME';
        throw error;
      }
      return originalFetch(input, options);
    };
  });
  await page.getByRole('button', { name: '로그아웃', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: '로그아웃', exact: true }).click();
  await expect(page.getByRole('dialog').getByRole('alert')).toContainText('로그아웃하지 못했어요.');
  expect(errors.filter((message) => message.startsWith('Unexpected non-API error'))).toEqual([
    'Unexpected non-API error TypeError',
  ]);
  expect(errors.join('\n')).not.toMatch(/PRIVATE_NETWORK_MARKER|PRIVATE_ERROR_NAME/);
  await expect(page).toHaveURL(/\/mypage$/);
});

test('세션 종료 가드의 Query와 Mutation 취소는 요청이나 오류 로그를 만들지 않는다', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  await page.goto('/login');
  const result = await page.evaluate(async () => {
    const apiUrl = '/src/shared/api.ts';
    const queryUrl = '/src/shared/queryClient.ts';
    const { api } = await import(apiUrl);
    const { queryClient, clearSessionQueries } = await import(queryUrl);
    await clearSessionQueries();
    const originalFetch = window.fetch;
    let requests = 0;
    window.fetch = (...args) => {
      requests++;
      return originalFetch(...args);
    };
    const queryError = await queryClient
      .fetchQuery({ queryKey: ['after-session'], queryFn: api.getMe })
      .catch((error: Error) => error.name);
    const mutationError = await queryClient
      .getMutationCache()
      .build(queryClient, { mutationFn: api.logout })
      .execute(undefined)
      .catch((error: Error) => error.name);
    window.fetch = originalFetch;
    return { requests, queryError, mutationError };
  });
  expect(result).toEqual({ requests: 0, queryError: 'AbortError', mutationError: 'AbortError' });
  expect(errors.filter((message) => message.startsWith('Unexpected non-API error'))).toEqual([]);
});

test('홈 재조회가 github_token_invalid로 실패하면 캐시된 홈 데이터가 있어도 연동 배지를 숨긴다', async ({
  page,
}) => {
  await page.goto('/home');
  await expect(page.getByRole('heading', { name: '안녕하세요, 김개발 님!' })).toBeVisible();
  await expect(page.getByText('GitHub 연동됨')).toBeVisible();
  await page.evaluate(async () => {
    localStorage.setItem(
      'msw.faults',
      JSON.stringify([
        { path: '/me/home', status: 403, reason: 'github_token_invalid', message: 'x' },
      ]),
    );
    const queryUrl = '/src/shared/queryClient.ts';
    const { queryClient } = await import(queryUrl);
    await queryClient.refetchQueries({ queryKey: ['home'] });
  });
  await expect(page.getByRole('link', { name: 'GitHub 재연동' })).toBeVisible();
  await expect(page.getByText('GitHub 연동됨')).toHaveCount(0);
});
