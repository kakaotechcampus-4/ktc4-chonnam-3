import { expect, test, type Page } from '@playwright/test';

// src/mocks/db/config.ts의 seed id. 완료 run과 jd_fetch_failed로 멈춘 실패 run이다.
const DONE_RUN = '5c7b9e10-0000-4000-8000-00000000aaaa';
const FAILED_RUN = '5c7b9e10-0000-4000-8000-00000000bbbb';
const TOKEN_INVALID_RUN = '5c7b9e10-0000-4000-8000-00000000dddd';
const RUNNING_RUN = '5c7b9e10-0000-4000-8000-00000000eeee';
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
