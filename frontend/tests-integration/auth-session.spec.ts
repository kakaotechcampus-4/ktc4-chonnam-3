import { expect, test } from '@playwright/test';

test('public callback proxy carries state and the real session survives reload, relink and logout', async ({
  page,
  context,
}) => {
  const callbackUrls: string[] = [];
  await page.route('https://avatars.githubusercontent.com/**', (route) => route.abort());
  // 외부 동의 화면만 대체하고 state 쿠키와 콜백은 실제 브라우저·서버 흐름으로 확인한다.
  await page.route('https://github.com/login/oauth/authorize**', async (route) => {
    const authorize = new URL(route.request().url());
    expect(authorize.searchParams.get('redirect_uri')).toBe(
      'http://localhost:5173/auth/github/callback',
    );
    expect(authorize.searchParams.get('scope')).toBe('read:user');
    expect(authorize.searchParams.get('code_challenge_method')).toBe('S256');
    const state = authorize.searchParams.get('state')!;
    const cookie = (await context.cookies()).find((cookie) => cookie.name === 'oauthState');
    expect(cookie).toMatchObject({
      value: state,
      path: '/auth/github',
      httpOnly: true,
      sameSite: 'Lax',
      secure: false,
    });
    const callback = new URL(authorize.searchParams.get('redirect_uri')!);
    callback.searchParams.set('state', state);
    callback.searchParams.set('code', `browser_${authorize.searchParams.get('code_challenge')}`);
    callbackUrls.push(callback.toString());
    await route.fulfill({ status: 302, headers: { location: callback.toString() } });
  });

  await page.goto('/login');
  const startOAuth = async (path: string) => {
    // Playwright는 리다이렉트 연쇄의 첫 요청만 가로채므로 동의 화면으로 직접 이동한다.
    // 시작 요청은 Vite를 거쳐 실제 서버로 보내 OAuth 쿠키와 리다이렉트 응답을 받는다.
    const start = await context.request.get(path, { maxRedirects: 0 });
    expect(start.status()).toBe(302);
    expect(new URL(start.headers().location).origin).toBe('https://github.com');
    await page.goto(start.headers().location);
  };
  await expect(page.getByRole('link', { name: 'GitHub로 계속하기' })).toHaveAttribute(
    'href',
    '/api/auth/github/login',
  );
  await startOAuth('/api/auth/github/login');
  await expect(page).toHaveURL('http://localhost:5173/home');
  await expect(
    page.getByRole('heading', { name: '안녕하세요, Browser Octocat 님!' }),
  ).toBeVisible();
  const session = (await context.cookies()).find((cookie) => cookie.name === 'devon_session')!;
  expect(session).toMatchObject({ path: '/', httpOnly: true, sameSite: 'Lax', secure: false });
  expect(session.expires - Date.now() / 1000).toBeGreaterThan(1209500);
  expect((await context.cookies()).some((cookie) => cookie.name === 'oauthState')).toBe(false);
  expect(await page.evaluate(() => document.cookie)).not.toContain('devon_session');
  const me = await context.request.get('/api/me');
  expect(me.status()).toBe(200);
  expect(await me.json()).toEqual({
    name: 'Browser Octocat',
    avatarUrl: 'https://avatars.githubusercontent.com/u/7001',
    githubLinked: true,
  });
  expect(me.headers()['set-cookie']).toContain('Max-Age=1209600');

  await page.reload();
  await expect(
    page.getByRole('heading', { name: '안녕하세요, Browser Octocat 님!' }),
  ).toBeVisible();
  await startOAuth('/api/auth/github/link');
  await expect(page).toHaveURL('http://localhost:5173/home');
  expect((await context.cookies()).find((cookie) => cookie.name === 'devon_session')?.value).toBe(
    session.value,
  );
  expect(callbackUrls).toHaveLength(2);

  const replay = await context.request.get(callbackUrls[0], { maxRedirects: 0 });
  expect(replay.status()).toBe(400);
  expect((await replay.json()).error.reason).toBe('invalid_state');
  const invalid = await context.request.get('/auth/github/callback?code=invalid&state=invalid');
  expect(invalid.status()).toBe(400);

  await page.goto('/mypage');
  await expect(page.getByRole('heading', { name: 'Browser Octocat 님의 정보' })).toBeVisible();
  await page.getByRole('button', { name: '로그아웃', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: '로그아웃', exact: true }).click();
  await expect(page).toHaveURL('http://localhost:5173/login');
  expect((await context.cookies()).some((cookie) => cookie.name === 'devon_session')).toBe(false);
  expect((await context.request.get('/api/me')).status()).toBe(401);
  await page.goto('/home');
  await expect(page).toHaveURL('http://localhost:5173/login');
  expect(await page.content()).not.toContain('browser-private-github-token');
});
