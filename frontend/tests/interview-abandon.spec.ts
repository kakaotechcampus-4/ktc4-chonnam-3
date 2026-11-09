import { expect, test, type Page } from '@playwright/test';

// 공통 0009: 나가기·레포 재선택의 abandon과 마이페이지 중단된 면접 행.
// seed id는 src/mocks/db/config.ts를 따른다.
const IN_PROGRESS = 'a3d51c20-1005-4c00-9a00-000000000005';
const PREPARING_FAILED = 'a3d51c20-1009-4c00-9a00-000000000009';

test('면접 종료를 확인하면 abandon을 보낸 뒤 홈으로 간다', async ({ page }) => {
  await page.goto(`/interview/${IN_PROGRESS}/session`);
  await page.getByRole('button', { name: '면접 종료' }).click({ timeout: 15_000 });
  const abandon = page.waitForRequest(
    (request) =>
      request.method() === 'POST' && request.url().endsWith(`/interviews/${IN_PROGRESS}/abandon`),
  );
  await page.getByRole('button', { name: '종료하기' }).click();
  await abandon;
  await expect(page).toHaveURL(/\/home$/);
});

test('레포 재선택은 기존 면접 abandon 후 새 면접을 만들고 뒤로 가기로 레포 선택에 돌아오지 않는다', async ({
  page,
}) => {
  const calls: string[] = [];
  page.on('request', (request) => {
    if (request.method() !== 'POST') return;
    const { pathname } = new URL(request.url());
    if (pathname.endsWith('/abandon')) calls.push('abandon');
    if (pathname.endsWith('/api/interviews')) calls.push('create');
  });

  await page.goto(`/interview/${PREPARING_FAILED}/prepare`);
  await page.getByRole('button', { name: '레포 다시 선택하기' }).click({ timeout: 15_000 });
  await expect(page).toHaveURL(/\/interview\/repos\//);
  await page.getByRole('button', { name: '선택한 레포로 면접 시작' }).click({ timeout: 15_000 });

  await expect(page).toHaveURL(/\/interview\/(?!a3d51c20-1009)[^/]+\/prepare$/);
  expect(calls).toEqual(['abandon', 'create']);
  await page.goBack();
  await expect(page).not.toHaveURL(/\/interview\/repos\//);
  // 캐시된 준비 실패 화면이 아니라 중단된 면접 안내가 보여야 한다.
  await expect(page.getByRole('heading', { name: '중단된 면접이에요' })).toBeVisible();
});

test('종료하기 후 abandon 응답을 기다리는 동안 종료 중임을 보여준다', async ({ page }) => {
  await page.addInitScript(() =>
    localStorage.setItem(
      'msw.faults',
      JSON.stringify([
        { path: '/interviews/*/abandon', method: 'POST', kind: 'timeout', delayMs: 2_000 },
      ]),
    ),
  );
  await page.goto(`/interview/${IN_PROGRESS}/session`);
  await page.getByRole('button', { name: '면접 종료' }).click({ timeout: 15_000 });
  await page.getByRole('button', { name: '종료하기' }).click();
  await expect(page.getByRole('button', { name: '종료하는 중…' })).toBeDisabled();
  await expect(page.getByRole('button', { name: '계속하기' })).toBeDisabled();
  // 응답이 실패해도 홈으로 간다(공통 0009).
  await expect(page).toHaveURL(/\/home$/);
});

test('abandon은 열린 면접 WS를 닫아 진행 화면이 중단된 면접 안내로 바뀐다', async ({ page }) => {
  await page.goto(`/interview/${IN_PROGRESS}/session`);
  // 답변 시작이 활성화되면 WS가 열린 상태다.
  await expect(page.getByRole('button', { name: '답변 시작' })).toBeEnabled({ timeout: 15_000 });
  // 다른 탭의 나가기처럼 화면 밖에서 abandon만 보낸다. 서버가 WS를 닫아야 화면이 상태를 다시 조회한다.
  const status = await page.evaluate(
    async (id) => (await fetch(`/api/interviews/${id}/abandon`, { method: 'POST' })).status,
    IN_PROGRESS,
  );
  expect(status).toBe(204);
  await expect(page.getByRole('heading', { name: '중단된 면접이에요' })).toBeVisible();
});

test('abandon과 엇갈린 마지막 답변 처리는 중단된 면접을 완료로 바꾸지 않는다', async ({ page }) => {
  await page.goto('/home');
  const status = await page.evaluate(async (id) => {
    const url = '/src/mocks/db/interviews.ts';
    const { abandonInterview, finishInterview, getInterview, interviewStatus } = await import(url);
    const record = getInterview(id);
    abandonInterview(record);
    finishInterview(record);
    return interviewStatus(record);
  }, IN_PROGRESS);
  // 공통 0009 §1: 한 번 abandoned가 된 면접은 다른 상태로 바뀌지 않는다.
  expect(status).toBe('abandoned');
});

test('마이페이지 중단된 면접 행은 중단됨과 다시 도전하기를 보여준다', async ({ page }) => {
  await page.goto('/mypage');
  const row = page.getByRole('listitem').filter({ hasText: '중단됨' });
  await expect(row).toHaveCount(1, { timeout: 15_000 });
  await expect(row.getByRole('button', { name: '리포트 보기 →' })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: /완료 \d+회/ })).toBeVisible();

  await row.getByRole('button', { name: '다시 도전하기 →' }).click();
  await expect(page).toHaveURL(/\/interview\/[^/]+\/prepare$/);
});

// 공통 0011: 저장 답변 이어가기가 허용되지 않는 fixture의 기존 중단·새 면접 경로다.
// 면접은 in_progress로 남으므로 abandon을 거쳐 새 면접이나 홈으로 보낸다(이슈 #200).
const QUESTION_FAILED_CLOSED = [
  {
    path: '/ws/interviews/*',
    reason: 'question_failed',
    code: 'ERR_QUESTION_FAILED',
    recoverable: false,
  },
];

function faults(page: Page, rules: object[]) {
  return page.addInitScript(
    (value) => localStorage.setItem('msw.faults', value),
    JSON.stringify(rules),
  );
}

test('복구할 수 없는 질문 생성 실패는 같은 레포로 다시 시작해 새 면접 준비로 간다', async ({
  page,
}) => {
  await faults(page, QUESTION_FAILED_CLOSED);
  const calls: string[] = [];
  page.on('request', (request) => {
    if (request.method() !== 'POST') return;
    const { pathname } = new URL(request.url());
    if (pathname.endsWith(`/interviews/${IN_PROGRESS}/abandon`)) calls.push('abandon');
    if (pathname.endsWith(`/interviews/${IN_PROGRESS}/retry`)) calls.push('retry');
  });

  await page.goto(`/interview/${IN_PROGRESS}/session`);
  await expect(page.getByRole('alert')).toContainText('다음 질문을 준비하지 못했어요.', {
    timeout: 15_000,
  });
  await page.getByRole('button', { name: '같은 레포로 다시 시작' }).click();

  await expect(page).toHaveURL(/\/interview\/(?!a3d51c20-1005)[^/]+\/prepare$/);
  expect(calls).toEqual(['abandon', 'retry']);
});

test('복구할 수 없는 질문 생성 실패에서 나가기는 abandon 후 홈으로 간다', async ({ page }) => {
  await faults(page, QUESTION_FAILED_CLOSED);
  await page.goto(`/interview/${IN_PROGRESS}/session`);
  const abandon = page.waitForRequest(
    (request) =>
      request.method() === 'POST' && request.url().endsWith(`/interviews/${IN_PROGRESS}/abandon`),
  );
  await page.getByRole('button', { name: '나가기' }).click({ timeout: 15_000 });
  await abandon;
  await expect(page).toHaveURL(/\/home$/);
});

test('같은 레포로 다시 시작이 run_expired면 공고 입력부터 다시 시작하게 안내한다', async ({
  page,
}) => {
  await faults(page, [
    ...QUESTION_FAILED_CLOSED,
    { path: '/interviews/*/retry', method: 'POST', status: 410, reason: 'run_expired' },
  ]);
  await page.goto(`/interview/${IN_PROGRESS}/session`);
  await page.getByRole('button', { name: '같은 레포로 다시 시작' }).click({ timeout: 15_000 });

  await expect(
    page.getByText('분석 결과가 만료됐어요. 공고 입력부터 다시 시작해주세요.'),
  ).toBeVisible();
  await page.getByRole('button', { name: '공고 입력부터 다시' }).click();
  await expect(page).toHaveURL(/\/interview\/new$/);
});

test('복구할 수 없는 질문 생성 실패 뒤에는 다시 연결하지 않는다', async ({ page }) => {
  // #200의 원래 문제: recoverable true면 FE가 복구되지 않는 면접에 계속 재접속했다.
  // 재연결은 항상 GET /interviews/{id}를 먼저 부르므로(useInterviewSocket) 그 호출 수로 센다.
  await faults(page, QUESTION_FAILED_CLOSED);
  let refetches = 0;
  let counting = false;
  page.on('request', (request) => {
    if (!counting || request.method() !== 'GET') return;
    if (new URL(request.url()).pathname.endsWith(`/interviews/${IN_PROGRESS}`)) refetches += 1;
  });

  await page.goto(`/interview/${IN_PROGRESS}/session`);
  await expect(page.getByRole('button', { name: '같은 레포로 다시 시작' })).toBeVisible({
    timeout: 15_000,
  });
  counting = true;
  // 재연결 간격(2초)을 두 번 넘게 기다린다.
  await page.waitForTimeout(5_000);
  expect(refetches).toBe(0);
});
