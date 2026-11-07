import { expect, test, type Page } from '@playwright/test';

// src/mocks/db/config.ts의 seed id. 완료 run과 jd_fetch_failed로 멈춘 실패 run이다.
const DONE_RUN = '5c7b9e10-0000-4000-8000-00000000aaaa';
const FAILED_RUN = '5c7b9e10-0000-4000-8000-00000000bbbb';
const TOKEN_INVALID_RUN = '5c7b9e10-0000-4000-8000-00000000dddd';
const RUNNING_RUN = '5c7b9e10-0000-4000-8000-00000000eeee';
const NO_PUBLIC_REPO_RUN = '5c7b9e10-0000-4000-8000-000000001111';
// DB partial run. API는 failed지만 성공한 저장소의 결과는 조회된다(analysis-run.md 부분 실패).
const PARTIAL_RUN = '5c7b9e10-0000-4000-8000-00000000ffff';
const RUN_GET = new RegExp(`/analysis-runs/${RUNNING_RUN}$`);
const RUN_EVENTS = new RegExp(`/analysis-runs/${RUNNING_RUN}/events$`);
const POSTING_URL = 'https://www.wanted.co.kr/wd/999999';

function faults(page: Page, rules: object[]) {
  return page.addInitScript(
    (value) => localStorage.setItem('msw.faults', value),
    JSON.stringify(rules),
  );
}

test('분석 진행 조회가 410이면 스피너 대신 만료 안내와 공고 입력 이동을 보여준다', async ({
  page,
}) => {
  // mock은 없는 run을 410 run_expired로 응답한다. SSE도 410이라 onerror 폴백 조회를 탄다.
  await page.goto('/interview/analyzing/missing-run');
  await expect(page.getByRole('alert')).toContainText('분석 결과가 만료됐어요.');
  await page.getByRole('button', { name: '공고 다시 입력' }).click();
  await expect(page).toHaveURL(/\/interview\/new$/);
});

test('분석 진행 조회가 5xx면 다시 시도로 복구한다', async ({ page }) => {
  await faults(page, [
    {
      path: `/analysis-runs/${DONE_RUN}`,
      method: 'GET',
      status: 500,
      reason: 'internal_error',
      times: 2,
    },
    { path: `/analysis-runs/${DONE_RUN}/events`, status: 500, reason: 'internal_error' },
  ]);
  await page.goto(`/interview/analyzing/${DONE_RUN}`);
  await expect(page.getByRole('alert')).toHaveText('분석 정보를 불러오지 못했어요.');
  await page.getByRole('button', { name: '다시 시도' }).click();
  await expect(page).toHaveURL(new RegExp(`/interview/repos/${DONE_RUN}$`));
});

test('분석이 끝나 이동한 뒤 뒤로 가기는 진행 화면으로 돌아오지 않는다', async ({ page }) => {
  await page.goto('/home');
  await page.goto(`/interview/analyzing/${DONE_RUN}`);
  await expect(page).toHaveURL(new RegExp(`/interview/repos/${DONE_RUN}$`));
  await page.goBack();
  await expect(page).toHaveURL(/\/home$/);
});

test('진행 중 10초 폴링이 실패해도 이미 받은 진행 화면을 오류로 바꾸지 않는다', async ({
  page,
}) => {
  test.setTimeout(30_000);
  await page.goto(`/interview/analyzing/${RUNNING_RUN}`);
  await expect(page.getByText('GitHub 레포를 분석하고 있어요')).toBeVisible();
  // 첫 조회가 끝난 뒤부터 run 조회만 실패시킨다. SSE(/events)는 그대로 둔다.
  await page.waitForResponse((res) => RUN_GET.test(res.url()) && res.ok());
  await page.evaluate((runId) => {
    localStorage.setItem(
      'msw.faults',
      JSON.stringify([
        { path: `/analysis-runs/${runId}`, method: 'GET', status: 500, reason: 'internal_error' },
      ]),
    );
  }, RUNNING_RUN);

  // 폴링 1회 + 자동 재시도 1회가 모두 실패해야 isError가 된다.
  await page.waitForResponse((res) => RUN_GET.test(res.url()) && res.status() === 500, {
    timeout: 15_000,
  });
  await page.waitForResponse((res) => RUN_GET.test(res.url()) && res.status() === 500);
  await page.waitForTimeout(300);
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('조회와 SSE가 모두 실패한 뒤 다시 시도하면 SSE를 다시 연다', async ({ page }) => {
  // 첫 조회(재시도 포함 2회)와 SSE 연결을 실패시킨다.
  await faults(page, [
    {
      path: `/analysis-runs/${RUNNING_RUN}`,
      method: 'GET',
      status: 500,
      reason: 'internal_error',
      times: 2,
    },
    {
      path: `/analysis-runs/${RUNNING_RUN}/events`,
      status: 500,
      reason: 'internal_error',
      times: 1,
    },
  ]);
  await page.goto(`/interview/analyzing/${RUNNING_RUN}`);
  await expect(page.getByRole('alert')).toContainText('분석 정보를 불러오지 못했어요.');

  const reopened = page.waitForRequest((req) => RUN_EVENTS.test(req.url()));
  await page.getByRole('button', { name: '다시 시도' }).click();
  await reopened;
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('run 조회 410은 자동 재시도하지 않고 바로 만료 안내를 보여준다', async ({ page }) => {
  // 한 번만 410을 준다. 재시도하면 두 번째 조회가 성공해 공고 실패 안내로 바뀐다.
  await faults(page, [
    {
      path: `/analysis-runs/${FAILED_RUN}`,
      method: 'GET',
      status: 410,
      reason: 'run_expired',
      times: 1,
    },
  ]);
  await page.goto(`/interview/failed/${FAILED_RUN}`);
  await expect(page.getByRole('alert')).toContainText('분석 결과가 만료됐어요.');
  await page.waitForTimeout(1500);
  await expect(page.getByRole('alert')).toContainText('분석 결과가 만료됐어요.');
});

test('분석 실패 token_invalid는 github_token_invalid와 같은 재연동 안내를 보여준다', async ({
  page,
}) => {
  await page.goto(`/interview/failed/${TOKEN_INVALID_RUN}`);
  await expect(page.getByRole('alert')).toContainText('GitHub 연동이 만료됐어요.');
  await expect(page.getByRole('link', { name: 'GitHub 재연동' })).toHaveAttribute(
    'href',
    /\/auth\/github\/link$/,
  );
});

test('분석 실패는 failureReason별 안내와 이전 URL을 채운 공고 입력 이동을 보여준다', async ({
  page,
}) => {
  await page.goto(`/interview/failed/${FAILED_RUN}`);
  // 실패 화면 진입 경로가 넘기는 router state를 흉내 낸다.
  await page.evaluate((postingUrl) => {
    window.history.replaceState({ ...window.history.state, usr: { postingUrl } }, '');
  }, POSTING_URL);
  await page.reload();

  await expect(page.getByRole('alert')).toContainText('공고를 불러오지 못했어요.');
  await page.getByRole('button', { name: '공고 URL 수정하기' }).click();
  await expect(page).toHaveURL(/\/interview\/new$/);
  await expect(page.getByPlaceholder('https://careers.example.com/jobs/123')).toHaveValue(
    POSTING_URL,
  );
});

test('분석할 레포가 없으면 분석 대상 기준과 포함하는 방법을 안내한다', async ({ page }) => {
  // 공개 레포가 있어도 fork·조직 레포만 있으면 같은 사유가 온다. 기준을 모르면 원인을 알 수 없다.
  await page.goto(`/interview/failed/${NO_PUBLIC_REPO_RUN}`);
  // 경고는 한 줄로 두고, 기준과 방법은 따로 읽기 쉬운 목록으로 보여 준다.
  const alert = page.getByRole('alert');
  await expect(alert).toHaveText('분석할 수 있는 레포를 찾지 못했어요.');
  const tips = page.getByRole('list', { name: '분석 기준과 해결 방법' }).getByRole('listitem');
  await expect(tips).toHaveCount(3);
  // 항목마다 짧은 제목을 두어 훑어보기 쉽게 한다.
  await expect(tips.nth(0)).toContainText('분석 대상');
  await expect(tips.nth(0)).toContainText('내 계정이 소유한 공개 레포만 분석해요');
  await expect(tips.nth(1)).toContainText('빠진 레포를 넣으려면');
  await expect(tips.nth(1)).toContainText('포트폴리오에 레포 주소를 적어 첨부해주세요');
  await expect(tips.nth(2)).toContainText('레포를 새로 올렸다면');
  await expect(tips.nth(2)).toContainText('다시 로그인');
  // 재시도 불가 사유라 공고 입력 버튼은 두지 않는다(spec/frontend/features/analysis.md).
  await expect(page.getByRole('button', { name: '홈으로' })).toBeVisible();
  await expect(page.getByRole('button', { name: /다시 시도|공고/ })).toHaveCount(0);
});

test('분석 실패 화면은 실행하지 않은 단계를 완료로 표시하지 않는다', async ({ page }) => {
  // jd_fetch에서 멈춘 run이다. 이후 단계와 미첨부 문서 단계는 BE가 skipped로 준다.
  await page.goto(`/interview/failed/${FAILED_RUN}`);
  await expect(page.getByRole('alert')).toContainText('공고를 불러오지 못했어요.');

  const row = (label: string) => page.locator('li', { hasText: label });
  await expect(row('Repository 구조 확인').getByText('✓')).toBeVisible();
  await expect(row('공고 요구사항 분석').getByText('!')).toBeVisible();
  // skipped는 체크리스트에서 숨긴다(frontend/docs/api-spec.md #13·#14).
  await expect(row('기술 스택 매칭')).toHaveCount(0);
  await expect(row('첨부 문서 확인')).toHaveCount(0);
});

test('분석 진행 화면은 문서를 첨부하지 않은 단계를 숨긴다', async ({ page }) => {
  await page.goto(`/interview/analyzing/${RUNNING_RUN}`);
  await expect(page.locator('li', { hasText: 'Repository 구조 확인' })).toBeVisible();
  await expect(page.locator('li', { hasText: '첨부 문서 확인' })).toHaveCount(0);
});

test('분석 실패 화면의 조회가 410이면 만료 안내를 보여준다', async ({ page }) => {
  await page.goto('/interview/failed/missing-run');
  await expect(page.getByRole('alert')).toContainText('분석 결과가 만료됐어요.');
  await expect(page.getByRole('button', { name: '공고 다시 입력' })).toBeVisible();
});

test('레포 목록 409 not_ready면 run 상태를 확인해 실패 화면으로 보낸다', async ({ page }) => {
  await faults(page, [
    { path: `/analysis-runs/${FAILED_RUN}/result`, status: 409, reason: 'not_ready' },
  ]);
  await page.goto(`/interview/repos/${FAILED_RUN}`);
  await expect(page).toHaveURL(new RegExp(`/interview/failed/${FAILED_RUN}$`));
});

test('레포 목록 not_ready면 run 상태를 확인하는 동안 빈 화면 대신 로딩을 보여준다', async ({
  page,
}) => {
  // 결과는 계속 not_ready, run은 완료라 이동할 화면이 없다. 상태 확인을 1.5초 늦춘다.
  await faults(page, [
    { path: `/analysis-runs/${DONE_RUN}/result`, status: 409, reason: 'not_ready' },
    { path: `/analysis-runs/${DONE_RUN}`, kind: 'timeout', delayMs: 1500, times: 1 },
  ]);
  const checking = page.waitForRequest((req) =>
    new RegExp(`/analysis-runs/${DONE_RUN}$`).test(req.url()),
  );
  await page.goto(`/interview/repos/${DONE_RUN}`);
  // 결과 조회(재시도 포함)가 끝나고 상태 확인이 시작된 구간이다.
  await checking;
  await expect(page.getByText('불러오는 중...')).toBeVisible({ timeout: 1000 });
  await expect(page.getByRole('alert')).toBeVisible({ timeout: 10_000 });
});

test('레포 목록 not_ready에서 다시 시도한 뒤 또 not_ready여도 로딩에 멈추지 않는다', async ({
  page,
}) => {
  // 결과는 계속 not_ready, run은 완료라 이동할 화면이 없다(완료 직후 경합).
  await faults(page, [
    { path: `/analysis-runs/${DONE_RUN}/result`, status: 409, reason: 'not_ready' },
  ]);
  await page.goto(`/interview/repos/${DONE_RUN}`);
  await expect(page.getByRole('alert')).toBeVisible({ timeout: 10_000 });

  const rechecked = page.waitForRequest((req) =>
    new RegExp(`/analysis-runs/${DONE_RUN}$`).test(req.url()),
  );
  await page.getByRole('button', { name: '다시 시도' }).click();
  // 새 409마다 run 상태를 다시 확인해야 안내로 돌아온다.
  await rechecked;
  await expect(page.getByRole('alert')).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText('불러오는 중...')).toBeHidden();
});

test('실패하지 않은 run으로 실패 화면에 들어오면 진행·레포 선택 화면으로 보낸다', async ({
  page,
}) => {
  await page.goto(`/interview/failed/${RUNNING_RUN}`);
  await expect(page).toHaveURL(new RegExp(`/interview/analyzing/${RUNNING_RUN}$`));
  await page.goto(`/interview/failed/${DONE_RUN}`);
  await expect(page).toHaveURL(new RegExp(`/interview/repos/${DONE_RUN}$`));
});

test('선택할 수 있는 레포가 없으면 안내와 공고 입력 이동을 보여준다', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('msw.result', 'all-failed'));
  await page.goto(`/interview/repos/${DONE_RUN}`);
  await expect(page.getByRole('alert')).toContainText('면접에 사용할 수 있는 레포가 없어요.');
  await expect(page.getByRole('button', { name: '+ Private 레포 직접 추가' })).toBeDisabled();
  await page.getByRole('button', { name: '공고 다시 입력' }).click();
  await expect(page).toHaveURL(/\/interview\/new$/);
});

test('레포 목록 410이면 만료 안내를 보여준다', async ({ page }) => {
  await page.goto('/interview/repos/missing-run');
  await expect(page.getByRole('alert')).toContainText('분석 결과가 만료됐어요.');
});

test('면접 생성 410 run_expired는 만료 안내와 공고 입력 이동을 보여준다', async ({ page }) => {
  await faults(page, [{ path: '/interviews', method: 'POST', status: 410, reason: 'run_expired' }]);
  await page.goto(`/interview/repos/${DONE_RUN}`);
  await page.getByRole('button', { name: '선택한 레포로 면접 시작' }).click();
  await expect(page.getByRole('alert')).toHaveText(
    '분석 결과가 만료됐어요. 공고 입력부터 다시 시작해주세요.',
  );
  await page.getByRole('button', { name: '공고 다시 입력' }).click();
  await expect(page).toHaveURL(/\/interview\/new$/);
});

test('면접 생성 409 session_limit_exceeded는 진행 중 면접을 안내한다', async ({ page }) => {
  await faults(page, [
    { path: '/interviews', method: 'POST', status: 409, reason: 'session_limit_exceeded' },
  ]);
  await page.goto(`/interview/repos/${DONE_RUN}`);
  await page.getByRole('button', { name: '선택한 레포로 면접 시작' }).click();
  await expect(page.getByRole('alert')).toContainText('이미 진행 중인 면접이 있어요.');
});

test('부분 실패 run은 실패 화면에서 성공한 저장소 선택으로 이어진다', async ({ page }) => {
  await page.goto(`/interview/failed/${PARTIAL_RUN}`);
  // 성공한 저장소가 있으면 일시 오류·재시도 안내 대신 부분 실패 안내를 보여 준다.
  const alert = page.getByRole('alert');
  await expect(alert).toHaveText(
    '일부 레포를 분석하지 못했어요. 분석에 성공한 저장소로 면접을 진행할 수 있어요.',
  );
  await page.getByRole('button', { name: '분석에 성공한 저장소 보기' }).click();
  await expect(page).toHaveURL(new RegExp(`/interview/repos/${PARTIAL_RUN}$`));
  // README 없는 partial 카드와 실패 카드는 서버 선택 조건(L1 succeeded) 밖이라 고를 수 없다.
  await expect(page.getByRole('button', { name: /batch-pipeline/ })).toBeDisabled();
  await expect(page.getByRole('button', { name: /legacy-crawler/ })).toBeDisabled();
  await expect(page.getByRole('button', { name: /payment-service/ })).toBeEnabled();
  // 기본 선택된 succeeded 추천 레포로 면접을 만들고 준비 화면까지 간다.
  await page.getByRole('button', { name: '선택한 레포로 면접 시작' }).click();
  await expect(page).toHaveURL(/\/interview\/[^/]+\/prepare$/);
});

test('부분 실패 run은 결과 조회 전에 기본 실패 안내를 그리지 않는다', async ({ page }) => {
  // DOM에 붙었던 alert 문구를 모두 기록한다. 잠깐 보였다 바뀐 문구도 남는다.
  await page.addInitScript(() => {
    const seen: string[] = [];
    (window as unknown as { alertTexts: string[] }).alertTexts = seen;
    new MutationObserver(() => {
      document.querySelectorAll('[role="alert"]').forEach((el) => seen.push(el.textContent ?? ''));
    }).observe(document, { childList: true, subtree: true, characterData: true });
  });
  await page.goto(`/interview/failed/${PARTIAL_RUN}`);
  await expect(page.getByRole('alert')).toHaveText(
    '일부 레포를 분석하지 못했어요. 분석에 성공한 저장소로 면접을 진행할 수 있어요.',
  );
  const seen = await page.evaluate(
    () => (window as unknown as { alertTexts: string[] }).alertTexts,
  );
  expect(seen.filter((text) => text.includes('일시적인 문제'))).toEqual([]);
});

test('부분 실패 run의 결과에 성공한 저장소가 없으면 성공한 저장소 보기 버튼을 보여주지 않는다', async ({
  page,
}) => {
  // 결과 조회는 200이지만 모든 저장소가 실패다. 버튼 조건은 응답 성공이 아니라 succeeded 저장소 유무다.
  await page.addInitScript(() => localStorage.setItem('msw.result', 'all-failed'));
  const result = page.waitForResponse((response) =>
    response.url().endsWith(`/analysis-runs/${PARTIAL_RUN}/result`),
  );
  await page.goto(`/interview/failed/${PARTIAL_RUN}`);
  expect((await result).status()).toBe(200);
  await expect(page.getByRole('alert')).toHaveText(
    '분석 중 일시적인 문제가 생겼어요. 다시 시도해주세요.',
  );
  await expect(page.getByRole('button', { name: '분석에 성공한 저장소 보기' })).toHaveCount(0);
});

test('부분 실패 run의 결과 조회가 실패하면 다시 불러와 성공한 저장소 선택으로 이어진다', async ({
  page,
}) => {
  // 일시적인 5xx 한 번으로 성공한 저장소 진입로가 사라지면 안 된다. 409 not_ready와 구분한다.
  await faults(page, [
    {
      path: `/analysis-runs/${PARTIAL_RUN}/result`,
      method: 'GET',
      status: 500,
      reason: 'internal_error',
      times: 1,
    },
  ]);
  await page.goto(`/interview/failed/${PARTIAL_RUN}`);
  await expect(page.getByText('분석 결과를 불러오지 못했어요.')).toBeVisible();
  await expect(page.getByRole('button', { name: '분석에 성공한 저장소 보기' })).toHaveCount(0);
  await page.getByRole('button', { name: '결과 다시 불러오기' }).click();
  await page.getByRole('button', { name: '분석에 성공한 저장소 보기' }).click();
  await expect(page).toHaveURL(new RegExp(`/interview/repos/${PARTIAL_RUN}$`));
});

test('결과가 없는 실패 run은 성공한 저장소 보기 버튼을 보여주지 않는다', async ({ page }) => {
  const result = page.waitForResponse((response) =>
    response.url().endsWith(`/analysis-runs/${FAILED_RUN}/result`),
  );
  await page.goto(`/interview/failed/${FAILED_RUN}`);
  // 진짜 실패한 run은 결과 조회가 409 not_ready다. 응답을 받은 뒤에도 버튼이 없어야 한다.
  expect((await result).status()).toBe(409);
  await expect(page.getByRole('alert')).toContainText('공고를 불러오지 못했어요.');
  await expect(page.getByRole('button', { name: '분석에 성공한 저장소 보기' })).toHaveCount(0);
});
