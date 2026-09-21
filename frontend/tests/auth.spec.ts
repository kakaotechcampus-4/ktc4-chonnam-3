import { expect, test, type Page } from '@playwright/test';
import { fileURLToPath } from 'node:url';
import { homeScenarios, interviewPage, meProfile } from '../src/mocks/fixtures/user';

test.beforeEach(async ({ context }) => {
  // 외부 이미지 서버 상태가 인증 UI 검증에 영향을 주지 않도록 로컬 자산으로 응답한다.
  await context.route('https://avatars.githubusercontent.com/**', (route) =>
    route.fulfill({
      path: fileURLToPath(new URL('../public/favicon.svg', import.meta.url)),
      contentType: 'image/svg+xml',
    }),
  );
  // 인증만 완성된 실제 BE처럼 상세 API의 미구현을 성공 응답으로 숨기지 않는다.
  await context.route(/\/api\/me\/(home|profile|interviews)(\?.*)?$/, (route) =>
    route.fulfill(apiError('not_found', 404)),
  );
});

const me = {
  name: '김개발',
  avatarUrl: 'https://avatars.githubusercontent.com/u/1?v=4',
  githubLinked: true,
};

function apiError(reason: string, status: number, message = reason) {
  return {
    status,
    contentType: 'application/json',
    body: JSON.stringify({ error: { reason, message, details: {} } }),
  };
}

async function mockAnonymous(page: Page, reason = 'access_token_invalid') {
  await page.route('**/api/me', (route) => route.fulfill(apiError(reason, 401)));
}

async function mockAuthenticated(page: Page) {
  await page.route('**/api/me', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(me) }),
  );
}

test('the login page is safe for anonymous visitors and preserves denial feedback', async ({
  page,
}) => {
  await mockAnonymous(page);

  await page.goto('/login?error=denied');

  await expect(page.getByRole('heading', { name: 'DEVON' })).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('GitHub 로그인이 취소되었습니다');
  await expect(page.getByRole('link', { name: 'GitHub로 계속하기' })).toHaveAttribute(
    'href',
    '/api/auth/github/login',
  );
});

test('the GitHub login control performs a browser navigation', async ({ page }) => {
  await mockAnonymous(page);
  await page.route('**/api/auth/github/login', (route) =>
    route.fulfill({ status: 302, headers: { location: '/login?error=denied' } }),
  );
  await page.goto('/login');

  await page.getByRole('link', { name: 'GitHub로 계속하기' }).click();

  await expect(page).toHaveURL(/\/login\?error=denied$/);
  await expect(page.getByRole('alert')).toContainText('GitHub 로그인이 취소되었습니다');
});

test('an authenticated visitor cannot stay on the login page', async ({ page }) => {
  await mockAuthenticated(page);

  await page.goto('/login');

  await expect(page).toHaveURL(/\/home$/);
  await expect(page.getByRole('heading', { name: '안녕하세요, 김개발 님!' })).toBeVisible();
});

test('a revoked GitHub connection is not presented as successfully linked', async ({ page }) => {
  await page.route('**/api/me', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ...me, githubLinked: false }),
    }),
  );

  await page.goto('/home');

  await expect(page.getByText('GitHub 계정 연결이 완료되었습니다.')).toHaveCount(0);
  await expect(page.getByText('GitHub 연결을 확인해주세요.')).toBeVisible();
});

test('a missing access cookie refreshes once and replays the original request once', async ({
  page,
}) => {
  let authenticated = false;
  let meRequests = 0;
  let refreshRequests = 0;
  await page.route('**/api/me', async (route) => {
    meRequests += 1;
    await route.fulfill(
      authenticated
        ? { status: 200, contentType: 'application/json', body: JSON.stringify(me) }
        : apiError('unauthenticated', 401),
    );
  });
  await page.route('**/api/auth/refresh', async (route) => {
    refreshRequests += 1;
    authenticated = true;
    await route.fulfill({ status: 204 });
  });

  await page.goto('/home');

  await expect(page.getByRole('heading', { name: '안녕하세요, 김개발 님!' })).toBeVisible();
  expect(refreshRequests).toBe(1);
  expect(meRequests).toBe(3);
});

test('two tabs coordinate an expired access refresh through the devon-auth Web Lock', async ({
  context,
}) => {
  let authenticated = false;
  let refreshRequests = 0;
  await context.route('**/api/me', async (route) => {
    await route.fulfill(
      authenticated
        ? { status: 200, contentType: 'application/json', body: JSON.stringify(me) }
        : apiError('access_token_expired', 401),
    );
  });
  await context.route('**/api/auth/refresh', async (route) => {
    refreshRequests += 1;
    await new Promise((resolve) => setTimeout(resolve, 100));
    authenticated = true;
    await route.fulfill({ status: 204 });
  });
  const first = await context.newPage();
  const second = await context.newPage();

  await Promise.all([first.goto('/home'), second.goto('/home')]);

  await expect(first.getByRole('heading', { name: '안녕하세요, 김개발 님!' })).toBeVisible();
  await expect(second.getByRole('heading', { name: '안녕하세요, 김개발 님!' })).toBeVisible();
  expect(refreshRequests).toBe(1);
});

test('an invalid access token never attempts refresh', async ({ page }) => {
  let refreshRequests = 0;
  await mockAnonymous(page);
  await page.route('**/api/auth/refresh', async (route) => {
    refreshRequests += 1;
    await route.fulfill({ status: 204 });
  });

  await page.goto('/home');

  await expect(page).toHaveURL(/\/login$/);
  expect(refreshRequests).toBe(0);
});

test('without Web Locks an expired session requires a new login without refreshing', async ({
  page,
}) => {
  await page.addInitScript(() => {
    Object.defineProperty(Navigator.prototype, 'locks', { configurable: true, value: undefined });
  });
  let refreshRequests = 0;
  await page.route('**/api/me', (route) => route.fulfill(apiError('access_token_expired', 401)));
  await page.route('**/api/auth/refresh', async (route) => {
    refreshRequests += 1;
    await route.fulfill({ status: 204 });
  });

  await page.goto('/home');

  await expect(page).toHaveURL(/\/login$/);
  expect(refreshRequests).toBe(0);
});

test('a service outage preserves the route and offers a working retry', async ({ page }) => {
  let available = false;
  await page.route('**/api/me', async (route) => {
    await route.fulfill(
      available
        ? { status: 200, contentType: 'application/json', body: JSON.stringify(me) }
        : apiError('service_unavailable', 503, '잠시 사용할 수 없습니다.'),
    );
  });

  await page.goto('/home');
  await expect(page).toHaveURL(/\/home$/);
  await expect(page.getByRole('alert')).toContainText('잠시 사용할 수 없습니다');

  available = true;
  await page.getByRole('button', { name: '다시 시도' }).click();
  await expect(page.getByRole('heading', { name: '안녕하세요, 김개발 님!' })).toBeVisible();
});

test('a refresh service outage remains recoverable from the guarded route', async ({ page }) => {
  let authenticated = false;
  let refreshAvailable = false;
  await page.route('**/api/me', (route) =>
    route.fulfill(
      authenticated
        ? { status: 200, contentType: 'application/json', body: JSON.stringify(me) }
        : apiError('access_token_expired', 401),
    ),
  );
  await page.route('**/api/auth/refresh', async (route) => {
    if (!refreshAvailable) {
      return route.fulfill(
        apiError('service_unavailable', 503, '인증 서비스를 사용할 수 없습니다.'),
      );
    }
    authenticated = true;
    await route.fulfill({ status: 204 });
  });

  await page.goto('/home');
  await expect(page).toHaveURL(/\/home$/);
  await expect(page.getByRole('alert')).toContainText('인증 서비스를 사용할 수 없습니다');

  refreshAvailable = true;
  await page.getByRole('button', { name: '다시 시도' }).click();
  await expect(page.getByRole('heading', { name: '안녕하세요, 김개발 님!' })).toBeVisible();
});

test('a malformed HTTP error is not reported as a network failure', async ({ page }) => {
  await page.route('**/api/me', (route) =>
    route.fulfill({ status: 503, contentType: 'text/html', body: '<h1>upstream unavailable</h1>' }),
  );

  await page.goto('/home');

  await expect(page).toHaveURL(/\/home$/);
  await expect(page.getByRole('alert')).toContainText('서버 응답에 문제가 있습니다');
});

test('a network error keeps authentication recoverable', async ({ page }) => {
  let available = false;
  await page.route('**/api/me', async (route) => {
    if (!available) return route.abort('connectionrefused');
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(me) });
  });

  await page.goto('/home');
  await expect(page).toHaveURL(/\/home$/);
  await expect(page.getByRole('alert')).toContainText('네트워크 연결을 확인해주세요');

  available = true;
  await page.getByRole('button', { name: '다시 시도' }).click();
  await expect(page.getByRole('heading', { name: '안녕하세요, 김개발 님!' })).toBeVisible();
});

test('blocked accounts are cleared and shown a stable explanation', async ({ page }) => {
  await page.route('**/api/me', (route) =>
    route.fulfill(apiError('account_suspended', 403, '이용이 정지된 계정입니다.')),
  );

  await page.goto('/home');

  await expect(page).toHaveURL(/\/login\?error=account_suspended$/);
  await expect(page.getByRole('alert')).toContainText('이용이 정지된 계정입니다');
});

test('an unsuccessful replay does not start a second refresh loop', async ({ page }) => {
  let refreshRequests = 0;
  let meRequests = 0;
  let terminalEvents = 0;
  await page.exposeFunction('recordTerminalAuthChange', () => {
    terminalEvents += 1;
  });
  await page.addInitScript(() => {
    window.addEventListener('devon:auth-change', (event) => {
      if ((event as CustomEvent<{ redirect: boolean }>).detail.redirect) {
        void (
          window as Window & { recordTerminalAuthChange: () => Promise<void> }
        ).recordTerminalAuthChange();
      }
    });
  });
  await page.route('**/api/me', async (route) => {
    meRequests += 1;
    await route.fulfill(apiError('access_token_expired', 401));
  });
  await page.route('**/api/auth/refresh', async (route) => {
    refreshRequests += 1;
    await route.fulfill({ status: 204 });
  });

  await page.goto('/home');

  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('heading', { name: 'DEVON' })).toBeVisible();
  // URL만 바뀐 시점에는 새 로그인 화면의 자동 갱신이 아직 시작되지 않을 수 있다.
  await page.waitForLoadState('networkidle');
  expect(refreshRequests).toBe(1);
  expect(meRequests).toBe(3);
  expect(terminalEvents).toBe(1);
});

test('logout requires confirmation and sends one coordinated request', async ({ page }) => {
  await mockAuthenticated(page);
  let logoutRequests = 0;
  await page.route('**/api/auth/logout', async (route) => {
    logoutRequests += 1;
    await route.fulfill({ status: 204 });
  });
  await page.goto('/mypage');

  await page.getByRole('button', { name: '로그아웃' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: '취소' }).click();
  expect(logoutRequests).toBe(0);

  await page.getByRole('button', { name: '로그아웃' }).click();
  await page.getByRole('dialog').getByRole('button', { name: '로그아웃' }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect(logoutRequests).toBe(1);
});

test('a failed logout keeps cached identity visible and can be retried', async ({ page }) => {
  let meRequests = 0;
  await page.route('**/api/me', async (route) => {
    meRequests += 1;
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(me) });
  });
  await page.route('**/api/auth/logout', (route) =>
    route.fulfill(apiError('service_unavailable', 503, '로그아웃 서비스를 사용할 수 없습니다.')),
  );
  await page.goto('/mypage');

  await page.getByRole('button', { name: '로그아웃' }).click();
  await page.getByRole('dialog').getByRole('button', { name: '로그아웃' }).click();

  await expect(page).toHaveURL(/\/mypage$/);
  await expect(page.getByRole('dialog').getByRole('alert')).toContainText(
    '로그아웃 서비스를 사용할 수 없습니다',
  );
  await expect(page.getByRole('heading', { name: '김개발 님의 정보' })).toBeVisible();
  expect(meRequests).toBe(1);
});

test('a late pre-logout 401 cannot refresh or restore identity in another tab', async ({
  context,
}) => {
  let releaseRequest!: () => void;
  const delayedResponse = new Promise<void>((resolve) => {
    releaseRequest = resolve;
  });
  let meRequests = 0;
  let refreshRequests = 0;
  let loggedOut = false;
  await context.route('**/api/me', async (route) => {
    meRequests += 1;
    if (meRequests === 2) {
      await delayedResponse;
      return route.fulfill(apiError('access_token_expired', 401));
    }
    await route.fulfill(
      loggedOut
        ? apiError('access_token_invalid', 401)
        : { status: 200, contentType: 'application/json', body: JSON.stringify(me) },
    );
  });
  await context.route('**/api/auth/refresh', async (route) => {
    refreshRequests += 1;
    await route.fulfill({ status: 204 });
  });
  await context.route('**/api/auth/logout', async (route) => {
    loggedOut = true;
    await route.fulfill({ status: 204 });
  });
  const home = await context.newPage();
  const myPage = await context.newPage();
  await myPage.goto('/mypage');
  await home.goto('/home');

  await myPage.getByRole('button', { name: '로그아웃' }).click();
  await myPage.getByRole('dialog').getByRole('button', { name: '로그아웃' }).click();
  releaseRequest();

  await expect(myPage).toHaveURL(/\/login$/);
  await expect(home).toHaveURL(/\/login$/);
  await expect(home.getByText('김개발')).toHaveCount(0);
  expect(refreshRequests).toBe(0);
});

test('the identity and logout controls remain usable on a narrow screen', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockAuthenticated(page);

  await page.goto('/mypage');

  await expect(page.getByRole('link', { name: '내 계정' })).toBeVisible();
  await expect(page.getByRole('button', { name: '로그아웃' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test('detail API failures preserve identity and do not fabricate dashboard data', async ({
  page,
}) => {
  await mockAuthenticated(page);
  await page.goto('/home');
  await expect(page.getByRole('heading', { name: '안녕하세요, 김개발 님!' })).toBeVisible();
  await expect(page.getByText('정보를 불러오지 못했어요.')).toBeVisible();
  await expect(page.getByText('GitHub 분석', { exact: false })).toHaveCount(0);
  await expect(page.getByRole('link', { name: '내 계정' }).locator('img')).toHaveAttribute(
    'src',
    me.avatarUrl,
  );

  await page.getByRole('link', { name: '내 계정' }).click();
  await expect(page.getByRole('heading', { name: '김개발 님의 정보' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '면접 이력', exact: true })).toBeVisible();
  await expect(page.getByText('이력을 불러오지 못했어요.')).toBeVisible();
  await expect(page.getByRole('button', { name: '로그아웃' })).toBeVisible();
  await expect(page).toHaveURL(/\/mypage$/);
});

test('develop dashboard and profile remain available with their contracted responses', async ({
  page,
}, testInfo) => {
  await mockAuthenticated(page);
  await page.route('**/api/me/home', (route) => route.fulfill({ json: homeScenarios.completed }));
  await page.route('**/api/me/profile', (route) => route.fulfill({ json: meProfile }));
  await page.route('**/api/me/interviews?*', (route) =>
    route.fulfill({ json: interviewPage(1, 10) }),
  );

  await page.goto('/home');
  await expect(page.getByRole('heading', { name: 'GitHub 분석 · 레포 2개 기반' })).toBeVisible();
  await expect(page.getByText('주로 사용하는 언어')).toBeVisible();
  await expect(page.getByRole('link', { name: '내 계정' }).locator('img')).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('home-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: testInfo.outputPath('home-mobile.png'), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.getByRole('link', { name: '내 계정' }).click();
  await expect(page.getByRole('heading', { name: '내 정보', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '리포트 보기 →' }).first()).toBeVisible();
  await expect(page.getByText('정보를 불러오지 못했어요.')).toHaveCount(0);
  await expect
    .poll(() =>
      page.locator('main img').evaluate((image) => (image as HTMLImageElement).naturalWidth),
    )
    .toBeGreaterThan(0);
  await page.screenshot({ path: testInfo.outputPath('mypage-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: testInfo.outputPath('mypage-mobile.png'), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test('an expired GitHub connection does not revoke the DEVON login', async ({ page }) => {
  await mockAuthenticated(page);
  let refreshRequests = 0;
  await page.route('**/api/me/home', (route) => route.fulfill(apiError('token_invalid', 401)));
  await page.route('**/api/auth/refresh', async (route) => {
    refreshRequests += 1;
    await route.fulfill({ status: 204 });
  });

  await page.goto('/home');
  await expect(page.getByText('GitHub 연동이 만료됐어요. 다시 연동해주세요.')).toBeVisible();
  await expect(page.getByRole('link', { name: 'GitHub으로 다시 로그인' })).toHaveAttribute(
    'href',
    '/api/auth/github/login',
  );
  await expect(page).toHaveURL(/\/home$/);
  await expect(page.getByRole('heading', { name: '안녕하세요, 김개발 님!' })).toBeVisible();
  expect(refreshRequests).toBe(0);
});

test('a direct login visit still restores an expired access cookie', async ({ page }) => {
  let authenticated = false;
  let refreshRequests = 0;
  await page.route('**/api/me', (route) => route.fulfill(
    authenticated
      ? { status: 200, json: me }
      : apiError('access_token_expired', 401),
  ));
  await page.route('**/api/auth/refresh', (route) => {
    refreshRequests += 1;
    authenticated = true;
    return route.fulfill({ status: 204 });
  });

  await page.goto('/login');
  await expect(page).toHaveURL(/\/home$/);
  await expect(page.getByRole('heading', { name: '안녕하세요, 김개발 님!' })).toBeVisible();
  await page.waitForLoadState('networkidle');
  expect(refreshRequests).toBe(1);
});

test('browser back cannot restore a logged-out page or restart refresh', async ({ page }) => {
  let loggedOut = false;
  let refreshRequests = 0;
  await page.route('**/api/me', (route) => route.fulfill(
    loggedOut ? apiError('access_token_invalid', 401) : { status: 200, json: me },
  ));
  await page.route('**/api/auth/logout', (route) => {
    loggedOut = true;
    return route.fulfill({ status: 204 });
  });
  await page.route('**/api/auth/refresh', (route) => {
    refreshRequests += 1;
    return route.fulfill(apiError('refresh_token_invalid', 401));
  });
  await page.goto('/home');
  await page.getByRole('link', { name: '내 계정' }).click();
  await page.getByRole('button', { name: '로그아웃', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: '로그아웃', exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);

  await page.goBack();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('link', { name: 'GitHub로 계속하기' })).toBeVisible();
  await expect(page.getByText('김개발', { exact: true })).toHaveCount(0);
  await page.waitForLoadState('networkidle');
  expect(refreshRequests).toBe(0);
});

test('the logout dialog keeps the existing theme and native keyboard behavior', async ({ page }, testInfo) => {
  await mockAuthenticated(page);
  await page.goto('/mypage');
  const logoutButton = page.getByRole('button', { name: '로그아웃', exact: true });
  await logoutButton.click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toHaveCSS('border-radius', '10px');
  await expect(dialog.getByRole('button', { name: '취소' })).toBeFocused();
  await page.screenshot({ path: testInfo.outputPath('logout-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: testInfo.outputPath('logout-mobile.png'), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.keyboard.press('Escape');
  await expect(dialog).not.toBeVisible();
  await expect(logoutButton).toBeFocused();
});

test.afterEach(async ({ context }) => {
  await context.unrouteAll({ behavior: 'ignoreErrors' });
});
