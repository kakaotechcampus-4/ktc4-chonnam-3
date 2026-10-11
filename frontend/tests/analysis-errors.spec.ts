import { expect, test, type Page } from '@playwright/test';

// src/mocks/db/config.ts의 seed id. 완료 run과 jd_fetch_failed로 멈춘 실패 run이다.
const DONE_RUN = '5c7b9e10-0000-4000-8000-00000000aaaa';
const FAILED_RUN = '5c7b9e10-0000-4000-8000-00000000bbbb';
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
